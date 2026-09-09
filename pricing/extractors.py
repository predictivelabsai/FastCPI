"""Evidence-preserving price extraction from discovered web pages."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx


@dataclass
class ExtractedOffer:
    url: str
    title: str = ""
    seller: str = ""
    amount: float | None = None
    currency: str = ""
    availability: str = ""
    sku: str = ""
    gtin: str = ""
    unit: str = "each"
    quantity: float = 1
    vat_included: bool | None = None
    shipping_included: bool | None = None
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: str = ""
    content_hash: str = ""
    extraction_method: str = ""
    confidence: float = 0.0


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.json_ld: list[str] = []
        self._json_buffer: list[str] | None = None
        self.meta: dict[str, str] = {}
        self.itemprops: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        values = {k.lower(): v for k, v in attrs if k and v}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "script" and values.get("type", "").lower() == "application/ld+json":
            self._json_buffer = []
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key and values.get("content"):
                self.meta[key] = values["content"]
        itemprop = values.get("itemprop", "")
        if itemprop and values.get("content"):
            for key in itemprop.lower().split():
                self.itemprops.setdefault(key, []).append(values["content"])

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() == "script" and self._json_buffer is not None:
            self.json_ld.append("".join(self._json_buffer))
            self._json_buffer = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._json_buffer is not None:
            self._json_buffer.append(data)


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _number(value: object) -> float:
    raw = re.sub(r"[^0-9,.-]", "", str(value)).strip()
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    return float(raw)


def _schema_offer(url: str, parser: _PageParser, body: str) -> ExtractedOffer | None:
    for block in parser.json_ld:
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = list(_walk_json(data))
        products = [n for n in nodes if str(n.get("@type", "")).lower() in {"product", "service"}]
        offers = [n for n in nodes if "offer" in str(n.get("@type", "")).lower()]
        for product in products or [{}]:
            offer_value = product.get("offers")
            candidates = list(_walk_json(offer_value)) if offer_value else offers
            for offer in candidates:
                amount = offer.get("price") or offer.get("lowPrice")
                currency = offer.get("priceCurrency")
                if amount is None or not currency:
                    continue
                seller = offer.get("seller") or product.get("brand") or ""
                if isinstance(seller, dict):
                    seller = seller.get("name", "")
                evidence = json.dumps({"product": product, "offer": offer}, ensure_ascii=False)[:4000]
                try:
                    numeric = _number(amount)
                except ValueError:
                    continue
                return ExtractedOffer(
                    url=url,
                    title=str(product.get("name") or parser.title).strip(),
                    seller=str(seller),
                    amount=numeric,
                    currency=str(currency).upper(),
                    availability=str(offer.get("availability", "")).rsplit("/", 1)[-1],
                    sku=str(product.get("sku") or product.get("mpn") or ""),
                    gtin=str(product.get("gtin13") or product.get("gtin14") or product.get("gtin") or ""),
                    evidence=evidence,
                    content_hash=hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
                    extraction_method="json-ld",
                    confidence=0.95,
                )
    return None


def _metadata_offer(url: str, parser: _PageParser, body: str) -> ExtractedOffer | None:
    amount = parser.meta.get("product:price:amount") or parser.meta.get("og:price:amount")
    currency = parser.meta.get("product:price:currency") or parser.meta.get("og:price:currency")
    if not amount or not currency:
        return None
    try:
        numeric = _number(amount)
    except ValueError:
        return None
    evidence = json.dumps({k: v for k, v in parser.meta.items() if "price" in k or k in {"og:title", "og:site_name"}})
    return ExtractedOffer(
        url=url,
        title=parser.meta.get("og:title", parser.title).strip(),
        seller=parser.meta.get("og:site_name", urlparse(url).netloc),
        amount=numeric,
        currency=currency.upper(),
        evidence=evidence,
        content_hash=hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
        extraction_method="open-graph",
        confidence=0.8,
    )


def _microdata_offer(url: str, parser: _PageParser, body: str) -> ExtractedOffer | None:
    prices = parser.itemprops.get("price", [])
    currencies = parser.itemprops.get("pricecurrency", [])
    if not prices or not currencies:
        return None
    try:
        amount = _number(prices[0])
    except ValueError:
        return None
    title = (parser.itemprops.get("name") or [parser.title])[0].strip()
    sku = (parser.itemprops.get("sku") or [""])[0].strip()
    evidence = json.dumps({
        "name": title,
        "price": prices[0],
        "priceCurrency": currencies[0],
        "sku": sku,
    }, ensure_ascii=False)
    return ExtractedOffer(
        url=url,
        title=title or parser.title.strip(),
        seller=urlparse(url).netloc,
        amount=amount,
        currency=currencies[0].upper(),
        sku=sku,
        evidence=evidence,
        content_hash=hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
        extraction_method="microdata",
        confidence=0.88,
    )


def _domain_offer(url: str, parser: _PageParser, body: str) -> ExtractedOffer | None:
    """Adapters justified by the recurring-domain pilot."""
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    if domain == "staver.eu":
        visible = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*€\s*/\s*(?:hour|h)\b", visible, re.I)
        if match:
            start, end = max(0, match.start() - 160), min(len(visible), match.end() + 160)
            return ExtractedOffer(
                url=url,
                title=parser.title.strip(),
                seller="STAVER",
                amount=_number(match.group(1)),
                currency="EUR",
                unit="hour",
                evidence=visible[start:end],
                content_hash=hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
                extraction_method="staver-hourly-rate",
                confidence=0.85,
            )
    return None


def _visible_hourly_offer(url: str, parser: _PageParser, body: str) -> ExtractedOffer | None:
    visible = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
    patterns = (
        (r"€\s*(\d+(?:[.,]\d+)?)\s*(?:/|per)\s*(?:hour|hr|h)\b", "EUR"),
        (r"(\d+(?:[.,]\d+)?)\s*€\s*(?:/|per)\s*(?:hour|hr|h)\b", "EUR"),
        (r"(\d+(?:[.,]\d+)?)\s*(?:SEK|kr)\s*(?:/|per)\s*(?:hour|hr|h)\b", "SEK"),
    )
    for pattern, currency in patterns:
        match = re.search(pattern, visible, re.I)
        if not match:
            continue
        start, end = max(0, match.start() - 160), min(len(visible), match.end() + 160)
        return ExtractedOffer(
            url=url,
            title=parser.title.strip(),
            seller=urlparse(url).netloc,
            amount=_number(match.group(1)),
            currency=currency,
            unit="hour",
            evidence=visible[start:end],
            content_hash=hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
            extraction_method="visible-hourly-rate",
            confidence=0.72,
        )
    return None


def extract_html(url: str, body: str) -> ExtractedOffer | None:
    parser = _PageParser()
    parser.feed(body)
    return (
        _schema_offer(url, parser, body)
        or _domain_offer(url, parser, body)
        or _microdata_offer(url, parser, body)
        or _metadata_offer(url, parser, body)
        or _visible_hourly_offer(url, parser, body)
    )


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) source URLs are allowed")
    if parsed.port and parsed.port not in {80, 443}:
        raise ValueError("Non-standard source URL ports are not allowed")
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Source hostname could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Private or non-global source addresses are not allowed")
    return url


def _get_with_safe_redirects(
    client: httpx.Client,
    url: str,
    *,
    max_redirects: int = 5,
) -> httpx.Response:
    """Validate the initial URL and every redirect target before connecting."""
    current = validate_public_url(url)
    for _ in range(max_redirects + 1):
        response = client.get(current, follow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = validate_public_url(urljoin(current, location))
    raise ValueError("Source page exceeded the redirect limit")


def fetch_and_extract(url: str, *, timeout: float = 15.0) -> ExtractedOffer | None:
    """Fetch a public page and extract its strongest structured offer evidence."""
    validate_public_url(url)
    headers = {"User-Agent": "FastCPI/1.0 price-observation research (+https://cpi.fastsme.com)"}
    with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers) as client:
        robots_url = urljoin(url, "/robots.txt")
        try:
            robots_response = _get_with_safe_redirects(client, robots_url)
            if robots_response.status_code == 200:
                robots = RobotFileParser()
                robots.set_url(robots_url)
                robots.parse(robots_response.text.splitlines())
                if not robots.can_fetch(headers["User-Agent"], url):
                    raise PermissionError("Source robots policy disallows this page")
        except PermissionError:
            raise
        except httpx.HTTPError:
            pass
        response = _get_with_safe_redirects(client, url)
        response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ValueError("Source page exceeds the 5 MB extraction limit")
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        return None
    return extract_html(str(response.url), response.text)
