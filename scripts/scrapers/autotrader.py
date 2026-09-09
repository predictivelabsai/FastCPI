"""AutoTrader UK scraper — UK's largest car marketplace.

Requires a postcode to show results. The postcode must be entered via the
on-page form (the URL parameter alone is no longer sufficient). Uses GBP
pricing and miles for mileage, both converted to EUR/km in parsing.

URL pattern:
    https://www.autotrader.co.uk/car-search?make=BMW&sort=price-desc&page=1

Cookie consent: SP Consent iframe with "Accept All" button.
Listings are in <li data-advertid="..."> elements with data-testid attributes
on child elements (search-listing-title, badges-container, etc.).
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    parse_price, convert_to_eur, parse_mileage, parse_power, parse_registration,
    setup_browser, dismiss_cookies, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate,
)

log = logging.getLogger(__name__)

from utils.config import get_brand_slugs
BRAND_PARAMS = get_brand_slugs("autotrader")

POSTCODE = "SW1A 1AA"  # Central London
BASE_URL = "https://www.autotrader.co.uk"
MAX_PAGES = 50


def _build_search_url(brand: str, page: int = 1) -> str:
    make_param = BRAND_PARAMS.get(brand, brand)
    return (
        f"{BASE_URL}/car-search?"
        f"make={make_param.replace(' ', '%20')}"
        f"&price-from=5000"
        f"&sort=price-desc"
        f"&page={page}"
    )


def _submit_postcode(page) -> bool:
    """Fill in the postcode form if AutoTrader asks for one.

    Returns True if the postcode was submitted (and we should wait for
    results to load), False if the form was not present.
    """
    try:
        postcode_input = page.locator("#postcode")
        if postcode_input.count() > 0 and postcode_input.first.is_visible(timeout=2000):
            postcode_input.first.click()
            time.sleep(0.3)
            postcode_input.first.fill(POSTCODE)
            time.sleep(0.5)
            show_btn = page.locator('button:has-text("Show results")')
            if show_btn.count() > 0:
                show_btn.first.click()
                log.debug("Postcode submitted via form")
                return True
    except Exception:
        pass
    return False


def _extract_listings(page) -> list[dict]:
    """Extract listing data from AutoTrader search results via JS.

    Current DOM (as of Jun 2026):
      - Each listing lives in ``<li data-advertid="...">``
      - Title:    ``<a data-testid="search-listing-title">``
      - Subtitle: ``<p data-testid="search-listing-subtitle">``
      - Price:    first ``<span>`` whose text matches ``£N,NNN`` inside the card
      - Specs:    ``<ul data-testid="badges-container"> <li data-testid="mileage|registered_year|...">``
      - Location: ``<span data-testid="search-listing-location">``
      - Images:   ``<img class="...main-image..." src="https://m.atcdn.co.uk/...">``
    """
    return page.evaluate("""() => {
        const items = document.querySelectorAll('li[data-advertid]');
        const results = [];

        for (const el of items) {
            // Title — <a data-testid="search-listing-title">
            // The element contains direct text ("BMW X3") plus a hidden
            // <span> with variant + price for screen readers.  Extract
            // only the direct text nodes to get the clean title.
            const titleEl = el.querySelector('[data-testid="search-listing-title"]');
            if (!titleEl) continue;

            const titleParts = [];
            for (const node of titleEl.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const t = node.textContent.trim();
                    if (t) titleParts.push(t);
                }
            }
            const title = titleParts.join(' ') || titleEl.textContent.trim();
            const detailUrl = titleEl.href || '';

            // Subtitle (variant detail) — <p data-testid="search-listing-subtitle">
            const subtitleEl = el.querySelector('[data-testid="search-listing-subtitle"]');
            const subtitle = subtitleEl ? subtitleEl.textContent.trim() : '';

            // Price — first span containing a £ amount
            let priceText = '';
            const spans = el.querySelectorAll('span');
            for (const sp of spans) {
                const t = sp.textContent.trim();
                if (/^£[\\d,]+$/.test(t)) {
                    priceText = t;
                    break;
                }
            }

            // Specs from badges container
            const badgeContainer = el.querySelector('[data-testid="badges-container"]');
            const specs = [];
            const specData = {};
            if (badgeContainer) {
                const badges = badgeContainer.querySelectorAll('li[data-testid]');
                for (const badge of badges) {
                    const testId = badge.getAttribute('data-testid');
                    const text = badge.textContent.trim();
                    specs.push(text);
                    specData[testId] = text;
                }
            }

            // Location — <span data-testid="search-listing-location">
            const locEl = el.querySelector('[data-testid="search-listing-location"]');
            const locationText = locEl ? locEl.textContent.trim() : '';

            // Attention grabber (extra info like "1-OWNER, CARPLAY, LED")
            const grabberEl = el.querySelector('[data-testid="search-listing-attention-grabber"]');
            const attentionGrabber = grabberEl ? grabberEl.textContent.trim() : '';

            // Images — main-image class, hosted on m.atcdn.co.uk
            const imgEls = el.querySelectorAll('img[class*="main-image"]');
            const imageUrls = [...imgEls]
                .map(img => img.src)
                .filter(s => s && !s.includes('placeholder'));

            if (title && priceText) {
                results.push({
                    title,
                    subtitle,
                    price_text: priceText,
                    specs,
                    spec_data: specData,
                    location_text: locationText,
                    attention_grabber: attentionGrabber,
                    source_url: detailUrl,
                    image_urls: imageUrls,
                });
            }
        }
        return results;
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict.

    The new DOM provides structured spec data via ``data-testid`` badges
    (``mileage``, ``registered_year``, etc.) instead of free-text spec
    lists.  The title now contains only make + model (e.g. "BMW 2 Series
    Gran Coupe") while the variant/engine detail lives in ``subtitle``
    (e.g. "2.0 220d Sport (LCP) Auto Euro 6 (s/s) 4dr").
    """
    title = raw.get("title", "")
    subtitle = raw.get("subtitle", "")

    # --- Model & variant --------------------------------------------------
    # Title format: "BMW 2 Series Gran Coupe"
    # Subtitle format: "2.0 220d Sport (LCP) Auto Euro 6 (s/s) 4dr"
    model = ""
    variant = subtitle or None
    title_lower = title.lower()
    brand_lower = brand.lower().replace("-", " ")
    if title_lower.startswith(brand_lower):
        remainder = title[len(brand):].strip()
    elif title_lower.startswith(brand_lower.split()[0]):
        remainder = title[len(brand):].strip()
    else:
        remainder = title

    parts = remainder.split(",")[0].strip()
    model_parts = parts.split(" ")
    if model_parts:
        model = model_parts[0]
        if len(model_parts) > 1 and model_parts[1].lower() in ("series", "class"):
            model = f"{model_parts[0]} {model_parts[1]}"
            # Any remaining words in the title are part of the model name
            # (e.g. "Gran Coupe"), append to model
            if len(model_parts) > 2:
                model = f"{model} {' '.join(model_parts[2:])}"
        elif len(model_parts) > 1:
            model = parts  # e.g. "Z8", "M3", "iX xDrive50"

    # --- Price (GBP) ------------------------------------------------------
    price_text = raw.get("price_text", "")
    price_gbp = parse_price(price_text, "GBP")
    price_eur = convert_to_eur(price_gbp, "GBP")

    # --- Specs from structured badge data ---------------------------------
    spec_data = raw.get("spec_data", {})
    specs = raw.get("specs", [])

    # Mileage — badge with data-testid="mileage", text like "75,172 miles"
    mileage_str = spec_data.get("mileage", "")
    # Year — badge with data-testid="registered_year", text like "2021 (21 reg)"
    year_str = spec_data.get("registered_year", "")

    # Fuel type and transmission are not in badges; try to parse from subtitle
    fuel_type = ""
    transmission = ""
    body_type = ""
    if subtitle:
        sub_lower = subtitle.lower()
        # Transmission from subtitle (e.g. "Auto", "Manual")
        if " auto " in f" {sub_lower} " or sub_lower.endswith(" auto"):
            transmission = "Automatic"
        elif "manual" in sub_lower:
            transmission = "Manual"
        elif "semi-auto" in sub_lower:
            transmission = "Semi-automatic"

    # Fall back to scanning free-text specs for fuel/body if present
    for spec in specs:
        spec_lower = spec.lower()
        if not fuel_type and spec_lower in (
            "petrol", "diesel", "electric", "hybrid",
            "plug-in hybrid", "petrol/electric", "diesel/electric",
        ):
            fuel_type = spec
        if not body_type and spec_lower in (
            "hatchback", "saloon", "estate", "suv", "coupe",
            "convertible", "mpv", "pickup",
        ):
            body_type = spec

    mileage_km = parse_mileage(mileage_str) if mileage_str else None
    _, reg_year = parse_registration(year_str) if year_str else (None, None)

    # --- Condition --------------------------------------------------------
    condition = "used"
    if spec_data.get("brand_new"):
        condition = "new"

    # --- Location ---------------------------------------------------------
    location_text = raw.get("location_text", "")
    city = None
    # Pattern: "Dealer locationRainham (14 miles)" — strip the icon title
    loc_clean = re.sub(r"Dealer\s*location\s*", "", location_text).strip()
    loc_match = re.match(r"(.+?)\s*\(\d+\s*miles?\)", loc_clean)
    if loc_match:
        city = loc_match.group(1).strip()
    elif loc_clean:
        city = loc_clean

    return {
        "provider": "autotrader",
        "make": brand,
        "model": model,
        "variant": variant,
        "price": price_gbp,
        "price_eur": price_eur,
        "price_original": price_gbp,
        "currency": "GBP",
        "year": reg_year,
        "registration_str": year_str or None,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type or None,
        "transmission": transmission or None,
        "body_type": body_type or None,
        "power_hp": None,
        "power_kw": None,
        "country": "GB",
        "city": city,
        "seller_type": "dealer",
        "seller_name": None,
        "steering_side": "RHD",
        "source_url": raw.get("source_url"),
        "image_urls": raw.get("image_urls") or [],
        "condition": condition,
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape AutoTrader UK listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("autotrader")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    brands = [brand] if brand else PREMIUM_BRANDS
    pw, browser, ctx, page = setup_browser(headless=headless)

    try:
        cookies_dismissed = False
        postcode_submitted = False

        for brand_name in brands:
            if brand_name not in BRAND_PARAMS:
                log.warning("No params for brand %s, skipping", brand_name)
                continue

            log.info("Scraping AutoTrader UK for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = _build_search_url(brand_name, page_num)
                safe_navigate(page, url)
                time.sleep(2)

                if not cookies_dismissed:
                    dismiss_cookies(page)
                    cookies_dismissed = True
                    time.sleep(1)

                # AutoTrader now requires postcode to be entered via the
                # on-page form; the URL parameter alone no longer works.
                if not postcode_submitted:
                    if _submit_postcode(page):
                        postcode_submitted = True
                        time.sleep(5)  # wait for results to load
                    else:
                        log.debug("Postcode form not found (may already have results)")

                # If the page still shows the postcode prompt after a brand
                # switch, re-submit the postcode.
                if postcode_submitted and page_num == 1:
                    _submit_postcode(page)
                    time.sleep(3)

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

                log.info("[autotrader] %s page %d/%d: %d items (%d new), total: %d",
                         brand_name, page_num, MAX_PAGES, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 25 == 0:
                    save_checkpoint(listings, "autotrader")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "autotrader")
        log.info("AutoTrader scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
