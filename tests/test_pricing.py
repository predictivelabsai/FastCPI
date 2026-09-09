"""Deterministic FastCPI domain tests; no database or network required."""

import pytest

from pricing.extractors import _get_with_safe_redirects, extract_html, validate_public_url
from pricing.identifiers import classify_query, cpv_prefix
from pricing.normalization import normalize_price
from pricing.service import search_web_prices


def test_identifier_precedence_and_cpv_hierarchy():
    identity = classify_query("Show CPV 30100000-0 prices in France")
    assert identity.kind == "cpv"
    assert identity.value == "30100000"
    assert cpv_prefix(identity.value) == "301"


def test_labelled_sku_and_plain_language():
    assert classify_query("price SKU 6ES7214-1AG40-0XB0").kind == "sku"
    assert classify_query("GTIN 4006381333931").kind == "gtin"
    assert classify_query("12345678").kind == "gtin"
    assert classify_query("A4 recycled paper").kind == "text"


def test_unit_normalization_preserves_unknown_commercial_terms():
    price = normalize_price("25.00", "EUR", quantity=5000, unit="g")
    assert float(price.comparable_amount) == 5.0
    assert price.comparable_unit == "kg"
    assert "VAT status unknown" in price.warnings
    assert "delivery not confirmed" in price.warnings


def test_shipping_is_included_in_comparable_price():
    price = normalize_price(10, "EUR", quantity=2, unit="each", shipping_amount=4, vat_included=False)
    assert float(price.comparable_amount) == 7.0
    assert price.shipping_included is True


def test_json_ld_product_offer_extraction_keeps_evidence():
    html = """
    <html><head><title>Paper</title>
    <script type="application/ld+json">
    {"@type":"Product","name":"A4 Paper","sku":"P-500",
     "offers":{"@type":"Offer","price":"4.95","priceCurrency":"EUR",
               "availability":"https://schema.org/InStock","seller":{"name":"Supplier SA"}}}
    </script></head></html>
    """
    offer = extract_html("https://supplier.example/paper", html)
    assert offer is not None
    assert offer.amount == 4.95
    assert offer.currency == "EUR"
    assert offer.seller == "Supplier SA"
    assert offer.sku == "P-500"
    assert offer.extraction_method == "json-ld"
    assert offer.content_hash
    assert '"price": "4.95"' in offer.evidence


def test_open_graph_price_is_lower_confidence_fallback():
    html = """<html><head><meta property="og:title" content="Managed support" />
    <meta property="og:site_name" content="Supplier" />
    <meta property="product:price:amount" content="99.00" />
    <meta property="product:price:currency" content="EUR" /></head></html>"""
    offer = extract_html("https://supplier.example/support", html)
    assert offer is not None
    assert offer.confidence == 0.8
    assert offer.extraction_method == "open-graph"


def test_microdata_price_adapter():
    html = """<html><head><title>Paper</title>
    <meta itemprop="name" content="A4 Paper 500 sheets">
    <meta itemprop="sku" content="PAPER-500">
    <meta itemprop="price" content="6,99">
    <meta itemprop="priceCurrency" content="EUR"></head></html>"""
    offer = extract_html("https://www.office-partner.de/paper", html)
    assert offer is not None
    assert offer.amount == 6.99
    assert offer.sku == "PAPER-500"
    assert offer.extraction_method == "microdata"


def test_staver_hourly_service_adapter():
    html = """<html><head><title>IT support</title></head>
    <body><div>Remote computer support</div><strong>38 €/hour</strong></body></html>"""
    offer = extract_html("https://staver.eu/en/price-list/", html)
    assert offer is not None
    assert offer.amount == 38
    assert offer.unit == "hour"
    assert offer.extraction_method == "staver-hourly-rate"


def test_visible_hourly_service_fallback():
    html = """<html><head><title>Business IT support</title></head>
    <body><div>Remote support for companies: €55 per hour.</div></body></html>"""
    offer = extract_html("https://direktsupport.eu/pricing/", html)
    assert offer is not None
    assert offer.amount == 55
    assert offer.unit == "hour"
    assert offer.extraction_method == "visible-hourly-rate"


def test_fetcher_rejects_private_and_non_http_urls():
    with pytest.raises(ValueError):
        validate_public_url("http://127.0.0.1/admin")
    with pytest.raises(ValueError):
        validate_public_url("file:///etc/passwd")


def test_fetcher_validates_redirect_before_following_it(monkeypatch):
    class Response:
        status_code = 302
        headers = {"location": "http://127.0.0.1/admin"}

    class Client:
        calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            return Response()

    monkeypatch.setattr(
        "pricing.extractors.socket.getaddrinfo",
        lambda host, *args, **kwargs: [
            (None, None, None, None, ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443))
        ],
    )
    client = Client()
    with pytest.raises(ValueError, match="Private or non-global"):
        _get_with_safe_redirects(client, "https://example.com/product")
    assert client.calls == ["https://example.com/product"]


def test_search_separates_observed_from_discovery_only(monkeypatch):
    from pricing.extractors import ExtractedOffer

    monkeypatch.setattr(
        "pricing.service.discover",
        lambda *args, **kwargs: [
            {"url": "https://supplier.example/observed", "title": "Observed"},
            {"url": "https://supplier.example/candidate", "title": "Candidate"},
        ],
    )
    monkeypatch.setattr(
        "pricing.service.fetch_and_extract",
        lambda url: ExtractedOffer(url=url, amount=5, currency="EUR")
        if url.endswith("observed") else None,
    )
    monkeypatch.setattr("pricing.service.to_eur", lambda amount, currency: (amount, 1, __import__("datetime").date.today()))

    result = search_web_prices("paper", "FR")
    assert len(result["offers"]) == 1
    assert [row["url"] for row in result["discovery_only"]] == ["https://supplier.example/candidate"]
