"""3-tier agent routing: prefix match -> keyword heuristics -> LLM fallback."""

from __future__ import annotations

import logging
import re

from agents.registry import AGENTS, AGENTS_BY_SLUG

log = logging.getLogger(__name__)

_PREFIX_MAP: dict[str, str] = {a.prefix.rstrip(":"): a.slug for a in AGENTS if a.prefix}

_SLUG_KEYWORDS: dict[str, list[str]] = {
    "car_search": ["search", "find", "looking for", "show me", "list", "filter", "under", "below"],
    "market_analyst": ["market", "trend", "depreciation", "analytics", "chart", "heat map",
                       "price trend", "segment", "average price", "cheapest"],
    "valuator": ["value", "valuation", "worth", "fair price", "estimate", "is .* fair",
                 "should i pay", "overpriced", "underpriced"],
    "car_compare": ["compare", "versus", "vs", "comparison", "side by side", "better",
                    "difference between"],
    "advisor": ["advise", "recommend", "budget", "suggest", "should i buy",
                "best car", "which car", "help me choose", "daily driver"],
    "kenri": ["kenri", "car hero", "deal", "sleeper", "what should i buy",
              "anything good", "hot deal", "best buy", "fire deal"],
}


def _prefix_match(message: str) -> str | None:
    m = re.match(r"^(\w+):\s", message.strip())
    if not m:
        return None
    prefix = m.group(1).lower()
    return _PREFIX_MAP.get(prefix)


def _keyword_scores(message: str) -> dict[str, int]:
    lower = message.lower()
    scores: dict[str, int] = {}
    for slug, keywords in _SLUG_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[slug] = score
    return scores


def _llm_classify(message: str) -> str:
    try:
        from utils.llm import build_llm
        slugs = ", ".join(AGENTS_BY_SLUG.keys())
        prompt = (
            f"Classify this user message into exactly one of these agent slugs: {slugs}\n"
            f"Message: {message}\n"
            f"Reply with ONLY the slug, nothing else."
        )
        llm = build_llm(temperature=0)
        resp = llm.invoke(prompt).content.strip().lower()
        if resp in AGENTS_BY_SLUG:
            return resp
    except Exception as e:
        log.warning("LLM classify failed: %s", e)
    return "car_search"


def route(message: str) -> str:
    slug = _prefix_match(message)
    if slug:
        return slug

    scores = _keyword_scores(message)
    if scores:
        return max(scores, key=scores.get)

    return _llm_classify(message)


def strip_prefix(message: str) -> str:
    return re.sub(r"^\w+:\s*", "", message.strip())
