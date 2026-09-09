"""Car listing search and stats tools for agents."""

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


def _first_image(image_urls):
    if isinstance(image_urls, str):
        try:
            image_urls = json.loads(image_urls)
        except (json.JSONDecodeError, TypeError):
            return ""
    if isinstance(image_urls, list) and image_urls:
        return image_urls[0]
    return ""


class SearchListingsArgs(BaseModel):
    make: Optional[str] = Field(default=None, description="Car make, e.g. BMW, Audi, Porsche")
    model: Optional[str] = Field(default=None, description="Car model, e.g. X5, A4, 911")
    min_price: Optional[int] = Field(default=None, description="Minimum price in EUR")
    max_price: Optional[int] = Field(default=None, description="Maximum price in EUR")
    min_year: Optional[int] = Field(default=None, description="Minimum year")
    max_year: Optional[int] = Field(default=None, description="Maximum year")
    max_mileage: Optional[int] = Field(default=None, description="Maximum mileage in km")
    fuel_type: Optional[str] = Field(default=None, description="Fuel type: Petrol, Diesel, Electric, Hybrid, Plugin Hybrid")
    transmission: Optional[str] = Field(default=None, description="Transmission: Automatic, Manual")
    body_type: Optional[str] = Field(default=None, description="Body type: Sedan, Estate, SUV, Coupe, Convertible, Hatchback")
    country: Optional[str] = Field(default=None, description="Country code: GB, DE, EU")
    provider: Optional[str] = Field(default=None, description="Source: autotrader, mobile_de, autoscout24, autohero")
    limit: int = Field(default=20, ge=1, le=50)


