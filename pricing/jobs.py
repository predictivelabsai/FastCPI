"""Durable asynchronous jobs for API-triggered web price observations."""

from __future__ import annotations

import json
import logging
import os
import socket
import uuid

from sqlalchemy import text

from db import SCHEMA, SessionLocal
from pricing.identifiers import classify_query
from pricing.markets import normalize_market

log = logging.getLogger(__name__)


def create_observation_job(
    db,
    *,
    user_id: int,
    query: str,
    market: str,
    limit: int = 10,
    fetch_pages: bool = True,
    item_id: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[dict, bool]:
    """Create an idempotent queued observation job; return (job, created)."""
    market = normalize_market(market)
    identity = classify_query(query)
    key = (idempotency_key or str(uuid.uuid4())).strip()
    if not key or len(key) > 255:
        raise ValueError("Idempotency key must contain 1 to 255 characters")
    if item_id is not None and not db.execute(text(f"""
        SELECT 1 FROM {SCHEMA}.catalog_items WHERE id=:id
    """), {"id": item_id}).fetchone():
        raise ValueError("Catalogue item not found")
    row = db.execute(text(f"""
        INSERT INTO {SCHEMA}.observation_jobs
            (user_id,idempotency_key,query,query_type,query_value,market,
             item_id,result_limit,fetch_pages)
        VALUES (:uid,:key,:query,:kind,:value,:market,:item_id,:limit,:fetch_pages)
        ON CONFLICT (user_id,idempotency_key) DO NOTHING
        RETURNING *
    """), {
        "uid": user_id, "key": key, "query": query,
        "kind": identity.kind, "value": identity.value, "market": market,
        "item_id": item_id, "limit": min(max(limit, 1), 25), "fetch_pages": fetch_pages,
    }).fetchone()
    created = row is not None
    if not row:
        row = db.execute(text(f"""
            SELECT * FROM {SCHEMA}.observation_jobs
            WHERE user_id=:uid AND idempotency_key=:key
        """), {"uid": user_id, "key": key}).fetchone()
    db.commit()
    from monitoring.jobs import wake_worker
    wake_worker()
    return dict(row._mapping), created


def claim_observation_job(worker_id: str, lease_seconds: int = 900) -> dict | None:
    db = SessionLocal()
    try:
        db.execute(text(f"""
            UPDATE {SCHEMA}.observation_jobs
            SET status='failed', error_code='AttemptsExhausted',
                error_message=COALESCE(error_message,'Maximum observation attempts exhausted'),
                lease_owner=NULL, lease_expires_at=NULL,
                completed_at=COALESCE(completed_at,NOW()),updated_at=NOW()
            WHERE attempt_count >= max_attempts
              AND (status IN ('queued','retry') OR (status='running' AND lease_expires_at < NOW()))
        """))
        row = db.execute(text(f"""
            WITH candidate AS (
                SELECT id FROM {SCHEMA}.observation_jobs
                WHERE attempt_count < max_attempts
                  AND ((status IN ('queued','retry') AND available_at <= NOW())
                    OR (status='running' AND lease_expires_at < NOW()))
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE {SCHEMA}.observation_jobs j
            SET status='running',lease_owner=:worker,
                lease_expires_at=NOW()+(:lease * INTERVAL '1 second'),
                attempt_count=attempt_count+1,started_at=COALESCE(started_at,NOW()),
                error_code=NULL,error_message=NULL,updated_at=NOW()
            FROM candidate WHERE j.id=candidate.id RETURNING j.*
        """), {"worker": worker_id, "lease": lease_seconds}).fetchone()
        db.commit()
        return dict(row._mapping) if row else None
    finally:
        db.close()


def _complete(job_id, result: dict) -> None:
    db = SessionLocal()
    try:
        db.execute(text(f"""
            UPDATE {SCHEMA}.observation_jobs
            SET status='succeeded',search_run_id=CAST(:search_run AS uuid),
                discovery_count=:discoveries,observation_count=:observations,
                observation_ids=CAST(:ids AS jsonb),lease_owner=NULL,lease_expires_at=NULL,
                completed_at=NOW(),updated_at=NOW()
            WHERE id=:id
        """), {
            "search_run": result["search_run_id"],
            "discoveries": len(result.get("discoveries", [])),
            "observations": len(result.get("offers", [])),
            "ids": json.dumps(result.get("persisted_observation_ids", [])), "id": job_id,
        })
        db.commit()
    finally:
        db.close()


def _fail(job: dict, exc: Exception) -> None:
    attempt = int(job.get("attempt_count") or 1)
    retrying = attempt < int(job.get("max_attempts") or 3)
    delay = min(3600, 60 * (2 ** max(0, attempt - 1)))
    db = SessionLocal()
    try:
        db.execute(text(f"""
            UPDATE {SCHEMA}.observation_jobs
            SET status=:status,
                available_at=CASE WHEN :retrying THEN NOW()+(:delay * INTERVAL '1 second') ELSE available_at END,
                error_code=:code,error_message=:message,lease_owner=NULL,lease_expires_at=NULL,
                completed_at=CASE WHEN :retrying THEN NULL ELSE NOW() END,updated_at=NOW()
            WHERE id=:id
        """), {"status": "retry" if retrying else "failed", "retrying": retrying,
                 "delay": delay, "code": type(exc).__name__, "message": str(exc)[:2000], "id": job["id"]})
        db.commit()
    finally:
        db.close()


def work_observation_once(worker_id: str | None = None) -> dict | None:
    worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    job = claim_observation_job(worker_id)
    if not job:
        return None
    try:
        from pricing.repository import persist_search_result
        from pricing.service import search_web_prices
        result = search_web_prices(
            job["query"], job["market"], limit=job["result_limit"],
            fetch_pages=job["fetch_pages"],
        )
        result["item_id"] = job.get("item_id")
        db = SessionLocal()
        try:
            result = persist_search_result(db, result, user_id=job["user_id"])
        finally:
            db.close()
        _complete(job["id"], result)
        return {"observation_job_id": str(job["id"]), "status": "succeeded"}
    except Exception as exc:
        log.exception("observation job %s failed", job["id"])
        _fail(job, exc)
        return {"observation_job_id": str(job["id"]), "status": "retry_or_failed", "error": type(exc).__name__}
