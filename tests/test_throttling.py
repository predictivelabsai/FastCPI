from datetime import datetime, timezone
from types import SimpleNamespace

import pricing.throttling as throttling


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Transaction:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return _Result(self.row)


class _SessionFactory:
    def __init__(self, row):
        self.row = row

    def begin(self):
        return _Transaction(self.row)


def test_domain_fetch_slot_is_allowed(monkeypatch):
    monkeypatch.setenv("DOMAIN_FETCHES_PER_MINUTE", "5")
    monkeypatch.setattr(throttling, "SessionLocal", _SessionFactory(SimpleNamespace(request_count=3)))

    decision = throttling.acquire_domain_fetch(
        "SUPPLIER.EXAMPLE.", now=datetime(2026, 9, 21, 10, 5, 12, tzinfo=timezone.utc),
    )

    assert decision.allowed is True
    assert decision.domain == "supplier.example"
    assert decision.count == 3
    assert decision.limit == 5
    assert decision.retry_after_seconds == 0


def test_domain_fetch_slot_reports_retry_window(monkeypatch):
    monkeypatch.setenv("DOMAIN_FETCHES_PER_MINUTE", "2")
    monkeypatch.setattr(throttling, "SessionLocal", _SessionFactory(None))

    decision = throttling.acquire_domain_fetch(
        "supplier.example", now=datetime(2026, 9, 21, 10, 5, 47, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert decision.count == 2
    assert decision.retry_after_seconds == 13
