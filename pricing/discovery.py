"""EXA discovery for B2B product and service prices."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from pricing.identifiers import QueryIdentity
from pricing.markets import MARKETS
from utils.config import settings

EXA_URL = "https://api.exa.ai/search"


def build_discovery_query(identity: QueryIdentity, market: str, cpv_labels: list[str] | None = None) -> str:
    info = MARKETS[market]
    terms = [identity.text, info["name"], "business price supplier"]
    if identity.kind == "cpv" and cpv_labels:
        terms.extend(cpv_labels[:5])
    return " ".join(t for t in terms if t)


def discover(identity: QueryIdentity, market: str, *, limit: int = 10, days: int | None = 30) -> list[dict]:
    key = settings().exa_api_key
    if not key:
        return []
    query = build_discovery_query(identity, market)
    payload: dict = {
        "query": query,
        "numResults": max(1, min(limit, 25)),
        "type": "auto",
        "contents": {"text": {"maxCharacters": 2500}, "highlights": {"numSentences": 5}},
    }
    if days:
        payload["startPublishedDate"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    response = httpx.post(
        EXA_URL,
        json=payload,
        headers={"x-api-key": key, "content-type": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    results = []
    for row in response.json().get("results", []):
        results.append({
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "published_date": row.get("publishedDate"),
            "text": (row.get("text") or "")[:2500],
            "highlights": row.get("highlights") or [],
            "score": row.get("score"),
            "discovery_provider": "exa",
        })
    return results
