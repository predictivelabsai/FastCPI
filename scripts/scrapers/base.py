"""Shared utilities for car listing scrapers."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "cars"
DATA_DIR.mkdir(parents=True, exist_ok=True)

from utils.config import get_all_brands

PREMIUM_BRANDS = get_all_brands()

GBP_TO_EUR = 1.17
MILES_TO_KM = 1.60934


def parse_price(text: str, currency: str = "EUR") -> float:
    """Extract numeric price from text.

    Handles:
      '£45,677'        → 45677.0  (GBP, comma thousands)
      '35.890 €'       → 35890.0  (German, period thousands)
      '€ 654,500'      → 654500.0
      '23,995'         → 23995.0
      '€ 9,999,999'    → 9999999.0
    """
    if not text:
        return 0.0
    cleaned = text.strip()

    # Detect German formatting: digits with period as thousands separator
    # Pattern: "35.890" or "1.234.567" (no comma decimal)
    # German format: periods are thousands, no comma present
    german_pattern = re.match(r"^[\s€£]*(\d{1,3}(?:\.\d{3})+)[\s€¹²³]*$", cleaned.replace(",", ""))
    if german_pattern or (currency == "EUR" and "." in cleaned and "," not in cleaned):
        # Check if it looks like German thousands formatting
        nums = re.findall(r"\d{1,3}(?:\.\d{3})+", cleaned)
        if nums:
            return float(nums[0].replace(".", ""))

    # Remove currency symbols, whitespace at edges
    cleaned = re.sub(r"[€£¹²³]", "", cleaned).strip()

    # Standard: commas are thousands separators
    cleaned = cleaned.replace(",", "")

    # Remove any remaining non-numeric chars except decimal point
    cleaned = re.sub(r"[^\d.]", "", cleaned)

    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def convert_to_eur(amount: float, currency: str) -> float:
    """Convert amount to EUR. GBP * 1.17, others pass through."""
    if currency == "GBP":
        return round(amount * GBP_TO_EUR, 2)
    return amount


def parse_mileage(text: str) -> int:
    """Parse mileage text to integer km.

    Handles:
      '9,261 miles'  → 14905  (miles to km)
      '134.287 km'   → 134287 (German thousands)
      '240,000 km'   → 240000 (comma thousands)
      '55000 km'     → 55000
    """
    if not text:
        return 0
    cleaned = text.strip().lower()

    is_miles = "mile" in cleaned

    # Remove unit text
    cleaned = re.sub(r"(miles?|km|mi)", "", cleaned).strip()

    # German formatting: period as thousands separator (e.g. "134.287")
    german_match = re.match(r"^(\d{1,3}(?:\.\d{3})+)$", cleaned.strip())
    if german_match:
        value = int(cleaned.strip().replace(".", ""))
    else:
        # Standard: comma thousands
        cleaned = cleaned.replace(",", "")
        cleaned = re.sub(r"[^\d]", "", cleaned)
        if not cleaned:
            return 0
        value = int(cleaned)

    if is_miles:
        value = int(value * MILES_TO_KM)

    return value


def parse_power(text: str) -> tuple[int | None, int | None]:
    """Parse power string to (hp, kw).

    Handles:
      '250 kW (340 PS)' → (340, 250)
      '94 kW (128 hp)'  → (128, 94)
      '340 PS'           → (340, None)
      '128 hp'           → (128, None)
    """
    if not text:
        return None, None

    hp, kw = None, None

    kw_match = re.search(r"(\d+)\s*kW", text, re.IGNORECASE)
    if kw_match:
        kw = int(kw_match.group(1))

    hp_match = re.search(r"(\d+)\s*(?:PS|hp|bhp|pk)", text, re.IGNORECASE)
    if hp_match:
        hp = int(hp_match.group(1))

    # If we have kW but no hp, compute hp (1 kW ≈ 1.36 hp)
    if kw and not hp:
        hp = int(kw * 1.35962)
    # If we have hp but no kW, compute kW
    if hp and not kw:
        kw = int(hp / 1.35962)

    return hp, kw


def parse_registration(text: str) -> tuple[int | None, int | None]:
    """Parse registration/first-reg text to (month, year).

    Handles:
      '02/1985'         → (2, 1985)
      'EZ 10/2022'      → (10, 2022)
      '2025 (75 reg)'   → (None, 2025)
      '2022'            → (None, 2022)
    """
    if not text:
        return None, None

    cleaned = text.strip()

    # "EZ 10/2022" or "10/2022" or "02/1985"
    m = re.search(r"(\d{1,2})/(\d{4})", cleaned)
    if m:
        return int(m.group(1)), int(m.group(2))

    # "2025 (75 reg)" or bare "2025"
    m = re.search(r"\b(19\d{2}|20[0-3]\d)\b", cleaned)
    if m:
        return None, int(m.group(1))

    return None, None


def setup_browser(headless: bool = True, browser_type: str = "chromium"):
    """Launch Playwright browser and return (playwright, browser, context, page).

    Args:
        headless: Run browser in headless mode.
        browser_type: "chromium" (default) or "firefox".
            Firefox is needed for sites with aggressive bot detection
            (e.g. Akamai Bot Manager on mobile.de).
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()

    if browser_type == "firefox":
        browser = pw.firefox.launch(
            headless=headless,
            firefox_user_prefs={
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
            },
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:130.0) "
                       "Gecko/20100101 Firefox/130.0",
            locale="de-DE",
            viewport={"width": 1920, "height": 1080},
            timezone_id="Europe/Berlin",
            extra_http_headers={
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
    else:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-GB",
            viewport={"width": 1920, "height": 1080},
        )

    page = ctx.new_page()
    return pw, browser, ctx, page


