"""Populate reference tables and generate market snapshots.

Usage:
    python -m scripts.load_car_data --models      # populate car_models from listings
    python -m scripts.load_car_data --snapshots    # generate today's market_snapshots
    python -m scripts.load_car_data --expire 30    # mark listings not seen in 30 days as expired
    python -m scripts.load_car_data --all          # all of the above
"""

from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load_data")


def _engine():
    from sqlalchemy import create_engine
    return create_engine(os.environ["DB_URL"])


def populate_car_models():
    """Extract distinct make/model/generation combos from car_listings into car_models."""
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO carhero.car_models (make, model, generation, body_type)
            SELECT DISTINCT
                cl.make,
                cl.model,
                cl.generation,
                MODE() WITHIN GROUP (ORDER BY cl.body_type) AS body_type
            FROM carhero.car_listings cl
            WHERE cl.make IS NOT NULL AND cl.model IS NOT NULL
            GROUP BY cl.make, cl.model, cl.generation
            ON CONFLICT (make, model, generation) DO UPDATE
                SET body_type = COALESCE(EXCLUDED.body_type, carhero.car_models.body_type)
        """))
        conn.commit()
        log.info("car_models: upserted %d rows", result.rowcount)
        return result.rowcount


def generate_market_snapshots():
    """Compute per-make/model/country aggregates for today and insert into market_snapshots."""
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("""
            DELETE FROM carhero.market_snapshots
            WHERE snapshot_date = CURRENT_DATE
        """))

        result = conn.execute(text("""
            INSERT INTO carhero.market_snapshots
                (make, model, country, avg_price_eur, median_price_eur,
                 listing_count, avg_mileage_km, avg_age_years, snapshot_date)
            SELECT
                make,
                model,
                country,
                ROUND(AVG(price_eur)::numeric, 2),
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur)::numeric, 2),
                COUNT(*),
                ROUND(AVG(mileage_km))::integer,
                ROUND(AVG(EXTRACT(YEAR FROM CURRENT_DATE) - year)::numeric, 1),
                CURRENT_DATE
            FROM carhero.car_listings
            WHERE status = 'active'
              AND price_eur IS NOT NULL
              AND price_eur > 0
            GROUP BY make, model, country
            HAVING COUNT(*) >= 2
        """))
        conn.commit()
        log.info("market_snapshots: inserted %d rows for today", result.rowcount)
        return result.rowcount


def cleanup_expired(days: int = 30):
    """Mark listings whose scraped_at is older than `days` as expired."""
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            UPDATE carhero.car_listings
            SET status = 'expired', updated_at = NOW()
            WHERE status = 'active'
              AND scraped_at < NOW() - INTERVAL ':days days'
        """.replace(":days", str(int(days)))))
        conn.commit()
        log.info("Expired %d listings older than %d days", result.rowcount, days)
        return result.rowcount


def main():
    ap = argparse.ArgumentParser(description="Populate reference tables and snapshots")
    ap.add_argument("--models", action="store_true", help="Populate car_models from listings")
    ap.add_argument("--snapshots", action="store_true", help="Generate today's market snapshots")
    ap.add_argument("--expire", type=int, metavar="DAYS", help="Expire listings older than N days")
    ap.add_argument("--all", action="store_true", help="Run models + snapshots + expire(30)")
    args = ap.parse_args()

    if not any([args.models, args.snapshots, args.expire, args.all]):
        ap.error("Specify --models, --snapshots, --expire DAYS, or --all")

    if args.all or args.models:
        populate_car_models()

    if args.all or args.snapshots:
        generate_market_snapshots()

    if args.all:
        cleanup_expired(30)
    elif args.expire:
        cleanup_expired(args.expire)

    log.info("Done.")


if __name__ == "__main__":
    main()
