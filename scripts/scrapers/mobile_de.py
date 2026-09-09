"""mobile.de scraper — Germany's largest car marketplace.

Uses German formatting (period = thousands separator) and brand codes in URLs.
Requires Firefox via Playwright to bypass Akamai Bot Manager anti-bot protection.

Listings are <a> tags with data-testid="result-listing-N" containing:
  - h2 with model/variant spans (class "eO87w" and "dc_Br")
  - [data-testid="price-label"] for price text
  - [data-testid="listing-details-attributes"] for specs string
  - [data-testid="seller-info"] for seller/location info
  - imgs with data-testid="result-listing-image-*" for images

URL pattern:
    https://suchen.mobile.de/fahrzeuge/search.html?dam=false&isSearchRequest=true
        &ms={brand_code}%3B%3B%3B&sb=p&sd=d&s=Car&vc=Car&pageNumber=1

Specs string format: "EZ 10/2022 • 134.287 km • 250 kW (340 PS) • Benzin"
Cookie consent: button "Einverstanden"
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
BRAND_CODES = get_brand_slugs("mobile_de")

BASE_URL = "https://suchen.mobile.de"
MAX_PAGES = 50


def _build_search_url(brand_code: str, page: int = 1) -> str:
    return (
        f"{BASE_URL}/fahrzeuge/search.html?"
        f"dam=false&isSearchRequest=true"
        f"&ms={brand_code}%3B%3B%3B"
        f"&sb=p&sd=d&s=Car&vc=Car"
        f"&pageNumber={page}"
    )


def _extract_listings(page) -> list[dict]:
    """Extract listing data from mobile.de search results via JS.

    Listings are <a data-testid="result-listing-N"> elements.
    Each contains structured sub-elements accessed by data-testid.
    """
    return page.evaluate("""() => {
        const links = document.querySelectorAll('a[data-testid^="result-listing-"]');
        const results = [];
        const seen = new Set();

        for (const el of links) {
            const testId = el.getAttribute('data-testid');
            // Skip image-only test ids (e.g. "result-listing-image-1")
            if (testId.includes('image')) continue;

            // Title: h2 > span.eO87w (model) + span.dc_Br (variant)
            const h2 = el.querySelector('h2');
            if (!h2) continue;
            // Model span has class "eO87w", variant span has class "dc_Br"
            const modelSpan = h2.querySelector('[class*="eO87w"]');
            const variantSpan = h2.querySelector('[class*="dc_Br"]');
            const modelTitle = modelSpan ? (modelSpan.getAttribute('title') || modelSpan.textContent.trim()) : '';
            const variantTitle = variantSpan ? (variantSpan.getAttribute('title') || variantSpan.textContent.trim()) : '';
            const title = (modelTitle + ' ' + variantTitle).trim();
            if (!title) continue;

            // Price: [data-testid="price-label"]
            const priceEl = el.querySelector('[data-testid="price-label"]');
            const priceText = priceEl ? priceEl.textContent.trim() : '';

            // Specs: [data-testid="listing-details-attributes"]
            const specEl = el.querySelector('[data-testid="listing-details-attributes"]');
            const specText = specEl ? specEl.textContent.trim() : '';

            // Seller info: [data-testid="seller-info"]
            const sellerEl = el.querySelector('[data-testid="seller-info"]');
            let sellerName = '';
            let locationText = '';
            if (sellerEl) {
                // Dealer name is in span with class containing "rjHf7"
                const nameSpan = sellerEl.querySelector('[class*="rjHf7"]');
                sellerName = nameSpan ? nameSpan.textContent.trim() : '';
                // Location is in div with class "Kh0Rn" — text after the dealer info
                const locDiv = sellerEl.querySelector('[class*="Kh0Rn"]');
                if (locDiv) {
                    // Get all direct text nodes (location is a text node child)
                    const walker = document.createTreeWalker(locDiv, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {
                        const txt = node.textContent.trim();
                        // Location pattern: "92245 Kümmersbruck" or "51149 Köln, Privatanbieter"
                        if (/\\d{5}/.test(txt)) {
                            locationText = txt;
                            break;
                        }
                    }
                }
            }

            // Detail URL: the <a> element itself has the href
            let detailUrl = el.href || '';
            if (detailUrl.startsWith('/')) {
                detailUrl = window.location.origin + detailUrl;
            }

            // Deduplicate by URL
            if (detailUrl && seen.has(detailUrl)) continue;
            if (detailUrl) seen.add(detailUrl);

            // Images: img elements with data-testid containing "result-listing-image"
            const imgEls = el.querySelectorAll('img[data-testid^="result-listing-image"]');
            const imageUrls = [];
            for (const img of imgEls) {
                // Prefer highest resolution from srcset
                const srcset = img.getAttribute('srcset') || '';
                if (srcset) {
                    const parts = srcset.split(',').map(s => s.trim());
                    const last = parts[parts.length - 1].split(' ')[0];
                    if (last && !last.includes('placeholder')) imageUrls.push(last);
                } else {
                    const src = img.src || '';
                    if (src && !src.includes('placeholder') && src.includes('classistatic'))
                        imageUrls.push(src);
                }
            }

            if (title && priceText) {
                results.push({
                    title,
                    model_name: modelTitle,
                    variant_name: variantTitle,
                    price_text: priceText,
                    spec_text: specText,
                    seller_name: sellerName,
                    location_text: locationText,
                    source_url: detailUrl,
                    image_urls: imageUrls,
                });
            }
        }
        return results;
    }""")


def _parse_specs_string(spec_text: str) -> dict:
    """Parse the combined specs string.

    Format: "EZ 10/2022 · 134.287 km · 250 kW (340 PS) · Diesel"
    Separator can be · or • or |
    """
    result = {
        "registration_str": None,
        "mileage_str": None,
        "power_str": None,
        "fuel_type": None,
    }
    if not spec_text:
        return result

    # Split on common separators
    parts = re.split(r"[·•|]", spec_text)
    parts = [p.strip() for p in parts if p.strip()]

    for part in parts:
        part_lower = part.lower()
        if "ez" in part_lower or re.search(r"\d{1,2}/\d{4}", part):
            result["registration_str"] = part
        elif "km" in part_lower and any(c.isdigit() for c in part):
            result["mileage_str"] = part
        elif "kw" in part_lower or "ps" in part_lower:
            result["power_str"] = part
        elif part_lower in ("diesel", "benzin", "elektro", "hybrid",
                            "plug-in-hybrid", "erdgas/cng", "autogas/lpg",
                            "wasserstoff", "ethanol") or \
             part_lower.startswith("hybrid"):
            # Handle composite types like "Hybrid (Benzin/Elektro)"
            result["fuel_type"] = part

    return result


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    # The new DOM provides model_name and variant_name separately.
    # model_name is e.g. "BMW 220 Active Tourer", variant_name is the detail line.
    model_name = raw.get("model_name", "")
    variant_name = raw.get("variant_name", "")

    # Strip brand prefix from model_name: "BMW 220 Active Tourer" → "220 Active Tourer"
    model = ""
    variant = variant_name
    brand_lower = brand.lower().replace("-", " ")
    model_clean = model_name
    if model_name.lower().startswith(brand_lower):
        model_clean = model_name[len(brand):].strip()
    elif brand_lower.split()[0] and model_name.lower().startswith(brand_lower.split()[0]):
        # Handle partial match, e.g. "Mercedes" from "Mercedes-Benz"
        first_word = brand_lower.split()[0]
        model_clean = model_name[len(first_word):].strip()
        # Also strip the hyphenated part if present, e.g. "-Benz"
        if model_clean.startswith("-"):
            rest = model_clean[1:]
            remaining_brand = brand_lower[len(first_word) + 1:]  # e.g. "benz"
            if rest.lower().startswith(remaining_brand):
                model_clean = rest[len(remaining_brand):].strip()

    parts = model_clean.split(" ", 1)
    model = parts[0] if parts else model_clean
    # If variant is empty, use remainder of model_name as variant
    if not variant and len(parts) > 1:
        variant = parts[1]

    # Truncate long variant
    if len(variant) > 200:
        variant = variant[:200]

    # Price (German format)
    price_text = raw.get("price_text", "")
    price = parse_price(price_text, "EUR")

    # Parse specs string: "EZ 03/2023 • 45.331 km • 115 kW (156 PS) • Benzin"
    # May also contain damage info: "Reparierter Unfallschaden • EZ 03/2023 • ..."
    spec_text = raw.get("spec_text", "")
    specs = _parse_specs_string(spec_text)

    mileage_km = parse_mileage(specs["mileage_str"]) if specs["mileage_str"] else None
    power_hp, power_kw = parse_power(specs["power_str"]) if specs["power_str"] else (None, None)
    reg_month, reg_year = parse_registration(specs["registration_str"]) if specs["registration_str"] else (None, None)
    fuel_type = specs.get("fuel_type")

    # Map German fuel types to English
    fuel_map = {
        "benzin": "Petrol",
        "diesel": "Diesel",
        "elektro": "Electric",
        "hybrid": "Hybrid",
        "plug-in-hybrid": "Plug-in Hybrid",
        "erdgas/cng": "CNG",
        "autogas/lpg": "LPG",
        "wasserstoff": "Hydrogen",
        "ethanol": "Ethanol",
    }
    if fuel_type:
        # Handle composite types like "Hybrid (Benzin/Elektro)"
        fuel_lower = fuel_type.lower().split("(")[0].strip()
        fuel_type = fuel_map.get(fuel_lower, fuel_type)

    # Accident-free detection from spec_text (now embedded in specs string)
    spec_lower = spec_text.lower()
    accident_free = "unfallfrei" in spec_lower
    # Note: "Reparierter Unfallschaden" means repaired accident damage (not accident-free)

    # Seller
    seller_name_raw = raw.get("seller_name", "")
    location_text = raw.get("location_text", "")
    seller_type = "private" if "privatanbieter" in (seller_name_raw + location_text).lower() else "dealer"
    seller_name = seller_name_raw if seller_type == "dealer" and seller_name_raw else None

    # Location — extract city and postal code
    # Pattern: "92245 Kümmersbruck" or "51149 Köln, Privatanbieter"
    city = None
    if location_text:
        loc_match = re.match(r"\d{5}\s+(.+?)(?:,|$)", location_text)
        if loc_match:
            city = loc_match.group(1).strip()
        else:
            city = location_text.split(",")[0].strip()

    return {
        "provider": "mobile_de",
        "make": brand,
        "model": model,
        "variant": variant or None,
        "price": price,
        "price_eur": price,
        "price_original": price,
        "currency": "EUR",
        "year": reg_year,
        "registration_str": specs.get("registration_str"),
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "power_hp": power_hp,
        "power_kw": power_kw,
        "power_str": specs.get("power_str"),
        "country": "DE",
        "city": city,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "accident_free": accident_free if accident_free else None,
        "steering_side": "LHD",
        "source_url": raw.get("source_url"),
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def _is_blocked(page) -> bool:
    """Check if the current page is an Akamai block/challenge page."""
    try:
        title = page.title()
        if "Zugriff verweigert" in title or "Access denied" in title:
            return True
        html_snippet = page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
        if "Zugriff verweigert" in html_snippet or "Access denied" in html_snippet:
            return True
    except Exception:
        pass
    return False


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape mobile.de listings for premium brands.

    Uses Firefox to bypass Akamai Bot Manager anti-bot protection.
    Chromium is detected and blocked by mobile.de.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("mobile_de")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    brands = [brand] if brand else PREMIUM_BRANDS
    pw, browser, ctx, page = setup_browser(headless=headless, browser_type="firefox")

    try:
        cookies_dismissed = False

        for brand_name in brands:
            brand_code = BRAND_CODES.get(brand_name)
            if not brand_code:
                log.warning("No brand code for %s, skipping", brand_name)
                continue

            log.info("Scraping mobile.de for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = _build_search_url(brand_code, page_num)
                safe_navigate(page, url)
                time.sleep(5)

                if _is_blocked(page):
                    log.warning("Blocked by Akamai on page %d for %s, waiting 30s...",
                                page_num, brand_name)
                    time.sleep(30)
                    safe_navigate(page, url)
                    time.sleep(5)
                    if _is_blocked(page):
                        log.error("Still blocked after retry for %s, stopping brand",
                                  brand_name)
                        break

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

                log.info("[mobile_de] %s page %d/%d: %d items (%d new), total: %d",
                         brand_name, page_num, MAX_PAGES, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 25 == 0:
                    save_checkpoint(listings, "mobile_de")

                time.sleep(4)

        listings = deduplicate(listings)
        save_checkpoint(listings, "mobile_de")
        log.info("mobile.de scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
