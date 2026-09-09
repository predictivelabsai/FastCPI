"""Web search tool -- Exa for car market research."""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from utils.config import settings

log = logging.getLogger(__name__)

EXA_URL = "https://api.exa.ai/search"


class SearchArgs(BaseModel):
    query: str = Field(description="Natural-language web search query about cars, reviews, market trends, or pricing.")
    max_results: int = Field(default=6, ge=1, le=15)
    days: Optional[int] = Field(default=None, description="Recency window in days (optional).")


def _exa(query: str, max_results: int, days: int | None) -> dict | None:
    key = settings().exa_api_key
    if not key:
        return None
    payload = {
        "query": query,
        "numResults": max_results,
        "type": "auto",
        "contents": {"text": {"maxCharacters": 800}, "highlights": {"numSentences": 3}},
    }
    if days:
        from datetime import datetime, timedelta
        payload["startPublishedDate"] = (datetime.utcnow() - timedelta(days=days)).isoformat()
    headers = {"x-api-key": key, "content-type": "application/json"}
    try:
        r = httpx.post(EXA_URL, json=payload, headers=headers, timeout=20.0)
        r.raise_for_status()
        data = r.json()
        return {
            "provider": "exa",
            "results": [
                {"title": h.get("title"), "url": h.get("url"),
                 "snippet": (h.get("text") or "")[:800],
                 "score": h.get("score")}
                for h in (data.get("results") or [])
            ],
        }
    except Exception as e:
        log.warning("exa failed: %s", e)
        return None


def _web_search(**kw) -> str:
    args = SearchArgs(**kw)
    data = _exa(args.query, args.max_results, args.days)
    if not data:
        return "Search unavailable -- no EXA_API_KEY configured or provider failed."

    items = data["results"]
    lines = [f"Web search: {args.query} ({len(items)} results)\n"]
    for it in items:
        title = it.get("title") or "Untitled"
        url = it.get("url") or ""
        snippet = (it.get("snippet") or "")[:200]
        lines.append(f"- **{title}**\n  {url}\n  {snippet}\n")
    return "\n".join(lines)


web_search = StructuredTool.from_function(
    func=_web_search,
    name="web_search",
    description=(
        "Search the web for information about cars, reviews, reliability reports, "
        "market trends, pricing guides, recalls, and automotive news. "
        "Returns title + URL + snippet from Exa search."
    ),
    args_schema=SearchArgs,
)
