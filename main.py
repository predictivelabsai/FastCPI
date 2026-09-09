import os
from fasthtml.common import *
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from components.layout import app_styles, Page
from pages.home import home_page
from pages.about import about_page
from pages.contact import contact_page
from pages.legal import delete_account_page, privacy_page

from starlette.responses import JSONResponse as _JSONResponse

from db import init_db

app, rt = fast_app(
    hdrs=(app_styles(),),
    secret_key=os.environ.get('APP_SECRET', 'carhero-app-2026'),
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@rt("/health")
def health():
    return _JSONResponse({"status": "ok"})


# --- Language switching ---

@rt('/set-lang/{code}')
def set_language(code: str, sess):
    from utils.i18n import set_lang, LANGUAGES
    if code in LANGUAGES:
        set_lang(sess, code)
    return RedirectResponse('/', status_code=303)


# --- Public pages ---

@rt
def index(sess):
    return Page(home_page(sess=sess), active='home', sess=sess)

@rt
def about(sess):
    return Page(about_page(), active='about', title='About', sess=sess)

@rt
def contact(sess):
    return Page(contact_page(), active='contact', title='Contact', sess=sess)

@rt
def privacy(sess):
    return Page(privacy_page(), title='Privacy Policy', sess=sess)

@rt('/delete-account')
def delete_account(sess):
    return Page(delete_account_page(), title='Delete Account', sess=sess)


# --- Chat routes (Phase 5) ---

from chat.routes import register_chat_routes
register_chat_routes(rt)

# --- Market Map + Analytics (Phase 6) ---

from chat.market_map import register_market_map_routes
register_market_map_routes(rt)

from chat.analytics import register_analytics_routes
register_analytics_routes(rt)

# --- Auth routes ---

from auth.routes import register_auth_routes
register_auth_routes(rt)

# --- Admin routes ---

from admin.routes import register_admin_routes
register_admin_routes(rt)

# --- Favorites + Saved Searches + Garage ---

from chat.favorites import register_favorites_routes
register_favorites_routes(rt)

from chat.garage import register_garage_routes
register_garage_routes(rt)

from chat.daily_scan import register_daily_scan_routes
register_daily_scan_routes(rt)


# --- Scraper + Daily digest scheduler ---

SCRAPE_PROVIDERS = [
    "autoscout24", "autotrader", "autohero", "mobile_de", "theparking",
    "auto24_ee", "auto24_lt", "auto24_lv", "blocket",
    "otomoto", "coches", "marktplaats", "nettiauto", "bilbasen",
    "donedeal", "finn", "standvirtual", "autovit", "collectingcars",
]


def _start_scrape_and_digest():
    """Background daemon: scrape all providers nightly, load to DB, then send digest.

    Timeline each day:
        SCRAPE_HOUR (default 02:00 UTC)  →  run all scrapers (sequential, ~2-3h)
        after scrape completes           →  load checkpoint JSONs into DB
        after load completes             →  mark stale listings (not seen this run)
        after cleanup                    →  send daily deals digest to all users
    """
    import threading
    import time as _time
    from datetime import datetime, timedelta

    SCRAPE_HOUR = int(os.environ.get("SCRAPE_HOUR", "2"))

    def _run_scrapers():
        from scripts.scrape_cars import get_scraper
        succeeded, failed_list = 0, []
        for provider in SCRAPE_PROVIDERS:
            try:
                print(f"INFO:     [scheduler] Scraping {provider}...", flush=True)
                scraper = get_scraper(provider)
                scraper(headless=True, limit=0, brand=None)
                succeeded += 1
            except Exception as e:
                print(f"ERROR:    [scheduler] Scraper {provider} failed: {e}", flush=True)
                failed_list.append(provider)
        print(f"INFO:     [scheduler] Scrape done: {succeeded} ok, {len(failed_list)} failed ({', '.join(failed_list) or 'none'})", flush=True)
        return succeeded

    def _load_to_db():
        from scripts.scrape_cars import load_to_db
        total = 0
        for provider in SCRAPE_PROVIDERS:
            try:
                total += load_to_db(provider)
            except Exception as e:
                print(f"ERROR:    [scheduler] DB load {provider} failed: {e}", flush=True)
        print(f"INFO:     [scheduler] Loaded {total} new/updated listings to DB", flush=True)
        return total

    def _mark_stale():
        """Mark listings not refreshed in 7 days as stale."""
        try:
            from db import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                result = conn.execute(text("""
                    UPDATE carhero.car_listings
                    SET status = 'stale'
                    WHERE status = 'active'
                      AND scraped_at < NOW() - INTERVAL '7 days'
                """))
                conn.commit()
                print(f"INFO:     [scheduler] Marked {result.rowcount} stale listings", flush=True)
        except Exception as e:
            print(f"ERROR:    [scheduler] Stale cleanup failed: {e}", flush=True)

    def _run_digest():
        try:
            from scripts.daily_deals import main as digest_main
            import sys
            sys.argv = ["daily_deals", "--all"]
            digest_main()
        except Exception as e:
            print(f"ERROR:    [scheduler] Digest error: {e}", flush=True)

    def _loop():
        while True:
            now = datetime.now()
            target = now.replace(hour=SCRAPE_HOUR, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            print(f"INFO:     [scheduler] Next scrape: {target.strftime('%Y-%m-%d %H:%M')} ({wait/3600:.1f}h)", flush=True)
            _time.sleep(wait)

            print(f"INFO:     [scheduler] === Nightly pipeline starting ===", flush=True)

            print(f"INFO:     [scheduler] Step 1/5: Scraping...", flush=True)
            scraped = _run_scrapers()

            print(f"INFO:     [scheduler] Step 2/5: Loading to DB...", flush=True)
            loaded = _load_to_db()

            print(f"INFO:     [scheduler] Step 3/5: Enriching variants...", flush=True)
            try:
                from scripts.enrich_variants import enrich_listings
                enrich_listings()
            except Exception as e:
                print(f"ERROR:    [scheduler] Variant enrichment failed: {e}", flush=True)

            print(f"INFO:     [scheduler] Step 4/5: Cleaning stale listings...", flush=True)
            _mark_stale()

            print(f"INFO:     [scheduler] Step 5/5: Sending digest...", flush=True)
            _run_digest()

            print(f"INFO:     [scheduler] === Nightly pipeline complete ===", flush=True)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


# --- Mount FastAPI mobile API at /api/v1 (optional) ---

_api_status = {"mounted": False, "error": None}
try:
    from api.app import api_router
    app.mount("/api/v1", api_router)
    _api_status["mounted"] = True
    print("INFO:     Mobile API mounted at /api/v1 (docs: /api/v1/docs)")
except ImportError as e:
    _api_status["error"] = f"ImportError: {e}"
    print("INFO:     FastAPI not installed — mobile API disabled (monolith mode)")
except Exception as e:
    _api_status["error"] = f"{type(e).__name__}: {e}"
    print(f"ERROR:    Failed to mount mobile API: {e}")

@rt("/api-status")
def api_status():
    return _JSONResponse(_api_status)


# --- Initialize DB on startup ---

@app.on_event("startup")
async def startup():
    try:
        init_db()
    except Exception as e:
        print(f"DB init warning: {e}")

    if os.environ.get("DIGEST_ENABLED", "1") == "1":
        _start_scrape_and_digest()


serve(port=int(os.environ.get('PORT', 5011)), reload=False)
