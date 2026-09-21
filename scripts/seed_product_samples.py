#!/usr/bin/env python3
"""Idempotently seed 100 concrete product samples below ten catalogue lines."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from db import SCHEMA, SessionLocal, init_db
from pricing.product_samples import SAMPLE_VERSION, load_product_samples, sample_summary


def seed_product_samples(db, rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "identifiers": 0}
    parents = {
        row.name: row
        for row in db.execute(text(f"""
            SELECT id,name,item_type,cpv_code,canonical_unit,attributes
            FROM {SCHEMA}.catalog_items WHERE catalogue_kind='line'
        """)).fetchall()
    }
    missing = sorted({row["catalogue_line_name"] for row in rows} - set(parents))
    if missing:
        raise ValueError("catalogue lines must be seeded first: " + ", ".join(missing))
    for sample in rows:
        parent = parents[sample["catalogue_line_name"]]
        inherited = parent.attributes if isinstance(parent.attributes, dict) else {}
        attributes = {
            "sample_version": SAMPLE_VERSION,
            "display_name_fr": sample["name_fr"],
            "brand": sample["brand"],
            "model": sample["model"],
            "source_url": sample["source_url"],
            "source_kind": "manufacturer_catalogue",
            "monitoring_cohort": sample["monitoring_cohort"] == "1",
            "default_market": sample["default_market"],
            "sector": inherited.get("sector"),
            "sector_name": inherited.get("sector_name"),
            "monitoring_tier": "web_price",
        }
        existing = db.execute(text(f"""
            SELECT id FROM {SCHEMA}.catalog_items
            WHERE catalogue_kind='sample_item' AND lower(name)=lower(:name)
            ORDER BY id LIMIT 1
        """), {"name": sample["name"]}).fetchone()
        if existing:
            item_id = existing.id
            db.execute(text(f"""
                UPDATE {SCHEMA}.catalog_items
                SET parent_item_id=:parent,catalogue_kind='sample_item',item_type=:item_type,
                    description=:description,cpv_code=:cpv,canonical_unit=:unit,
                    attributes=CAST(:attributes AS jsonb),updated_at=NOW()
                WHERE id=:id
            """), {
                "id": item_id, "parent": parent.id, "item_type": parent.item_type,
                "description": f"{sample['brand']} {sample['model']}", "cpv": parent.cpv_code,
                "unit": parent.canonical_unit, "attributes": json.dumps(attributes),
            })
            counts["updated"] += 1
        else:
            created = db.execute(text(f"""
                INSERT INTO {SCHEMA}.catalog_items
                    (parent_item_id,catalogue_kind,item_type,name,description,cpv_code,
                     canonical_unit,attributes)
                VALUES (:parent,'sample_item',:item_type,:name,:description,:cpv,:unit,
                        CAST(:attributes AS jsonb)) RETURNING id
            """), {
                "parent": parent.id, "item_type": parent.item_type, "name": sample["name"],
                "description": f"{sample['brand']} {sample['model']}", "cpv": parent.cpv_code,
                "unit": parent.canonical_unit, "attributes": json.dumps(attributes),
            }).fetchone()
            item_id = created.id
            counts["created"] += 1
        result = db.execute(text(f"""
            INSERT INTO {SCHEMA}.item_identifiers
                (item_id,identifier_type,identifier_value,issuer,confidence)
            VALUES (:item,:kind,:value,:issuer,1)
            ON CONFLICT (identifier_type,identifier_value,item_id) DO UPDATE SET issuer=EXCLUDED.issuer
        """), {
            "item": item_id, "kind": sample["identifier_type"].lower(),
            "value": sample["identifier_value"], "issuer": sample["brand"],
        })
        counts["identifiers"] += max(0, result.rowcount or 0)
    db.commit()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write samples to the configured database")
    args = parser.parse_args()
    rows = load_product_samples()
    report = sample_summary(rows)
    if not args.apply:
        print(json.dumps({**report, "mode": "dry-run"}, indent=2))
        return 0
    init_db()
    db = SessionLocal()
    try:
        counts = seed_product_samples(db, rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(json.dumps({**report, "mode": "applied", **counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
