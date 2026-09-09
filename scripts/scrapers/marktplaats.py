"""Marktplaats.nl scraper — Netherlands' largest car marketplace.

Marktplaats (owned by eBay/Adevinta) is the dominant classifieds platform in
the Netherlands.  Listings are server-rendered LI elements with structured
attribute spans (year, mileage, fuel, transmission, body type).

URL pattern:
    https://www.marktplaats.nl/l/auto-s/{brand}/
    https://www.marktplaats.nl/l/auto-s/{brand}/p/{page}/

Pagination via /p/N/, ~30 listings per page, high volume per brand.
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
BRAND_SLUGS = get_brand_slugs("marktplaats")

BASE_URL = "https://www.marktplaats.nl"
MAX_PAGES = 700  # High volume: BMW 19K, VW 26K listings at ~30/page


def _dismiss_marktplaats_cookies(page) -> bool:
    """Dismiss the Sourcepoint consent dialog on marktplaats.nl.

    Marktplaats uses a Sourcepoint iframe (sp_message) for GDPR consent.
    We look for the 'Accepteren' button inside the iframe.
    Falls back to the generic dismiss_cookies() from base.
    """
    try:
        iframe_el = page.frame_locator("iframe[id*='sp_message']")
        btn = iframe_el.locator("button:has-text('Accepteren')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass

    return dismiss_cookies(page)


def _extract_listings(page) -> list[dict]:
    """Extract all car listing items from the current page via DOM queries."""
    return page.evaluate("""() => {
        const items = document.querySelectorAll(".hz-Listing.hz-Listing--list-item-cars");
        return [...items].map(el => {
            // Title
            const titleEl = el.querySelector("[class*='title__']");
            const title = titleEl ? titleEl.textContent.trim() : '';

            // Price
            const priceEl = el.querySelector(".hz-Title--title4");
            const price_text = priceEl ? priceEl.textContent.trim() : '';

            // Detail link
            const linkEl = el.querySelector("a[href*='/v/auto-s/']");
            const href = linkEl ? linkEl.href : '';

            // Clean URL (strip tracking params)
            let source_url = '';
            if (href) {
                try {
                    const u = new URL(href);
                    source_url = u.origin + u.pathname;
                } catch (e) {
                    source_url = href.split('?')[0];
                }
            }

            // Attributes: each .hz-Attribute span contains an icon + text
            // Icon classes identify the attribute type:
            //   hz-SvgIconCarConstructionYear -> year
            //   hz-SvgIconCarMileage -> mileage
            // Remaining attrs are fuel, transmission, body type (in order)
            const attrEls = el.querySelectorAll(".hz-Attribute");
            let year = '';
            let mileage_text = '';
            const other_attrs = [];

            for (const attr of attrEls) {
                const text = attr.textContent.trim();
                const icon = attr.querySelector("i[class*='SvgIcon']");
                const iconClass = icon ? icon.className : '';

                if (iconClass.includes('ConstructionYear')) {
                    year = text;
                } else if (iconClass.includes('Mileage')) {
                    mileage_text = text;
                } else {
                    other_attrs.push(text);
                }
            }

            // Seller name
            const sellerEl = el.querySelector(".hz-Listing-seller-name");
            const seller_name = sellerEl ? sellerEl.textContent.trim() : '';

            // Seller location
            const locEl = el.querySelector("[class*='sellerLocation']");
            let city = locEl ? locEl.textContent.trim() : '';
            // Remove "Bezoek website" suffix if present
            city = city.replace(/Bezoek website/i, '').trim();
            // Remove "Heel Nederland" as it's not a real city
            if (city === 'Heel Nederland') city = '';

            // Images
            const imgEls = el.querySelectorAll("img[src*='marktplaats'], img[src*='admarkt']");
            const image_urls = [...imgEls].map(img => img.src).filter(s => s && !s.includes('placeholder'));

            // Options/features
            const optionsEl = el.querySelector("[class*='attributeOptions']");
            const options = optionsEl ? optionsEl.textContent.trim() : '';

            return {
                title,
                price_text,
                source_url,
                year,
                mileage_text,
                other_attrs,
                seller_name,
                city,
                image_urls,
                options,
            };
        }).filter(item => item.title && item.price_text);
    }""")


# Known Dutch fuel type names mapped to English
_FUEL_MAP = {
    "benzine": "Petrol",
    "diesel": "Diesel",
    "elektrisch": "Electric",
    "hybride": "Hybrid",
    "plug-in hybride": "Plug-in Hybrid",
    "lpg": "LPG",
    "cng": "CNG",
    "cng (aardgas)": "CNG",
    "waterstof": "Hydrogen",
    "overig": "Other",
}

# Known Dutch transmission names
_TRANSMISSION_SET = {
    "automaat", "handgeschakeld", "semi-automaat", "cvt",
}

# Known Dutch body types
_BODY_TYPE_SET = {
    "sedan", "hatchback", "stationwagon", "suv of terreinwagen",
    "cabriolet", "coupé", "coupe", "mpv", "bus", "bedrijfswagens",
    "pick-up", "targa",
}


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    title = raw.get("title", "")

    # Split title into model and variant
    # Title often starts with brand: "BMW 320i Sportline Aut ..."
    brand_lower = brand.lower()
    title_lower = title.lower()
    if title_lower.startswith(brand_lower):
        remainder = title[len(brand):].strip()
    elif brand_lower == "mercedes-benz" and title_lower.startswith("mercedes"):
        # Handle "Mercedes" vs "Mercedes-Benz"
        remainder = re.sub(r"^mercedes[\s-]*benz\s*", "", title, flags=re.IGNORECASE).strip()
    else:
        remainder = title

    parts = remainder.split(" ", 1)
    model = parts[0] if parts else remainder
    variant = parts[1] if len(parts) > 1 else ""

    # Price: "€ 19.950,-" or "€ 74.900,-"
    # Strip Dutch price suffix ",-" before parsing so the German-thousands
    # detector in parse_price can recognise the dot-separated format.
    price_text = raw.get("price_text", "")
    price_text = re.sub(r",-\s*$", "", price_text)
    price = parse_price(price_text, "EUR")

    # Year
    year_str = raw.get("year", "")
    year = None
    if year_str:
        m = re.search(r"\b(19\d{2}|20[0-3]\d)\b", year_str)
        if m:
            year = int(m.group(1))

    # Mileage: "49.950 km" (Dutch thousands separator is period)
    mileage_text = raw.get("mileage_text", "")
    mileage_km = parse_mileage(mileage_text) if mileage_text else None

    # Parse other_attrs: fuel_type, transmission, body_type
    fuel_type = None
    transmission = None
    body_type = None

    for attr in raw.get("other_attrs", []):
        attr_lower = attr.lower().strip()
        if attr_lower in _FUEL_MAP:
            fuel_type = _FUEL_MAP[attr_lower]
        elif attr_lower in _TRANSMISSION_SET:
            if attr_lower == "automaat":
                transmission = "Automatic"
            elif attr_lower == "handgeschakeld":
                transmission = "Manual"
            elif attr_lower == "semi-automaat":
                transmission = "Semi-automatic"
            elif attr_lower == "cvt":
                transmission = "CVT"
        elif attr_lower in _BODY_TYPE_SET:
            body_type = attr.strip()

    # Seller - if seller_name looks like a dealer (B.V., Auto, etc.)
    seller_name = raw.get("seller_name", "") or None
    seller_type = "private"
    if seller_name:
        sn_lower = seller_name.lower()
        if any(kw in sn_lower for kw in ("b.v.", "bv", "auto", "cars", "dealer",
                                          "motors", "garage", "automotive",
                                          "trading", "lease", "group")):
            seller_type = "dealer"

    city = raw.get("city", "") or None

    return {
        "provider": "marktplaats",
        "make": brand,
        "model": model,
        "variant": variant or None,
        "price": price,
        "price_eur": price,
        "price_original": price,
        "currency": "EUR",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "body_type": body_type,
        "country": "NL",
        "city": city,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "steering_side": "LHD",
        "source_url": raw.get("source_url"),
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Marktplaats car listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("marktplaats")
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

            log.info("Scraping Marktplaats for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                if page_num == 1:
                    url = f"{BASE_URL}/l/auto-s/{slug}/"
                else:
                    url = f"{BASE_URL}/l/auto-s/{slug}/p/{page_num}/"

                safe_navigate(page, url)
                time.sleep(2)

                if not cookies_dismissed:
                    _dismiss_marktplaats_cookies(page)
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

                log.info("[marktplaats] %s page %d: %d items (%d new), total: %d",
                         brand_name, page_num, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "marktplaats")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "marktplaats")
        log.info("Marktplaats scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
