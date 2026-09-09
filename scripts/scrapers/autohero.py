"""Autohero scraper — certified used cars from Auto1 Group.

All listings are certified pre-owned, sold by Autohero (dealer).
EUR pricing, km for mileage.

URL pattern:
    https://www.autohero.com/de/search/?make=bmw&sort=price_desc&page=1
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    parse_price, parse_mileage, parse_power, parse_registration,
    setup_browser, dismiss_cookies, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate,
)

log = logging.getLogger(__name__)

from utils.config import get_brand_slugs
BRAND_SLUGS = get_brand_slugs("autohero")

BASE_URL = "https://www.autohero.com"
MAX_PAGES = 50


def _build_search_url(brand_slug: str, page: int = 1) -> str:
    return f"{BASE_URL}/de/search/?make={brand_slug}&sort=price_desc&page={page}"


def _dismiss_autohero_cookies(page):
    """Dismiss Autohero's cookie consent popup."""
    try:
        btn = page.locator("button:has-text('Alle akzeptieren'), button:has-text('Accept All'), button:has-text('alle akzeptieren')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass
    try:
        btn = page.locator("#onetrust-accept-btn-handler")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass
    return False


def _extract_listings(page) -> list[dict]:
    """Extract listing data from Autohero search results via JS."""
    return page.evaluate("""() => {
        const cards = document.querySelectorAll('a[data-qa-selector="ad-card-link"]');
        const results = [];

        for (const el of cards) {
            const label = el.getAttribute('aria-label') || '';
            const href = el.href || '';

            const specEls = el.querySelectorAll('li[class*="specItem"]');
            const specs = [...specEls].map(s => s.textContent.trim()).filter(s => s.length > 0 && s.length < 100);

            const priceMatch = label.match(/([\d.,]+)\s*€/);
            const priceText = priceMatch ? priceMatch[1].replace(/\./g, '').replace(',', '.') : '';

            const imgEls = el.querySelectorAll('img[src*="autohero"]');
            const imageUrls = [...imgEls].map(img => img.src).filter(Boolean);

            if (label && priceText) {
                const titleClean = label.replace(/\s*-?\s*[\d.,]+\s*€.*$/, '').trim();
                const parts = titleClean.split(' - ');
                const namePart = parts[0] || titleClean;
                const variantPart = parts.slice(1).join(' - ');
                const multiWordMakes = ['Mercedes-Benz', 'Land Rover', 'Alfa Romeo'];
                let make = '', model = '';
                let matched = false;
                for (const mw of multiWordMakes) {
                    if (namePart.startsWith(mw + ' ') || namePart === mw) {
                        make = mw; model = namePart.substring(mw.length).trim(); matched = true; break;
                    }
                }
                if (!matched) {
                    const words = namePart.split(' ');
                    make = words[0]; model = words.slice(1).join(' ');
                }

                results.push({
                    title: titleClean,
                    make: make, model: model, variant: variantPart,
                    price_text: priceText,
                    specs,
                    source_url: href.startsWith('/') ? window.location.origin + href : href,
                    image_urls: imageUrls,
                });
            }
        }
        return results;
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    make = raw.get("make", brand)
    model = raw.get("model", "")
    variant = raw.get("variant", "")

    # Price
    price_text = raw.get("price_text", "")
    price = parse_price(price_text, "EUR")

    # Parse specs
    specs = raw.get("specs", [])
    mileage_str = ""
    registration_str = ""
    fuel_type = ""
    transmission = ""
    power_str = ""

    for spec in specs:
        spec_lower = spec.lower()
        if "km" in spec_lower and any(c.isdigit() for c in spec):
            mileage_str = spec
        elif re.search(r"\d{1,2}/\d{4}", spec):
            registration_str = spec
        elif re.search(r"^\d{4}$", spec.strip()):
            registration_str = spec
        elif "kw" in spec_lower or "ps" in spec_lower or "hp" in spec_lower:
            power_str = spec
        elif spec_lower in ("benzin", "diesel", "elektro", "hybrid",
                            "plug-in-hybrid", "petrol", "electric",
                            "gasoline"):
            fuel_type = spec
        elif spec_lower in ("automatik", "schaltgetriebe", "automatic",
                            "manual"):
            transmission = spec

    mileage_km = parse_mileage(mileage_str) if mileage_str else None
    power_hp, power_kw = parse_power(power_str) if power_str else (None, None)
    reg_month, reg_year = parse_registration(registration_str) if registration_str else (None, None)

    # Map German terms
    fuel_map = {
        "benzin": "Petrol",
        "diesel": "Diesel",
        "elektro": "Electric",
        "hybrid": "Hybrid",
        "plug-in-hybrid": "Plug-in Hybrid",
    }
    if fuel_type:
        fuel_type = fuel_map.get(fuel_type.lower(), fuel_type)

    transmission_map = {
        "automatik": "Automatic",
        "schaltgetriebe": "Manual",
    }
    if transmission:
        transmission = transmission_map.get(transmission.lower(), transmission)

    return {
        "provider": "autohero",
        "make": make,
        "model": model,
        "variant": variant or None,
        "price": price,
        "price_eur": price,
        "price_original": price,
        "currency": "EUR",
        "year": reg_year,
        "registration_str": registration_str or None,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type or None,
        "transmission": transmission or None,
        "power_hp": power_hp,
        "power_kw": power_kw,
        "power_str": power_str or None,
        "country": "DE",
        "city": None,
        "seller_type": "dealer",
        "seller_name": "Autohero",
        "accident_free": None,
        "steering_side": "LHD",
        "source_url": raw.get("source_url"),
        "image_urls": raw.get("image_urls") or [],
        "condition": "certified",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Autohero listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("autohero")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    brands = [brand] if brand else PREMIUM_BRANDS
    pw, browser, ctx, page = setup_browser(headless=headless)

    try:
        cookies_dismissed = False

        for brand_name in brands:
            slug = BRAND_SLUGS.get(brand_name)
            if not slug:
                log.warning("No slug for brand %s, skipping", brand_name)
                continue

            log.info("Scraping Autohero for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = _build_search_url(slug, page_num)
                safe_navigate(page, url)
                time.sleep(2)

                if not cookies_dismissed:
                    _dismiss_autohero_cookies(page)
                    dismiss_cookies(page)
                    cookies_dismissed = True
                    time.sleep(1)

                try:
                    raw_items = _extract_listings(page)
                except Exception as e:
                    log.error("Failed to extract listings on page %d: %s", page_num, e)
                    raw_items = []

                if not raw_items:
                    log.info("No items on page %d for %s, stopping", page_num, brand_name)
                    break

                new_count = 0
                for raw in raw_items:
                    listing = _parse_listing(raw, brand_name)
                    src = listing.get("source_url")
                    if src and src in seen_urls:
                        continue
                    listings.append(listing)
                    if src:
                        seen_urls.add(src)
                    new_count += 1
                    brand_count += 1

                log.info("[autohero] %s page %d/%d: %d items (%d new), total: %d",
                         brand_name, page_num, MAX_PAGES, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 25 == 0:
                    save_checkpoint(listings, "autohero")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "autohero")
        log.info("Autohero scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
