"""Compute matched-item daily observed median indices (base=100)."""

from __future__ import annotations

from sqlalchemy import text

from db import SCHEMA, SessionLocal

METHODOLOGY = "observed-median-v1"


def compute_indices() -> int:
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            WITH daily AS (
                SELECT o.item_id, o.market, po.captured_at::date period_date,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY po.amount_comparable) median_price,
                       COUNT(*) observation_count, COUNT(DISTINCT o.source_id) source_count
                FROM {SCHEMA}.offers o JOIN {SCHEMA}.price_observations po ON po.offer_id=o.id
                WHERE o.item_id IS NOT NULL AND po.currency_comparable='EUR'
                  AND po.amount_comparable IS NOT NULL
                GROUP BY o.item_id,o.market,po.captured_at::date
            ), based AS (
                SELECT daily.*, FIRST_VALUE(median_price) OVER (
                    PARTITION BY item_id,market ORDER BY period_date
                ) base_price, MIN(period_date) OVER (PARTITION BY item_id,market) base_date
                FROM daily
            )
            SELECT b.*, ci.name, ci.cpv_code FROM based b
            JOIN {SCHEMA}.catalog_items ci ON ci.id=b.item_id
            WHERE base_price > 0
        """)).fetchall()
        for row in rows:
            series_key = f"item:{row.item_id}"
            index_value = (float(row.median_price) / float(row.base_price)) * 100
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.price_indices
                    (series_key,market,cpv_code,item_id,period_date,index_value,base_date,
                     median_price,observation_count,source_count,methodology_version,coverage)
                VALUES (:series,:market,:cpv,:item,:period,:value,:base,:median,:observations,
                        :sources,:methodology,jsonb_build_object('item_name',:name))
                ON CONFLICT (series_key,market,period_date,methodology_version) DO UPDATE SET
                    index_value=EXCLUDED.index_value, median_price=EXCLUDED.median_price,
                    observation_count=EXCLUDED.observation_count, source_count=EXCLUDED.source_count,
                    coverage=EXCLUDED.coverage
            """), {"series": series_key, "market": row.market, "cpv": row.cpv_code,
                     "item": row.item_id, "period": row.period_date, "value": index_value,
                     "base": row.base_date, "median": row.median_price,
                     "observations": row.observation_count, "sources": row.source_count,
                     "methodology": METHODOLOGY, "name": row.name})
        db.commit()
        return len(rows)
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Computed {compute_indices()} FastCPI index points")
