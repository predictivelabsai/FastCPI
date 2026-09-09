"""Durable PostgreSQL-backed watchlist scan queue and worker."""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from db import SCHEMA, SessionLocal

log = logging.getLogger(__name__)

TERMINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled"}
_WAKE_EVENT = threading.Event()


def wake_worker() -> None:
    _WAKE_EVENT.set()


def enqueue_watchlist_scan(
    db,
    watchlist_id: int,
    user_id: int,
    *,
    trigger: str = "manual",
    scheduled_for=None,
    idempotency_key: str | None = None,
) -> dict:
    """Persist a scan request and return it; duplicate keys return the original run."""
    if trigger not in {"scheduled", "manual", "api"}:
        raise ValueError("Unsupported scan trigger")
    scheduled_for = scheduled_for or datetime.now(timezone.utc)
    idempotency_key = idempotency_key or f"{trigger}:{watchlist_id}:{uuid.uuid4()}"
    row = db.execute(text(f"""
        INSERT INTO {SCHEMA}.scan_runs
            (watchlist_id,user_id,trigger,idempotency_key,scheduled_for,available_at)
        VALUES (:watchlist,:user_id,:trigger,:key,:scheduled_for,NOW())
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING *
    """), {
        "watchlist": watchlist_id, "user_id": user_id, "trigger": trigger,
        "key": idempotency_key, "scheduled_for": scheduled_for,
    }).fetchone()
    if not row:
        row = db.execute(text(f"""
            SELECT * FROM {SCHEMA}.scan_runs WHERE idempotency_key=:key
        """), {"key": idempotency_key}).fetchone()
    db.commit()
    wake_worker()
    return dict(row._mapping)


def enqueue_due_watchlists(limit: int = 50) -> list[dict]:
    """Create one stable scheduled job per due occurrence without double-enqueueing."""
    db = SessionLocal()
    queued = []
    try:
        rows = db.execute(text(f"""
            SELECT id,user_id,COALESCE(next_run_at,created_at,NOW()) AS scheduled_for
            FROM {SCHEMA}.watchlists
            WHERE is_active=TRUE AND (next_run_at IS NULL OR next_run_at <= NOW())
            ORDER BY next_run_at NULLS FIRST, id
            FOR UPDATE SKIP LOCKED
            LIMIT :limit
        """), {"limit": max(1, min(limit, 500))}).fetchall()
        for row in rows:
            scheduled = row.scheduled_for
            key = f"scheduled:{row.id}:{scheduled.astimezone(timezone.utc).isoformat()}"
            queued.append(enqueue_watchlist_scan(
                db, row.id, row.user_id, trigger="scheduled",
                scheduled_for=scheduled, idempotency_key=key,
            ))
            # Move the schedule forward when the durable job is accepted. Retries
            # belong to this run; the next daily occurrence must remain independent.
            db.execute(text(f"""
                UPDATE {SCHEMA}.watchlists
                SET next_run_at=GREATEST(:scheduled_for,NOW())+INTERVAL '1 day',updated_at=NOW()
                WHERE id=:id
            """), {"scheduled_for": scheduled, "id": row.id})
            db.commit()
        return queued
    finally:
        db.close()


def claim_next_scan(worker_id: str, lease_seconds: int = 900) -> dict | None:
    """Atomically claim an available or expired job using SKIP LOCKED."""
    db = SessionLocal()
    try:
        db.execute(text(f"""
            UPDATE {SCHEMA}.scan_runs
            SET status='failed', error_code='AttemptsExhausted',
                error_message=COALESCE(error_message,'Maximum scan attempts exhausted'),
                lease_owner=NULL, lease_expires_at=NULL,
                completed_at=COALESCE(completed_at,NOW()), updated_at=NOW()
            WHERE attempt_count >= max_attempts
              AND (status IN ('queued','retry') OR (status='running' AND lease_expires_at < NOW()))
        """))
        row = db.execute(text(f"""
            WITH candidate AS (
                SELECT id FROM {SCHEMA}.scan_runs
                WHERE attempt_count < max_attempts
                  AND (
                    (status IN ('queued','retry') AND available_at <= NOW())
                    OR (status='running' AND lease_expires_at < NOW())
                  )
                ORDER BY scheduled_for, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE {SCHEMA}.scan_runs r
            SET status='running', lease_owner=:worker,
                lease_expires_at=NOW()+(:lease_seconds * INTERVAL '1 second'),
                attempt_count=attempt_count+1,
                started_at=COALESCE(started_at,NOW()), updated_at=NOW(),
                error_code=NULL, error_message=NULL
            FROM candidate
            WHERE r.id=candidate.id
            RETURNING r.*
        """), {"worker": worker_id, "lease_seconds": lease_seconds}).fetchone()
        db.commit()
        return dict(row._mapping) if row else None
    finally:
        db.close()