def dismiss_cookies(page):
    """Try to dismiss common cookie consent dialogs across all 4 sites."""
    # AutoTrader UK: SP Consent in iframe
    try:
        iframe_el = page.frame_locator("iframe[title*='SP Consent']")
        btn = iframe_el.locator("button:has-text('Accept All')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(0.5)
            return True
    except Exception:
        pass

    # Blocket.se: SP Consent in iframe
    try:
        iframe_el = page.frame_locator("iframe[title*='Cookie'], iframe[id*='sp_message']")
        btn = iframe_el.locator("button:has-text('Godkänn alla')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(0.5)
            return True
    except Exception:
        pass

    # Finn.no: CMP consent in iframe (title="Cookieinnstillinger")
    try:
        iframe_el = page.frame_locator("iframe[title*='Cookie'], iframe[id*='sp_message']")
        btn = iframe_el.locator("button:has-text('Godta alle')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(0.5)
            return True
    except Exception:
        pass

    # Bilbasen.dk: CMP consent in iframe
    try:
        iframe_el = page.frame_locator("iframe[title*='Cookie']")
        btn = iframe_el.locator("button:has-text('Kun nødvendige')")
        if btn.count() > 0:
            btn.first.click()
            time.sleep(0.5)
            return True
    except Exception:
        pass

    selectors = [
        # mobile.de
        "button:has-text('Einverstanden')",
        # AutoScout24
        '[data-testid="as24-cmp-accept-all-button"]',
        # auto24 Baltic
        "button:has-text('Nõustun')",
        "button:has-text('Sutinku')",
        "button:has-text('Piekrītu')",
        # Blocket.se (non-iframe fallback)
        "button:has-text('Godkänn alla')",
        # Generic
        "button:has-text('Accept All')",
        "button:has-text('Accept all')",
        "button:has-text('Alle akzeptieren')",
        "#onetrust-accept-btn-handler",
        "button:has-text('OK')",
        "button:has-text('Accept')",
        "button:has-text('AGREE')",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click()
                time.sleep(0.5)
                return True
        except Exception:
            continue
    return False


def save_checkpoint(listings: list[dict], provider: str) -> Path:
    """Save listings to JSON checkpoint file."""
    path = DATA_DIR / f"{provider}.json"
    path.write_text(json.dumps(listings, ensure_ascii=False, indent=2, default=str))
    log.info("Checkpoint saved: %s (%d listings)", path, len(listings))
    return path


def load_checkpoint(provider: str) -> list[dict]:
    """Load listings from JSON checkpoint file."""
    path = DATA_DIR / f"{provider}.json"
    if path.exists():
        data = json.loads(path.read_text())
        log.info("Resumed from checkpoint: %s (%d listings)", path, len(data))
        return data
    return []


def deduplicate(listings: list[dict]) -> list[dict]:
    """Deduplicate listings by source_url."""
    seen = set()
    result = []
    for listing in listings:
        url = listing.get("source_url")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        result.append(listing)
    return result


def safe_navigate(page, url: str, timeout: int = 30000):
    """Navigate with retry on timeout."""
    for attempt in range(3):
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return
        except Exception as e:
            if attempt < 2:
                log.warning("Navigate retry %d for %s: %s", attempt + 1, url, e)
                time.sleep(2)
            else:
                raise


def _clean(val: str | None, maxlen: int = 500) -> str | None:
    """Strip HTML tags, whitespace, and truncate."""
    if not val:
        return None
    cleaned = re.sub(r"<[^>]+>", "", val).strip()
    return cleaned[:maxlen] if cleaned else None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None


def listing_to_db_row(listing: dict) -> dict:
    """Normalize a scraped listing dict to match the car_listings DB columns."""
    # Parse year from registration if not set
    year = listing.get("year")
    if isinstance(year, str):
        _, y = parse_registration(year)
        year = y
    elif isinstance(year, float):
        year = int(year) if year > 1900 else None

    # Parse price
    price_original = listing.get("price_original") or listing.get("price", 0)
    currency = listing.get("currency", "EUR")
    if isinstance(price_original, str):
        price_original = parse_price(price_original, currency)
    price_eur = listing.get("price_eur")
    if price_eur is None:
        price_eur = convert_to_eur(float(price_original or 0), currency)

    # Parse mileage
    mileage = listing.get("mileage_km")
    if isinstance(mileage, str):
        mileage = parse_mileage(mileage)

    # Parse power
    power_hp = listing.get("power_hp")
    power_kw = listing.get("power_kw")
    if power_hp is None and power_kw is None and listing.get("power_str"):
        power_hp, power_kw = parse_power(listing["power_str"])

    # Registration date
    reg_date = listing.get("first_registration_date")
    if reg_date is None and listing.get("registration_str"):
        month, reg_year = parse_registration(listing["registration_str"])
        if reg_year:
            month = month or 1
            reg_date = f"{reg_year}-{month:02d}-01"
            if year is None:
                year = reg_year

    make = _clean(listing.get("make"), 100) or "Unknown"
    model = _clean(listing.get("model"), 100) or "Unknown"
    variant = _clean(listing.get("variant"), 200)

    # Tesla: many providers split "Model 3" into model="Model" variant="3 ..."
    if make == "Tesla" and model and model.lower() in ("model", "models"):
        if variant:
            for prefix, full in [("3", "Model 3"), ("Y", "Model Y"), ("S", "Model S"), ("X", "Model X")]:
                if variant.startswith(prefix):
                    model = full
                    variant = variant[len(prefix):].strip() or None
                    break

    row = {
        "make": make,
        "model": model,
        "variant": variant,
        "generation": _clean(listing.get("generation"), 100),
        "price_eur": price_eur,
        "price_original": price_original,
        "currency": currency,
        "year": year if year and year > 1900 else None,
        "mileage_km": _safe_int(mileage),
        "fuel_type": _clean(listing.get("fuel_type"), 50),
        "transmission": _clean(listing.get("transmission"), 50),
        "body_type": _clean(listing.get("body_type"), 50),
        "engine_size_cc": _safe_int(listing.get("engine_size_cc")),
        "power_hp": _safe_int(power_hp),
        "power_kw": _safe_int(power_kw),
        "torque_nm": _safe_int(listing.get("torque_nm")),
        "drive_type": _clean(listing.get("drive_type"), 20),
        "steering_side": _clean(listing.get("steering_side"), 5),
        "gears": _safe_int(listing.get("gears")),
        "co2_grams": _safe_int(listing.get("co2_grams")),
        "fuel_consumption_l100km": listing.get("fuel_consumption_l100km"),
        "emission_class": _clean(listing.get("emission_class"), 20),
        "doors": _safe_int(listing.get("doors")),
        "seats": _safe_int(listing.get("seats")),
        "exterior_color": _clean(listing.get("exterior_color"), 50),
        "interior_color": _clean(listing.get("interior_color"), 50),
        "interior_material": _clean(listing.get("interior_material"), 50),
        "condition": listing.get("condition", "used"),
        "first_registration_date": reg_date,
        "owners_count": _safe_int(listing.get("owners_count")),
        "accident_free": listing.get("accident_free"),
        "service_history": listing.get("service_history"),
        "features": json.dumps(listing["features"]) if listing.get("features") else None,
        "equipment_packages": json.dumps(listing["equipment_packages"]) if listing.get("equipment_packages") else None,
        "source_url": (listing.get("source_url") or "")[:500] or None,
        "provider": listing.get("provider", "unknown"),
        "country": listing.get("country"),
        "city": _clean(listing.get("city"), 100),
        "seller_type": _clean(listing.get("seller_type"), 20),
        "seller_name": _clean(listing.get("seller_name"), 200),
        "listed_date": listing.get("listed_date"),
        "image_urls": json.dumps(listing["image_urls"]) if listing.get("image_urls") else None,
        "image_count": len(listing.get("image_urls") or []),
        "status": listing.get("status", "active"),
        "canonical_variant": None,
    }
    try:
        from utils.variant_matcher import match_variant
        label = match_variant(
            make=row.get("make", ""),
            model=row.get("model", ""),
            variant=row.get("variant"),
            year=row.get("year"),
        )
        if label:
            row["canonical_variant"] = label
    except Exception:
        pass
    return row
