"""Shared per-domain fetch budgets for polite, multi-process crawling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from db import SCHEMA, SessionLocal


@dataclass(frozen=True)
class DomainFetchDecision:
    allowed: bool
    domain: str
    count: int
    limit: int
    retry_after_seconds: int


def domain_fetch_limit() -> int:
    return max(1, int(os.environ.get("DOMAIN_FETCHES_PER_MINUTE", "30")))


def acquire_domain_fetch(domain: str, *, now: datetime | None = None) -> DomainFetchDecision:
    """Atomically reserve one fetch in the domain's current UTC minute."""
    normalized = domain.strip().lower().rstrip(".")[:255]
    if not normalized:
        raise ValueError("A source domain is required")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window = current.replace(second=0, microsecond=0)
    limit = domain_fetch_limit()
    with SessionLocal.begin() as db:
        row = db.execute(text(f"""
            INSERT INTO {SCHEMA}.source_rate_limits AS current_limit
                (domain,window_started_at,request_count,updated_at)
            VALUES (:domain,:window,1,NOW())
            ON CONFLICT (domain) DO UPDATE SET
                window_started_at=:window,
                request_count=CASE
                    WHEN current_limit.window_started_at < :window THEN 1
                    ELSE current_limit.request_count+1
                END,
                updated_at=NOW()
            WHERE current_limit.window_started_at < :window
               OR current_limit.request_count < :limit
            RETURNING request_count
        """), {"domain": normalized, "window": window, "limit": limit}).fetchone()
    retry_after = max(1, 60 - current.second)
    return DomainFetchDecision(
        allowed=row is not None,
        domain=normalized,
        count=int(row.request_count) if row else limit,
        limit=limit,
        retry_after_seconds=0 if row else retry_after,
    )
