"""Market visualization tools -- Plotly charts returned as artifacts."""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class TreemapArgs(BaseModel):
    country: Optional[str] = Field(default=None, description="Filter by country code (GB, DE, EU)")
    fuel_type: Optional[str] = Field(default=None, description="Filter by fuel type")


def _treemap(**kw) -> str:
    args = TreemapArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["status = 'active'", "price_eur > 0"]
    params = {}
    if args.country:
        conditions.append("country = :country")
        params["country"] = args.country
    if args.fuel_type:
        conditions.append("fuel_type ILIKE :fuel_type")
        params["fuel_type"] = f"%{args.fuel_type}%"

    where = " AND ".join(conditions)

    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT make, model,
                   COUNT(*) AS listings,
                   ROUND(AVG(price_eur)::numeric, 0) AS avg_price
            FROM carhero.car_listings
            WHERE {where}
            GROUP BY make, model
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC
            LIMIT 30
        """), params).fetchall()
    finally:
        db.close()

    if not rows:
        return "No data available for treemap."

    data = [dict(r._mapping) for r in rows]
    lines = ["Market treemap (top 30 make/model combos by listing count):\n"]
    lines.append("Make | Model | Listings | Avg Price EUR")
    lines.append("--- | --- | --- | ---")
    for d in data:
        lines.append(f"{d['make']} | {d['model']} | {d['listings']} | {d['avg_price']:,.0f}")

    lines.append(f"\nView interactive treemap at /app/market-map")

    figure = {
        "data": [{
            "type": "treemap",
            "labels": [d["model"] for d in data],
            "parents": [d["make"] for d in data],
            "values": [int(d["listings"]) for d in data],
            "text": [f"EUR {d['avg_price']:,.0f}" for d in data],
            "textinfo": "label+text",
        }],
        "layout": {"title": "Car Listings by Make/Model", "margin": {"t": 40, "b": 10, "l": 10, "r": 10}},
    }

    return f"__ARTIFACT__{json.dumps({'kind': 'chart', 'title': 'Market Treemap', 'figure': figure})}" + "\n\n" + "\n".join(lines)


class PriceTrendArgs(BaseModel):
    make: Optional[str] = Field(default=None, description="Car make to analyze")
    model: Optional[str] = Field(default=None, description="Car model to analyze")


def _price_trend(**kw) -> str:
    args = PriceTrendArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["status = 'active'", "price_eur > 0", "year IS NOT NULL", "year >= 2005"]
    params = {}
    if args.make:
        conditions.append("make ILIKE :make")
        params["make"] = f"%{args.make}%"
    if args.model:
        conditions.append("model ILIKE :model")
        params["model"] = f"%{args.model}%"

    where = " AND ".join(conditions)

    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT year,
                   COUNT(*) AS listings,
                   ROUND(AVG(price_eur)::numeric, 0) AS avg_price,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur)::numeric, 0) AS median_price,
                   MIN(price_eur)::integer AS min_price,
                   MAX(price_eur)::integer AS max_price
            FROM carhero.car_listings
            WHERE {where}
            GROUP BY year
            ORDER BY year
        """), params).fetchall()
    finally:
        db.close()

    if not rows:
        return "No price trend data available."

    data = [dict(r._mapping) for r in rows]
    label = " ".join(filter(None, [args.make, args.model])) or "All premium cars"

    lines = [f"Price trend for {label}:\n"]
    lines.append("Year | Listings | Avg Price | Median | Min | Max")
    lines.append("--- | --- | --- | --- | --- | ---")
    for d in data:
        lines.append(
            f"{d['year']} | {d['listings']} | EUR {d['avg_price']:,.0f} | "
            f"EUR {d['median_price']:,.0f} | EUR {d['min_price']:,.0f} | EUR {d['max_price']:,.0f}"
        )

    figure = {
        "data": [
            {"type": "scatter", "mode": "lines+markers", "name": "Avg Price",
             "x": [d["year"] for d in data], "y": [float(d["avg_price"]) for d in data]},
            {"type": "scatter", "mode": "lines", "name": "Median Price",
             "x": [d["year"] for d in data], "y": [float(d["median_price"]) for d in data],
             "line": {"dash": "dash"}},
        ],
        "layout": {"title": f"Price by Year: {label}", "xaxis": {"title": "Year"}, "yaxis": {"title": "Price (EUR)"},
                   "margin": {"t": 40, "b": 40, "l": 60, "r": 20}},
    }

    return f"__ARTIFACT__{json.dumps({'kind': 'chart', 'title': f'Price Trend: {label}', 'figure': figure})}" + "\n\n" + "\n".join(lines)


