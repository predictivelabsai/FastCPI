"""Validated concrete product samples beneath municipal catalogue lines."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


SAMPLE_VERSION = "eu-municipal-product-samples-v1-2026-09-21"
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "product_samples.tsv"
SUPPORTED_IDENTIFIERS = {"sku", "mpn", "gtin", "ean", "upc", "vendor"}


def load_product_samples(path: Path = SAMPLE_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream, delimiter="\t")]
    validate_product_samples(rows)
    return rows


def validate_product_samples(rows: list[dict[str, str]]) -> None:
    if len(rows) != 100:
        raise ValueError(f"product sample catalogue must contain exactly 100 items, found {len(rows)}")
    counts = Counter(row.get("catalogue_line_name", "").strip() for row in rows)
    if len(counts) != 10 or set(counts.values()) != {10}:
        raise ValueError("product samples must contain ten items for each of ten catalogue lines")
    if sum(row.get("monitoring_cohort") == "1" for row in rows) != 20:
        raise ValueError("exactly 20 product samples must be selected for the monitoring cohort")
    names = [row.get("name", "").strip().casefold() for row in rows]
    identities = [
        (row.get("identifier_type", "").strip().lower(), row.get("identifier_value", "").strip().casefold())
        for row in rows
    ]
    if len(set(names)) != len(names):
        raise ValueError("product sample names must be unique")
    if len(set(identities)) != len(identities):
        raise ValueError("product sample identifiers must be unique")
    for position, row in enumerate(rows, start=2):
        required = (
            "catalogue_line_name", "name", "name_fr", "brand", "model",
            "identifier_type", "identifier_value", "source_url", "default_market",
        )
        missing = [key for key in required if not row.get(key, "").strip()]
        if missing:
            raise ValueError(f"row {position}: missing {', '.join(missing)}")
        if row["identifier_type"].lower() not in SUPPORTED_IDENTIFIERS:
            raise ValueError(f"row {position}: unsupported identifier type")
        parsed = urlparse(row["source_url"])
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"row {position}: source_url must be public HTTPS")
        if len(row["default_market"]) != 2 or not row["default_market"].isupper():
            raise ValueError(f"row {position}: default_market must be a two-letter code")


def sample_summary(rows: list[dict[str, str]]) -> dict:
    return {
        "version": SAMPLE_VERSION,
        "items": len(rows),
        "catalogue_lines": len({row["catalogue_line_name"] for row in rows}),
        "items_per_line": dict(sorted(Counter(row["catalogue_line_name"] for row in rows).items())),
        "monitoring_cohort": sum(row["monitoring_cohort"] == "1" for row in rows),
        "brands": len({row["brand"] for row in rows}),
    }
