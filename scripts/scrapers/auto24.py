"""Auto24 scraper — Baltic car marketplace (Estonia, Latvia, Lithuania).

All three sites (auto24.ee, auto24.lt, auto24.lv) share the same BCG
platform with identical DOM structure. Brand filtering via numeric IDs,
pagination via offset parameter `ak`.

URL pattern:
    https://www.auto24.ee/kasutatud/nimekiri.php?b=4&a=100&ae=2&af=50
    Pagination: &ak=50, &ak=100, ...

Listing detail: /soidukid/<id>
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    parse_price, parse_mileage,
    setup_browser, dismiss_cookies, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate,
)

log = logging.getLogger(__name__)

from utils.config import get_brand_slugs
BRAND_IDS = get_brand_slugs("auto24")

SITES = {
    "EE": {"domain": "www.auto24.ee", "country": "EE", "provider": "auto24_ee"},
    "LT": {"domain": "www.auto24.lt", "country": "LT", "provider": "auto24_lt"},
    "LV": {"domain": "www.auto24.lv", "country": "LV", "provider": "auto24_lv"},
}

FUEL_MAP = {
    "bensiin": "Petrol", "benzinas": "Petrol", "benzīns": "Petrol",
    "diisel": "Diesel", "dyzelinas": "Diesel", "dīzelis": "Diesel",
    "elekter": "Electric", "elektra": "Electric", "elektriskais": "Electric",
    "hübriid": "Hybrid", "hibridas": "Hybrid", "hibrīds": "Hybrid",
    "gaas": "LPG", "dujos": "LPG", "gāze": "LPG",
    "b": "Petrol", "d": "Diesel", "e": "Electric", "h": "Hybrid",
}

TRANS_MAP = {
    "automaat": "Automatic", "automatinė": "Automatic", "automātiskā": "Automatic",
    "manuaal": "Manual", "mechaninė": "Manual", "manuālā": "Manual",
    "a": "Automatic", "m": "Manual",
}

BODY_MAP = {
    "sedaan": "Sedan", "luukpära": "Hatchback", "universaal": "Estate",
    "maastur": "SUV", "kupee": "Coupe", "kabriolett": "Convertible",
    "mahtuniversaal": "SUV", "kaubik": "Van",
}

ITEMS_PER_PAGE = 50
MAX_PAGES = 30


def _extract_listings(page, domain: str) -> list[dict]:
    """Extract listing items from auto24 search results page."""
    return page.evaluate("""(domain) => {
        const rows = document.querySelectorAll('.result-row');
        return [...rows].map(el => {
            const titleLink = el.querySelector('.title a.main');
            if (!titleLink) return null;

            const makeSpan = titleLink.querySelector('span:first-child');
            const modelSpan = titleLink.querySelector('span.model');
            const make = makeSpan ? makeSpan.textContent.trim() : '';
            const model = modelSpan ? modelSpan.textContent.trim() : '';
            if (!make) return null;

            const priceSpan = el.querySelector('.finance .price');
            const priceText = priceSpan ? priceSpan.textContent.trim() : '';

            const extra = el.querySelector('.extra');
            const specs = {};
            if (extra) {
                const yearEl = extra.querySelector('.year');
                const mileageEl = extra.querySelector('.mileage');
                const fuelEl = extra.querySelector('.fuel.sm-none');
                const transEl = extra.querySelector('.transmission.sm-none');
                const bodyEl = extra.querySelector('.bodytype');
                const driveEl = extra.querySelector('.drive');
                if (yearEl) specs.year = yearEl.textContent.trim();
                if (mileageEl) specs.mileage = mileageEl.textContent.trim();
                if (fuelEl) specs.fuel = fuelEl.textContent.trim();
                if (transEl) specs.transmission = transEl.textContent.trim();
                if (bodyEl) specs.body = bodyEl.textContent.trim();
                if (driveEl) specs.drive = driveEl.textContent.trim();
            }

            const imgEl = el.querySelector('img.thumb');
            const detailUrl = titleLink.href || '';

            return {
                make, model,
                price_text: priceText,
                specs,
                source_url: detailUrl,
                image_url: imgEl ? imgEl.src : '',
            };
        }).filter(Boolean);
    }""", domain)


def _parse_listing(raw: dict, brand: str, site: dict) -> dict:
    """Normalize a raw auto24 listing into our standard format."""
    make = raw.get("make") or brand
    model = raw.get("model", "")

    price_text = raw.get("price_text", "")
    price = parse_price(price_text, "EUR")

    specs = raw.get("specs", {})

    year_str = specs.get("year", "")
    year = None
    if year_str:
        m = re.search(r"(19\d{2}|20[0-3]\d)", year_str)
        year = int(m.group(1)) if m else None

    mileage_str = specs.get("mileage", "")
    mileage_km = parse_mileage(mileage_str) if mileage_str else None

    fuel_raw = (specs.get("fuel") or "").strip().lower()
    fuel_type = FUEL_MAP.get(fuel_raw, fuel_raw.capitalize() if fuel_raw else None)

    trans_raw = (specs.get("transmission") or "").strip().lower()
    transmission = TRANS_MAP.get(trans_raw, trans_raw.capitalize() if trans_raw else None)

    body_raw = (specs.get("body") or "").strip().lower()
    body_type = BODY_MAP.get(body_raw, body_raw.capitalize() if body_raw else None)

    drive_raw = (specs.get("drive") or "").strip().lower()
    drive_type = None
    if any(w in drive_raw for w in ("nelik", "4wd", "awd", "pilna")):
        drive_type = "AWD"
    elif any(w in drive_raw for w in ("esi", "priekš", "front")):
        drive_type = "FWD"
    elif any(w in drive_raw for w in ("taga", "galin", "rear")):
        drive_type = "RWD"

    image_urls = []
    if raw.get("image_url"):
        image_urls.append(raw["image_url"])

    return {
        "provider": site["provider"],
        "make": make,
        "model": model,
        "variant": None,
        "price": price,
        "price_eur": price,
        "price_original": price,
        "currency": "EUR",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "body_type": body_type,
        "drive_type": drive_type,
        "country": site["country"],
        "steering_side": "LHD",
        "source_url": raw.get("source_url"),
        "image_urls": image_urls,
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None,
           site_code: str | None = None):
    """Scrape auto24 listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
        site_code: 'EE', 'LT', or 'LV'. None = all three.
    """
    sites = [SITES[site_code]] if site_code and site_code in SITES else list(SITES.values())

    for site in sites:
        provider = site["provider"]
        domain = site["domain"]
        listings = load_checkpoint(provider)
        seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

        brands = [brand] if brand else PREMIUM_BRANDS
        pw, browser, ctx, page = setup_browser(headless=headless)

        try:
            cookies_dismissed = False

            for brand_name in brands:
                brand_id = BRAND_IDS.get(brand_name)
                if not brand_id:
                    log.warning("No brand ID for %s, skipping", brand_name)
                    continue

                log.info("Scraping %s for %s...", provider, brand_name)
                brand_count = 0

                for page_num in range(MAX_PAGES):
                    offset = page_num * ITEMS_PER_PAGE
                    url = f"https://{domain}/kasutatud/nimekiri.php?b={brand_id}&a=100&ae=2&af={ITEMS_PER_PAGE}"
                    if offset > 0:
                        url += f"&ak={offset}"

                    safe_navigate(page, url)
                    time.sleep(2)

                    if not cookies_dismissed:
                        dismiss_cookies(page)
                        cookies_dismissed = True
                        time.sleep(1)

                    try:
                        raw_items = _extract_listings(page, domain)
                    except Exception as e:
                        log.error("Extract failed on page %d: %s", page_num + 1, e)
                        raw_items = []

                    if not raw_items:
                        log.info("No items on page %d for %s, stopping", page_num + 1, brand_name)
                        break

                    new_count = 0
                    for raw in raw_items:
                        listing = _parse_listing(raw, brand_name, site)
                        src = listing.get("source_url")
                        if src and src in seen_urls:
                            continue
                        listings.append(listing)
                        if src:
                            seen_urls.add(src)
                        new_count += 1
                        brand_count += 1

                    log.info("[%s] %s page %d: %d items (%d new), total: %d",
                             provider, brand_name, page_num + 1, len(raw_items), new_count, len(listings))

                    if limit and brand_count >= limit:
                        log.info("Reached limit of %d for %s", limit, brand_name)
                        break

                    if page_num % 10 == 9:
                        save_checkpoint(listings, provider)

                    time.sleep(2)

            listings = deduplicate(listings)
            save_checkpoint(listings, provider)
            log.info("%s scrape complete: %d listings", provider, len(listings))

        finally:
            browser.close()
            pw.stop()

    return listings


def scrape_ee(headless: bool = True, limit: int = 0, brand: str | None = None):
    return scrape(headless=headless, limit=limit, brand=brand, site_code="EE")

def scrape_lt(headless: bool = True, limit: int = 0, brand: str | None = None):
    return scrape(headless=headless, limit=limit, brand=brand, site_code="LT")

def scrape_lv(headless: bool = True, limit: int = 0, brand: str | None = None):
    return scrape(headless=headless, limit=limit, brand=brand, site_code="LV")
