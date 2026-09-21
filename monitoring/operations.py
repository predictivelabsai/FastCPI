"""Operator-facing queue inspection and audited dead-letter replay."""

from __future__ import annotations

import json

from sqlalchemy import text

from db import SCHEMA


JOB_TABLES = {
    "scan": f"{SCHEMA}.scan_runs",
    "observation": f"{SCHEMA}.observation_jobs",
}


def operations_snapshot(db, *, limit: int = 50) -> dict:
    size = min(max(limit, 1), 200)
    dead_letters = db.execute(text(f"""
        SELECT * FROM (
            SELECT 'scan' AS job_type,sr.id,sr.status,sr.attempt_count,sr.max_attempts,
                   sr.error_code,sr.error_message,sr.completed_at,sr.updated_at,
                   u.email,COALESCE(w.name,'Watch scan') AS label
            FROM {SCHEMA}.scan_runs sr
            JOIN {SCHEMA}.chat_users u ON u.id=sr.user_id
            LEFT JOIN {SCHEMA}.watchlists w ON w.id=sr.watchlist_id
            WHERE sr.status='failed'
            UNION ALL
            SELECT 'observation' AS job_type,oj.id,oj.status,oj.attempt_count,oj.max_attempts,
                   oj.error_code,oj.error_message,oj.completed_at,oj.updated_at,
                   u.email,oj.query AS label
            FROM {SCHEMA}.observation_jobs oj
            JOIN {SCHEMA}.chat_users u ON u.id=oj.user_id
            WHERE oj.status='failed'
        ) failed
        ORDER BY completed_at DESC NULLS LAST,updated_at DESC
        LIMIT :limit
    """), {"limit": size}).fetchall()
    usage = db.execute(text(f"""
        SELECT operation,status,COUNT(*) AS entries,COALESCE(SUM(units),0) AS units
        FROM {SCHEMA}.usage_ledger
        WHERE created_at>=NOW()-INTERVAL '24 hours'
        GROUP BY operation,status ORDER BY operation,status
    """)).fetchall()
    actions = db.execute(text(f"""
        SELECT oa.*,u.email AS actor_email
        FROM {SCHEMA}.operations_actions oa
        LEFT JOIN {SCHEMA}.chat_users u ON u.id=oa.actor_user_id
        ORDER BY oa.created_at DESC LIMIT 25
    """)).fetchall()
    from monitoring.health import latest_worker_health, queue_health
    worker = latest_worker_health()
    worker.update(queue_health(db))
    worker["alerts"] = [
        name for name, active in (
            ("stalled_jobs", worker.get("stalled_jobs", 0) > 0),
            ("dead_letters", worker.get("dead_letters", 0) > 0),
            ("queue_slo", worker.get("oldest_queue_age_seconds", 0) > 900),
        ) if active
    ]
    return {
        "worker": worker,
        "dead_letters": [dict(row._mapping) for row in dead_letters],
        "usage": [dict(row._mapping) for row in usage],
        "actions": [dict(row._mapping) for row in actions],
    }


def replay_dead_letter(db, *, actor_user_id: int, job_type: str, job_id: str) -> dict | None:
    table = JOB_TABLES.get(job_type)
    if not table:
        raise ValueError("Unsupported job type")
    row = db.execute(text(f"""
        SELECT id,status,attempt_count,max_attempts,error_code,error_message
        FROM {table} WHERE id=CAST(:id AS uuid) FOR UPDATE
    """), {"id": job_id}).fetchone()
    if not row or row.status != "failed":
        return None
    metadata = {
        "previous_attempt_count": row.attempt_count,
        "previous_max_attempts": row.max_attempts,
        "previous_error_code": row.error_code,
        "previous_error_message": (row.error_message or "")[:1000],
    }
    db.execute(text(f"""
        UPDATE {table}
        SET status='retry',available_at=NOW(),attempt_count=0,
            lease_owner=NULL,lease_expires_at=NULL,completed_at=NULL,updated_at=NOW()
        WHERE id=CAST(:id AS uuid) AND status='failed'
    """), {"id": job_id})
    db.execute(text(f"""
        INSERT INTO {SCHEMA}.operations_actions
            (actor_user_id,action,job_type,job_id,metadata)
        VALUES (:actor,'replay_dead_letter',:job_type,CAST(:job_id AS uuid),CAST(:metadata AS jsonb))
    """), {
        "actor": actor_user_id, "job_type": job_type, "job_id": job_id,
        "metadata": json.dumps(metadata),
    })
    db.commit()
    return {"job_type": job_type, "job_id": job_id, "status": "retry"}
