"""Shared metering and quotas for paid discovery and page fetching."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import text

from db import SCHEMA, SessionLocal


_USER_ID: ContextVar[int | None] = ContextVar("fastcpi_usage_user_id", default=None)
_ORIGIN: ContextVar[str | None] = ContextVar("fastcpi_usage_origin", default=None)
_CONTEXT_ID: ContextVar[str | None] = ContextVar("fastcpi_usage_context_id", default=None)


@dataclass(frozen=True)
class UsageContext:
    user_id: int | None
    origin: str | None
    context_id: str | None


class UsageQuotaExceeded(RuntimeError):
    def __init__(self, operation: str, limit: int):
        self.operation = operation
        self.limit = limit
        super().__init__(f"Daily {operation.replace('_', ' ')} quota exhausted ({limit})")


@contextmanager
def usage_context(user_id: int | None, origin: str, context_id: str | None = None):
    user_token = _USER_ID.set(user_id)
    origin_token = _ORIGIN.set(origin)
    context_token = _CONTEXT_ID.set(context_id)
    try:
        yield
    finally:
        _CONTEXT_ID.reset(context_token)
        _ORIGIN.reset(origin_token)
        _USER_ID.reset(user_token)


def current_usage_context(
    user_id: int | None = None,
    origin: str | None = None,
    context_id: str | None = None,
) -> UsageContext:
    return UsageContext(
        user_id if user_id is not None else _USER_ID.get(),
        origin or _ORIGIN.get(),
        context_id or _CONTEXT_ID.get(),
    )


def _limit(operation: str) -> int:
    key = "DAILY_EXA_SEARCH_QUOTA" if operation == "exa_search" else "DAILY_PAGE_FETCH_QUOTA"
    return max(1, int(os.environ.get(key, "100" if operation == "exa_search" else "1000")))


def usage_total(user_id: int, operation: str) -> int:
    db = SessionLocal()
    try:
        return int(db.execute(text(f"""
            SELECT COALESCE(SUM(units),0) FROM {SCHEMA}.usage_ledger
            WHERE user_id=:uid AND operation=:operation
              AND created_at >= NOW()-INTERVAL '24 hours'
        """), {"uid": user_id, "operation": operation}).scalar() or 0)
    finally:
        db.close()


def enforce_usage_quota(context: UsageContext, operation: str, units: int = 1) -> None:
    if context.user_id is None or not context.origin:
        return
    limit = _limit(operation)
    if usage_total(context.user_id, operation) + units > limit:
        raise UsageQuotaExceeded(operation, limit)


def record_usage(
    context: UsageContext,
    operation: str,
    *,
    status: str,
    units: int = 1,
    provider: str | None = None,
    source_domain: str | None = None,
    metadata: dict | None = None,
) -> None:
    if not context.origin:
        return
    db = SessionLocal()
    try:
        db.execute(text(f"""
            INSERT INTO {SCHEMA}.usage_ledger
                (user_id,operation,units,status,origin,context_id,provider,source_domain,metadata)
            VALUES (:uid,:operation,:units,:status,:origin,:context_id,:provider,:domain,
                    CAST(:metadata AS jsonb))
        """), {
            "uid": context.user_id, "operation": operation, "units": max(1, units),
            "status": status[:30], "origin": context.origin[:40],
            "context_id": (context.context_id or "")[:255] or None,
            "provider": (provider or "")[:80] or None,
            "domain": (source_domain or "")[:255] or None,
            "metadata": json.dumps(metadata or {}),
        })
        db.commit()
    finally:
        db.close()
