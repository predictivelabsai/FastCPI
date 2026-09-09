"""MVP market and language configuration."""

from __future__ import annotations

MARKETS: dict[str, dict[str, str]] = {
    "DE": {"name": "Germany", "language": "de", "currency": "EUR"},
    "DK": {"name": "Denmark", "language": "da", "currency": "DKK"},
    "EE": {"name": "Estonia", "language": "et", "currency": "EUR"},
    "FI": {"name": "Finland", "language": "fi", "currency": "EUR"},
    "FR": {"name": "France", "language": "fr", "currency": "EUR"},
    "LT": {"name": "Lithuania", "language": "lt", "currency": "EUR"},
    "LV": {"name": "Latvia", "language": "lv", "currency": "EUR"},
    "NL": {"name": "Netherlands", "language": "nl", "currency": "EUR"},
    "PL": {"name": "Poland", "language": "pl", "currency": "PLN"},
    "SE": {"name": "Sweden", "language": "sv", "currency": "SEK"},
}


def normalize_market(value: str | None) -> str:
    code = (value or "").strip().upper()
    if code not in MARKETS:
        raise ValueError(f"Unsupported market {value!r}; use one of {', '.join(MARKETS)}")
    return code
