"""FastCPI routing: explicit prefix, identifiers, heuristics, then LLM."""

from __future__ import annotations

import logging
import re

from agents.registry import AGENTS, AGENTS_BY_SLUG
from pricing.identifiers import classify_query

log = logging.getLogger(__name__)
_PREFIX_MAP = {a.prefix.rstrip(":"): a.slug for a in AGENTS if a.prefix}
_KEYWORDS = {
    "watchlist_monitor": ["watch", "monitor", "alert", "notify", "daily scan", "threshold"],
    "cpv_specialist": ["cpv", "procurement vocabulary", "division", "descendant"],
    "market_analyst": ["market", "trend", "index", "distribution", "chart", "median", "coverage"],
    "product_compare": ["compare", "versus", " vs ", "comparison", "supplier offers"],
    "advisor": ["advise", "recommend", "competitive", "should we", "sourcing strategy"],
    "price_finder": ["price", "find", "show me", "lowest", "cheapest", "supplier", "quote"],
}


def _llm_classify(message: str) -> str:
    try:
        from utils.llm import build_llm
        slugs = ", ".join(AGENTS_BY_SLUG)
        response = build_llm(temperature=0).invoke(
            f"Classify this B2B price-intelligence request into one slug: {slugs}\n"
            f"Message: {message}\nReply with only the slug."
        ).content.strip().lower()
        if response in AGENTS_BY_SLUG:
            return response
    except Exception as exc:
        log.warning("LLM classify failed: %s", exc)
    return "price_finder"


def route(message: str) -> str:
    match = re.match(r"^(\w+):\s", (message or "").strip())
    if match and match.group(1).lower() in _PREFIX_MAP:
        return _PREFIX_MAP[match.group(1).lower()]
    lower = (message or "").lower()
    if any(keyword in lower for keyword in _KEYWORDS["watchlist_monitor"]):
        return "watchlist_monitor"
    identity = classify_query(message)
    if identity.kind == "cpv":
        return "cpv_specialist"
    if identity.kind in {"sku", "gtin"}:
        return "price_finder"
    scores = {slug: sum(keyword in lower for keyword in keywords) for slug, keywords in _KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else _llm_classify(message)


def strip_prefix(message: str) -> str:
    return re.sub(r"^\w+:\s*", "", (message or "").strip())
