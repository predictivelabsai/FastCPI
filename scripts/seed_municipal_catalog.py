#!/usr/bin/env python3
"""Idempotently seed the researched local-government catalogue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from db import SCHEMA, SessionLocal, init_db
from pricing.catalog import (
    CATALOG_VERSION, catalogue_summary, load_municipal_catalog,
    validate_against_official_cpv,
)


SOURCE_URLS = [
    "https://ted.europa.eu/en/simap/cpv",
    "https://api.ted.europa.eu/v3/notices/search",
    "https://single-market-economy.ec.europa.eu/single-market/public-procurement/digital-procurement/public-procurement-data-space-ppds_en",
]


def seed_catalog(db, rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "identifiers": 0}
    for row in rows:
        attributes = {
            "catalogue_version": CATALOG_VERSION,
            "sector": row["sector"],
            "sector_name": row["sector_name"],
            "monitoring_tier": row["monitoring_tier"],
            "cpv_label_en": row["cpv_label"],
            "cpv_label_fr": row["cpv_label_fr"],
            "display_name_fr": row["name_fr"],
            "procurement_basis": "Recent EU local-authority notices and official CPV 2008",
            "source_urls": SOURCE_URLS,
        }
        existing = db.execute(text(f"""
            SELECT id FROM {SCHEMA}.catalog_items WHERE lower(name)=lower(:name) ORDER BY id LIMIT 1
        """), {"name": row["name"]}).fetchone()
        if existing:
            item_id = existing.id
            db.execute(text(f"""
                UPDATE {SCHEMA}.catalog_items
                SET parent_item_id=NULL, catalogue_kind='line',
                    item_type=:item_type, cpv_code=:cpv, canonical_unit=:unit,
                    description=:description, attributes=COALESCE(attributes,'{{}}'::jsonb) || CAST(:attributes AS jsonb),
                    updated_at=NOW()
                WHERE id=:id
            """), {
                "id": item_id, "item_type": row["item_type"], "cpv": row["cpv_code"],
                "unit": row["canonical_unit"], "description": row["cpv_label"],
                "attributes": json.dumps(attributes),
            })
            counts["updated"] += 1
        else:
            created = db.execute(text(f"""
                INSERT INTO {SCHEMA}.catalog_items
                    (catalogue_kind,item_type,name,description,cpv_code,canonical_unit,attributes)
                VALUES ('line',:item_type,:name,:description,:cpv,:unit,CAST(:attributes AS jsonb))
                RETURNING id
            """), {
                "item_type": row["item_type"], "name": row["name"],
                "description": row["cpv_label"], "cpv": row["cpv_code"],
                "unit": row["canonical_unit"], "attributes": json.dumps(attributes),
            }).fetchone()
            item_id = created.id
            counts["created"] += 1
        if row.get("identifier_type"):
            result = db.execute(text(f"""
                INSERT INTO {SCHEMA}.item_identifiers
                    (item_id,identifier_type,identifier_value,issuer)
                VALUES (:item,:kind,:value,:issuer)
                ON CONFLICT (identifier_type,identifier_value,item_id) DO NOTHING
            """), {
                "item": item_id, "kind": row["identifier_type"],
                "value": row["identifier_value"], "issuer": row.get("issuer") or None,
            })
            counts["identifiers"] += max(0, result.rowcount or 0)
    db.commit()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the validated catalogue to the configured database")
    parser.add_argument("--official-cpv-ods", type=Path,
                        help="optionally verify every code and English label against the official CPV 2008 ODS")
    args = parser.parse_args()
    rows = load_municipal_catalog()
    if args.official_cpv_ods:
        validate_against_official_cpv(rows, args.official_cpv_ods)
    report = catalogue_summary(rows)
    if not args.apply:
        print(json.dumps({**report, "mode": "dry-run"}, indent=2))
        return 0
    init_db()
    db = SessionLocal()
    try:
        counts = seed_catalog(db, rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(json.dumps({**report, "mode": "applied", **counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