def complete_scan_run(run_id, result: dict) -> None:
    db = SessionLocal()
    try:
        failed_markets = len(result.get("failed_markets", []))
        succeeded_markets = len(result.get("market_results", [])) - failed_markets
        status = "partial" if failed_markets and succeeded_markets else "succeeded"
        db.execute(text(f"""
            UPDATE {SCHEMA}.scan_runs
            SET status=:status, market_count=:markets,
                discovered_count=:discoveries, observed_count=:observations,
                event_count=:events, lease_owner=NULL, lease_expires_at=NULL,
                completed_at=NOW(), updated_at=NOW()
            WHERE id=:id
        """), {
            "status": status, "markets": len(result.get("markets", [])),
            "discoveries": result.get("discovered_count", 0),
            "observations": result.get("observed_offers", 0),
            "events": result.get("events", 0), "id": run_id,
        })
        db.commit()
    finally:
        db.close()


def fail_scan_run(run: dict, exc: Exception) -> None:
    """Schedule bounded exponential retry, or persist a terminal failure."""
    attempt = int(run.get("attempt_count") or 1)
    maximum = int(run.get("max_attempts") or 3)
    retrying = attempt < maximum
    delay_seconds = min(3600, 60 * (2 ** max(0, attempt - 1)))
    db = SessionLocal()
    try:
        db.execute(text(f"""
            UPDATE {SCHEMA}.scan_runs
            SET status=:status,
                available_at=CASE WHEN :retrying THEN NOW()+(:delay * INTERVAL '1 second') ELSE available_at END,
                error_code=:code, error_message=:message,
                lease_owner=NULL, lease_expires_at=NULL,
                completed_at=CASE WHEN :retrying THEN NULL ELSE NOW() END,
                updated_at=NOW()
            WHERE id=:id
        """), {
            "status": "retry" if retrying else "failed", "retrying": retrying,
            "delay": delay_seconds, "code": type(exc).__name__,
            "message": str(exc)[:2000], "id": run["id"],
        })
        db.commit()
    finally:
        db.close()


def work_once(worker_id: str | None = None) -> dict | None:
    """Claim and execute one durable job."""
    worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    run = claim_next_scan(worker_id)
    if not run:
        return None
    try:
        from monitoring.scanner import scan_watchlist
        result = scan_watchlist(run["watchlist_id"], scan_run_id=run["id"])
        complete_scan_run(run["id"], result)
        return {"scan_run_id": str(run["id"]), "status": "complete", **result}
    except Exception as exc:
        log.exception("scan run %s failed", run["id"])
        fail_scan_run(run, exc)
        return {"scan_run_id": str(run["id"]), "status": "retry_or_failed", "error": type(exc).__name__}


def queue_and_work(limit: int = 50) -> list[dict]:
    enqueue_due_watchlists(limit)
    results = []
    for _ in range(limit):
        scan_result = work_once()
        from pricing.jobs import work_observation_once
        observation_result = work_observation_once()
        if scan_result is None and observation_result is None:
            break
        if scan_result is not None:
            results.append(scan_result)
        if observation_result is not None:
            results.append(observation_result)
    return results


def start_job_worker(interval_seconds: int = 60) -> None:
    """Run the durable queue in-process; the same loop can run as a standalone worker."""
    def loop():
        while True:
            try:
                queue_and_work()
            except Exception:
                log.exception("watchlist job worker iteration failed")
            _WAKE_EVENT.wait(timeout=max(15, interval_seconds))
            _WAKE_EVENT.clear()

    threading.Thread(target=loop, name="fastcpi-scan-jobs", daemon=True).start()
