"""Dated EUR conversion using official ECB reference rates."""

from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import httpx

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_cache: tuple[float, date, dict[str, Decimal]] | None = None
_lock = threading.Lock()


def ecb_rates(*, max_age_seconds: int = 21600) -> tuple[date, dict[str, Decimal]]:
    global _cache
    with _lock:
        if _cache and time.time() - _cache[0] < max_age_seconds:
            return _cache[1], _cache[2]
        response = httpx.get(ECB_DAILY_URL, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "FastCPI/1.0 (+https://cpi.fastsme.com)"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        dated = next((node for node in root.iter() if node.attrib.get("time")), None)
        if dated is None:
            raise ValueError("ECB response did not contain a dated rate set")
        rate_date = date.fromisoformat(dated.attrib["time"])
        rates = {"EUR": Decimal("1")}
        for node in dated:
            currency, rate = node.attrib.get("currency"), node.attrib.get("rate")
            if currency and rate:
                rates[currency] = Decimal(rate)
        _cache = (time.time(), rate_date, rates)
        return rate_date, rates


def to_eur(amount: Decimal, currency: str) -> tuple[Decimal, Decimal, date]:
    rate_date, rates = ecb_rates()
    code = currency.upper()
    if code not in rates:
        raise ValueError(f"ECB has no EUR reference rate for {code}")
    eur_per_source = Decimal("1") / rates[code]
    return amount * eur_per_source, eur_per_source, rate_date
