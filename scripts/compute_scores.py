"""CLI to compute investment scores for all active listings.

Usage:
    python -m scripts.compute_scores --all
    python -m scripts.compute_scores --make BMW
    python -m scripts.compute_scores --make Porsche
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Compute investment scores for car listings")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Score all active listings")
    group.add_argument("--make", type=str, help="Score listings for a specific make")
    parser.add_argument("--date", type=str, help="Snapshot date (YYYY-MM-DD), default today")
    args = parser.parse_args()

    snapshot_date = date.fromisoformat(args.date) if args.date else date.today()

    from scoring.engine import compute_all_scores, compute_scores_for_make

    if args.all:
        log.info("Computing scores for ALL active listings (snapshot=%s)", snapshot_date)
        result = compute_all_scores(snapshot_date)
    else:
        log.info("Computing scores for make=%s (snapshot=%s)", args.make, snapshot_date)
        result = compute_scores_for_make(args.make, snapshot_date)

    log.info("Done: %d listings scored", result["scored"])
    log.info("Tier distribution: %s", result["tiers"])


if __name__ == "__main__":
    main()
