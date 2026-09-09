"""Tests for utils/deals_scanner.py -- deal scanning and email rendering."""

import os
import pytest

os.environ.setdefault("TO_EMAIL_TEST", "julian@predictivelabs.co.uk")

from utils.deals_scanner import (
    scan_deals,
    scan_lowest_prices,
    build_digest_html,
    build_digest_text,
    _fmt_eur,
    _source_label,
)


class TestFormatHelpers:
    def test_fmt_eur_normal(self):
        assert _fmt_eur(45000) == "EUR 45,000"

    def test_fmt_eur_decimal(self):
        assert _fmt_eur(45000.50) == "EUR 45,000"

    def test_fmt_eur_none(self):
        assert _fmt_eur(None) == "--"

    def test_fmt_eur_zero(self):
        assert _fmt_eur(0) == "--"

    def test_source_label(self):
        assert _source_label("DE", "mobile_de") == "Germany / mobile.de"

    def test_source_label_gb(self):
        assert _source_label("GB", "autotrader") == "UK / AutoTrader"

    def test_source_label_unknown(self):
        assert _source_label("XX", "unknown_provider") == "XX / unknown_provider"

    def test_source_label_none(self):
        assert _source_label(None, None) == " / "


class TestScanDeals:
    def test_returns_list(self):
        deals = scan_deals(limit=5)
        assert isinstance(deals, list)

    def test_deal_structure(self):
        deals = scan_deals(limit=5)
        if not deals:
            pytest.skip("No deals in database")
        d = deals[0]
        assert "make" in d
        assert "model" in d
        assert "min_price" in d
        assert "max_price" in d
        assert "savings_eur" in d
        assert "savings_pct" in d
        assert "listing_count" in d

    def test_deal_has_source_info(self):
        deals = scan_deals(limit=5)
        if not deals:
            pytest.skip("No deals in database")
        d = deals[0]
        assert "cheapest_country" in d
        assert "cheapest_provider" in d
        assert "priciest_country" in d
        assert "priciest_provider" in d

    def test_deals_sorted_by_savings(self):
        deals = scan_deals(limit=10)
        if len(deals) < 2:
            pytest.skip("Need at least 2 deals")
        pcts = [float(d["savings_pct"]) for d in deals]
        assert pcts == sorted(pcts, reverse=True)

    def test_savings_positive(self):
        deals = scan_deals(limit=5)
        for d in deals:
            assert float(d["savings_eur"]) > 0

    def test_deal_has_uuid(self):
        deals = scan_deals(limit=5)
        if not deals:
            pytest.skip("No deals in database")
        import uuid
        for d in deals:
            assert "deal_id" in d
            assert d["deal_id"] is not None
            uuid.UUID(d["deal_id"])

    def test_deal_id_persisted_in_db(self):
        deals = scan_deals(limit=3)
        if not deals:
            pytest.skip("No deals in database")
        from db import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            for d in deals:
                row = db.execute(
                    text("SELECT id, make, model FROM carhero.deals WHERE id = :did"),
                    {"did": d["deal_id"]},
                ).fetchone()
                assert row is not None
                assert row.make == d["make"]
                assert row.model == d["model"]
        finally:
            db.close()

    def test_deal_id_stable_on_rescan(self):
        deals1 = scan_deals(limit=3)
        if not deals1:
            pytest.skip("No deals in database")
        deals2 = scan_deals(limit=3)
        ids1 = {d["make"] + d["model"]: d["deal_id"] for d in deals1}
        ids2 = {d["make"] + d["model"]: d["deal_id"] for d in deals2}
        for key in ids1:
            assert ids1[key] == ids2[key], f"Deal ID changed for {key}"


class TestScanLowestPrices:
    def test_returns_list(self):
        cheapest = scan_lowest_prices(limit=5)
        assert isinstance(cheapest, list)

    def test_listing_structure(self):
        cheapest = scan_lowest_prices(limit=5)
        if not cheapest:
            pytest.skip("No listings in database")
        c = cheapest[0]
        assert "make" in c
        assert "model" in c
        assert "price_eur" in c
        assert "country" in c
        assert "provider" in c

    def test_sorted_by_price_asc(self):
        cheapest = scan_lowest_prices(limit=10)
        if len(cheapest) < 2:
            pytest.skip("Need at least 2 listings")
        prices = [float(c["price_eur"]) for c in cheapest]
        assert prices == sorted(prices)

    def test_limit_respected(self):
        result = scan_lowest_prices(limit=3)
        assert len(result) <= 3


