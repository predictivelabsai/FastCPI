"""Operational heartbeat and queue health for the standalone worker."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from db import SCHEMA, SessionLocal


def queue_health(db) -> dict[str, int]:
    row = db.execute(text(f"""
        SELECT
          (SELECT COUNT(*) FROM {SCHEMA}.scan_runs
           WHERE status IN ('queued','retry') OR (status='running' AND lease_expires_at<NOW()))
          +
          (SELECT COUNT(*) FROM {SCHEMA}.observation_jobs
           WHERE status IN ('queued','retry') OR (status='running' AND lease_expires_at<NOW())) AS queue_depth,
          (SELECT COUNT(*) FROM {SCHEMA}.scan_runs WHERE status='running' AND lease_expires_at>=NOW())
          +
          (SELECT COUNT(*) FROM {SCHEMA}.observation_jobs WHERE status='running' AND lease_expires_at>=NOW()) AS running_jobs,
          (SELECT COUNT(*) FROM {SCHEMA}.scan_runs WHERE status='failed' AND completed_at>=NOW()-INTERVAL '24 hours')
          +
          (SELECT COUNT(*) FROM {SCHEMA}.observation_jobs WHERE status='failed' AND completed_at>=NOW()-INTERVAL '24 hours') AS failed_24h
    """)).fetchone()
    return {key: int(getattr(row, key) or 0) for key in ("queue_depth", "running_jobs", "failed_24h")}


def record_worker_heartbeat(worker_id: str, status: str = "ready", metadata: dict | None = None) -> dict:
    db = SessionLocal()
    try:
        health = queue_health(db)
        db.execute(text(f"""
            INSERT INTO {SCHEMA}.worker_heartbeats
                (worker_id,status,queue_depth,running_jobs,failed_24h,metadata)
            VALUES (:worker,:status,:queue_depth,:running_jobs,:failed_24h,CAST(:metadata AS jsonb))
            ON CONFLICT (worker_id) DO UPDATE SET
                status=EXCLUDED.status,queue_depth=EXCLUDED.queue_depth,
                running_jobs=EXCLUDED.running_jobs,failed_24h=EXCLUDED.failed_24h,
                metadata=EXCLUDED.metadata,last_seen_at=NOW()
        """), {
            "worker": worker_id[:160], "status": status[:30], **health,
            "metadata": json.dumps(metadata or {}),
        })
        db.commit()
        return health
    finally:
        db.close()


def latest_worker_health(max_age_seconds: int = 180) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(text(f"""
            SELECT *, EXTRACT(EPOCH FROM (NOW()-last_seen_at)) AS age_seconds
            FROM {SCHEMA}.worker_heartbeats ORDER BY last_seen_at DESC LIMIT 1
        """)).fetchone()
    finally:
        db.close()
    if not row:
        return {"status": "missing", "ready": False, "max_age_seconds": max_age_seconds}
    payload = dict(row._mapping)
    payload["started_at"] = payload["started_at"].astimezone(timezone.utc).isoformat()
    payload["last_seen_at"] = payload["last_seen_at"].astimezone(timezone.utc).isoformat()
    payload["age_seconds"] = float(payload["age_seconds"] or 0)
    payload["ready"] = payload["status"] == "ready" and payload["age_seconds"] <= max_age_seconds
    payload["checked_at"] = datetime.now(timezone.utc).isoformat()
    return payload