def _search_listings(**kw) -> str:
    args = SearchListingsArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["status = 'active'"]
    params = {}

    if args.make:
        conditions.append("make ILIKE :make")
        params["make"] = f"%{args.make}%"
    if args.model:
        conditions.append("model ILIKE :model")
        params["model"] = f"%{args.model}%"
    if args.min_price:
        conditions.append("price_eur >= :min_price")
        params["min_price"] = args.min_price
    if args.max_price:
        conditions.append("price_eur <= :max_price")
        params["max_price"] = args.max_price
    if args.min_year:
        conditions.append("year >= :min_year")
        params["min_year"] = args.min_year
    if args.max_year:
        conditions.append("year <= :max_year")
        params["max_year"] = args.max_year
    if args.max_mileage:
        conditions.append("mileage_km <= :max_mileage")
        params["max_mileage"] = args.max_mileage
    if args.fuel_type:
        conditions.append("fuel_type ILIKE :fuel_type")
        params["fuel_type"] = f"%{args.fuel_type}%"
    if args.transmission:
        conditions.append("transmission ILIKE :transmission")
        params["transmission"] = f"%{args.transmission}%"
    if args.body_type:
        conditions.append("body_type ILIKE :body_type")
        params["body_type"] = f"%{args.body_type}%"
    if args.country:
        conditions.append("country = :country")
        params["country"] = args.country
    if args.provider:
        conditions.append("provider = :provider")
        params["provider"] = args.provider

    where = " AND ".join(conditions)
    params["lim"] = args.limit

    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT id, make, model, variant, year, mileage_km, price_eur, currency,
                   fuel_type, transmission, body_type, power_hp, country, city,
                   provider, source_url, steering_side, condition, image_urls
            FROM carhero.car_listings
            WHERE {where}
            ORDER BY price_eur ASC NULLS LAST
            LIMIT :lim
        """), params).fetchall()
    finally:
        db.close()

    if not rows:
        return "No listings found matching your criteria."

    listings = []
    lines = []
    for r in rows:
        m = dict(r._mapping)
        price = f"EUR {m['price_eur']:,.0f}" if m.get("price_eur") else "Price N/A"
        mileage = f"{m['mileage_km']:,} km" if m.get("mileage_km") else "N/A"
        lines.append(
            f"- **{m['make']} {m['model']}** {m.get('variant') or ''} ({m.get('year', 'N/A')}) "
            f"| {price} | {mileage} | {m.get('fuel_type', '')} {m.get('transmission', '')} "
            f"| {m.get('power_hp', '')}hp | {m.get('country', '')} ({m.get('provider', '')}) "
            f"| {m.get('steering_side', '')} | {m.get('source_url', '')}"
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
            "country_label": COUNTRY_LABELS.get(m.get("country", ""), m.get("country", "")),
            "provider": m.get("provider") or "",
            "provider_label": PROVIDER_LABELS.get(m.get("provider", ""), m.get("provider", "")),
            "steering_side": m.get("steering_side") or "",
            "condition": m.get("condition") or "",
            "url": m.get("source_url") or "",
            "image_url": _first_image(m.get("image_urls")),
        })

    label = " ".join(filter(None, [args.make, args.model]))
    artifact = {
        "kind": "listings",
        "title": f"{label or 'Car'} Listings",
        "subtitle": f"{len(listings)} result(s)",
        "listings": listings,
    }
    text = f"Found {len(rows)} listings:\n\n" + "\n".join(lines)
    return f"__ARTIFACT__{json.dumps(artifact)}\n\n{text}"


class CarStatsArgs(BaseModel):
    make: Optional[str] = Field(default=None, description="Filter by make")
    model: Optional[str] = Field(default=None, description="Filter by model")
    country: Optional[str] = Field(default=None, description="Filter by country code")


def _car_stats(**kw) -> str:
    args = CarStatsArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["status = 'active'", "price_eur > 0"]
    params = {}

    if args.make:
        conditions.append("make ILIKE :make")
        params["make"] = f"%{args.make}%"
    if args.model:
        conditions.append("model ILIKE :model")
        params["model"] = f"%{args.model}%"
    if args.country:
        conditions.append("country = :country")
        params["country"] = args.country

    where = " AND ".join(conditions)

    db = SessionLocal()
    try:
        row = db.execute(text(f"""
            SELECT
                COUNT(*) AS total,
                ROUND(AVG(price_eur)::numeric, 0) AS avg_price,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur)::numeric, 0) AS median_price,
                MIN(price_eur) AS min_price,
                MAX(price_eur) AS max_price,
                ROUND(AVG(mileage_km)::numeric, 0) AS avg_mileage,
                ROUND(AVG(EXTRACT(YEAR FROM CURRENT_DATE) - year)::numeric, 1) AS avg_age
            FROM carhero.car_listings
            WHERE {where}
        """), params).fetchone()
    finally:
        db.close()

    if not row or row._mapping["total"] == 0:
        return "No data available for these filters."

    m = dict(row._mapping)
    label = " ".join(filter(None, [args.make, args.model, f"({args.country})" if args.country else None])) or "all listings"
    return (
        f"Market stats for {label}:\n"
        f"- Total active listings: {m['total']:,}\n"
        f"- Average price: EUR {m['avg_price']:,.0f}\n"
        f"- Median price: EUR {m['median_price']:,.0f}\n"
        f"- Price range: EUR {m['min_price']:,.0f} - EUR {m['max_price']:,.0f}\n"
        f"- Average mileage: {m['avg_mileage']:,.0f} km\n"
        f"- Average age: {m['avg_age']} years"
    )


search_car_listings = StructuredTool.from_function(
    func=_search_listings,
    name="search_car_listings",
    description=(
        "Search European premium car listings by make, model, price range, year, mileage, "
        "fuel type, transmission, body type, country, and provider. "
        "Covers BMW, Mercedes-Benz, Audi, Porsche, Jaguar, Land Rover, Volvo, Tesla, Lexus "
        "from AutoTrader UK, mobile.de, AutoScout24, and Autohero."
    ),
    args_schema=SearchListingsArgs,
)

car_stats = StructuredTool.from_function(
    func=_car_stats,
    name="car_stats",
    description=(
        "Get aggregate market statistics (count, avg/median/min/max price, avg mileage, avg age) "
        "for car listings, optionally filtered by make, model, and country."
    ),
    args_schema=CarStatsArgs,
)
