"""Tests for tools/deals.py -- price arbitrage tool and artifact output."""

import json

import pytest

from tools.deals import _find_deals, price_arbitrage, COUNTRY_LABELS, PROVIDER_LABELS


class TestDealFinderTool:
    def test_tool_metadata(self):
        assert price_arbitrage.name == "price_arbitrage"
        assert "arbitrage" in price_arbitrage.description.lower()

    def test_returns_string(self):
        result = _find_deals()
        assert isinstance(result, str)

    def test_with_make_filter(self):
        result = _find_deals(make="BMW")
        assert isinstance(result, str)

    def test_with_model_filter(self):
        result = _find_deals(make="BMW", model="X5")
        assert isinstance(result, str)

    def test_no_results_message(self):
        result = _find_deals(make="NonexistentBrand12345")
        assert "No price arbitrage" in result

    def test_limit_parameter(self):
        result = _find_deals(limit=2)
        assert isinstance(result, str)


class TestDealArtifactPayload:
    @pytest.fixture
    def artifact_payload(self):
        result = _find_deals()
        if "__ARTIFACT__" not in result:
            pytest.skip("No deals found in database to test artifact")
        art_start = result.index("__ARTIFACT__") + len("__ARTIFACT__")
        art_end = result.index("\n\n", art_start)
        return json.loads(result[art_start:art_end])

    def test_artifact_kind(self, artifact_payload):
        assert artifact_payload["kind"] == "deals"

    def test_artifact_has_title(self, artifact_payload):
        assert "title" in artifact_payload
        assert "Price Arbitrage" in artifact_payload["title"]

    def test_artifact_has_deals_list(self, artifact_payload):
        assert "deals" in artifact_payload
        assert isinstance(artifact_payload["deals"], list)
        assert len(artifact_payload["deals"]) > 0

    def test_deal_structure(self, artifact_payload):
        deal = artifact_payload["deals"][0]
        assert "make" in deal
        assert "model" in deal
        assert "savings_eur" in deal
        assert "savings_pct" in deal
        assert "cheapest" in deal
        assert "priciest" in deal

    def test_deal_has_uuid(self, artifact_payload):
        import uuid
        deal = artifact_payload["deals"][0]
        assert "deal_id" in deal
        assert deal["deal_id"] is not None
        uuid.UUID(deal["deal_id"])

    def test_deal_listing_has_url(self, artifact_payload):
        deal = artifact_payload["deals"][0]
        assert "url" in deal["cheapest"]
        assert "url" in deal["priciest"]

    def test_deal_listing_has_price(self, artifact_payload):
        deal = artifact_payload["deals"][0]
        assert deal["cheapest"]["price_eur"] > 0
        assert deal["priciest"]["price_eur"] > 0
        assert deal["priciest"]["price_eur"] > deal["cheapest"]["price_eur"]

    def test_deal_listing_has_source(self, artifact_payload):
        deal = artifact_payload["deals"][0]
        for side in ["cheapest", "priciest"]:
            assert "country" in deal[side]
            assert "country_label" in deal[side]
            assert "provider" in deal[side]
            assert "provider_label" in deal[side]

    def test_deal_listing_has_specs(self, artifact_payload):
        deal = artifact_payload["deals"][0]
        for side in ["cheapest", "priciest"]:
            assert "year" in deal[side]
            assert "fuel_type" in deal[side]
            assert "transmission" in deal[side]

    def test_savings_consistent(self, artifact_payload):
        deal = artifact_payload["deals"][0]
        expected = deal["priciest"]["price_eur"] - deal["cheapest"]["price_eur"]
        assert deal["savings_eur"] == expected


class TestLabelMaps:
    def test_all_countries_mapped(self):
        for code in ["GB", "DE", "EU"]:
            assert code in COUNTRY_LABELS

    def test_all_providers_mapped(self):
        for p in ["autotrader", "mobile_de", "autoscout24", "autohero", "theparking"]:
            assert p in PROVIDER_LABELS
