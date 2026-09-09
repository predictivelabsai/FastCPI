"""Otomoto.pl scraper — Poland's largest car marketplace.

Otomoto is owned by OLX Group and covers the Polish market. Listings are in
article elements with data-id attributes, structured parameters via
dd[data-parameter], and prices in PLN.

URL pattern:
    https://www.otomoto.pl/osobowe/{brand}

Pagination is client-side via "Go to next Page" button clicks (no query-param
pagination).
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
BRAND_SLUGS = get_brand_slugs("otomoto")

BASE_URL = "https://www.otomoto.pl"
MAX_PAGES = 50  # safety cap per brand
PLN_TO_EUR = 0.23


def _extract_listings(page) -> list[dict]:
    """Extract all listing articles from the current page via JS evaluation."""
    return page.evaluate("""() => {
        const articles = document.querySelectorAll('article[data-id]');
        return [...articles].map(el => {
            const id = el.getAttribute('data-id') || '';

            // Title and detail URL from h2 > a
            const titleEl = el.querySelector('h2 a');
            const title = titleEl ? titleEl.textContent.trim() : '';
            const detailUrl = titleEl ? titleEl.getAttribute('href') || '' : '';

            // Description line (engine, power, extras)
            const descEl = el.querySelector('p[class*="e1kj25my"]');
            const description = descEl ? descEl.textContent.trim() : '';

            // Price from h3 span[translate="no"]
            const priceEl = el.querySelector('h3 span[translate="no"]');
            const priceText = priceEl ? priceEl.textContent.trim() : '';
            const currencyEl = el.querySelector('p[translate="no"]');
            const currency = currencyEl ? currencyEl.textContent.trim() : '';

            // Parameters: mileage, fuel_type, gearbox, year
            const params = {};
            const dds = el.querySelectorAll('dd[data-parameter]');
            for (const dd of dds) {
                const key = dd.getAttribute('data-parameter');
                params[key] = dd.textContent.trim();
            }

            // Location and seller info
            const infoPs = el.querySelectorAll('ul p');
            const locationTexts = [];
            const sellerTexts = [];
            for (const p of infoPs) {
                const text = p.textContent.trim();
                if (text.includes('(') && text.includes(')')) {
                    locationTexts.push(text);
                } else if (text.includes('Firma') || text.includes('Prywatny') ||
                           text.includes('Dealer') || text.includes('Opublikowano') ||
                           text.includes('Podbite')) {
                    sellerTexts.push(text);
                }
            }
            const location = locationTexts.join(', ');
            const sellerInfo = sellerTexts.join(', ');

            // Image URLs
            const imgs = el.querySelectorAll('img[src*="apollo.olxcdn.com"]');
            const imageUrls = [...imgs].map(img => img.src).filter(s => s && !s.includes('placeholder'));

            return {
                id, title, detail_url: detailUrl, description,
                price_text: priceText, currency,
                params, location, seller_info: sellerInfo,
                image_urls: imageUrls,
            };
        }).filter(item => item.price_text);
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    title = raw.get("title", "")

    # Split title into model and variant
    # Title format: "BMW X2 xDrive25e Advantage" or "BMW Seria 3 330i xDrive Sport"
    model = ""
    variant = ""
    title_lower = title.lower()
    brand_lower = brand.lower()
    if title_lower.startswith(brand_lower):
        remainder = title[len(brand):].strip()
    else:
        remainder = title
    parts = remainder.split(" ", 1)
    model = parts[0] if parts else remainder
    variant = parts[1] if len(parts) > 1 else ""

    # Price — "85 977" (space as thousands separator)
    price_text = raw.get("price_text", "")
    price_cleaned = price_text.replace("\xa0", "").replace(" ", "").replace(",", "")
    try:
        price_pln = float(price_cleaned)
    except (ValueError, TypeError):
        price_pln = parse_price(price_text, "PLN")
    price_eur = round(price_pln * PLN_TO_EUR, 2) if price_pln else 0

    # Parameters
    params = raw.get("params", {})

    # Mileage — "74 000 km"
    mileage_str = params.get("mileage", "")
    mileage_km = parse_mileage(mileage_str) if mileage_str else None

    # Fuel type — Polish to English mapping
    FUEL_MAP = {
        "benzyna": "Petrol",
        "diesel": "Diesel",
        "elektryczny": "Electric",
        "hybryda": "Hybrid",
        "hybryda plug-in": "Plug-in Hybrid",
        "lpg": "LPG",
        "cng": "CNG",
        "wodór": "Hydrogen",
        "etanol": "Ethanol",
        "benzyna+lpg": "Petrol/LPG",
        "benzyna+cng": "Petrol/CNG",
    }
    fuel_raw = params.get("fuel_type", "")
    fuel_type = FUEL_MAP.get(fuel_raw.lower(), fuel_raw) if fuel_raw else None

    # Gearbox — Polish to English
    GEARBOX_MAP = {
        "automatyczna": "Automatic",
        "manualna": "Manual",
    }
    gearbox_raw = params.get("gearbox", "")
    transmission = GEARBOX_MAP.get(gearbox_raw.lower(), gearbox_raw) if gearbox_raw else None

    # Year
    year_str = params.get("year", "")
    year = int(year_str) if year_str.isdigit() else None

    # Location — "Piaseczno (Mazowieckie)"
    location = raw.get("location", "")
    city = location.split("(")[0].strip() if location else None

    # Seller type from seller_info — "Firma" = dealer, "Prywatny" = private
    seller_info = raw.get("seller_info", "")
    if "firma" in seller_info.lower() or "dealer" in seller_info.lower():
        seller_type = "dealer"
    elif "prywatny" in seller_info.lower():
        seller_type = "private"
    else:
        seller_type = None

    # Power from description — "220 KM"
    description = raw.get("description", "")
    power_hp = None
    power_kw = None
    hp_match = re.search(r"(\d+)\s*KM", description)
    if hp_match:
        power_hp = int(hp_match.group(1))
        power_kw = int(power_hp / 1.35962)

    # Detail URL — ensure absolute
    detail_url = raw.get("detail_url", "")
    if detail_url and not detail_url.startswith("http"):
        detail_url = BASE_URL + detail_url

    return {
        "provider": "otomoto",
        "make": brand,
        "model": model,
        "variant": variant or None,
        "price": price_pln,
        "price_eur": price_eur,
        "price_original": price_pln,
        "currency": "PLN",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "power_hp": power_hp,
        "power_kw": power_kw,
        "country": "PL",
        "city": city,
        "seller_type": seller_type,
        "seller_name": None,
        "steering_side": "LHD",
        "source_url": detail_url,
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def _click_next_page(page) -> bool:
    """Click the 'Go to next Page' pagination button. Returns True on success."""
    try:
        btn = page.locator('button[aria-label="Go to next Page"]')
        if btn.count() > 0 and btn.first.is_visible(timeout=3000):
            btn.first.scroll_into_view_if_needed()
            time.sleep(0.5)
            btn.first.click()
            return True
    except Exception:
        pass
    return False


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Otomoto.pl listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("otomoto")
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

            log.info("Scraping Otomoto for %s...", brand_name)
            brand_count = 0

            # Navigate to the first page for this brand
            url = f"{BASE_URL}/osobowe/{slug}"
            safe_navigate(page, url)
            time.sleep(3)

            if not cookies_dismissed:
                dismiss_cookies(page)
                cookies_dismissed = True
                time.sleep(1)

            for page_num in range(1, MAX_PAGES + 1):
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

                log.info("[otomoto] %s page %d: %d items (%d new), total: %d",
                         brand_name, page_num, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "otomoto")

                # Navigate to next page via button click
                if not _click_next_page(page):
                    log.info("No next page button on page %d for %s, stopping",
                             page_num, brand_name)
                    break

                # Wait for new content to load
                time.sleep(3)

        listings = deduplicate(listings)
        save_checkpoint(listings, "otomoto")
        log.info("Otomoto scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
