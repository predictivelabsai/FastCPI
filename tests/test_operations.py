from types import SimpleNamespace

import pytest

from monitoring.operations import replay_dead_letter


class _Result:
    def __init__(self, row=None, rowcount=1):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class _DB:
    def __init__(self, row):
        self.row = row
        self.statements = []
        self.committed = False

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params or {}))
        if len(self.statements) == 1:
            return _Result(self.row)
        return _Result()

    def commit(self):
        self.committed = True


def test_replay_dead_letter_resets_attempts_and_audits():
    row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001", status="failed",
        attempt_count=3, max_attempts=3, error_code="TimeoutError",
        error_message="supplier timed out",
    )
    db = _DB(row)

    result = replay_dead_letter(
        db, actor_user_id=7, job_type="scan", job_id=str(row.id),
    )

    assert result["status"] == "retry"
    assert "attempt_count=0" in db.statements[1][0]
    assert "operations_actions" in db.statements[2][0]
    assert db.committed is True


def test_replay_rejects_unknown_job_type():
    with pytest.raises(ValueError, match="Unsupported job type"):
        replay_dead_letter(_DB(None), actor_user_id=7, job_type="other", job_id="bad")


def test_replay_only_accepts_failed_job():
    row = SimpleNamespace(status="succeeded")
    db = _DB(row)

    assert replay_dead_letter(
        db, actor_user_id=7, job_type="observation",
        job_id="00000000-0000-0000-0000-000000000001",
    ) is None
    assert db.committed is False
