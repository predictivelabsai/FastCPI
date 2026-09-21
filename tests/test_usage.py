import pytest

from pricing.usage import UsageContext, UsageQuotaExceeded, enforce_usage_quota


def test_user_quota_is_shared_by_operation(monkeypatch):
    monkeypatch.setenv("DAILY_EXA_SEARCH_QUOTA", "5")
    monkeypatch.setattr("pricing.usage.usage_total", lambda user_id, operation: 5)
    with pytest.raises(UsageQuotaExceeded, match="quota exhausted"):
        enforce_usage_quota(UsageContext(42, "watchlist-scan", "run-1"), "exa_search")


def test_unattributed_offline_calls_do_not_require_a_database(monkeypatch):
    monkeypatch.setattr(
        "pricing.usage.usage_total",
        lambda *args: (_ for _ in ()).throw(AssertionError("database should not be queried")),
    )
    enforce_usage_quota(UsageContext(None, None, None), "page_fetch")


def test_price_search_records_discovery_and_page_fetch_usage(monkeypatch):
    from datetime import date
    from pricing.extractors import ExtractedOffer
    from pricing.service import search_web_prices

    recorded = []
    monkeypatch.setattr("pricing.service.enforce_usage_quota", lambda *args, **kwargs: None)
    monkeypatch.setattr("pricing.service.record_usage", lambda *args, **kwargs: recorded.append((args, kwargs)))
    monkeypatch.setattr(
        "pricing.service.acquire_domain_fetch",
        lambda domain: type("Decision", (), {"allowed": True})(),
    )
    monkeypatch.setattr(
        "pricing.service.discover",
        lambda *args, **kwargs: [{"url": "https://supplier.example/item", "title": "Supplier"}],
    )
    monkeypatch.setattr(
        "pricing.service.fetch_and_extract",
        lambda url: ExtractedOffer(url=url, amount=10, currency="EUR"),
    )
    monkeypatch.setattr("pricing.service.to_eur", lambda amount, currency: (amount, 1, date.today()))

    result = search_web_prices("paper", "FR", user_id=42, usage_origin="test")

    assert result["usage"] == {"exa_searches": 1, "page_fetches": 1, "throttled_fetches": 0}
    assert [args[1] for args, _ in recorded] == ["exa_search", "page_fetch"]


def test_domain_throttle_skips_fetch_without_charging_page_usage(monkeypatch):
    from pricing.service import search_web_prices

    recorded = []
    monkeypatch.setattr("pricing.service.enforce_usage_quota", lambda *args, **kwargs: None)
    monkeypatch.setattr("pricing.service.record_usage", lambda *args, **kwargs: recorded.append((args, kwargs)))
    monkeypatch.setattr(
        "pricing.service.discover",
        lambda *args, **kwargs: [{"url": "https://supplier.example/item", "title": "Supplier"}],
    )
    monkeypatch.setattr(
        "pricing.service.acquire_domain_fetch",
        lambda domain: type("Decision", (), {
            "allowed": False, "retry_after_seconds": 20, "limit": 5,
        })(),
    )
    monkeypatch.setattr(
        "pricing.service.fetch_and_extract",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fetch must be skipped")),
    )

    result = search_web_prices("paper", "FR", user_id=42, usage_origin="test")

    assert result["usage"] == {"exa_searches": 1, "page_fetches": 0, "throttled_fetches": 1}
    assert result["extraction_failures"][0]["reason"] == "domain rate limit"
    assert [args[1] for args, _ in recorded] == ["exa_search"]
