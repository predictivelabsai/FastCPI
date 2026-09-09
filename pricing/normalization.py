"""Comparable-price rules for procurement offers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

UNIT_ALIASES = {
    "ea": "each", "each": "each", "item": "each", "unit": "each", "pc": "each", "pcs": "each",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg", "g": "g",
    "l": "l", "litre": "l", "liter": "l", "ml": "ml",
    "hour": "hour", "hr": "hour", "h": "hour", "day": "day", "month": "month", "year": "year",
}


@dataclass(frozen=True)
class NormalizedPrice:
    original_amount: Decimal
    comparable_amount: Decimal | None
    currency: str
    original_unit: str
    comparable_unit: str | None
    vat_included: bool | None
    shipping_included: bool | None
    warnings: tuple[str, ...]


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("Price must be a positive number") from exc


def normalize_price(
    amount: object,
    currency: str,
    *,
    quantity: object = 1,
    unit: str = "each",
    vat_included: bool | None = None,
    shipping_amount: object | None = None,
    shipping_included: bool | None = None,
) -> NormalizedPrice:
    """Normalize an offer to a per-unit amount in its source currency.

    Currency conversion is intentionally a separate, dated operation. An offer
    with unknown VAT or delivery remains usable but is explicitly flagged.
    """
    price = _decimal(amount)
    qty = _decimal(quantity)
    if price <= 0 or qty <= 0:
        raise ValueError("Price and quantity must be positive")

    original_unit = (unit or "each").strip().lower()
    canonical_unit = UNIT_ALIASES.get(original_unit)
    warnings: list[str] = []
    if not canonical_unit:
        warnings.append(f"unrecognised unit: {original_unit}")

    landed = price
    if shipping_amount is not None:
        landed += _decimal(shipping_amount)
        shipping_included = True
    elif shipping_included is not True:
        warnings.append("delivery not confirmed")
    if vat_included is None:
        warnings.append("VAT status unknown")

    comparable = None
    if canonical_unit:
        factor = Decimal("1")
        output_unit = canonical_unit
        if canonical_unit == "g":
            factor, output_unit = Decimal("0.001"), "kg"
        elif canonical_unit == "ml":
            factor, output_unit = Decimal("0.001"), "l"
        comparable = (landed / (qty * factor)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    else:
        output_unit = None

    return NormalizedPrice(
        original_amount=price,
        comparable_amount=comparable,
        currency=(currency or "EUR").upper(),
        original_unit=original_unit,
        comparable_unit=output_unit,
        vat_included=vat_included,
        shipping_included=shipping_included,
        warnings=tuple(warnings),
    )
