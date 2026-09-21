"""Versioned rules deciding whether an observed offer may be ranked.

The extraction pipeline deliberately retains imperfect evidence.  This module
keeps that evidence visible while preventing materially incompatible offers
from influencing supplier variance statistics.
"""

from __future__ import annotations

from typing import Any


POLICY_VERSION = "offer-comparability-v1"
MINIMUM_RANKING_CONFIDENCE = 0.65

_COMMERCIAL_ITEM_UNITS = {"each", "item", "unit", "pack"}

_REASON_MESSAGES = {
    "missing_comparable_price": "No normalised comparable price is available.",
    "non_eur_comparable_currency": "The comparable price is not expressed in EUR.",
    "non_positive_comparable_price": "The comparable price must be positive.",
    "unit_not_normalized": "The source unit could not be normalised.",
    "unit_mismatch": "The observed unit is incompatible with the catalogue item.",
    "low_extraction_confidence": "Extraction confidence is below the ranking threshold.",
    "market_conflict": "Source geography conflicts with the selected market.",
    "identifier_mismatch": "The observed product identifier conflicts with the catalogue item.",
    "vat_status_unknown": "VAT treatment is not confirmed.",
    "delivery_not_confirmed": "Delivery cost inclusion is not confirmed.",
    "market_delivery_unverified": "Delivery to the selected market is not independently verified.",
    "identity_not_verified": "The catalogue identifier was not found in the source evidence.",
    "supplier_entity_unresolved": "The legal supplier entity is not resolved.",
}


def _reason(code: str) -> dict[str, str]:
    return {"code": code, "message": _REASON_MESSAGES[code]}


def _normalise_identifier(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _units_compatible(observed: str, canonical: str) -> bool:
    if observed == canonical:
        return True
    return observed in _COMMERCIAL_ITEM_UNITS and canonical in _COMMERCIAL_ITEM_UNITS


def assess_offer(offer: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, machine-readable ranking assessment for one offer."""
    exclusions: list[str] = []
    caveats: list[str] = []

    amount = offer.get("amount_comparable")
    if amount is None:
        exclusions.append("missing_comparable_price")
    else:
        try:
            if float(amount) <= 0:
                exclusions.append("non_positive_comparable_price")
        except (TypeError, ValueError):
            exclusions.append("missing_comparable_price")

    if amount is not None and offer.get("currency_comparable") != "EUR":
        exclusions.append("non_eur_comparable_currency")

    observed_unit = str(offer.get("unit_comparable") or "").strip().lower()
    canonical_unit = str(offer.get("item_canonical_unit") or "").strip().lower()
    if not observed_unit:
        exclusions.append("unit_not_normalized")
    elif canonical_unit and not _units_compatible(observed_unit, canonical_unit):
        exclusions.append("unit_mismatch")

    try:
        confidence = float(offer.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    if confidence < MINIMUM_RANKING_CONFIDENCE:
        exclusions.append("low_extraction_confidence")

    warnings = [str(value).lower() for value in (offer.get("warnings") or [])]
    if any("unrecognised unit" in warning for warning in warnings):
        exclusions.append("unit_not_normalized")
    if any("conflicts with requested market" in warning for warning in warnings):
        exclusions.append("market_conflict")

    terms = offer.get("terms") if isinstance(offer.get("terms"), dict) else {}
    market_status = terms.get("market_status")
    if market_status == "country-domain-conflict":
        exclusions.append("market_conflict")
    elif market_status != "country-domain-match":
        caveats.append("market_delivery_unverified")

    expected = offer.get("item_identifiers") if isinstance(offer.get("item_identifiers"), list) else []
    expected_values = {
        _normalise_identifier(row.get("value"))
        for row in expected if isinstance(row, dict) and row.get("value")
    }
    observed_values = {
        _normalise_identifier(terms.get(key)) for key in ("sku", "mpn", "gtin") if terms.get(key)
    }
    if expected_values:
        if observed_values and expected_values.isdisjoint(observed_values):
            exclusions.append("identifier_mismatch")
        elif not observed_values:
            caveats.append("identity_not_verified")

    if offer.get("vat_included") is None:
        caveats.append("vat_status_unknown")
    if offer.get("shipping_included") is not True:
        caveats.append("delivery_not_confirmed")
    if not (offer.get("seller_name") or "").strip():
        caveats.append("supplier_entity_unresolved")

    exclusions = list(dict.fromkeys(exclusions))
    caveats = [code for code in dict.fromkeys(caveats) if code not in exclusions]
    eligible = not exclusions
    status = "eligible_with_caveats" if eligible and caveats else "eligible" if eligible else "excluded"
    basis = None
    if amount is not None and observed_unit:
        basis = f"EUR/{observed_unit}"
    return {
        "policy_version": POLICY_VERSION,
        "ranking_eligible": eligible,
        "status": status,
        "comparable_basis": basis,
        "exclusion_reasons": [_reason(code) for code in exclusions],
        "caveats": [_reason(code) for code in caveats],
    }


def ranking_eligible(offer: dict[str, Any]) -> bool:
    assessment = offer.get("comparability")
    return not isinstance(assessment, dict) or assessment.get("ranking_eligible", True) is True
