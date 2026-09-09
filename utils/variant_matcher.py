"""Variant matching engine -- maps listing data to canonical variant labels.

Matches against config/variant_catalog.yaml. Conservative: false negatives
(missed match) are far better than false positives (wrong grouping).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "variant_catalog.yaml"


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict]:
    with open(_CATALOG_PATH) as f:
        data = yaml.safe_load(f)
    entries = data.get("variants", [])
    for e in entries:
        e["_model_re"] = re.compile(e["model_pattern"], re.IGNORECASE)
        kws = sorted(e.get("match_keywords", []), key=len, reverse=True)
        e["_kw_patterns"] = [re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE) for k in kws]
        e["_excl_patterns"] = [re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE)
                               for k in e.get("exclude_keywords", [])]
        e["_specificity"] = sum(len(k) for k in kws)
    return sorted(entries, key=lambda e: e["_specificity"], reverse=True)


def match_variant(
    make: str,
    model: str,
    variant: str | None,
    year: int | None,
) -> str | None:
    if not make or not model:
        return None
    if not variant:
        return None

    catalog = _load_catalog()
    combined = f"{model} {variant}"
    make_lower = make.lower().strip()

    best = None
    best_specificity = -1

    for entry in catalog:
        if entry["make"].lower() != make_lower:
            continue

        if not entry["_model_re"].search(model):
            continue

        if entry.get("year_range") and year:
            lo, hi = entry["year_range"]
            if year < lo or year > hi:
                continue

        if any(ep.search(combined) for ep in entry["_excl_patterns"]):
            continue

        if not any(kp.search(combined) for kp in entry["_kw_patterns"]):
            continue

        if entry["_specificity"] > best_specificity:
            best = entry
            best_specificity = entry["_specificity"]

    return best["canonical_label"] if best else None


def match_batch(listings: list[dict]) -> dict[int, str]:
    """Batch-match listings. Returns {listing_id: canonical_label}."""
    results = {}
    for l in listings:
        label = match_variant(
            make=l.get("make", ""),
            model=l.get("model", ""),
            variant=l.get("variant"),
            year=l.get("year"),
        )
        if label and l.get("id"):
            results[l["id"]] = label
    return results
