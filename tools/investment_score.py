"""Investment Score tool for agents — find top-scored listings."""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


def _first_image(image_urls):
    if isinstance(image_urls, str):
        try:
            image_urls = json.loads(image_urls)
        except (json.JSONDecodeError, TypeError):
            return ""
    if isinstance(image_urls, list) and image_urls:
        return image_urls[0]
    return ""


COUNTRY_LABELS = {
    "GB": "UK", "DE": "Germany", "EU": "Other EU",
    "EE": "Estonia", "LT": "Lithuania", "LV": "Latvia", "SE": "Sweden",
}
PROVIDER_LABELS = {
    "autotrader": "AutoTrader UK",
    "mobile_de": "mobile.de",
    "autoscout24": "AutoScout24",
    "autohero": "Autohero",
    "auto24_ee": "Auto24.ee",
    "auto24_lt": "Auto24.lt",
    "auto24_lv": "Auto24.lv",
    "blocket": "Blocket.se",
}

TIER_LABELS = {1: "Tier 1 (Top Pick)", 2: "Tier 2 (Good Value)", 3: "Tier 3 (Average)"}


class InvestmentScoreArgs(BaseModel):
    make: Optional[str] = Field(default=None, description="Car make, e.g. BMW, Porsche")
    model: Optional[str] = Field(default=None, description="Car model, e.g. X5, 911")
    min_score: Optional[int] = Field(default=None, description="Minimum investment score (0-100)")
    tier: Optional[int] = Field(default=None, description="Filter by tier: 1 (top picks), 2 (good), 3 (average)")
    country: Optional[str] = Field(default=None, description="Country code: GB, DE, EU, EE, LT, LV, SE")
    fuel_type: Optional[str] = Field(default=None, description="Fuel type: Petrol, Diesel, Electric, Hybrid")
    max_price: Optional[int] = Field(default=None, description="Maximum price in EUR")
    limit: int = Field(default=20, ge=1, le=50)


def _get_investment_scores(**kw) -> str:
    args = InvestmentScoreArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["cl.status = 'active'", "cl.price_eur > 0"]
    score_conditions = [
        "s.snapshot_date = (SELECT MAX(snapshot_date) FROM carhero.investment_scores)"
    ]
    params = {"lim": args.limit}

    if args.make:
        conditions.append("cl.make ILIKE :make")
        params["make"] = f"%{args.make}%"
    if args.model:
        conditions.append("cl.model ILIKE :model")
        params["model"] = f"%{args.model}%"
    if args.min_score:
        score_conditions.append("s.score >= :min_score")
        params["min_score"] = args.min_score
    if args.tier:
        score_conditions.append("s.tier = :tier")
        params["tier"] = args.tier
    if args.country:
        conditions.append("cl.country = :country")
        params["country"] = args.country
    if args.fuel_type:
        conditions.append("cl.fuel_type ILIKE :fuel_type")
        params["fuel_type"] = f"%{args.fuel_type}%"
    if args.max_price:
        conditions.append("cl.price_eur <= :max_price")
        params["max_price"] = args.max_price

    where = " AND ".join(conditions + score_conditions)

    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT cl.id, cl.make, cl.model, cl.variant, cl.year, cl.mileage_km,
                   cl.price_eur, cl.fuel_type, cl.transmission, cl.body_type,
                   cl.power_hp, cl.country, cl.provider, cl.source_url, cl.image_urls,
                   s.score, s.tier, s.percentile, s.strength_summary,
                   s.price_score, s.mileage_score, s.depreciation_score,
                   s.scarcity_score, s.config_score
            FROM carhero.car_listings cl
            JOIN carhero.investment_scores s ON s.listing_id = cl.id
            WHERE {where}
            ORDER BY s.score DESC, cl.price_eur ASC
            LIMIT :lim
        """), params).fetchall()
    finally:
        db.close()

    if not rows:
        return "No scored listings found matching your criteria. Try running the scoring engine first or broadening your filters."

    listings = []
    lines = [f"Found {len(rows)} scored listings:\n"]
    for r in rows:
        m = dict(r._mapping)
        price = f"EUR {m['price_eur']:,.0f}" if m.get("price_eur") else "N/A"
        mileage = f"{m['mileage_km']:,} km" if m.get("mileage_km") else "N/A"
        pct_label = f"Top {m['percentile']:.0f}%" if m.get("percentile") else ""
        tier_label = TIER_LABELS.get(m["tier"], "")

        lines.append(
            f"- **{m['make']} {m['model']}** {m.get('variant') or ''} ({m.get('year', 'N/A')}) "
            f"| Score: **{m['score']}/100** ({tier_label}) {pct_label} "
            f"| {price} | {mileage} "
            f"| {m.get('fuel_type', '')} {m.get('transmission', '')} "
            f"| {m.get('country', '')} ({m.get('provider', '')}) "
            f"| _{m.get('strength_summary', '')}_"
        )
        listings.append({
            "id": m["id"],
            "make": m["make"],
            "model": m["model"],
            "variant": m.get("variant") or "",
            "year": m.get("year"),
            "price_eur": round(float(m["price_eur"])) if m.get("price_eur") else None,
            "mileage_km": int(m["mileage_km"]) if m.get("mileage_km") else None,
            "fuel_type": m.get("fuel_type") or "",
            "transmission": m.get("transmission") or "",
            "body_type": m.get("body_type") or "",
            "power_hp": m.get("power_hp"),
            "country": m.get("country") or "",
            "country_label": COUNTRY_LABELS.get(m.get("country", ""), ""),
            "provider": m.get("provider") or "",
            "provider_label": PROVIDER_LABELS.get(m.get("provider", ""), ""),
            "url": m.get("source_url") or "",
            "image_url": _first_image(m.get("image_urls")),
            "investment_score": m["score"],
            "tier": m["tier"],
            "tier_label": TIER_LABELS.get(m["tier"], ""),
            "percentile": m.get("percentile"),
            "strength_summary": m.get("strength_summary") or "",
        })

    label = " ".join(filter(None, [args.make, args.model]))
    artifact = {
        "kind": "listings",
        "title": f"{label or 'Top'} Investment Picks",
        "subtitle": f"{len(listings)} result(s) sorted by score",
        "listings": listings,
    }
    text_output = "\n".join(lines)
    return f"__ARTIFACT__{json.dumps(artifact)}\n\n{text_output}"


investment_scores = StructuredTool.from_function(
    func=_get_investment_scores,
    name="investment_scores",
    description=(
        "Get car listings ranked by Investment Score (0-100). Higher scores mean better "
        "value: underpriced, low mileage, good value retention, rare, desirable spec. "
        "Filter by make, model, minimum score, tier (1=top picks, 2=good, 3=average), "
        "country, fuel type, and max price. Use when the user asks about best deals, "
        "top picks, investment opportunities, or best value cars."
    ),
    args_schema=InvestmentScoreArgs,
)
