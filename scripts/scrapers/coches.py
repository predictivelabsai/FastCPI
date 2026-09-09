"""Coches.net scraper — Spain's #1 car marketplace.

Coches.net is part of the Adevinta group and lists used and new cars
across Spain. Listings are rendered server-side in card elements with
structured price, attributes (fuel, year, mileage, power, location),
and image galleries.

URL pattern:
    https://www.coches.net/{brand}/segunda-mano/?pg=1

Pagination via ?pg=N.
"""

from __future__ import annotations

import logging
import re
import time

from scripts.scrapers.base import (
    PREMIUM_BRANDS,
    parse_price, parse_mileage,
    dismiss_cookies, save_checkpoint, load_checkpoint,
    deduplicate, safe_navigate,
)

log = logging.getLogger(__name__)

from utils.config import get_brand_slugs
BRAND_SLUGS = get_brand_slugs("coches")

BASE_URL = "https://www.coches.net"
MAX_PAGES = 50  # practical limit per brand to avoid bot detection


def _setup_browser_es(headless: bool = True):
    """Launch Chromium with Spanish locale for coches.net.

    Uses Chrome's new headless mode (``--headless=new``) which shares the
    same rendering pipeline as headed Chrome, making it much harder to
    fingerprint.  Combined with ``--disable-blink-features=AutomationControlled``
    this avoids Adevinta's bot detection on coches.net.
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--headless=new",
        ],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="es-ES",
        viewport={"width": 1366, "height": 768},
        timezone_id="Europe/Madrid",
        extra_http_headers={
            "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    page = ctx.new_page()

    # Remove the navigator.webdriver flag that Playwright sets
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        delete navigator.__proto__.webdriver;
    """)

    return pw, browser, ctx, page


def _scroll_to_load(page) -> None:
    """Scroll down the page progressively to trigger lazy-loaded listings."""
    for i in range(8):
        page.evaluate(f"window.scrollTo(0, {(i + 1) * 1500})")
        time.sleep(0.5)
    # Scroll back to top
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.3)


def _extract_listings(page) -> list[dict]:
    """Extract all listing cards from the current page via DOM queries."""
    return page.evaluate("""() => {
        const cards = document.querySelectorAll('.mt-CardAd.mt-CardBasic');
        return [...cards].map(el => {
            // Title and detail URL
            const titleLink = el.querySelector('.mt-CardAd-infoHeaderTitleLink');
            const title = titleLink ? titleLink.textContent.trim() : '';
            const href = titleLink ? titleLink.getAttribute('href') || '' : '';

            // Price
            const priceEl = el.querySelector('.mt-CardAdPrice-cashAmount');
            const priceText = priceEl ? priceEl.textContent.trim() : '';

            // Attributes: fuel, year, mileage, power, location
            // Some items may contain eco-label images; we only want text nodes
            const attrEls = el.querySelectorAll('.mt-CardAd-attrItem');
            const attrs = [...attrEls].map(a => {
                // Skip items that are just images (eco labels)
                if (a.querySelector('img') && !a.textContent.trim()) return null;
                return a.textContent.trim();
            }).filter(a => a && a.length > 0);

            // Images (skip eco-label svgs and financing logos)
            const imgEls = el.querySelectorAll('img.sui-AtomImage-image');
            const imageUrls = [...imgEls]
                .map(img => img.src || img.getAttribute('data-src') || '')
                .filter(s => s && s.includes('ccdn.es/cnet') && !s.includes('.svg'));

            // Seller type: check for "Profesional" badge
            const tagArea = el.querySelector('.mt-CardAd-tags');
            const tagText = tagArea ? tagArea.textContent.trim() : '';
            const isProfessional = tagText.toLowerCase().includes('profesional');

            return {
                title,
                href,
                price_text: priceText,
                attrs,
                image_urls: imageUrls,
                is_professional: isProfessional,
            };
        }).filter(item => item.title && item.price_text);
    }""")


