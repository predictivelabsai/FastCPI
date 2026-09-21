#!/usr/bin/env python3
"""Rank recurring price domains and parser gaps from persisted evidence."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from db import SCHEMA, SessionLocal


def build_report(db, days: int = 30, limit: int = 50) -> dict:
    rows = db.execute(text(f"""
        WITH observed AS (
          SELECT ps.domain,ps.parser_key,COUNT(DISTINCT o.id) AS offer_count,
                 COUNT(po.id) AS observation_count,MAX(po.captured_at) AS last_observed_at,
                 COUNT(DISTINCT o.market) AS market_count,
                 COUNT(DISTINCT o.item_id) FILTER (WHERE o.item_id IS NOT NULL) AS item_count
          FROM {SCHEMA}.price_sources ps
          LEFT JOIN {SCHEMA}.offers o ON o.source_id=ps.id
          LEFT JOIN {SCHEMA}.price_observations po ON po.offer_id=o.id
            AND po.captured_at>=NOW()-(:days * INTERVAL '1 day')
          GROUP BY ps.id
        ), attempts AS (
          SELECT source_domain AS domain,COUNT(*) AS fetch_attempts,
                 COUNT(*) FILTER (WHERE status='error') AS fetch_errors,
                 COUNT(*) FILTER (WHERE status='succeeded'
                    AND COALESCE((metadata->>'extracted')::boolean,FALSE)=FALSE) AS no_price_pages
          FROM {SCHEMA}.usage_ledger
          WHERE operation='page_fetch' AND created_at>=NOW()-(:days * INTERVAL '1 day')
          GROUP BY source_domain
        )
        SELECT o.*,COALESCE(a.fetch_attempts,0) AS fetch_attempts,
               COALESCE(a.fetch_errors,0) AS fetch_errors,
               COALESCE(a.no_price_pages,0) AS no_price_pages,
               CASE
                 WHEN COALESCE(a.fetch_errors,0)+COALESCE(a.no_price_pages,0)>0 THEN 'adapter-review'
                 WHEN o.observation_count>=3 THEN 'maintain-fixture'
                 ELSE 'insufficient-evidence'
               END AS recommendation
        FROM observed o LEFT JOIN attempts a USING (domain)
        WHERE o.observation_count>0 OR COALESCE(a.fetch_attempts,0)>0
        ORDER BY o.observation_count DESC,
                 (COALESCE(a.fetch_errors,0)+COALESCE(a.no_price_pages,0)) DESC,o.domain
        LIMIT :limit
    """), {"days": max(1, min(days, 365)), "limit": max(1, min(limit, 500))}).fetchall()
    return {
        "period_days": days,
        "domains": [dict(row._mapping) for row in rows],
        "methodology": (
            "Ranked by persisted observations, then recent failed or no-price page fetches. "
            "An adapter recommendation is evidence for parser work, not proof of market coverage."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        report = build_report(db, args.days, args.limit)
    finally:
        db.close()
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
