"""Finn.no scraper — Norway's dominant car marketplace.

Finn.no is the most visited marketplace in Norway, covering cars, real estate,
and classifieds. Listings are in article elements with structured title, price,
specs, and location data.

URL pattern:
    https://www.finn.no/mobility/search/car?variant=0.{BRAND_ID}&sort=PRICE_DESC&page=1

Pagination via ?page=N, 50 listings per page.
Currency: NOK (Norwegian Krone).
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
BRAND_SLUGS = get_brand_slugs("finn")

BASE_URL = "https://www.finn.no"
MAX_PAGES = 50  # Safety cap; finn.no can have 100+ pages for popular brands
NOK_TO_EUR = 0.085


def _extract_listings(page) -> list[dict]:
    """Extract all article listing items from the current page via DOM queries."""
    return page.evaluate("""() => {
        const articles = document.querySelectorAll('article.sf-search-ad');
        return [...articles].map(el => {
            // Title from h2
            const h2 = el.querySelector('h2');
            const title = h2 ? h2.textContent.trim() : '';

            // Variant/subtitle (text-caption below title, subtle text)
            const subtitleEl = el.querySelector('.text-caption.s-text-subtle');
            const subtitle = subtitleEl ? subtitleEl.textContent.trim() : '';

            // Specs line: "2022 · 45 000 km · Bensin · Manuell"
            const specsEl = el.querySelector('span.text-caption.font-bold');
            const specsText = specsEl ? specsEl.textContent.trim() : '';

            // Price: spans with t3/t4 classes
            const priceEl = el.querySelector('.t3.font-bold');
            const priceText = priceEl ? priceEl.textContent.trim() : '';

            // Detail URL from the main link
            const linkEl = el.querySelector('a.sf-search-ad-link');
            const sourceUrl = linkEl ? linkEl.href : '';

            // Finn ID from the link href or id attribute
            const finnId = linkEl ? (linkEl.id || '') : '';

            // Image
            const imgEl = el.querySelector('img[src*="finncdn"]');
            const imageUrl = imgEl ? imgEl.src : '';

            // Location and seller info (bottom section)
            const detailDiv = el.querySelector('.flex.items-end.text-detail');
            let location = '';
            let sellerType = '';
            if (detailDiv) {
                const spans = detailDiv.querySelectorAll('span.truncate');
                if (spans.length >= 1) location = spans[0].textContent.trim();
                if (spans.length >= 2) sellerType = spans[1].textContent.trim();
            }

            return {
                title,
                subtitle,
                specs_text: specsText,
                price_text: priceText,
                source_url: sourceUrl,
                finn_id: finnId,
                image_url: imageUrl,
                location,
                seller_type_raw: sellerType,
            };
        }).filter(item => item.title && item.price_text);
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    title = raw.get("title", "")
    subtitle = raw.get("subtitle", "")

    # Split title into model — title is like "BMW M5" or "BMW 3-Serie"
    model = ""
    title_lower = title.lower()
    brand_lower = brand.lower()
    if title_lower.startswith(brand_lower):
        model = title[len(brand):].strip()
    else:
        model = title

    # Use subtitle as variant (e.g. "CS 635HK V8 BØTTESETER FULL SERVICE")
    variant = subtitle if subtitle else None

    # Price — remove non-breaking spaces and parse
    price_text = raw.get("price_text", "")
    # price_text is like "2 490 000" (with nbsp) or "251 942"
    cleaned_price = price_text.replace("\xa0", "").replace(" ", "")
    cleaned_price = re.sub(r"[^\d]", "", cleaned_price)
    price_nok = int(cleaned_price) if cleaned_price else 0
    price_eur = round(price_nok * NOK_TO_EUR, 2) if price_nok else 0

    # Specs: "2022 · 45 000 km · Bensin · Manuell" or "1989 · 210 095 km · Bensin · Manuell"
    specs_text = raw.get("specs_text", "")
    # Replace non-breaking spaces with regular spaces
    specs_text = specs_text.replace("\xa0", " ")
    # Split by the dot separator (·)
    specs_parts = [s.strip() for s in specs_text.split("∙") if s.strip()]
    # Also try middot
    if len(specs_parts) <= 1:
        specs_parts = [s.strip() for s in specs_text.split("·") if s.strip()]
    # Also try bullet
    if len(specs_parts) <= 1:
        specs_parts = [s.strip() for s in specs_text.split("•") if s.strip()]
    # Fallback: split by common separator pattern
    if len(specs_parts) <= 1:
        specs_parts = [s.strip() for s in re.split(r"\s*[·∙•]\s*", specs_text) if s.strip()]

    year = None
    mileage_km = None
    fuel_type = None
    transmission = None

    for part in specs_parts:
        part_clean = part.strip()
        # Year: 4-digit number starting with 19 or 20
        year_match = re.match(r"^(19\d{2}|20[0-3]\d)$", part_clean)
        if year_match:
            year = int(year_match.group(1))
            continue

        # Mileage: contains "km"
        if "km" in part_clean.lower():
            mileage_km = parse_mileage(part_clean)
            continue

        # Fuel types in Norwegian
        fuel_map = {
            "bensin": "Petrol",
            "diesel": "Diesel",
            "elektrisk": "Electric",
            "el": "Electric",
            "hybrid": "Hybrid",
            "plug-in hybrid": "Plug-in Hybrid",
            "ladbar hybrid": "Plug-in Hybrid",
            "hydrogen": "Hydrogen",
        }
        part_lower = part_clean.lower()
        if part_lower in fuel_map:
            fuel_type = fuel_map[part_lower]
            continue

        # Transmission in Norwegian
        trans_map = {
            "manuell": "Manual",
            "automat": "Automatic",
            "automatisk": "Automatic",
        }
        if part_lower in trans_map:
            transmission = trans_map[part_lower]
            continue

    # Location and seller
    location_raw = raw.get("location", "")
    seller_type_raw = raw.get("seller_type_raw", "")

    # Location may contain "City · DEALER NAME" pattern
    city = None
    seller_name = None
    if "∙" in location_raw or "·" in location_raw or "•" in location_raw:
        loc_parts = re.split(r"\s*[·∙•]\s*", location_raw, maxsplit=1)
        city = loc_parts[0].strip() if loc_parts else None
        seller_name = loc_parts[1].strip() if len(loc_parts) > 1 else None
    else:
        city = location_raw if location_raw else None

    # Seller type: "Privat" = private, "Forhandler" = dealer
    seller_type = "private" if seller_type_raw.lower() == "privat" else "dealer"

    # Image URLs
    image_url = raw.get("image_url", "")
    image_urls = [image_url] if image_url else []

    return {
        "provider": "finn",
        "make": brand,
        "model": model,
        "variant": variant,
        "price": price_nok,
        "price_eur": price_eur,
        "price_original": price_nok,
        "currency": "NOK",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "country": "NO",
        "city": city,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "steering_side": "LHD",
        "source_url": raw.get("source_url"),
        "image_urls": image_urls,
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Finn.no listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("finn")
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

            log.info("Scraping Finn.no for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = (
                    f"{BASE_URL}/mobility/search/car"
                    f"?variant=0.{slug}&sales_form=1&sort=PRICE_DESC&page={page_num}"
                )
                safe_navigate(page, url)
                time.sleep(2)

                if not cookies_dismissed:
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

                log.info("[finn] %s page %d/%d: %d items (%d new), total: %d",
                         brand_name, page_num, MAX_PAGES, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "finn")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "finn")
        log.info("Finn.no scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
