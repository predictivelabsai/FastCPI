#!/usr/bin/env python3
"""Seed attributable pilot observations into the configured FastCPI database."""

from __future__ import annotations

import argparse

from sqlalchemy import text

from db import SCHEMA, SessionLocal
from pricing.markets import MARKETS
from pricing.repository import persist_search_result
from pricing.service import search_web_prices


ITEMS = (
    {"key": "office_paper", "type": "good", "name": "A4 80 gsm office copy paper, 500 sheets",
     "query": "A4 80gsm office copy paper 500 sheets business pack", "unit": "pack"},
    {"key": "toner_sku", "type": "good", "name": "HP 207A black toner cartridge W2210A",
     "query": "SKU W2210A HP 207A black toner cartridge business supplier", "unit": "each",
     "identifier": ("sku", "W2210A", "HP")},
    {"key": "it_support_cpv", "type": "service", "name": "Hourly technical computer support",
     "query": "CPV 72611000 hourly technical computer support service B2B rate", "unit": "hour",
     "cpv": "72611000"},
)


def ensure_item(db, item: dict) -> int:
    row = db.execute(
        text(f"SELECT id FROM {SCHEMA}.catalog_items WHERE name=:name ORDER BY id LIMIT 1"),
        {"name": item["name"]},
    ).fetchone()
    if row:
        return row.id
    row = db.execute(text(f"""
        INSERT INTO {SCHEMA}.catalog_items (item_type,name,cpv_code,canonical_unit)
        VALUES (:type,:name,:cpv,:unit) RETURNING id
    """), {"type": item["type"], "name": item["name"], "cpv": item.get("cpv"), "unit": item["unit"]}).fetchone()
    if item.get("identifier"):
        kind, value, issuer = item["identifier"]
        db.execute(text(f"""
            INSERT INTO {SCHEMA}.item_identifiers (item_id,identifier_type,identifier_value,issuer)
            VALUES (:item,:kind,:value,:issuer)
        """), {"item": row.id, "kind": kind, "value": value, "issuer": issuer})
    db.commit()
    return row.id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--markets", default=",".join(MARKETS))
    args = parser.parse_args()
    markets = [value.strip().upper() for value in args.markets.split(",") if value.strip()]
    unknown = sorted(set(markets) - set(MARKETS))
    if unknown:
        raise ValueError("unsupported markets: " + ", ".join(unknown))

    db = SessionLocal()
    totals = {"runs": 0, "offers": 0, "failures": 0}
    try:
        for item in ITEMS:
            item_id = ensure_item(db, item)
            for market in markets:
                try:
                    result = search_web_prices(item["query"], market, limit=args.limit, fetch_pages=True)
                    result["item_id"] = item_id
                    persist_search_result(db, result)
                    totals["runs"] += 1
                    totals["offers"] += len(result["offers"])
                    print(f"{item['key']} {market}: {len(result['offers'])}/{len(result['discoveries'])} observed", flush=True)
                except Exception as exc:
                    db.rollback()
                    totals["failures"] += 1
                    print(f"{item['key']} {market}: failed ({type(exc).__name__})", flush=True)
    finally:
        db.close()
    print("complete " + " ".join(f"{key}={value}" for key, value in totals.items()))
    return 1 if totals["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
