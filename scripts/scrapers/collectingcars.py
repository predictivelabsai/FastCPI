"""Collecting Cars scraper — 24/7 online car auctions.

Collecting Cars is an auction platform for enthusiast/collector cars across
Europe, UK, Australia, and globally. Listings include current bid price,
time remaining, LHD/RHD, and location.

URL patterns:
    Browse: https://collectingcars.com/buy?refinementList[listingStage]=live
    Detail: https://collectingcars.com/for-sale/{slug}

The browse page shows ~40 live auctions per page via Algolia InstantSearch,
paginated across ~6 pages (~220 total). We use a fresh browser per page to
bypass Cloudflare rate-limiting and extract title, price, currency, LHD/RHD,
and location from the cards.
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    setup_browser, dismiss_cookies, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate, GBP_TO_EUR,
)

log = logging.getLogger(__name__)

BASE_URL = "https://collectingcars.com"
BROWSE_URL = f"{BASE_URL}/buy?refinementList%5BlistingStage%5D=live"

CURRENCY_RATES = {
    "EUR": 1.0,
    "GBP": GBP_TO_EUR,
    "CHF": 1.05,
    "A$": 0.60,
    "NZ$": 0.55,
    "US$": 0.92,
}

COUNTRY_MAP = {
    "united kingdom": "GB",
    "france": "FR",
    "germany": "DE",
    "italy": "IT",
    "spain": "ES",
    "netherlands": "NL",
    "belgium": "BE",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "austria": "AT",
    "switzerland": "CH",
    "portugal": "PT",
    "ireland": "IE",
    "poland": "PL",
    "czechia": "CZ",
    "czech republic": "CZ",
    "finland": "FI",
    "romania": "RO",
    "slovenia": "SI",
    "andorra": "AD",
    "australia": "AU",
    "new zealand": "NZ",
    "japan": "JP",
    "hong kong": "HK",
    "united arab emirates": "AE",
}


def _extract_browse_listings(page) -> list[dict]:
    """Extract all listing cards from the /buy browse page.

    Uses Algolia InstantSearch `ais-InfiniteHits-item` elements when available,
    falling back to anchor-based extraction.
    """
    return page.evaluate(r"""() => {
        // Primary: use Algolia InstantSearch hit items
        let cards = [...document.querySelectorAll('.ais-InfiniteHits-item')];
        // Fallback: find all for-sale links and walk up
        if (!cards.length) {
            const links = document.querySelectorAll('a[href*="/for-sale/"]');
            const seen = new Set();
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                if (seen.has(href)) continue;
                seen.add(href);
                const card = link.closest('li') || link.closest('button') || link.parentElement?.parentElement?.parentElement;
                if (card) cards.push(card);
            }
        }

        const seen = new Set();
        const results = [];

        for (const card of cards) {
            const link = card.querySelector('a[href*="/for-sale/"]');
            if (!link) continue;
            const href = link.getAttribute('href') || '';
            if (seen.has(href)) continue;
            seen.add(href);

            const allText = card.innerText || card.textContent || '';

            // Title from img alt (primary image, not flag)
            const imgEl = card.querySelector('img[alt]');
            let title = '';
            if (imgEl && imgEl.alt && !imgEl.src.includes('flagcdn')) {
                title = imgEl.alt.trim();
            }
            if (!title) {
                const pLink = card.querySelector('p a[href*="/for-sale/"]');
                title = pLink ? pLink.textContent.trim() : '';
            }
            if (!title) continue;

            const imageUrl = imgEl ? (imgEl.getAttribute('src') || '') : '';

            // Price — find currency symbols
            const priceMatch = allText.match(/(€|£|CHF\s?|A\$|NZ\$|US\$)\s?[\d,]+/);
            const priceText = priceMatch ? priceMatch[0].trim() : '';

            // Steering side
            const steeringMatch = allText.match(/\b(LHD|RHD)\b/);
            const steering = steeringMatch ? steeringMatch[1] : '';

            // Location — find country flag img (flagcdn.com) + nearby city text
            let location = '';
            const flagImg = card.querySelector('img[src*="flagcdn"]');
            if (flagImg) {
                const country = flagImg.alt.trim();
                const parent = flagImg.closest('div') || flagImg.parentElement;
                const cityEl = parent ? (parent.nextElementSibling || parent.previousElementSibling) : null;
                const city = cityEl ? cityEl.textContent.trim() : '';
                location = city ? city + ', ' + country : country;
            }

            const typeMatch = allText.match(/\b(Auction|Buy Now|Boosted)\b/);
            const listingType = typeMatch ? typeMatch[1] : 'Auction';
            const noReserve = allText.includes('No Reserve');

            results.push({
                title,
                price_text: priceText,
                steering,
                location,
                listing_type: listingType,
                no_reserve: noReserve,
                source_url: href.startsWith('http') ? href : 'https://collectingcars.com' + href,
                image_urls: (imageUrl && !imageUrl.includes('data:')) ? [imageUrl] : [],
            });
        }
        return results;
    }""")


def _extract_detail_specs(page) -> dict:
    """Extract detailed specs from a listing detail page.

    NOTE: Collecting Cars uses Cloudflare protection that blocks sequential
    detail page visits after the browse page. This function works standalone
    but returns {} during scraper runs. Kept for future use if bypass found.
    """
    try:
        page.wait_for_selector('[class*="listingOverview"]', timeout=5000)
    except Exception:
        return {}

    return page.evaluate(r"""() => {
        const specs = {};
        const container = document.querySelector('[class*="listingOverview"][class*="container"]');
        if (container) {
            for (const row of container.children) {
                const kids = [...row.children];
                if (kids.length >= 2) {
                    const label = kids[0].textContent.trim().toLowerCase();
                    const value = kids[1].textContent.trim();
                    if (label && value) specs[label] = value;
                }
            }
        }
        return specs;
    }""")


def _parse_title(title: str) -> tuple[int | None, str, str, str]:
    """Parse title like '1999 Aston Martin V8 Vantage V600' into (year, make, model, variant)."""
    m = re.match(r"^(\d{4})\s+(.+)$", title.strip())
    year = None
    rest = title.strip()
    if m:
        year = int(m.group(1))
        rest = m.group(2)

    known_makes = {
        "aston martin", "alfa romeo", "land rover", "mercedes-benz",
        "rolls-royce",
    }
    make = ""
    remainder = rest
    rest_lower = rest.lower()
    for km in sorted(known_makes, key=len, reverse=True):
        if rest_lower.startswith(km):
            make = rest[:len(km)]
            remainder = rest[len(km):].strip()
            break
    if not make:
        parts = rest.split(" ", 1)
        make = parts[0]
        remainder = parts[1] if len(parts) > 1 else ""

    parts = remainder.split(" ", 1)
    model = parts[0] if parts else remainder
    variant = parts[1] if len(parts) > 1 else ""

    return year, make, model, variant


def _parse_price_and_currency(text: str) -> tuple[float, str, float]:
    """Parse price text like '€183,000' or '£85,000' to (price_original, currency, price_eur)."""
    if not text:
        return 0, "EUR", 0

    currency = "EUR"
    if text.startswith("£"):
        currency = "GBP"
    elif text.startswith("CHF"):
        currency = "CHF"
    elif text.startswith("A$"):
        currency = "AUD"
    elif text.startswith("NZ$"):
        currency = "NZD"
    elif text.startswith("US$"):
        currency = "USD"

    cleaned = re.sub(r"[€£A-Za-z$]", "", text).strip().replace(",", "")
    try:
        price = float(cleaned)
    except ValueError:
        return 0, currency, 0

    rate = CURRENCY_RATES.get(currency, CURRENCY_RATES.get(text[:2], 1.0))
    if currency == "AUD":
        rate = 0.60
    elif currency == "NZD":
        rate = 0.55
    elif currency == "USD":
        rate = 0.92

    price_eur = round(price * rate, 2)
    return price, currency, price_eur


def _parse_location(location_text: str) -> tuple[str | None, str | None]:
    """Parse location like 'Colmar, France' to (city, country_code)."""
    if not location_text:
        return None, None
    parts = [p.strip() for p in location_text.split(",")]
    if len(parts) >= 2:
        city = parts[0]
        country_raw = parts[-1].strip().lower()
        country = COUNTRY_MAP.get(country_raw, country_raw.upper()[:2] if country_raw else None)
        return city, country
    single = location_text.strip().lower()
    country = COUNTRY_MAP.get(single)
    if country:
        return None, country
    return location_text.strip(), None


def _is_target_brand(title: str) -> bool:
    """Check if the listing title contains one of our tracked brands."""
    title_lower = title.lower()
    for brand in PREMIUM_BRANDS:
        if brand.lower() in title_lower:
            return True
    return False


def _scrape_page(page_num: int, headless: bool) -> list[dict]:
    """Scrape a single browse page. Uses a fresh browser to bypass Cloudflare."""
    pw, browser, ctx, page = setup_browser(headless=headless)
    try:
        url = BROWSE_URL + (f"&page={page_num}" if page_num > 1 else "")
        safe_navigate(page, url, timeout=30000)
        time.sleep(3)
        dismiss_cookies(page)
        time.sleep(1)

        if "Just a moment" in (page.title() or ""):
            log.warning("Cloudflare blocked page %d", page_num)
            return []

        return _extract_browse_listings(page)
    finally:
        browser.close()
        pw.stop()


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Collecting Cars live auction listings.

    Paginates through all browse pages (fresh browser per page to bypass
    Cloudflare). Each page has ~40 listings; typically 6 pages total (~220).

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to filter, or None for all tracked brands.
    """
    listings = load_checkpoint("collectingcars")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    raw_items = []
    max_pages = 10

    for pg in range(1, max_pages + 1):
        log.info("Fetching browse page %d...", pg)
        page_items = _scrape_page(pg, headless)
        log.info("Page %d: %d listing cards", pg, len(page_items))

        if not page_items:
            break
        raw_items.extend(page_items)
        time.sleep(2)

    log.info("Total listing cards across all pages: %d", len(raw_items))

    new_count = 0
    brand_counts = {}

    for raw in raw_items:
        title = raw.get("title", "")

        if "Number Plate" in title or "number plate" in title.lower():
            continue
        if not re.match(r"^\d{4}\s", title):
            continue

        if brand:
            if brand.lower() not in title.lower():
                continue
        elif not _is_target_brand(title):
            continue

        src = raw.get("source_url", "")
        if src in seen_urls:
            continue

        year, make, model, variant = _parse_title(title)
        price_original, currency, price_eur = _parse_price_and_currency(raw.get("price_text", ""))
        city, country = _parse_location(raw.get("location", ""))
        steering = raw.get("steering", "")

        make_lower = make.lower()
        matched_brand = None
        for b in PREMIUM_BRANDS:
            if b.lower() == make_lower or b.lower() in make_lower:
                matched_brand = b
                break
        if not matched_brand:
            matched_brand = make

        if limit:
            bc = brand_counts.get(matched_brand, 0)
            if bc >= limit:
                continue

        listing = {
            "provider": "collectingcars",
            "make": matched_brand,
            "model": model,
            "variant": variant or None,
            "price": price_original,
            "price_eur": price_eur,
            "price_original": price_original,
            "currency": currency,
            "year": year,
            "mileage_km": None,
            "fuel_type": None,
            "transmission": None,
            "body_type": None,
            "power_hp": None,
            "power_kw": None,
            "country": country,
            "city": city,
            "seller_type": "auction",
            "seller_name": "Collecting Cars",
            "steering_side": steering or None,
            "source_url": src,
            "image_urls": raw.get("image_urls") or [],
            "condition": "used",
            "listing_type": raw.get("listing_type", "Auction"),
            "no_reserve": raw.get("no_reserve", False),
        }
        listings.append(listing)
        seen_urls.add(src)
        new_count += 1
        brand_counts[matched_brand] = brand_counts.get(matched_brand, 0) + 1

    listings = deduplicate(listings)
    save_checkpoint(listings, "collectingcars")
    log.info("Collecting Cars scrape complete: %d listings total (%d new)", len(listings), new_count)

    return listings
