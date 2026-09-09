from tools.prices import _search_web_prices


def test_price_tool_text_keeps_discovery_only_urls(monkeypatch):
    monkeypatch.setattr("tools.prices.search_web_prices", lambda *args, **kwargs: {
        "coverage_statement": "Observed public sample; not complete coverage.",
        "offers": [],
        "discovery_only": [{"title": "Supplier candidate", "url": "https://supplier.example/item"}],
    })

    output = _search_web_prices(query="paper", market="FR", limit=3)

    assert "https://supplier.example/item" in output
    assert "no attributable price extracted" in output.lower()
