"""Item-level price variance analytics shared by the dashboard and API."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from statistics import median, pstdev
from typing import Any

from sqlalchemy import text

from db import SCHEMA


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def list_observed_items(db) -> list[dict]:
    """Return catalogue items with their current observation coverage."""
    rows = db.execute(text(f"""
        SELECT ci.id, ci.name, ci.item_type, ci.canonical_unit, ci.cpv_code,
               COUNT(DISTINCT o.id) FILTER (
                   WHERE po.amount_comparable IS NOT NULL
                     AND po.currency_comparable = 'EUR'
                     AND o.status = 'active'
               ) AS offer_count,
               COUNT(DISTINCT o.market) FILTER (
                   WHERE po.amount_comparable IS NOT NULL
                     AND po.currency_comparable = 'EUR'
                     AND o.status = 'active'
               ) AS market_count,
               COUNT(DISTINCT ps.domain) FILTER (
                   WHERE po.amount_comparable IS NOT NULL
                     AND po.currency_comparable = 'EUR'
                     AND o.status = 'active'
               ) AS source_count,
               MAX(po.captured_at) AS latest_observation
        FROM {SCHEMA}.catalog_items ci
        LEFT JOIN {SCHEMA}.offers o ON o.item_id = ci.id
        LEFT JOIN {SCHEMA}.price_sources ps ON ps.id = o.source_id
        LEFT JOIN {SCHEMA}.price_observations po ON po.offer_id = o.id
        GROUP BY ci.id
        ORDER BY (COUNT(DISTINCT o.id) FILTER (
                    WHERE po.amount_comparable IS NOT NULL
                      AND po.currency_comparable = 'EUR'
                      AND o.status = 'active'
                 ) > 0) DESC,
                 ci.name
    """)).fetchall()
    return [dict(row._mapping) for row in rows]


def get_catalog_item(db, item_id: int) -> dict | None:
    row = db.execute(text(f"""
        SELECT id, name, description, item_type, canonical_unit, cpv_code
        FROM {SCHEMA}.catalog_items WHERE id = :item_id
    """), {"item_id": item_id}).fetchone()
    return dict(row._mapping) if row else None


def latest_item_offers(db, item_id: int) -> list[dict]:
    """Return one latest comparable observation per active public offer."""
    rows = db.execute(text(f"""
        WITH ranked AS (
            SELECT po.id AS observation_id, po.offer_id, o.item_id, o.market,
                   o.title, o.seller_name, o.source_url, ps.domain AS source_domain,
                   ps.name AS source_name, po.amount_original, po.currency_original,
                   po.amount_comparable, po.currency_comparable,
                   po.unit_original, po.unit_comparable, po.vat_included,
                   po.shipping_included, po.confidence, po.warnings,
                   po.captured_at, po.extraction_method,
                   COUNT(*) OVER (PARTITION BY po.offer_id) AS observation_count,
                   ROW_NUMBER() OVER (
                       PARTITION BY po.offer_id ORDER BY po.captured_at DESC, po.id DESC
                   ) AS recency_rank
            FROM {SCHEMA}.price_observations po
            JOIN {SCHEMA}.offers o ON o.id = po.offer_id
            JOIN {SCHEMA}.price_sources ps ON ps.id = o.source_id
            WHERE o.item_id = :item_id
              AND o.status = 'active'
              AND po.amount_comparable IS NOT NULL
              AND po.currency_comparable = 'EUR'
        )
        SELECT * FROM ranked WHERE recency_rank = 1
        ORDER BY market, amount_comparable, source_domain, title
    """), {"item_id": item_id}).fetchall()
    offers = []
    for row in rows:
        offer = dict(row._mapping)
        offer["amount_original"] = float(offer["amount_original"])
        offer["amount_comparable"] = float(offer["amount_comparable"])
        offer["confidence"] = float(offer["confidence"] or 0)
        offer["warnings"] = _json_list(offer.get("warnings"))
        offer["supplier"] = (
            (offer.get("seller_name") or "").strip()
            or (offer.get("source_name") or "").strip()
            or offer["source_domain"]
        )
        offers.append(offer)
    return offers


def summarize_offers(offers: list[dict]) -> dict:
    """Describe the dispersion of a latest-offer snapshot."""
    prices = [float(offer["amount_comparable"]) for offer in offers]
    sources = {offer["source_domain"] for offer in offers}
    suppliers = {offer["supplier"] for offer in offers}
    if not prices:
        return {
            "offer_count": 0, "source_count": 0, "supplier_count": 0,
            "lowest": None, "median": None, "highest": None,
            "range": None, "spread_pct": None, "stddev": None,
            "unit": None, "latest_observation": None,
        }
    midpoint = median(prices)
    low, high = min(prices), max(prices)
    spread = ((high - low) / midpoint * 100) if midpoint else None
    units = [offer.get("unit_comparable") or offer.get("unit_original") or "unit" for offer in offers]
    latest_values = [offer.get("captured_at") for offer in offers if offer.get("captured_at")]
    return {
        "offer_count": len(offers),
        "source_count": len(sources),
        "supplier_count": len(suppliers),
        "lowest": round(low, 4),
        "median": round(midpoint, 4),
        "highest": round(high, 4),
        "range": round(high - low, 4),
        "spread_pct": round(spread, 4) if spread is not None else None,
        "stddev": round(pstdev(prices), 4) if len(prices) > 1 else 0,
        "unit": Counter(units).most_common(1)[0][0],
        "latest_observation": max(latest_values) if latest_values else None,
    }


def summarize_markets(offers: list[dict]) -> list[dict]:
    markets: dict[str, list[dict]] = {}
    for offer in offers:
        markets.setdefault(offer["market"], []).append(offer)
    return [
        {"market": market, **summarize_offers(values)}
        for market, values in sorted(markets.items())
    ]


def choose_default_market(offers: list[dict]) -> str:
    """Choose the best-covered country, preferring France when coverage ties."""
    summaries = summarize_markets(offers)
    if not summaries:
        return "FR"
    summaries.sort(key=lambda row: (
        row["source_count"], row["offer_count"], row["market"] == "FR"
    ), reverse=True)
    return summaries[0]["market"]


def json_ready(value: Any) -> Any:
    """Recursively convert dashboard values to JSON-safe primitives."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value
