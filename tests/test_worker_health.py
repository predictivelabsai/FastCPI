from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import monitoring.health as worker_health


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Session:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        return _Result(self.row)

    def close(self):
        pass


def test_latest_worker_health_is_json_ready(monkeypatch):
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(_mapping={
        "worker_id": "worker-1",
        "status": "ready",
        "queue_depth": 2,
        "running_jobs": 1,
        "failed_24h": 0,
        "stalled_jobs": 1,
        "dead_letters": 2,
        "oldest_queue_age_seconds": 1200,
        "metadata": {},
        "started_at": now - timedelta(minutes=5),
        "last_seen_at": now,
        "age_seconds": Decimal("1.25"),
    })
    monkeypatch.setattr(worker_health, "SessionLocal", lambda: _Session(row))

    payload = worker_health.latest_worker_health(max_age_seconds=180)

    assert payload["ready"] is True
    assert payload["started_at"].endswith("+00:00")
    assert payload["last_seen_at"].endswith("+00:00")
    assert payload["age_seconds"] == 1.25
    assert payload["alerts"] == ["stalled_jobs", "dead_letters", "queue_slo"]


def test_latest_worker_health_reports_missing(monkeypatch):
    monkeypatch.setattr(worker_health, "SessionLocal", lambda: _Session(None))

    assert worker_health.latest_worker_health(90) == {
        "status": "missing", "ready": False, "max_age_seconds": 90,
    }