class TestDigestHTML:
    @pytest.fixture
    def sample_deals(self):
        return [
            {
                "make": "BMW", "model": "X5", "listing_count": 6,
                "min_price": 42000, "max_price": 48000, "avg_price": 45000,
                "savings_eur": 6000, "savings_pct": 13.3,
                "cheapest_country": "GB", "cheapest_provider": "autotrader",
                "priciest_country": "DE", "priciest_provider": "mobile_de",
            },
        ]

    @pytest.fixture
    def sample_cheapest(self):
        return [
            {
                "make": "Audi", "model": "A4", "variant": "35 TFSI",
                "year": 2020, "mileage_km": 55000, "price_eur": 22000,
                "country": "DE", "provider": "autoscout24",
                "fuel_type": "Petrol", "transmission": "Automatic",
            },
        ]

    def test_html_contains_deal_info(self, sample_deals, sample_cheapest):
        html = build_digest_html(sample_deals, sample_cheapest)
        assert "BMW X5" in html
        assert "42,000" in html
        assert "48,000" in html
        assert "13" in html

    def test_html_contains_cheapest(self, sample_deals, sample_cheapest):
        html = build_digest_html(sample_deals, sample_cheapest)
        assert "Audi A4" in html
        assert "22,000" in html or "22000" in html

    def test_html_contains_header(self, sample_deals, sample_cheapest):
        html = build_digest_html(sample_deals, sample_cheapest)
        assert "CarHero" in html
        assert "Top Price Deals" in html
        assert "Lowest Prices Right Now" in html

    def test_html_contains_period(self, sample_deals, sample_cheapest):
        html = build_digest_html(sample_deals, sample_cheapest)
        assert any(p in html for p in ["Morning", "Afternoon", "Evening"])

    def test_html_contains_links(self, sample_deals, sample_cheapest):
        html = build_digest_html(sample_deals, sample_cheapest)
        assert "carhero.chat/app" in html

    def test_html_uses_deal_id_url(self):
        deals = [{
            "make": "BMW", "model": "X5", "listing_count": 6,
            "min_price": 42000, "max_price": 48000, "avg_price": 45000,
            "savings_eur": 6000, "savings_pct": 13.3,
            "cheapest_country": "GB", "cheapest_provider": "autotrader",
            "priciest_country": "DE", "priciest_provider": "mobile_de",
            "deal_id": "abc12345-1234-5678-9abc-def012345678",
        }]
        html = build_digest_html(deals, [])
        assert "deal_id=abc12345-1234-5678-9abc-def012345678" in html

    def test_html_falls_back_to_deal_param(self):
        deals = [{
            "make": "BMW", "model": "X5", "listing_count": 6,
            "min_price": 42000, "max_price": 48000, "avg_price": 45000,
            "savings_eur": 6000, "savings_pct": 13.3,
            "cheapest_country": "GB", "cheapest_provider": "autotrader",
            "priciest_country": "DE", "priciest_provider": "mobile_de",
        }]
        html = build_digest_html(deals, [])
        assert "deal=BMW" in html

    def test_empty_deals(self, sample_cheapest):
        html = build_digest_html([], sample_cheapest)
        assert "No price differences found" in html

    def test_empty_cheapest(self, sample_deals):
        html = build_digest_html(sample_deals, [])
        assert "No listings yet" in html


class TestDigestText:
    def test_text_contains_deal_info(self):
        deals = [
            {
                "make": "Porsche", "model": "911", "listing_count": 3,
                "savings_eur": 15000, "savings_pct": 18.0,
                "cheapest_country": "EU", "cheapest_provider": "autoscout24",
                "priciest_country": "GB", "priciest_provider": "autotrader",
                "min_price": 75000, "max_price": 90000,
            },
        ]
        cheapest = [
            {"make": "BMW", "model": "3 Series", "year": 2020,
             "mileage_km": 60000, "price_eur": 25000,
             "country": "DE", "provider": "mobile_de"},
        ]
        text = build_digest_text(deals, cheapest)
        assert "Porsche 911" in text
        assert "CarHero" in text
        assert "TOP PRICE DEALS" in text
        assert "LOWEST PRICES" in text

    def test_text_contains_period(self):
        text = build_digest_text([], [])
        assert any(p in text for p in ["Morning", "Afternoon", "Evening"])
