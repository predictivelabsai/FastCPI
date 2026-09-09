"""Recognise CPV and common product identifiers without using an LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CPV = re.compile(r"(?<!\d)(\d{8})(?:-(\d))?(?!\d)")
_GTIN = re.compile(r"(?<!\d)(\d{8}|\d{12}|\d{13}|\d{14})(?!\d)")
_LABELLED_GTIN = re.compile(r"\b(?:gtin|ean|upc)\s*[:#]?\s*(\d{8}|\d{12}|\d{13}|\d{14})\b", re.IGNORECASE)
_LABELLED_SKU = re.compile(
    r"\b(?:sku|mpn|manufacturer(?:'s)?\s+(?:part|product)\s+number|part\s+no\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9._/-]{2,63})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QueryIdentity:
    kind: str
    value: str
    text: str
    check_digit: str | None = None


def classify_query(query: str) -> QueryIdentity:
    """Return the strongest explicit identifier, otherwise a text query."""
    text = " ".join((query or "").split())
    cpv = _CPV.search(text)
    if cpv and (cpv.group(2) is not None or "cpv" in text.lower()):
        return QueryIdentity("cpv", cpv.group(1), text, cpv.group(2))
    labelled = _LABELLED_SKU.search(text)
    if labelled:
        return QueryIdentity("sku", labelled.group(1).upper(), text)
    labelled_gtin = _LABELLED_GTIN.search(text)
    if labelled_gtin:
        return QueryIdentity("gtin", labelled_gtin.group(1), text)
    gtin = _GTIN.fullmatch(text)
    if gtin:
        return QueryIdentity("gtin", gtin.group(1), text)
    return QueryIdentity("text", text, text)


def cpv_prefix(code: str) -> str:
    """Return the significant hierarchy prefix for an eight-digit CPV code."""
    digits = re.sub(r"\D", "", code or "")[:8]
    if len(digits) != 8:
        raise ValueError("CPV code must contain eight digits")
    return digits.rstrip("0") or digits[:2]
