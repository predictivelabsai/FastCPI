from types import SimpleNamespace

from monitoring.scanner import _watchlist_alert_content


def test_watchlist_alert_includes_provenance_and_product_disclaimer():
    watch = SimpleNamespace(name="Office paper", target_currency="EUR")
    events = [("target_price", {
        "current": 4.95,
        "currency": "EUR",
        "source_url": "https://supplier.example/paper?pack=500&x=1",
        "source_title": "A4 paper <500 sheets>",
    })]

    subject, html, text = _watchlist_alert_content(watch, events)

    assert subject == "FastCPI alert: Office paper"
    assert "https://supplier.example/paper?pack=500&amp;x=1" in html
    assert "A4 paper &lt;500 sheets&gt;" in html
    assert "not an official CPI" in html
    assert "Source: https://supplier.example/paper?pack=500&x=1" in text
