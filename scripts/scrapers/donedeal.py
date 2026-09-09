"""DoneDeal.ie scraper — Ireland's #1 car marketplace.

DoneDeal serves ~2.2M monthly users. The site is built on Next.js and
embeds structured listing data in a ``__NEXT_DATA__`` JSON blob, which
we extract instead of parsing DOM elements.

URL pattern:
    https://www.donedeal.ie/cars/{Brand}?start=0

Pagination via ?start=N (increments of 30, up to totalPages).

Note: DoneDeal uses Cloudflare protection so we use Firefox to bypass it.
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
BRAND_SLUGS = get_brand_slugs("donedeal")

BASE_URL = "https://www.donedeal.ie"
PAGE_SIZE = 30  # DoneDeal returns 30 ads per page
MAX_PAGES = 50  # Safety cap


def _extract_listings(page) -> tuple[list[dict], dict]:
    """Extract listing data from __NEXT_DATA__ JSON embedded in the page.

    Returns:
        (ads, paging) — list of raw ad dicts and the paging metadata dict.
    """
    raw = page.evaluate("""() => {
        const el = document.getElementById('__NEXT_DATA__');
        if (!el) return null;
        try {
            const data = JSON.parse(el.textContent);
            const props = data.props && data.props.pageProps ? data.props.pageProps : {};
            return {
                ads: props.ads || [],
                paging: props.paging || {},
            };
        } catch (e) {
            return null;
        }
    }""")
    if raw is None:
        return [], {}
    return raw.get("ads", []), raw.get("paging", {})


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert a raw DoneDeal ad dict into a normalized listing dict."""
    title = raw.get("title", "")

    # --- Model / Variant from title -----------------------------------
    # Titles can be:
    #   "BMW 5-Series 520d SE Saloon"
    #   "BMW 116i Auto 2015"
    #   "2016 BMW 430d M Sport Gran Coupe"  (year-first format)
    title_clean = title
    # Strip leading year if present (e.g. "2016 BMW 430d ...")
    year_prefix = re.match(r"^((?:19|20)\d{2})\s+", title_clean)
    if year_prefix:
        title_clean = title_clean[year_prefix.end():]

    title_lower = title_clean.lower()
    brand_lower = brand.lower()
    if title_lower.startswith(brand_lower):
        remainder = title_clean[len(brand):].strip()
    else:
        remainder = title_clean
    parts = remainder.split(" ", 1)
    model = parts[0] if parts else remainder
    variant = parts[1] if len(parts) > 1 else ""

    # --- Price --------------------------------------------------------
    price_info = raw.get("priceInfo", {})
    price_on_request = price_info.get("priceOnRequest", False)
    price_eur = price_info.get("priceInEuro", 0)
    if not price_eur and not price_on_request:
        price_text = price_info.get("price", "")
        price_eur = parse_price(price_text, "EUR")

    # --- metaInfo: ["2015", "1.6 Petrol", "80,389 km"] ---------------
    meta = raw.get("metaInfo", [])
    year = None
    fuel_type = None
    engine_str = None
    mileage_str = None

    for item in meta:
        item_stripped = item.strip()
        # Year: pure 4-digit number
        if re.match(r"^\d{4}$", item_stripped):
            year = int(item_stripped)
        # Mileage: contains "km"
        elif "km" in item_stripped.lower():
            mileage_str = item_stripped
        # Engine + fuel: e.g. "2.0 Diesel", "1.6 Petrol", "Electric"
        else:
            engine_str = item_stripped
            # Extract fuel type from the engine spec
            fuel_match = re.search(
                r"(Diesel(?:\s+Hybrid)?|Petrol(?:\s+Plug-in Hybrid|\s+Hybrid)?|"
                r"Electric|Hybrid|CNG|LPG)",
                item_stripped, re.IGNORECASE,
            )
            if fuel_match:
                fuel_type = fuel_match.group(1).strip()

    # --- Mileage ------------------------------------------------------
    mileage_km = raw.get("mileageInKm")
    if mileage_km is None and mileage_str:
        mileage_km = parse_mileage(mileage_str)

    # --- imageAlt: "BMW 1-Series Hatchback, Petrol, 2015, White" ------
    image_alt = raw.get("imageAlt", "")
    body_type = None
    exterior_color = None
    if image_alt:
        alt_parts = [p.strip() for p in image_alt.split(",")]
        # Pattern: "Make Model BodyType, FuelType, Year, Color"
        if len(alt_parts) >= 1:
            # First part: "BMW 1-Series Hatchback" — extract body type
            first = alt_parts[0]
            body_types = [
                "Hatchback", "Saloon", "Estate", "SUV", "Coupe", "Convertible",
                "Cabriolet", "MPV", "Van", "Pickup", "Limousine", "Roadster",
                "Fastback", "Crossover", "Sports",
            ]
            for bt in body_types:
                if bt.lower() in first.lower():
                    body_type = bt
                    break
        if len(alt_parts) >= 4:
            exterior_color = alt_parts[3].strip() if alt_parts[3].strip() else None

    # --- Seller -------------------------------------------------------
    seller = raw.get("seller", {}) or raw.get("dealer", {})
    seller_type_raw = seller.get("type", "")
    if seller_type_raw == "TRADER" or "Dealership" in seller_type_raw:
        seller_type = "dealer"
    elif seller_type_raw == "PRIVATE" or "Private" in seller_type_raw:
        seller_type = "private"
    else:
        seller_type = "dealer" if raw.get("dealerId") else "private"
    seller_name = seller.get("name")

    # --- Location -----------------------------------------------------
    county = raw.get("county", "")
    county_town = raw.get("countyTown", "")
    city = county_town or county

    # --- Images -------------------------------------------------------
    gallery = raw.get("gallery", {})
    cover = gallery.get("coverImage", {})
    image_urls = []
    # Prefer medium-size images
    img_url = cover.get("medium") or cover.get("large") or cover.get("small")
    if img_url:
        image_urls.append(img_url)

    # --- Source URL ----------------------------------------------------
    source_url = raw.get("friendlyUrl", "")
    if not source_url:
        relative = raw.get("relativeUrl", "")
        if relative:
            source_url = f"{BASE_URL}{relative}"

    # --- Engine power -------------------------------------------------
    power_hp = None
    power_kw = None
    engine_size = engine_str  # e.g. "2.0 Diesel"

    return {
        "provider": "donedeal",
        "make": brand,
        "model": model,
        "variant": variant or None,
        "price": price_eur,
        "price_eur": price_eur if not price_on_request else None,
        "price_original": price_eur if not price_on_request else None,
        "currency": "EUR",
        "year": year,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "body_type": body_type,
        "exterior_color": exterior_color,
        "power_hp": power_hp,
        "power_kw": power_kw,
        "power_str": engine_size,
        "country": "IE",
        "city": city or None,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "steering_side": "RHD",
        "source_url": source_url,
        "image_urls": image_urls,
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape DoneDeal.ie listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("donedeal")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    brands = [brand] if brand else PREMIUM_BRANDS
    # Use Firefox to bypass Cloudflare
    pw, browser, ctx, page = setup_browser(headless=headless, browser_type="firefox")

    try:
        cookies_dismissed = False

        for brand_name in brands:
            slug = BRAND_SLUGS.get(brand_name)
            if not slug:
                log.warning("No slug for brand %s, skipping", brand_name)
                continue

            log.info("Scraping DoneDeal for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                start = (page_num - 1) * PAGE_SIZE
                url = f"{BASE_URL}/cars/{slug}?start={start}"
                safe_navigate(page, url)
                time.sleep(3)

                if not cookies_dismissed:
                    dismiss_cookies(page)
                    cookies_dismissed = True
                    time.sleep(1)

                try:
                    raw_items, paging = _extract_listings(page)
                except Exception as e:
                    log.error("Failed to extract listings on page %d: %s", page_num, e)
                    raw_items, paging = [], {}

                total_pages = paging.get("totalPages", 0)

                if not raw_items:
                    log.info("No items on page %d for %s, stopping", page_num, brand_name)
                    break

                new_count = 0
                for raw in raw_items:
                    # Skip price-on-request listings with zero price
                    price_info = raw.get("priceInfo", {})
                    if price_info.get("priceOnRequest", False):
                        continue

                    listing = _parse_listing(raw, brand_name)
                    src = listing.get("source_url")
                    if src and src in seen_urls:
                        continue
                    listings.append(listing)
                    if src:
                        seen_urls.add(src)
                    new_count += 1
                    brand_count += 1

                log.info("[donedeal] %s page %d/%d: %d items (%d new), total: %d",
                         brand_name, page_num, total_pages or "?",
                         len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if total_pages and page_num >= total_pages:
                    log.info("Reached last page %d for %s", page_num, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "donedeal")

                time.sleep(2)

        listings = deduplicate(listings)
        save_checkpoint(listings, "donedeal")
        log.info("DoneDeal scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