def _parse_listing(raw: dict, brand: str) -> dict:
    """Convert raw JS-extracted data into a normalized listing dict."""
    title = raw.get("title", "")

    # Split title into model and variant
    # Title format: "BMW Serie 3 320d Auto." or "Mercedes-Benz Clase A 180d"
    # "Serie X" and "Clase X" are two-word model names common in Spain
    title_lower = title.lower()
    brand_lower = brand.lower()
    if title_lower.startswith(brand_lower):
        remainder = title[len(brand):].strip()
    else:
        remainder = title

    # Handle two-word model prefixes: "Serie 3", "Clase A", "Clase E", etc.
    two_word_match = re.match(r"^((?:Serie|Clase|Class)\s+\S+)\s*(.*)", remainder, re.IGNORECASE)
    if two_word_match:
        model = two_word_match.group(1)
        variant = two_word_match.group(2)
    else:
        parts = remainder.split(" ", 1)
        model = parts[0] if parts else remainder
        variant = parts[1] if len(parts) > 1 else ""

    # Price — format is "26.000 €" (period as thousands separator, EUR)
    price_text = raw.get("price_text", "")
    price = parse_price(price_text, "EUR")

    # Attributes: typically [fuel_type, year, mileage, power, location]
    # But some may have eco-label first, so we parse by pattern
    attrs = raw.get("attrs", [])
    fuel_type = None
    year = None
    mileage_km = None
    power_hp = None
    location = None

    FUEL_TYPES = {
        "diesel", "gasolina", "eléctrico", "electrico", "híbrido",
        "hibrido", "gas", "glp", "gnc", "gas natural",
        "gasolina/eléctrico", "diésel/eléctrico",
    }

    for attr in attrs:
        attr_lower = attr.lower().strip()

        # Year: 4-digit number between 1990-2030
        if re.match(r"^\d{4}$", attr_lower) and 1990 <= int(attr_lower) <= 2030:
            year = int(attr_lower)
        # Mileage: contains "km"
        elif "km" in attr_lower:
            mileage_km = parse_mileage(attr)
        # Power: contains "cv" (caballos de vapor = hp)
        elif "cv" in attr_lower:
            hp_match = re.search(r"(\d+)", attr)
            if hp_match:
                power_hp = int(hp_match.group(1))
        # Fuel type
        elif attr_lower in FUEL_TYPES or any(f in attr_lower for f in FUEL_TYPES):
            fuel_type = attr.strip()
        # Location: anything else that's a word (not a number pattern)
        elif re.match(r"^[A-ZÁÉÍÓÚÑa-záéíóúñ\s\-/]+$", attr.strip()):
            location = attr.strip()

    # Normalize fuel type to English
    FUEL_MAP = {
        "diesel": "Diesel",
        "diésel": "Diesel",
        "gasolina": "Petrol",
        "eléctrico": "Electric",
        "electrico": "Electric",
        "híbrido": "Hybrid",
        "hibrido": "Hybrid",
        "gasolina/eléctrico": "Hybrid",
        "diésel/eléctrico": "Hybrid",
        "gas": "LPG",
        "glp": "LPG",
        "gnc": "CNG",
        "gas natural": "CNG",
    }
    if fuel_type:
        fuel_type = FUEL_MAP.get(fuel_type.lower(), fuel_type)

    # Compute power_kw from hp
    power_kw = int(power_hp / 1.35962) if power_hp else None

    # Build source URL
    href = raw.get("href", "")
    source_url = f"{BASE_URL}{href}" if href and not href.startswith("http") else href

    # Seller type
    seller_type = "dealer" if raw.get("is_professional") else "private"

    return {
        "provider": "coches",
        "make": brand,
        "model": model,
        "variant": variant or None,
        "price": price,
        "price_eur": price,
        "price_original": price,
        "currency": "EUR",
        "year": year,
        "registration_str": str(year) if year else None,
        "mileage_km": mileage_km,
        "fuel_type": fuel_type,
        "power_hp": power_hp,
        "power_kw": power_kw,
        "power_str": f"{power_hp} cv" if power_hp else None,
        "country": "ES",
        "city": location,
        "seller_type": seller_type,
        "seller_name": None,
        "steering_side": "LHD",
        "source_url": source_url,
        "image_urls": raw.get("image_urls") or [],
        "condition": "used",
    }


def scrape(headless: bool = True, limit: int = 0, brand: str | None = None):
    """Scrape coches.net listings for premium brands.

    Args:
        headless: Run browser in headless mode.
        limit: Max listings per brand (0 = unlimited).
        brand: Specific brand to scrape, or None for all.
    """
    listings = load_checkpoint("coches")
    seen_urls = {l.get("source_url") for l in listings if l.get("source_url")}

    brands = [brand] if brand else PREMIUM_BRANDS
    pw, browser, ctx, page = _setup_browser_es(headless=headless)

    try:
        cookies_dismissed = False

        for brand_name in brands:
            slug = BRAND_SLUGS.get(brand_name)
            if not slug:
                log.warning("No slug for brand %s, skipping", brand_name)
                continue

            if brand_name != brands[0]:
                pause = 60 + (hash(brand_name) % 30)
                log.info("Pausing %ds between brands to avoid bot detection...", pause)
                time.sleep(pause)

            log.info("Scraping coches.net for %s...", brand_name)
            brand_count = 0

            for page_num in range(1, MAX_PAGES + 1):
                url = f"{BASE_URL}/{slug}/segunda-mano/?pg={page_num}"
                safe_navigate(page, url)
                time.sleep(3)

                if not cookies_dismissed:
                    # Dismiss Didomi cookie consent
                    try:
                        btn = page.locator('button:has-text("Aceptar y cerrar")').first
                        if btn.is_visible(timeout=3000):
                            btn.click()
                            time.sleep(1)
                            cookies_dismissed = True
                    except Exception:
                        pass
                    if not cookies_dismissed:
                        dismiss_cookies(page)
                        cookies_dismissed = True
                    time.sleep(1)

                # Scroll to load lazy-loaded listing cards
                _scroll_to_load(page)

                # Check for bot detection page
                try:
                    body_text = page.evaluate("() => document.body.innerText")
                    if "algo no va bien" in body_text.lower() or "eres un bot" in body_text.lower():
                        log.warning("Bot detection triggered on page %d, waiting and retrying...", page_num)
                        time.sleep(30)
                        safe_navigate(page, url)
                        time.sleep(5)
                        body_text = page.evaluate("() => document.body.innerText")
                        if "algo no va bien" in body_text.lower():
                            log.error("Bot detection persists, stopping brand %s", brand_name)
                            break
                except Exception:
                    pass

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

                log.info("[coches] %s page %d/%d: %d items (%d new), total: %d",
                         brand_name, page_num, MAX_PAGES, len(raw_items), new_count, len(listings))

                if limit and brand_count >= limit:
                    log.info("Reached limit of %d for %s", limit, brand_name)
                    break

                if page_num % 10 == 0:
                    save_checkpoint(listings, "coches")

                time.sleep(3)

        listings = deduplicate(listings)
        save_checkpoint(listings, "coches")
        log.info("Coches.net scrape complete: %d listings", len(listings))

    finally:
        browser.close()
        pw.stop()

    return listings
