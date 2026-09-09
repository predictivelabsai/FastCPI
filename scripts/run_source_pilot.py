#!/usr/bin/env python3
"""Run the FastCPI three-category, ten-market Exa source pilot."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pricing.discovery import discover
from pricing.extractors import fetch_and_extract
from pricing.identifiers import classify_query
from pricing.markets import MARKETS


CATEGORIES = {
    "office_paper": "A4 80gsm office copy paper 500 sheets business pack",
    "toner_sku": "SKU W2210A HP 207A black toner cartridge business supplier",
    "it_support_cpv": "CPV 72611000 hourly technical computer support service B2B rate",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--extract-top", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("output/pilot/source-pilot.json"))
    parser.add_argument("--reuse-discovery", action="store_true")
    args = parser.parse_args()

    rows: list[dict] = []
    domain_urls: dict[str, list[str]] = defaultdict(list)
    if args.reuse_discovery and args.output.exists():
        rows = json.loads(args.output.read_text(encoding="utf-8")).get("discoveries", [])
        print(f"reuse discoveries: {len(rows)}", flush=True)
    else:
        for category, query in CATEGORIES.items():
            identity = classify_query(query)
            for market in MARKETS:
                results = discover(identity, market, limit=args.limit, days=None)
                print(f"discover {category} {market}: {len(results)}", flush=True)
                rows.extend({**result, "category": category, "query": query, "market": market} for result in results)
    for result in rows:
        domain = urlparse(result.get("url", "")).netloc.lower()
        if domain and result.get("url") not in domain_urls[domain]:
            domain_urls[domain].append(result["url"])

    frequency = Counter(urlparse(row.get("url", "")).netloc.lower() for row in rows)
    extraction: list[dict] = []
    for domain, count in frequency.most_common(max(0, args.extract_top)):
        if not domain:
            continue
        outcome = {"domain": domain, "discovery_count": count, "url": domain_urls[domain][0]}
        try:
            offer = fetch_and_extract(outcome["url"])
            outcome.update({
                "status": "extracted" if offer else "no_structured_price",
                "method": offer.extraction_method if offer else None,
                "currency": offer.currency if offer else None,
                "confidence": offer.confidence if offer else None,
            })
        except Exception as exc:
            outcome.update({"status": "failed", "reason": type(exc).__name__})
        extraction.append(outcome)
        print(f"extract {domain}: {outcome['status']}", flush=True)

    categories = {
        category: {
            "discoveries": sum(row["category"] == category for row in rows),
            "unique_domains": len({urlparse(row["url"]).netloc.lower() for row in rows if row["category"] == category}),
        }
        for category in CATEGORIES
    }
    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "markets": list(MARKETS),
        "categories": categories,
        "discovery_count": len(rows),
        "unique_domain_count": len(frequency),
        "top_domains": [{"domain": domain, "count": count} for domain, count in frequency.most_common()],
        "extraction_sample": extraction,
        "discoveries": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"complete discoveries={len(rows)} domains={len(frequency)} extracted={sum(r['status'] == 'extracted' for r in extraction)}")
    print(f"artifact={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
