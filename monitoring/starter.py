"""Idempotent starter monitoring for new and existing FastCPI users."""

from __future__ import annotations

import json

from sqlalchemy import text

from db import SCHEMA, SessionLocal
from pricing.identifiers import classify_query


STARTER_WATCHLISTS = (
    {
        "name": "A4 copy paper · France",
        "query": "A4 80 gsm office copy paper",
        "markets": ["FR"],
    },
    {
        "name": "HP W2210A toner · Germany",
        "query": "SKU: W2210A HP toner",
        "markets": ["DE"],
    },
    {
        "name": "Hourly IT support · Estonia",
        "query": "CPV 72611000 hourly technical computer support",
        "markets": ["EE"],
    },
)


def seed_starter_watchlists(db, user_id: int) -> int:
    """Attach the three starter watches once; later user deletion stays respected."""
    user = db.execute(text(f"""
        SELECT starter_watchlists_seeded_at
        FROM {SCHEMA}.chat_users WHERE id=:uid FOR UPDATE
    """), {"uid": user_id}).fetchone()
    if not user or user.starter_watchlists_seeded_at is not None:
        return 0

    inserted = 0
    for starter in STARTER_WATCHLISTS:
        identity = classify_query(starter["query"])
        row = db.execute(text(f"""
            INSERT INTO {SCHEMA}.watchlists
                (user_id,name,query,query_type,query_value,markets,cpv_code,
                 change_threshold_pct,notify_email,next_run_at)
            SELECT :uid,:name,:query,:kind,:value,CAST(:markets AS jsonb),:cpv,
                   5,FALSE,NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM {SCHEMA}.watchlists WHERE user_id=:uid AND name=:name
            )
            RETURNING id
        """), {
            "uid": user_id,
            "name": starter["name"],
            "query": starter["query"],
            "kind": identity.kind,
            "value": identity.value,
            "markets": json.dumps(starter["markets"]),
            "cpv": identity.value if identity.kind == "cpv" else None,
        }).fetchone()
        inserted += int(row is not None)
    db.execute(text(f"""
        UPDATE {SCHEMA}.chat_users SET starter_watchlists_seeded_at=NOW() WHERE id=:uid
    """), {"uid": user_id})
    db.commit()
    return inserted


def ensure_starter_watchlists(user_id: int) -> int:
    db = SessionLocal()
    try:
        return seed_starter_watchlists(db, user_id)
    finally:
        db.close()


def seed_all_existing_users() -> int:
    db = SessionLocal()
    try:
        user_ids = [row.id for row in db.execute(text(f"SELECT id FROM {SCHEMA}.chat_users")).fetchall()]
    finally:
        db.close()
    return sum(ensure_starter_watchlists(user_id) for user_id in user_ids)
