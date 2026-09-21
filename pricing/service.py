"""Orchestrate discovery, page extraction, normalization and provenance."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from pricing.discovery import discover
from pricing.extractors import fetch_and_extract
from pricing.fx import to_eur
from pricing.identifiers import classify_query
from pricing.markets import normalize_market
from pricing.normalization import normalize_price
from pricing.throttling import acquire_domain_fetch
from pricing.usage import (
    UsageQuotaExceeded, current_usage_context, enforce_usage_quota, record_usage,
)

log = logging.getLogger(__name__)


def source_market_assessment(url: str, market_code: str) -> tuple[str, str | None]:
    """Classify geographic evidence without pretending generic domains prove locality.

    A conflicting country-code TLD is strong negative evidence. Generic and ``.eu``
    domains remain usable, but are explicitly marked as unverified rather than local.
    """
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    suffix = hostname.rsplit(".", 1)[-1] if "." in hostname else ""
    if len(suffix) == 2 and suffix != "eu":
        if suffix.upper() == market_code:
            return "country-domain-match", None
        return (
            "country-domain-conflict",
            f"Source country domain .{suffix} conflicts with requested market {market_code}",
        )
    return "unverified-domain", None


def search_web_prices(
    query: str,
    market: str,
    *,
    limit: int = 10,
    fetch_pages: bool = True,
    user_id: int | None = None,
    usage_origin: str | None = None,
    usage_context_id: str | None = None,
) -> dict:
    """Return observed offers and EXA discoveries as separate evidence classes."""
    market_code = normalize_market(market)
    identity = classify_query(query)
    usage = current_usage_context(user_id, usage_origin, usage_context_id)
    enforce_usage_quota(usage, "exa_search")
    try:
        discovered = discover(identity, market_code, limit=limit)
    except Exception as exc:
        record_usage(
            usage, "exa_search", status="error", provider="exa",
            metadata={"market": market_code, "error": type(exc).__name__},
        )
        raise
    record_usage(
        usage, "exa_search", status="succeeded", provider="exa",
        metadata={"market": market_code, "result_count": len(discovered)},
    )
    offers: list[dict] = []
    failures: list[dict] = []
    page_fetches = 0
    throttled_fetches = 0

    if fetch_pages:
        for candidate in discovered:
            url = candidate.get("url") or ""
            if not url.startswith(("http://", "https://")):
                continue
            enforce_usage_quota(usage, "page_fetch")
            domain = urlparse(url).netloc
            throttle = acquire_domain_fetch(domain)
            if not throttle.allowed:
                throttled_fetches += 1
                failures.append({
                    "url": url,
                    "reason": "domain rate limit",
                    "retry_after_seconds": throttle.retry_after_seconds,
                    "limit_per_minute": throttle.limit,
                })
                continue
            try:
                extracted = fetch_and_extract(url)
                page_fetches += 1
                record_usage(
                    usage, "page_fetch", status="succeeded", provider="public-web",
                    source_domain=domain, metadata={"market": market_code, "extracted": bool(extracted)},
                )
                if not extracted or extracted.amount is None:
                    failures.append({"url": url, "reason": "no structured price found"})
                    continue
                normalized = normalize_price(
                    extracted.amount,
                    extracted.currency,
                    quantity=extracted.quantity,
                    unit=extracted.unit,
                    vat_included=extracted.vat_included,
                    shipping_included=extracted.shipping_included,
                )
                offer = asdict(extracted)
                comparable_eur = fx_rate = fx_date = None
                warnings = list(normalized.warnings)
                market_status, market_warning = source_market_assessment(extracted.url, market_code)
                if market_warning:
                    warnings.append(market_warning)
                if normalized.comparable_amount is not None:
                    try:
                        comparable_eur, fx_rate, fx_date = to_eur(normalized.comparable_amount, normalized.currency)
                    except Exception as exc:
                        warnings.append(f"EUR conversion unavailable: {type(exc).__name__}")
                offer.update({
                    "market": market_code,
                    "source_domain": urlparse(extracted.url).netloc,
                    "comparable_amount": float(comparable_eur) if comparable_eur is not None else None,
                    "comparable_currency": "EUR" if comparable_eur is not None else None,
                    "comparable_unit": normalized.comparable_unit,
                    "fx_rate": float(fx_rate) if fx_rate is not None else None,
                    "fx_rate_date": fx_date.isoformat() if fx_date is not None else None,
                    "warnings": warnings,
                    "market_status": market_status,
                })
                if market_status == "country-domain-conflict":
                    failures.append({
                        "url": url,
                        "reason": "source market conflict",
                        "detail": market_warning,
                    })
                    continue
                offers.append(offer)
            except UsageQuotaExceeded:
                raise
            except Exception as exc:
                page_fetches += 1
                record_usage(
                    usage, "page_fetch", status="error", provider="public-web",
                    source_domain=domain, metadata={"market": market_code, "error": type(exc).__name__},
                )
                log.info("price extraction failed for %s: %s", url, exc)
                failures.append({"url": url, "reason": type(exc).__name__})

    offers.sort(key=lambda row: (
        row.get("comparable_amount") is None,
        row.get("comparable_amount") or float("inf"),
    ))
    observed_urls = {offer.get("url") for offer in offers}
    discovery_only = [
        candidate for candidate in discovered
        if candidate.get("url") not in observed_urls
    ]
    return {
        "query": query,
        "market": market_code,
        "identity": asdict(identity),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "coverage_statement": "Lowest observed prices from discovered public sources; not a claim of complete market coverage.",
        "offers": offers,
        "discoveries": discovered,
        "discovery_only": discovery_only,
        "extraction_failures": failures,
        "usage": {
            "exa_searches": 1,
            "page_fetches": page_fetches,
            "throttled_fetches": throttled_fetches,
        },
    }
