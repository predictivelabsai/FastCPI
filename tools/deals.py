"""Price arbitrage tool -- finds the same make/model at different prices across sources."""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

COUNTRY_LABELS = {
    "GB": "UK", "DE": "Germany", "EU": "Other EU",
    "EE": "Estonia", "LT": "Lithuania", "LV": "Latvia", "SE": "Sweden",
}
PROVIDER_LABELS = {
    "autotrader": "AutoTrader UK",
    "mobile_de": "mobile.de",
    "autoscout24": "AutoScout24",
    "autohero": "Autohero",
    "theparking": "TheParking",
    "auto24_ee": "Auto24.ee",
    "auto24_lt": "Auto24.lt",
    "auto24_lv": "Auto24.lv",
    "blocket": "Blocket.se",
}


class DealFinderArgs(BaseModel):
    make: Optional[str] = Field(default=None, description="Car make (e.g. BMW, Porsche). Leave empty for all brands.")
    model: Optional[str] = Field(default=None, description="Car model (e.g. X5, 911). Leave empty for all models.")
    limit: Optional[int] = Field(default=10, description="Max number of deals to show")


def _find_deals(**kw) -> str:
    args = DealFinderArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["status = 'active'", "price_eur > 0"]
    params = {"lim": args.limit or 10}
    if args.make:
        conditions.append("make ILIKE :make")
        params["make"] = f"%{args.make}%"
    if args.model:
        conditions.append("model ILIKE :model")
        params["model"] = f"%{args.model}%"

    where = " AND ".join(conditions)

    db = SessionLocal()
    try:
        spread_sql = text(f"""
            WITH by_source AS (
                SELECT make, model, country, provider,
                       COUNT(*) AS cnt,
                       ROUND(AVG(price_eur)::numeric, 0) AS avg_price
                FROM carhero.car_listings
                WHERE {where}
                GROUP BY make, model, country, provider
            ),
            spreads AS (
                SELECT make, model,
                       SUM(cnt) AS listing_count,
                       ROUND(AVG(avg_price)::numeric, 0) AS avg_price,
                       (MAX(avg_price) - MIN(avg_price)) AS spread_eur,
                       ROUND(((MAX(avg_price) - MIN(avg_price))
                              / NULLIF(AVG(avg_price), 0) * 100)::numeric, 1) AS spread_pct
                FROM by_source
                GROUP BY make, model
                HAVING COUNT(DISTINCT country || '/' || provider) >= 2
            )
            SELECT * FROM spreads
            WHERE spread_eur > 0
            ORDER BY spread_pct DESC
            LIMIT :lim
        """)
        spread_rows = [dict(r._mapping) for r in db.execute(spread_sql, params)]

        deals = []
        for row in spread_rows:
            listings_sql = text(f"""
                SELECT id, make, model, variant, year, mileage_km,
                       price_eur, country, provider, fuel_type,
                       transmission, source_url
                FROM carhero.car_listings
                WHERE make = :make AND model = :model
                  AND status = 'active' AND price_eur > 0
                ORDER BY price_eur ASC
            """)
            listings = [dict(r._mapping) for r in db.execute(
                listings_sql, {"make": row["make"], "model": row["model"]}
            )]
            if len(listings) < 2:
                continue

            cheapest = listings[0]
            priciest = listings[-1]
            savings_eur = float(priciest["price_eur"]) - float(cheapest["price_eur"])
            savings_pct = float(row["spread_pct"])

            deal_row = db.execute(text("""
                INSERT INTO carhero.deals
                    (make, model, cheapest_listing_id, priciest_listing_id,
                     cheapest_price_eur, priciest_price_eur, savings_eur, savings_pct,
                     cheapest_country, cheapest_provider, priciest_country, priciest_provider,
                     listing_count, status, updated_at)
                VALUES
                    (:make, :model, :cl, :pl,
                     :cp_eur, :pp_eur, :sav, :spct,
                     :cc, :cprov, :pc, :pprov,
                     :cnt, 'active', NOW())
                ON CONFLICT (make, model) DO UPDATE SET
                    cheapest_listing_id  = EXCLUDED.cheapest_listing_id,
                    priciest_listing_id  = EXCLUDED.priciest_listing_id,
                    cheapest_price_eur   = EXCLUDED.cheapest_price_eur,
                    priciest_price_eur   = EXCLUDED.priciest_price_eur,
                    savings_eur          = EXCLUDED.savings_eur,
                    savings_pct          = EXCLUDED.savings_pct,
                    cheapest_country     = EXCLUDED.cheapest_country,
                    cheapest_provider    = EXCLUDED.cheapest_provider,
                    priciest_country     = EXCLUDED.priciest_country,
                    priciest_provider    = EXCLUDED.priciest_provider,
                    listing_count        = EXCLUDED.listing_count,
                    status               = 'active',
                    updated_at           = NOW()
                RETURNING id
            """), {
                "make": row["make"], "model": row["model"],
                "cl": cheapest["id"], "pl": priciest["id"],
                "cp_eur": float(cheapest["price_eur"]),
                "pp_eur": float(priciest["price_eur"]),
                "sav": savings_eur, "spct": savings_pct,
                "cc": cheapest["country"], "cprov": cheapest["provider"],
                "pc": priciest["country"], "pprov": priciest["provider"],
                "cnt": int(row["listing_count"]),
            })
            deal = deal_row.first()
            deal_id = str(deal.id) if deal else None

            deals.append({
                "deal_id": deal_id,
                "make": row["make"],
                "model": row["model"],
                "listing_count": int(row["listing_count"]),
                "savings_eur": round(savings_eur),
                "savings_pct": savings_pct,
                "cheapest": {
                    "price_eur": round(float(cheapest["price_eur"])),
                    "country": cheapest["country"],
                    "country_label": COUNTRY_LABELS.get(cheapest["country"], cheapest["country"] or ""),
                    "provider": cheapest["provider"],
                    "provider_label": PROVIDER_LABELS.get(cheapest["provider"], cheapest["provider"] or ""),
                    "variant": cheapest.get("variant") or "",
                    "year": cheapest.get("year"),
                    "mileage_km": int(cheapest["mileage_km"]) if cheapest.get("mileage_km") else None,
                    "fuel_type": cheapest.get("fuel_type") or "",
                    "transmission": cheapest.get("transmission") or "",
                    "url": cheapest.get("source_url") or "",
                },
                "priciest": {
                    "price_eur": round(float(priciest["price_eur"])),
                    "country": priciest["country"],
                    "country_label": COUNTRY_LABELS.get(priciest["country"], priciest["country"] or ""),
                    "provider": priciest["provider"],
                    "provider_label": PROVIDER_LABELS.get(priciest["provider"], priciest["provider"] or ""),
                    "variant": priciest.get("variant") or "",
                    "year": priciest.get("year"),
                    "mileage_km": int(priciest["mileage_km"]) if priciest.get("mileage_km") else None,
                    "fuel_type": priciest.get("fuel_type") or "",
                    "transmission": priciest.get("transmission") or "",
                    "url": priciest.get("source_url") or "",
                },
            })

        db.commit()
    finally:
        db.close()

    if not deals:
        return "No price arbitrage deals found for the given criteria."

    lines = [f"Found {len(deals)} price arbitrage deal(s):\n"]
    for d in deals:
        ch = d["cheapest"]
        pr = d["priciest"]
        lines.append(f"**{d['make']} {d['model']}** -- save EUR {d['savings_eur']:,} ({d['savings_pct']:.0f}%)")
        lines.append(f"  Cheapest: EUR {ch['price_eur']:,} at {ch['provider_label']} ({ch['country_label']})")
        lines.append(f"  Priciest: EUR {pr['price_eur']:,} at {pr['provider_label']} ({pr['country_label']})")
        lines.append("")

    artifact = {
        "kind": "deals",
        "title": "Price Arbitrage Deals",
        "subtitle": f"{len(deals)} deal(s) found",
        "deals": deals,
    }

    return f"__ARTIFACT__{json.dumps(artifact)}" + "\n\n" + "\n".join(lines)


price_arbitrage = StructuredTool.from_function(
    func=_find_deals,
    name="price_arbitrage",
    description=(
        "Find price arbitrage deals -- same car make/model listed at different prices "
        "across different countries or providers. Shows the cheapest and most expensive "
        "listings side by side with savings amount and links to original listings. "
        "Use when the user asks about deals, bargains, price differences, or arbitrage."
    ),
    args_schema=DealFinderArgs,
)
