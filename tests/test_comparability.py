from datetime import datetime, timezone

from pricing.analytics import summarize_offers
from pricing.comparability import POLICY_VERSION, assess_offer


def _offer(**changes):
    offer = {
        "market": "DE",
        "amount_comparable": 84.5,
        "currency_comparable": "EUR",
        "unit_comparable": "each",
        "item_canonical_unit": "each",
        "confidence": 0.9,
        "vat_included": True,
        "shipping_included": True,
        "seller_name": "Example Supplies GmbH",
        "source_domain": "example.de",
        "supplier": "Example Supplies GmbH",
        "terms": {"market_status": "country-domain-match", "sku": "W2210A"},
        "item_identifiers": [{"type": "sku", "value": "W2210A", "issuer": "HP"}],
        "warnings": [],
        "captured_at": datetime(2026, 9, 21, tzinfo=timezone.utc),
    }
    offer.update(changes)
    return offer


def test_matching_offer_is_eligible_under_versioned_policy():
    assessment = assess_offer(_offer())
    assert assessment["policy_version"] == POLICY_VERSION
    assert assessment["status"] == "eligible"
    assert assessment["ranking_eligible"] is True
    assert assessment["exclusion_reasons"] == []
    assert assessment["caveats"] == []


def test_unknown_commercial_terms_are_visible_caveats_not_silent_assumptions():
    assessment = assess_offer(_offer(
        vat_included=None,
        shipping_included=None,
        terms={"market_status": "unverified-domain", "sku": "W2210A"},
    ))
    codes = {row["code"] for row in assessment["caveats"]}
    assert assessment["status"] == "eligible_with_caveats"
    assert assessment["ranking_eligible"] is True
    assert codes == {"vat_status_unknown", "delivery_not_confirmed", "market_delivery_unverified"}


def test_low_confidence_and_identifier_mismatch_exclude_offer_from_ranking():
    offer = _offer(confidence=0.4, terms={"market_status": "country-domain-match", "sku": "W2211A"})
    offer["comparability"] = assess_offer(offer)
    codes = {row["code"] for row in offer["comparability"]["exclusion_reasons"]}
    assert codes == {"low_extraction_confidence", "identifier_mismatch"}
    assert offer["comparability"]["ranking_eligible"] is False
    assert summarize_offers([offer])["offer_count"] == 0


def test_catalogue_pack_and_single_commercial_item_units_are_compatible():
    assessment = assess_offer(_offer(item_canonical_unit="pack", unit_comparable="each"))
    assert assessment["ranking_eligible"] is True


def test_incompatible_service_unit_is_excluded():
    assessment = assess_offer(_offer(item_canonical_unit="hour", unit_comparable="each"))
    assert [row["code"] for row in assessment["exclusion_reasons"]] == ["unit_mismatch"]


def test_unnormalised_observation_is_retained_but_excluded():
    assessment = assess_offer(_offer(amount_comparable=None, currency_comparable=None, unit_comparable=None))
    codes = {row["code"] for row in assessment["exclusion_reasons"]}
    assert assessment["ranking_eligible"] is False
    assert codes == {"missing_comparable_price", "unit_not_normalized"}
