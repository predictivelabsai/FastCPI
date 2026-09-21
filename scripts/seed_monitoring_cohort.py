#!/usr/bin/env python3
"""Seed the controlled 20-item cohort for the configured admin account."""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import text

from db import SCHEMA, SessionLocal, init_db
from monitoring.cohort import cohort_specs, seed_monitoring_cohort


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--activate", action="store_true",
        help="enable daily execution; omit while a paid discovery provider is unavailable",
    )
    args = parser.parse_args()
    specs = cohort_specs()
    report = {"items": len(specs), "item_market_scans_per_day": len(specs), "requested_active": args.activate}
    if not args.apply:
        print(json.dumps({**report, "mode": "dry-run"}, indent=2))
        return 0
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not email:
        raise RuntimeError("ADMIN_EMAIL is required")
    init_db()
    db = SessionLocal()
    try:
        user_id = db.execute(text(f"SELECT id FROM {SCHEMA}.chat_users WHERE email=:email"), {"email": email}).scalar()
        if not user_id:
            raise RuntimeError("Configured admin account was not found")
        counts = seed_monitoring_cohort(db, int(user_id), active=args.activate)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(json.dumps({**report, "mode": "applied", **counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
