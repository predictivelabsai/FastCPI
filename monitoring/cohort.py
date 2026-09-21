"""Controlled 20-item daily monitoring cohort derived from product samples."""

from __future__ import annotations

import json

from sqlalchemy import text

from db import SCHEMA
from pricing.product_samples import load_product_samples


COHORT_PREFIX = "Cohort · "


def cohort_specs() -> list[dict[str, str]]:
    return [
        {
            **row,
            "watch_name": f"{COHORT_PREFIX}{row['brand']} {row['model']} · {row['default_market']}",
            "query": f"{row['identifier_type'].upper()}: {row['identifier_value']} {row['brand']} {row['model']}",
        }
        for row in load_product_samples()
        if row["monitoring_cohort"] == "1"
    ]


def seed_monitoring_cohort(db, user_id: int, *, active: bool) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "active": 0, "paused": 0}
    for spec in cohort_specs():
        item = db.execute(text(f"""
            SELECT id,cpv_code FROM {SCHEMA}.catalog_items
            WHERE catalogue_kind='sample_item' AND lower(name)=lower(:name)
        """), {"name": spec["name"]}).fetchone()
        if not item:
            raise ValueError(f"product sample must be seeded first: {spec['name']}")
        row = db.execute(text(f"""
            INSERT INTO {SCHEMA}.watchlists
                (user_id,item_id,name,query,query_type,query_value,markets,cpv_code,
                 change_threshold_pct,notify_email,is_active,next_run_at)
            SELECT :uid,:item,:name,:query,:kind,:value,CAST(:markets AS jsonb),:cpv,
                   5,FALSE,:active,NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM {SCHEMA}.watchlists WHERE user_id=:uid AND name=:name
            )
            RETURNING id
        """), {
            "uid": user_id, "item": item.id, "name": spec["watch_name"],
            "query": spec["query"], "kind": spec["identifier_type"],
            "value": spec["identifier_value"], "markets": json.dumps([spec["default_market"]]),
            "cpv": item.cpv_code, "active": active,
        }).fetchone()
        if row:
            counts["created"] += 1
        else:
            db.execute(text(f"""
                UPDATE {SCHEMA}.watchlists
                SET item_id=:item,query=:query,query_type=:kind,query_value=:value,
                    markets=CAST(:markets AS jsonb),cpv_code=:cpv,is_active=:active,updated_at=NOW()
                WHERE user_id=:uid AND name=:name
            """), {
                "uid": user_id, "item": item.id, "name": spec["watch_name"],
                "query": spec["query"], "kind": spec["identifier_type"],
                "value": spec["identifier_value"], "markets": json.dumps([spec["default_market"]]),
                "cpv": item.cpv_code, "active": active,
            })
            counts["updated"] += 1
        counts["active" if active else "paused"] += 1
    db.commit()
    return counts