class GeoCompareArgs(BaseModel):
    make: str = Field(description="Car make to compare across countries")
    model: Optional[str] = Field(default=None, description="Car model to compare")


def _geographic_compare(**kw) -> str:
    args = GeoCompareArgs(**kw)

    from db import SessionLocal
    from sqlalchemy import text

    conditions = ["status = 'active'", "price_eur > 0", "make ILIKE :make"]
    params = {"make": f"%{args.make}%"}
    if args.model:
        conditions.append("model ILIKE :model")
        params["model"] = f"%{args.model}%"

    where = " AND ".join(conditions)

    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT country, provider,
                   COUNT(*) AS listings,
                   ROUND(AVG(price_eur)::numeric, 0) AS avg_price,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur)::numeric, 0) AS median_price,
                   ROUND(AVG(mileage_km)::numeric, 0) AS avg_mileage
            FROM carhero.car_listings
            WHERE {where}
            GROUP BY country, provider
            ORDER BY avg_price
        """), params).fetchall()
    finally:
        db.close()

    if not rows:
        return "No geographic comparison data available."

    data = [dict(r._mapping) for r in rows]
    label = " ".join(filter(None, [args.make, args.model]))

    lines = [f"Geographic price comparison for {label}:\n"]
    lines.append("Country | Provider | Listings | Avg Price | Median | Avg Mileage")
    lines.append("--- | --- | --- | --- | --- | ---")
    for d in data:
        lines.append(
            f"{d['country']} | {d['provider']} | {d['listings']} | "
            f"EUR {d['avg_price']:,.0f} | EUR {d['median_price']:,.0f} | {d['avg_mileage']:,.0f} km"
        )

    countries = [f"{d['country']}/{d['provider']}" for d in data]
    figure = {
        "data": [{
            "type": "bar",
            "x": countries,
            "y": [float(d["avg_price"]) for d in data],
            "text": [f"EUR {d['avg_price']:,.0f}" for d in data],
            "textposition": "outside",
        }],
        "layout": {"title": f"Average Price by Country: {label}", "yaxis": {"title": "Price (EUR)"},
                   "margin": {"t": 40, "b": 60, "l": 60, "r": 20}},
    }

    return f"__ARTIFACT__{json.dumps({'kind': 'chart', 'title': f'Geographic Compare: {label}', 'figure': figure})}" + "\n\n" + "\n".join(lines)


market_treemap = StructuredTool.from_function(
    func=_treemap,
    name="market_treemap",
    description="Generate a market treemap showing listing counts and average prices by make/model. Optionally filter by country or fuel type.",
    args_schema=TreemapArgs,
)

price_trend = StructuredTool.from_function(
    func=_price_trend,
    name="price_trend",
    description="Show price depreciation/trends by model year. Displays avg, median, min, max prices per year for a given make/model.",
    args_schema=PriceTrendArgs,
)

geographic_compare = StructuredTool.from_function(
    func=_geographic_compare,
    name="geographic_compare",
    description="Compare prices for the same car across different countries and providers (UK vs Germany vs EU). Shows price arbitrage opportunities.",
    args_schema=GeoCompareArgs,
)
