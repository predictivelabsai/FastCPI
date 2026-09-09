"""Blocket.se scraper — Sweden's largest car marketplace.

Blocket is a SPA (single-page app) that renders listings client-side.
Cookie consent uses an SP Consent iframe. Listings appear as card elements
after the page hydrates.

URL pattern:
    https://www.blocket.se/mobility/search/car?make=BMW&sort=price_desc&page=1

SEK prices are converted to EUR at scrape time.
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    parse_price, parse_mileage,
    setup_browser, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate,
)

log = logging.getLogger(__name__)

SEK_TO_EUR = 0.087

from utils.config import get_brand_slugs
BRAND_SLUGS = get_brand_slugs("blocket")

FUEL_MAP = {
    "bensin": "Petrol",
    "diesel": "Diesel",
    "el": "Electric",
    "elhybrid": "Hybrid",
    "laddhybrid": "Plugin Hybrid",
    "miljöbränsle/hybrid": "Hybrid",
    "etanol": "Ethanol",
    "gas": "LPG",
}

TRANS_MAP = {
    "automatisk": "Automatic",
    "manuell": "Manual",
    "automat": "Automatic",
}

BASE_URL = "https://www.blocket.se/mobility/search/car"
MAX_PAGES = 30


def _dismiss_blocket_cookies(page):
    """Dismiss Blocket's SP Consent cookie iframe."""
    try:
        iframe = page.frame_locator("iframe[title*='Cookie'], iframe[title*='cookie'], iframe[id*='sp_message']")
        btn = iframe.locator("button:has-text('Godkänn alla'), button:has-text('Accept All')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass

    try:
        btn = page.locator("button:has-text('Godkänn alla')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass

    return False


def _close_popups(page):
    """Close any overlay popups (compare feature, etc.)."""
    try:
        close_btns = page.locator("button:has-text('Stäng'), button[aria-label='Stäng']")
        if close_btns.count() > 0:
            close_btns.first.click()
            time.sleep(0.5)
    except Exception:
        pass


def _extract_listings(page) -> list[dict]:
    """Extract car listings from Blocket search results via article cards."""
    page.wait_for_timeout(3000)

    return page.evaluate("""() => {
        const cards = document.querySelectorAll('article.mobility-search-ad-card');
        const results = [];

        for (const card of cards) {
            const linkEl = card.querySelector('a.sf-search-ad-link');
            const href = linkEl ? linkEl.href : '';
            if (!href) continue;

            const h2 = card.querySelector('h2');
            const title = h2 ? h2.textContent.trim() : '';

            const subtitle = card.querySelector('.text-caption:not(.font-bold)');
            const variant = subtitle ? subtitle.textContent.trim() : '';

            const specSpan = card.querySelector('span.text-caption.font-bold');
            const specText = specSpan ? specSpan.textContent.trim() : '';

            const text = card.textContent || '';
            const priceMatch = text.match(/(\\d[\\d\\s]+)\\s*kr/);
            const priceText = priceMatch ? priceMatch[0] : '';

            const yearMatch = specText.match(/\\b(19\\d{2}|20[0-3]\\d)\\b/);
            const year = yearMatch ? yearMatch[1] : '';

            const mileageMatch = specText.match(/(\\d[\\d\\s]+)\\s*mil/);
            const mileage = mileageMatch ? mileageMatch[0] : '';

            const fuelWords = ['bensin', 'diesel', 'el', 'elhybrid', 'laddhybrid'];
            let fuel = '';
            const specLower = specText.toLowerCase();
            for (const fw of fuelWords) {
                if (specLower.includes(fw)) { fuel = fw; break; }
            }

            let trans = '';
            if (specLower.includes('automatisk') || specLower.includes('automat')) trans = 'automatisk';
            else if (specLower.includes('manuell')) trans = 'manuell';

            const imgs = card.querySelectorAll('img[src*="blocketcdn"]');
            const imageUrls = [...imgs].map(i => i.src).filter(Boolean);

            if (title && priceText) {
                results.push({
                    title, variant, price_text: priceText, year, mileage, fuel, trans,
                    source_url: href,
                    image_urls: imageUrls.slice(0, 5),
                });
            }
        }
        return results;
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Normalize a raw Blocket listing."""
    title = raw.get("title", "")
    variant = raw.get("variant", "")

    MULTI_WORD = ["Mercedes-Benz", "Land Rover", "Alfa Romeo", "Lynk & Co"]
    make = brand
    model = ""
    for mw in MULTI_WORD:
        if title.startswith(mw + " ") or title == mw:
            make = mw
            model = title[len(mw):].strip()
            break
    else:
        parts = title.split(" ", 1)
        make = parts[0] if parts else title
        model = parts[1] if len(parts) > 1 else ""

    price_text = raw.get("price_text", "")
    price_sek = parse_price(price_text, "SEK")
    price_eur = round(price_sek * SEK_TO_EUR) if price_sek else 0

    year = None
    year_str = raw.get("year", "")
    if year_str:
        m = re.search(r"(19\d{2}|20[0-3]\d)", year_str)
        year = int(m.group(1)) if m else None

    # Blocket mileage is in "mil" (Swedish miles = 10km)
    mileage_str = raw.get("mileage", "")
    mileage_km = None
    if mileage_str:
        m = re.search(r"([\d\s]+)", mileage_str.replace(" ", ""))
        if m:
            mil = int(m.group(1).replace(" ", "").replace("\xa0", ""))
            mileage_km = mil * 10  # 1 Swedish mil = 10 km

    fuel_raw = raw.get("fuel", "").lower()
    fuel_type = FUEL_MAP.get(fuel_raw, fuel_raw.capitalize() if fuel_raw else None)

    trans_raw = raw.get("trans", "").lower()
    transmission = TRANS_MAP.get(trans_raw, trans_raw.capitalize() if trans_raw else None)

    return {
        "provider": "blocket",
        "make": make,
        "model": model,
        "variant": variant or None,
        "price": price_sek,
        "price_eur": price_eur,
        "price_original": price_sek,
        "currency": "SEK",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "country": "SE",
        "steering_side": "LHD",
        "source_url": raw.get("source_url"),
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Blocket.se listings for premium brands."""
    listings = load_checkpoint("blocket")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    brands = [brand] if brand else PREMIUM_BRANDS
    pw, browser, ctx, page = setup_browser(headless=headless)

    try:
        cookies_dismissed = False

        for brand_name in brands:
            slug = BRAND_SLUGS.get(brand_name)
            if not slug:
                log.warning("No slug for %s, skipping", brand_name)
                continue

            log.info("Scraping Blocket for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = f"{BASE_URL}?make={slug}&sort=price_desc&page={page_num}"
                safe_navigate(page, url)
                time.sleep(3)

                if not cookies_dismissed:
                    _dismiss_blocket_cookies(page)
                    _close_popups(page)
                    cookies_dismissed = True
                    time.sleep(2)

                try:
                    raw_items = _extract_listings(page)
                except Exception as e:
                    log.error("Extract failed on page %d: %s", page_num, e)
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

                log.info("[blocket] %s page %d: %d items (%d new), total: %d",
                         brand_name, page_num, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "blocket")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "blocket")
        log.info("Blocket scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
