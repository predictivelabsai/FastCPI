"""Bilbasen scraper — Denmark's largest car marketplace.

Bilbasen.dk has 60K+ active listings. Server-rendered with clean
path-based URLs and a modern React frontend using CSS module classes.

URL pattern:
    https://www.bilbasen.dk/brugt/bil/{brand}?page=1

Pagination via ?page=N, up to ~100 pages per search (30 items/page).
Prices in DKK, converted to EUR.
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    parse_price, parse_mileage, parse_registration,
    setup_browser, dismiss_cookies, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate,
)

log = logging.getLogger(__name__)

from utils.config import get_brand_slugs
BRAND_SLUGS = get_brand_slugs("bilbasen")

BASE_URL = "https://www.bilbasen.dk"
MAX_PAGES = 100  # Bilbasen can have 80+ pages per brand
DKK_TO_EUR = 0.134


def _dismiss_bilbasen_cookies(page) -> bool:
    """Dismiss Bilbasen's cookie consent dialog (CMP in iframe)."""
    try:
        iframe = page.frame_locator('iframe[title*="Cookie"]')
        btn = iframe.locator('button:has-text("Kun nødvendige")')
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass
    # Fall back to the generic dismiss_cookies helper
    return dismiss_cookies(page)


def _extract_listings(page) -> list[dict]:
    """Extract all listing articles from the current page via JS evaluation."""
    return page.evaluate("""() => {
        const articles = document.querySelectorAll('article');
        return [...articles].map(el => {
            const link = el.querySelector("a[href*='/brugt/bil/']");
            const makeModelEl = el.querySelector("[class*='makeModel'] h3");
            const priceEl = el.querySelector("[class*='price']");
            const detailEls = el.querySelectorAll("[class*='ListingDetails'] li");
            const locationEl = el.querySelector("[class*='location'] span");
            const descEl = el.querySelector("[class*='description']");

            // Variant text is after the h3 in the makeModel container
            const makeModelParent = el.querySelector("[class*='makeModel']");
            let variant = '';
            if (makeModelParent) {
                const allText = makeModelParent.textContent.trim();
                const h3Text = makeModelEl ? makeModelEl.textContent.trim() : '';
                variant = allText.replace(h3Text, '').trim();
            }

            // Collect image URLs from carousel
            const imgEls = el.querySelectorAll("img[alt]:not([alt='Forhandlerlogo'])");
            const imageUrls = [...imgEls]
                .map(img => img.src)
                .filter(s => s && !s.includes('data:') && s.startsWith('http'));

            return {
                url: link ? link.href : '',
                make_model: makeModelEl ? makeModelEl.textContent.trim() : '',
                variant: variant,
                price_text: priceEl ? priceEl.textContent.trim() : '',
                details: [...detailEls].map(d => d.textContent.trim()),
                location: locationEl ? locationEl.textContent.trim() : '',
                description: descEl ? descEl.textContent.trim().substring(0, 500) : '',
                image_urls: imageUrls,
            };
        }).filter(item => item.url && item.price_text);
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    make_model = raw.get("make_model", "")
    variant = raw.get("variant", "")

    # make_model is e.g. "BMW 320i" — strip brand prefix to get model
    model = ""
    mm_lower = make_model.lower()
    brand_lower = brand.lower()
    if mm_lower.startswith(brand_lower):
        model = make_model[len(brand):].strip()
    else:
        model = make_model

    # Price — e.g. "229.900 kr." or "149.700 kr.(Engros/CVR)"
    price_text = raw.get("price_text", "")
    # Check for engros/wholesale pricing
    is_engros = "engros" in price_text.lower() or "cvr" in price_text.lower()
    seller_type = "dealer"  # Bilbasen is primarily dealer listings

    # Clean price text: remove "kr.", "(Engros/CVR)", non-breaking spaces
    price_cleaned = price_text.replace("\xa0", " ")
    price_cleaned = re.sub(r"\(.*?\)", "", price_cleaned)
    price_cleaned = price_cleaned.replace("kr.", "").replace("kr", "").strip()
    # Danish formatting: periods as thousands separators (e.g. "229.900")
    price_dkk = parse_price(price_cleaned, "DKK")
    price_eur = round(price_dkk * DKK_TO_EUR, 2) if price_dkk else 0

    # Details list: [registration, mileage, fuel_economy/range, transmission, fuel_type]
    details = raw.get("details", [])
    registration_str = ""
    mileage_str = ""
    fuel_type = ""
    transmission = ""

    FUEL_MAP = {
        "benzin": "Petrol",
        "diesel": "Diesel",
        "el": "Electric",
        "hybrid": "Hybrid",
        "plug-in hybrid": "Plug-in Hybrid",
        "plugin hybrid": "Plug-in Hybrid",
        "brint": "Hydrogen",
    }

    TRANSMISSION_MAP = {
        "manuelt gear": "Manual",
        "automatisk gear": "Automatic",
        "automatgear": "Automatic",
    }

    for detail in details:
        detail_lower = detail.lower().strip()

        # Registration: "3/1989" or "6/2025"
        if re.match(r"^\d{1,2}/\d{4}$", detail.strip()):
            registration_str = detail.strip()
        # Mileage: "108.000 km"
        elif "km" in detail_lower and not ("km/l" in detail_lower or "rækkevidde" in detail_lower):
            mileage_str = detail.strip()
        # Fuel type
        elif detail_lower in FUEL_MAP:
            fuel_type = FUEL_MAP[detail_lower]
        # Transmission
        elif detail_lower in TRANSMISSION_MAP:
            transmission = TRANSMISSION_MAP[detail_lower]

    # Parse mileage (Danish uses period as thousands sep: "108.000 km")
    mileage_km = parse_mileage(mileage_str) if mileage_str else None

    # Parse registration
    reg_month, reg_year = parse_registration(registration_str) if registration_str else (None, None)

    # Location: "Viborg, Østjylland" -> city is first part
    location = raw.get("location", "")
    city = location.split(",")[0].strip() if location else None

    return {
        "provider": "bilbasen",
        "make": brand,
        "model": model,
        "variant": variant or None,
        "price": price_dkk,
        "price_eur": price_eur,
        "price_original": price_dkk,
        "currency": "DKK",
        "year": reg_year,
        "registration_str": registration_str,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type or None,
        "transmission": transmission or None,
        "power_hp": None,
        "power_kw": None,
        "power_str": None,
        "country": "DK",
        "city": city,
        "seller_type": seller_type,
        "seller_name": None,
        "steering_side": "LHD",
        "source_url": raw.get("url"),
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Bilbasen listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("bilbasen")
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

            log.info("Scraping Bilbasen for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = f"{BASE_URL}/brugt/bil/{slug}?includeengroscvr=true&includeleasing=false&page={page_num}"
                safe_navigate(page, url)
                time.sleep(2)

                if not cookies_dismissed:
                    _dismiss_bilbasen_cookies(page)
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

                log.info("[bilbasen] %s page %d: %d items (%d new), total: %d",
                         brand_name, page_num, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "bilbasen")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "bilbasen")
        log.info("Bilbasen scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
