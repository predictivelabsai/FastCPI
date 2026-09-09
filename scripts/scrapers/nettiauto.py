"""Nettiauto scraper — Finland's #1 car marketplace.

Nettiauto (nettiauto.com) is the largest car marketplace in Finland.
Listings are server-rendered as product-card divs with structured
data-datalayer JSON attributes.

URL pattern:
    https://www.nettiauto.com/en/{brand}/vaihtoautot?page=1

Pagination via ?page=N.
"""

from __future__ import annotations

import json
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
BRAND_SLUGS = get_brand_slugs("nettiauto")

BASE_URL = "https://www.nettiauto.com"
MAX_PAGES = 250  # Nettiauto can have 200+ pages per brand


def _dismiss_nettiauto_cookies(page) -> bool:
    """Dismiss the Nettiauto privacy-mgmt cookie consent iframe."""
    try:
        iframe = page.frame_locator('iframe[src*="privacy-mgmt"]')
        btn = iframe.locator('button[title*="Hyväksy"], button:has-text("Hyväksy")')
        if btn.count() > 0:
            btn.first.click()
            time.sleep(1)
            return True
    except Exception:
        pass
    # Fall back to the generic dismiss_cookies
    return dismiss_cookies(page)


def _extract_listings(page) -> list[dict]:
    """Extract all product-card listing items from the current page."""
    return page.evaluate("""() => {
        const cards = document.querySelectorAll('.product-card');
        return [...cards].map(el => {
            // Parse the structured data-datalayer JSON attribute
            let dlData = {};
            const dlAttr = el.getAttribute('data-datalayer');
            if (dlAttr) {
                try { dlData = JSON.parse(dlAttr); } catch(e) {}
            }

            // Title (make + model, e.g. "BMW 320 Gran Turismo")
            const titleEl = el.querySelector('.product-card__title');
            const title = titleEl ? titleEl.textContent.trim() : '';

            // Detail link and listing ID
            const linkEl = el.querySelector('a.product-card-link__tricky-link');
            const detailPath = linkEl ? linkEl.getAttribute('href') : '';

            // Price text from the visible price element
            const priceEl = el.querySelector('.product-card__price-main');
            const priceText = priceEl ? priceEl.textContent.trim() : '';

            // Sub-title / variant info (e.g. "4.0, E92 Coupé")
            const subEl = el.querySelector('.product-card__sub-title');
            const subTitle = subEl ? subEl.textContent.trim() : '';

            // Basic info spans: year, mileage, fuel, transmission, drive
            const infoSpans = el.querySelectorAll('.product-card__basic-info-list span');
            const specs = [...infoSpans].map(s => s.textContent.trim().replace(/^●\\s*/, ''));

            // Image URLs from the slider
            const imgEls = el.querySelectorAll('img[data-testid="listing-slider-thumbnail"]');
            const imageUrls = [...imgEls].map(img => img.src).filter(s => s && !s.includes('placeholder'));

            // Seller info
            const addressEl = el.querySelector('.product-card__address .block-row');
            const addressText = addressEl ? addressEl.textContent.trim() : '';
            const isDealerEl = el.querySelector('.product-card__address-dealer');
            const isSellerEl = el.querySelector('.product-card__address-seller');
            const sellerType = isDealerEl ? 'dealer' : (isSellerEl ? 'private' : 'unknown');

            // USP / description
            const uspEl = el.querySelector('.product-card__usp-info');
            const usp = uspEl ? uspEl.textContent.trim() : '';

            return {
                title,
                price_text: priceText,
                sub_title: subTitle,
                specs,
                detail_path: detailPath,
                image_urls: imageUrls,
                address_text: addressText,
                seller_type: sellerType,
                usp,
                dl_id: dlData.item_id || null,
                dl_brand: dlData.item_brand || '',
                dl_variant: dlData.item_variant || '',
                dl_year: dlData.item_year_model || null,
                dl_price: dlData.item_vehicle_price || null,
                dl_mileage: dlData.item_mileage || null,
                dl_power_type: dlData.item_power_type || '',
                dl_seller: dlData.item_seller || '',
            };
        }).filter(item => item.title && (item.dl_price || item.price_text));
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    title = raw.get("title", "")

    # Model: strip brand prefix from title
    title_lower = title.lower()
    brand_lower = brand.lower()
    if title_lower.startswith(brand_lower):
        remainder = title[len(brand):].strip()
    else:
        remainder = title
    model = remainder or raw.get("dl_variant", "")

    # Variant / sub-title (e.g. "4.0, E92 Coupé")
    variant = raw.get("sub_title", "")
    # Clean up variant text
    variant = re.sub(r"\s+", " ", variant).strip()
    variant = variant if variant else None

    # Price — prefer the structured data-datalayer value (integer)
    dl_price = raw.get("dl_price")
    if dl_price and isinstance(dl_price, (int, float)):
        price = int(dl_price)
    else:
        price_text = raw.get("price_text", "")
        price = parse_price(price_text, "EUR")

    # Year — prefer structured data
    dl_year = raw.get("dl_year")
    year = int(dl_year) if dl_year else None

    # Mileage — prefer structured data (in km)
    dl_mileage = raw.get("dl_mileage")
    if dl_mileage and isinstance(dl_mileage, (int, float)):
        mileage_km = int(dl_mileage)
    else:
        mileage_km = None

    # Specs: [year, mileage, fuel_type, transmission, drive_type]
    specs = raw.get("specs", [])
    fuel_type = None
    transmission = None
    drive_type = None

    # Map Finnish/mixed fuel type names to normalized English
    FUEL_NORMALIZE = {
        "petrol": "Petrol", "diesel": "Diesel", "electric": "Electric",
        "hybrid": "Hybrid", "plug-in hybrid": "Plug-in Hybrid",
        "lpg": "LPG", "cng": "CNG", "hydrogen": "Hydrogen",
        "petrol/electric": "Hybrid", "diesel/electric": "Hybrid",
        "natural gas/petrol": "CNG", "ethanol": "Ethanol",
        # Finnish names
        "bensiini": "Petrol", "sähkö": "Electric",
        "kaasu": "LPG", "vety": "Hydrogen",
    }

    for spec in specs:
        spec_lower = spec.lower().strip()
        # Direct match
        if spec_lower in FUEL_NORMALIZE:
            fuel_type = FUEL_NORMALIZE[spec_lower]
        # Finnish hybrid patterns: "Hybridi (bensiini/sähkö)", etc.
        elif "hybridi" in spec_lower or "hybrid" in spec_lower:
            if "plug" in spec_lower or "ladattava" in spec_lower:
                fuel_type = "Plug-in Hybrid"
            else:
                fuel_type = "Hybrid"
        elif spec_lower in ("automatic", "manual"):
            transmission = spec.strip()
        elif spec_lower in ("front wheel", "rear wheel", "four wheel",
                            "front-wheel", "rear-wheel", "four-wheel",
                            "fwd", "rwd", "awd", "4wd"):
            drive_type = spec.strip()
        elif "km" in spec_lower and mileage_km is None:
            mileage_km = parse_mileage(spec)
        elif re.match(r"^\d{4}$", spec.strip()) and year is None:
            year = int(spec.strip())

    # Finnish power type mapping (from data-datalayer)
    dl_power = raw.get("dl_power_type", "")
    if not fuel_type and dl_power:
        POWER_MAP = {
            "bensiini": "Petrol", "diesel": "Diesel",
            "sähkö": "Electric", "hybridi": "Hybrid",
            "kaasu": "LPG", "vety": "Hydrogen",
            "petrol": "Petrol", "electric": "Electric",
        }
        fuel_type = POWER_MAP.get(dl_power.lower(), dl_power)

    # Build source URL
    detail_path = raw.get("detail_path", "")
    source_url = f"{BASE_URL}{detail_path}" if detail_path else None

    # Seller info: "City, Dealer Name" or "City, Person Name"
    address_text = raw.get("address_text", "")
    city = None
    seller_name = raw.get("dl_seller", "") or None
    if address_text:
        parts = [p.strip() for p in address_text.split(",", 1)]
        if len(parts) >= 1:
            city = parts[0] if parts[0] else None
        if len(parts) >= 2 and not seller_name:
            seller_name = parts[1] if parts[1] else None

    seller_type = raw.get("seller_type", "unknown")
    if seller_type == "unknown" and seller_name:
        # Heuristic: if seller from data-datalayer is "Private seller", mark as private
        if "private" in (raw.get("dl_seller", "")).lower():
            seller_type = "private"
        else:
            seller_type = "dealer"

    return {
        "provider": "nettiauto",
        "make": brand,
        "model": model,
        "variant": variant,
        "price": price,
        "price_eur": price,
        "price_original": price,
        "currency": "EUR",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "drive_type": drive_type,
        "country": "FI",
        "city": city,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "steering_side": "LHD",
        "source_url": source_url,
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape Nettiauto listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("nettiauto")
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

            log.info("Scraping Nettiauto for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = f"{BASE_URL}/en/{slug}/vaihtoautot?page={page_num}"
                safe_navigate(page, url)
                time.sleep(2)

                if not cookies_dismissed:
                    _dismiss_nettiauto_cookies(page)
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

                log.info("[nettiauto] %s page %d: %d items (%d new), total: %d",
                         brand_name, page_num, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "nettiauto")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "nettiauto")
        log.info("Nettiauto scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
