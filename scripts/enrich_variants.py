"""Enrich car_listings with canonical_variant labels.

Usage:
    python -m scripts.enrich_variants              # enrich un-enriched active listings
    python -m scripts.enrich_variants --force      # re-enrich all active listings
    python -m scripts.enrich_variants --make Porsche
    python -m scripts.enrich_variants --dry-run    # count matches without updating DB
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich")


def enrich_listings(force: bool = False, make: str | None = None, dry_run: bool = False) -> dict:
    import os
    from sqlalchemy import create_engine, text
    from utils.variant_matcher import match_variant

    engine = create_engine(os.environ["DB_URL"])

    where = "WHERE status = 'active' AND variant IS NOT NULL"
    if not force:
        where += " AND canonical_variant IS NULL"
    if make:
        where += f" AND make = '{make}'"

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, make, model, variant, year
            FROM carhero.car_listings {where}
        """)).fetchall()

        log.info("Checking %d listings...", len(rows))

        matched = 0
        updates = []

        for row in rows:
            label = match_variant(
                make=row[1] or "",
                model=row[2] or "",
                variant=row[3],
                year=row[4],
            )
            if label:
                updates.append((row[0], label))
                matched += 1

        if not dry_run and updates:
            for i in range(0, len(updates), 1000):
                batch = updates[i:i + 1000]
                for lid, label in batch:
                    conn.execute(
                        text("UPDATE carhero.car_listings SET canonical_variant = :label WHERE id = :id"),
                        {"label": label, "id": lid},
                    )
                conn.commit()
                log.info("Updated batch %d-%d", i, min(i + 1000, len(updates)))

        from collections import Counter
        label_counts = Counter(label for _, label in updates)
        log.info("Matched %d / %d listings (%d variants)", matched, len(rows), len(label_counts))
        for label, count in label_counts.most_common(20):
            log.info("  %s: %d", label, count)

        return {"matched": matched, "total": len(rows), "variants": len(label_counts)}


def main():
    ap = argparse.ArgumentParser(description="Enrich listings with canonical variant labels")
    ap.add_argument("--force", action="store_true", help="Re-enrich all active listings")
    ap.add_argument("--make", type=str, default=None, help="Only enrich specific make")
    ap.add_argument("--dry-run", action="store_true", help="Count matches without updating DB")
    args = ap.parse_args()

    enrich_listings(force=args.force, make=args.make, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
