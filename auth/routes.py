"""Authentication routes: register, login, verify, forgot password, reset, profile, Google OAuth."""

from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timedelta

import requests as http_requests

from fasthtml.common import (
    Html, Head, Body, Div, H2, H3, P, A, Button, Form, Input, Label, Script, NotStr,
)
from starlette.responses import RedirectResponse, JSONResponse

from auth.utils import (
    hash_password, verify_password, generate_token,
    send_verification_email, send_reset_email,
)
from chat.layout import _head
from utils.session import get_user_email, set_user_email, get_user_id, set_user_id, clear_user

log = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("SERVICE_URL_CARHERO", "https://carhero.chat") + "/auth/google/callback"

SCHEMA = "carhero"


def _get_db():
    from db import SessionLocal
    return SessionLocal()


def register_auth_routes(rt):

    @rt("/auth/register")
    def post(request):
        """Register a new user."""
        import asyncio
        return asyncio.ensure_future(_register(request))

    @rt("/auth/register", methods=["POST"])
    async def auth_register(request):
        from sqlalchemy import text
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        password = form.get("password") or ""
        name = (form.get("name") or "").strip()

        if not email or not password:
            return JSONResponse({"error": "Email and password are required"}, status_code=400)
        if len(password) < 6:
            return JSONResponse({"error": "Password must be at least 6 characters"}, status_code=400)

        db = _get_db()
        try:
            existing = db.execute(
                text(f"SELECT id, password_hash FROM {SCHEMA}.chat_users WHERE email = :email"),
                {"email": email},
            ).fetchone()

            if existing and existing.password_hash:
                return JSONResponse({"error": "An account with this email already exists"}, status_code=409)

            token = generate_token()
            pw_hash = hash_password(password)

            if existing:
                db.execute(text(f"""
                    UPDATE {SCHEMA}.chat_users
                    SET password_hash = :pw, name = :name, verify_token = :token, is_verified = FALSE
                    WHERE email = :email
                """), {"pw": pw_hash, "name": name, "token": token, "email": email})
            else:
                db.execute(text(f"""
                    INSERT INTO {SCHEMA}.chat_users (email, password_hash, name, verify_token, is_verified)
                    VALUES (:email, :pw, :name, :token, FALSE)
                """), {"email": email, "pw": pw_hash, "name": name, "token": token})
            db.commit()
        finally:
            db.close()

        send_verification_email(email, token, name)
        return JSONResponse({"ok": True, "message": "Check your email to verify your account"})

    @rt("/auth/verify/{token}")
    def auth_verify(token: str, sess):
        from sqlalchemy import text
        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id, email FROM {SCHEMA}.chat_users WHERE verify_token = :token"),
                {"token": token},
            ).fetchone()
            if not row:
                return Html(_head("Verification"), Body(
                    Div(H2("Invalid or expired link"), P("Please register again."),
                        cls="max-w-md mx-auto mt-20 text-center"),
                    cls="bg-white font-sans",
                ))
            db.execute(text(f"""
                UPDATE {SCHEMA}.chat_users
                SET is_verified = TRUE, verify_token = NULL
                WHERE id = :id
            """), {"id": row.id})
            db.commit()

            set_user_email(sess, row.email)
            set_user_id(sess, row.id)
        finally:
            db.close()

        return RedirectResponse("/app", status_code=303)

    @rt("/auth/login", methods=["POST"])
    async def auth_login(request, sess):
        from sqlalchemy import text
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        password = form.get("password") or ""

        if not email or not password:
            return JSONResponse({"error": "Email and password are required"}, status_code=400)

        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id, email, password_hash, is_verified, name FROM {SCHEMA}.chat_users WHERE email = :email"),
                {"email": email},
            ).fetchone()
        finally:
            db.close()

        if not row:
            return JSONResponse({"error": "Invalid email or password"}, status_code=401)

        if not row.password_hash:
            return JSONResponse({"error": "no_password", "message": "Please set a password for your account"}, status_code=401)

        if not verify_password(password, row.password_hash):
            return JSONResponse({"error": "Invalid email or password"}, status_code=401)

        set_user_email(sess, row.email)
        set_user_id(sess, row.id)
        return JSONResponse({"ok": True, "email": row.email, "name": row.name or ""})

    @rt("/auth/forgot", methods=["POST"])
    async def auth_forgot(request):
        from sqlalchemy import text
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        if not email:
            return JSONResponse({"error": "Email is required"}, status_code=400)

        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id FROM {SCHEMA}.chat_users WHERE email = :email"),
                {"email": email},
            ).fetchone()
            if row:
                token = generate_token()
                expires = datetime.utcnow() + timedelta(hours=1)
                db.execute(text(f"""
                    UPDATE {SCHEMA}.chat_users
                    SET reset_token = :token, reset_token_expires = :expires
                    WHERE id = :id
                """), {"token": token, "expires": expires, "id": row.id})
                db.commit()
                send_reset_email(email, token)
        finally:
            db.close()

        return JSONResponse({"ok": True, "message": "If an account exists, a reset link has been sent"})

    @rt("/auth/reset/{token}")
    def auth_reset_page(token: str):
        from sqlalchemy import text
        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id FROM {SCHEMA}.chat_users WHERE reset_token = :token AND reset_token_expires > NOW()"),
                {"token": token},
            ).fetchone()
        finally:
            db.close()

        if not row:
            return Html(_head("Reset Password"), Body(
                Div(H2("Invalid or expired link"), P("Please request a new reset link."),
                    A("Back to login", href="/app", cls="text-black font-semibold"),
                    cls="max-w-md mx-auto mt-20 text-center"),
                cls="bg-white font-sans",
            ))

        return Html(_head("Reset Password"), Body(
            Div(
                H2("Set new password", cls="text-xl font-bold mb-4"),
                Form(
                    Input(type="password", name="password", placeholder="New password (min 6 chars)",
                          cls="w-full px-3 py-2 border border-gray-200 rounded-md text-sm mb-3", required=True),
                    Input(type="password", name="password_confirm", placeholder="Confirm password",
                          cls="w-full px-3 py-2 border border-gray-200 rounded-md text-sm mb-4", required=True),
                    Button("Reset Password", type="submit",
                           cls="w-full py-2 bg-black text-white rounded-md text-sm cursor-pointer border-none"),
                    id="reset-form",
                    method="POST",
                    action=f"/auth/reset/{token}/submit",
                ),
                Div(id="reset-error", cls="text-red-500 text-sm mt-2"),
                cls="max-w-sm mx-auto mt-20 p-6 bg-white rounded-lg border border-gray-200",
            ),
            cls="bg-gray-50 font-sans min-h-screen",
        ))

    @rt("/auth/reset/{token}/submit", methods=["POST"])
    async def auth_reset_submit(token: str, request, sess):
        from sqlalchemy import text
        form = await request.form()
        password = form.get("password") or ""
        password_confirm = form.get("password_confirm") or ""

        if len(password) < 6:
            return RedirectResponse(f"/auth/reset/{token}", status_code=303)
        if password != password_confirm:
            return RedirectResponse(f"/auth/reset/{token}", status_code=303)

        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id, email FROM {SCHEMA}.chat_users WHERE reset_token = :token AND reset_token_expires > NOW()"),
                {"token": token},
            ).fetchone()
            if not row:
                return RedirectResponse("/app", status_code=303)

            pw_hash = hash_password(password)
            db.execute(text(f"""
                UPDATE {SCHEMA}.chat_users
                SET password_hash = :pw, reset_token = NULL, reset_token_expires = NULL, is_verified = TRUE
                WHERE id = :id
            """), {"pw": pw_hash, "id": row.id})
            db.commit()

            set_user_email(sess, row.email)
            set_user_id(sess, row.id)
        finally:
            db.close()

        return RedirectResponse("/app", status_code=303)

    @rt("/auth/logout", methods=["POST"])
    def auth_logout(sess):
        clear_user(sess)
        return JSONResponse({"ok": True})

    @rt("/auth/set-password", methods=["POST"])
    async def auth_set_password(request, sess):
        from sqlalchemy import text
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        password = form.get("password") or ""

        if not email or len(password) < 6:
            return JSONResponse({"error": "Email and password (min 6 chars) required"}, status_code=400)

        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id FROM {SCHEMA}.chat_users WHERE email = :email AND password_hash IS NULL"),
                {"email": email},
            ).fetchone()
            if not row:
                return JSONResponse({"error": "Account not found or already has password"}, status_code=404)

            pw_hash = hash_password(password)
            db.execute(text(f"""
                UPDATE {SCHEMA}.chat_users
                SET password_hash = :pw, is_verified = TRUE
                WHERE id = :id
            """), {"pw": pw_hash, "id": row.id})
            db.commit()

            set_user_email(sess, email)
            set_user_id(sess, row.id)
        finally:
            db.close()

        return JSONResponse({"ok": True, "email": email})

    # ─── Profile & Preferences ─────────────────────────────────────────────

    from utils.config import get_featured_brands
    MAKES = get_featured_brands()
    BODY_TYPES = ['Sedan', 'SUV', 'Estate', 'Coupe', 'Convertible', 'Hatchback', 'MPV', 'Pickup']
    FUEL_TYPES = ['Petrol', 'Diesel', 'Hybrid', 'Electric', 'Plug-in Hybrid']
    TRANSMISSIONS = ['Automatic', 'Manual']
    CURRENCIES = [('EUR', '€ EUR'), ('GBP', '£ GBP'), ('USD', '$ USD')]

    def _checkbox_group(name, options, selected):
        items = []
        for opt in options:
            checked = 'checked' if opt in selected else ''
            items.append(NotStr(
                f'<label class="cb-pill"><input type="checkbox" name="{name}" value="{opt}" {checked}>'
                f'<span>{opt}</span></label>'
            ))
        return Div(*items, cls="cb-group")

    @rt("/app/profile")
    def profile_page(sess):
        from sqlalchemy import text
        import json as _json
        email = get_user_email(sess)
        if not email:
            return RedirectResponse("/app", status_code=303)

        uid = get_user_id(sess)
        db = _get_db()
        try:
            user = db.execute(
                text(f"SELECT name, email, created_at FROM {SCHEMA}.chat_users WHERE id = :id"),
                {"id": uid},
            ).fetchone()
            prefs = db.execute(
                text(f"SELECT * FROM {SCHEMA}.user_profiles WHERE user_id = :uid"),
                {"uid": uid},
            ).fetchone()
        finally:
            db.close()

        name = user.name or "" if user else ""
        user_email = user.email if user else email

        p_country = prefs.country if prefs else ""
        p_city = prefs.city if prefs else ""
        p_currency = prefs.currency if prefs else "EUR"
        p_lang = prefs.language if prefs else "en"
        p_phone = prefs.phone if prefs else ""
        p_bmin = str(prefs.budget_min_eur or "") if prefs else ""
        p_bmax = str(prefs.budget_max_eur or "") if prefs else ""
        p_makes = _json.loads(prefs.preferred_makes) if prefs and prefs.preferred_makes else []
        p_bodies = _json.loads(prefs.preferred_body_types) if prefs and prefs.preferred_body_types else []
        p_fuels = _json.loads(prefs.preferred_fuel_types) if prefs and prefs.preferred_fuel_types else []
        p_trans = prefs.preferred_transmission if prefs else ""
        p_max_km = str(prefs.max_mileage_km or "") if prefs else ""
        p_min_yr = str(prefs.min_year or "") if prefs else ""
        p_max_yr = str(prefs.max_year or "") if prefs else ""
        p_notify_new = prefs.notify_new_listings if prefs else True
        p_notify_price = prefs.notify_price_drops if prefs else True
        p_notify_digest = prefs.notify_weekly_digest if prefs else True

        inp = "w-full px-3 py-2 border border-gray-200 rounded-md text-sm"
        lbl = "text-xs text-gray-500 block mb-1"
        half = "flex-1"

        def _select(name, options, selected):
            opts = [NotStr(f'<option value="{v}"{" selected" if v == selected else ""}>{label}</option>')
                    for v, label in options]
            return NotStr(f'<select name="{name}" class="{inp}">{"".join(str(o) for o in opts)}</select>')

        def _toggle(name, label_text, checked):
            chk = "checked" if checked else ""
            return Div(
                NotStr(f'<label class="toggle-row"><input type="checkbox" name="{name}" value="1" {chk}>'
                       f'<span class="toggle-label">{label_text}</span></label>'),
                cls="mb-2",
            )

        return Html(_head("Profile & Preferences"), Body(
            Div(
                A("< Back to chat", href="/app", cls="text-sm text-gray-500 mb-4 block no-underline hover:text-black"),

                # ─── Account ────
                H2("Account", cls="text-xl font-bold mb-1"),
                P("Your account details and password.", cls="text-xs text-gray-400 mb-4"),
                Form(
                    Div(
                        Div(Label("Name", cls=lbl), Input(type="text", name="name", value=name, placeholder="Your name", cls=inp), cls=half),
                        Div(Label("Email", cls=lbl), Input(type="email", value=user_email, disabled=True, cls=f"{inp} bg-gray-50"), cls=half),
                        cls="flex gap-3 mb-3",
                    ),
                    Div(
                        Div(Label("Phone", cls=lbl), Input(type="tel", name="phone", value=p_phone, placeholder="+44...", cls=inp), cls=half),
                        Div(Label("Country", cls=lbl), Input(type="text", name="country", value=p_country, placeholder="e.g. GB, DE", maxlength="5", cls=inp), cls=half),
                        Div(Label("City", cls=lbl), Input(type="text", name="city", value=p_city, placeholder="e.g. London", cls=inp), cls=half),
                        cls="flex gap-3 mb-3",
                    ),
                    Div(
                        Div(Label("Currency", cls=lbl), _select("currency", CURRENCIES, p_currency), cls=half),
                        Div(Label("Language", cls=lbl),
                            _select("language", [("en","English"),("de","Deutsch"),("fr","Francais"),("es","Espanol"),("it","Italiano"),("et","Eesti"),("lv","Latviesu"),("lt","Lietuviu"),("pl","Polski"),("nl","Nederlands"),("pt","Portugues"),("sv","Svenska")], p_lang),
                            cls=half),
                        cls="flex gap-3 mb-4",
                    ),
                    H3("Change Password", cls="text-sm font-semibold mt-2 mb-2"),
                    Div(
                        Div(Input(type="password", name="current_password", placeholder="Current password", cls=inp), cls=half),
                        Div(Input(type="password", name="new_password", placeholder="New password (min 6 chars)", cls=inp), cls=half),
                        cls="flex gap-3 mb-4",
                    ),
                    Div(
                        Button("Save Account", type="submit", cls="px-5 py-2 bg-black text-white rounded-md text-sm cursor-pointer border-none"),
                        Span(id="profile-msg", cls="text-sm ml-3"),
                        cls="flex items-center",
                    ),
                    id="profile-form",
                    onsubmit="return submitProfile(event)",
                ),

                # ─── Search Preferences ────
                NotStr('<hr class="my-8 border-gray-100">'),
                H2("Search Preferences", cls="text-xl font-bold mb-1"),
                P("Set your defaults — these will pre-fill search filters and help agents tailor recommendations.", cls="text-xs text-gray-400 mb-4"),
                Form(
                    H3("Budget Range (EUR)", cls="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2"),
                    Div(
                        Div(Label("Min", cls=lbl), Input(type="number", name="budget_min", value=p_bmin, placeholder="e.g. 10000", step="1000", cls=inp), cls=half),
                        Div(Label("Max", cls=lbl), Input(type="number", name="budget_max", value=p_bmax, placeholder="e.g. 80000", step="1000", cls=inp), cls=half),
                        cls="flex gap-3 mb-4",
                    ),

                    H3("Preferred Makes", cls="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2"),
                    _checkbox_group("preferred_makes", MAKES, p_makes),

                    H3("Body Types", cls="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2 mt-4"),
                    _checkbox_group("preferred_body_types", BODY_TYPES, p_bodies),

                    H3("Fuel Types", cls="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2 mt-4"),
                    _checkbox_group("preferred_fuel_types", FUEL_TYPES, p_fuels),

                    H3("Drivetrain", cls="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2 mt-4"),
                    Div(
                        Div(Label("Transmission", cls=lbl), _select("preferred_transmission", [("","Any"),("Automatic","Automatic"),("Manual","Manual")], p_trans), cls=half),
                        Div(Label("Max Mileage (km)", cls=lbl), Input(type="number", name="max_mileage_km", value=p_max_km, placeholder="e.g. 100000", step="5000", cls=inp), cls=half),
                        cls="flex gap-3 mb-3",
                    ),
                    Div(
                        Div(Label("Min Year", cls=lbl), Input(type="number", name="min_year", value=p_min_yr, placeholder="e.g. 2018", cls=inp), cls=half),
                        Div(Label("Max Year", cls=lbl), Input(type="number", name="max_year", value=p_max_yr, placeholder="e.g. 2025", cls=inp), cls=half),
                        cls="flex gap-3 mb-4",
                    ),
                    Div(
                        Button("Save Preferences", type="submit", cls="px-5 py-2 bg-black text-white rounded-md text-sm cursor-pointer border-none"),
                        Span(id="prefs-msg", cls="text-sm ml-3"),
                        cls="flex items-center",
                    ),
                    id="prefs-form",
                    onsubmit="return submitPrefs(event)",
                ),

                # ─── Notifications ────
                NotStr('<hr class="my-8 border-gray-100">'),
                H2("Notifications", cls="text-xl font-bold mb-1"),
                P("Choose what emails you'd like to receive.", cls="text-xs text-gray-400 mb-4"),
                Form(
                    _toggle("notify_new_listings", "New listings matching my preferences", p_notify_new),
                    _toggle("notify_price_drops", "Price drops on my favorites", p_notify_price),
                    _toggle("notify_weekly_digest", "Weekly market digest", p_notify_digest),
                    Div(
                        Button("Save Notifications", type="submit", cls="px-5 py-2 bg-black text-white rounded-md text-sm cursor-pointer border-none mt-2"),
                        Span(id="notify-msg", cls="text-sm ml-3"),
                        cls="flex items-center",
                    ),
                    id="notify-form",
                    onsubmit="return submitNotify(event)",
                ),

                cls="max-w-2xl mx-auto mt-8 mb-16 px-6",
            ),
            Style(NotStr("""
                .cb-group { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
                .cb-pill { display:inline-flex; align-items:center; gap:4px; padding:5px 12px; border:1px solid #e5e7eb; border-radius:20px; font-size:13px; cursor:pointer; transition:all .15s; user-select:none; }
                .cb-pill:has(input:checked) { background:#111; color:#fff; border-color:#111; }
                .cb-pill input { display:none; }
                .toggle-row { display:flex; align-items:center; gap:8px; cursor:pointer; font-size:14px; }
                .toggle-row input { width:16px; height:16px; accent-color:#111; }
                .toggle-label { color:#374151; }
            """)),
            Script(NotStr("""
async function submitProfile(e) {
    e.preventDefault();
    var form = document.getElementById('profile-form');
    var resp = await fetch('/app/profile', { method:'POST', body: new FormData(form) });
    var data = await resp.json();
    var msg = document.getElementById('profile-msg');
    msg.style.color = data.ok ? '#16A34A' : '#DC2626';
    msg.textContent = data.ok ? 'Saved!' : (data.error || 'Error');
    setTimeout(function(){ msg.textContent = ''; }, 3000);
    return false;
}
async function submitPrefs(e) {
    e.preventDefault();
    var form = document.getElementById('prefs-form');
    var resp = await fetch('/api/user-profile', { method:'POST', body: new FormData(form) });
    var data = await resp.json();
    var msg = document.getElementById('prefs-msg');
    msg.style.color = data.ok ? '#16A34A' : '#DC2626';
    msg.textContent = data.ok ? 'Preferences saved!' : (data.error || 'Error');
    setTimeout(function(){ msg.textContent = ''; }, 3000);
    return false;
}
async function submitNotify(e) {
    e.preventDefault();
    var form = document.getElementById('notify-form');
    var resp = await fetch('/api/user-profile', { method:'POST', body: new FormData(form) });
    var data = await resp.json();
    var msg = document.getElementById('notify-msg');
    msg.style.color = data.ok ? '#16A34A' : '#DC2626';
    msg.textContent = data.ok ? 'Notification settings saved!' : (data.error || 'Error');
    setTimeout(function(){ msg.textContent = ''; }, 3000);
    return false;
}
""")),
            cls="bg-white font-sans min-h-screen",
        ))

    @rt("/app/profile", methods=["POST"])
    async def profile_update(request, sess):
        from sqlalchemy import text
        import json as _json
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        form = await request.form()
        name = (form.get("name") or "").strip()
        phone = (form.get("phone") or "").strip()
        country = (form.get("country") or "").strip()
        city = (form.get("city") or "").strip()
        currency = form.get("currency") or "EUR"
        language = form.get("language") or "en"
        current_password = form.get("current_password") or ""
        new_password = form.get("new_password") or ""

        db = _get_db()
        try:
            updates = ["name = :name"]
            params = {"name": name, "id": uid}

            if new_password:
                if len(new_password) < 6:
                    return JSONResponse({"error": "New password must be at least 6 characters"}, status_code=400)
                row = db.execute(
                    text(f"SELECT password_hash FROM {SCHEMA}.chat_users WHERE id = :id"),
                    {"id": uid},
                ).fetchone()
                if row and row.password_hash:
                    if not verify_password(current_password, row.password_hash):
                        return JSONResponse({"error": "Current password is incorrect"}, status_code=400)
                params["pw"] = hash_password(new_password)
                updates.append("password_hash = :pw")

            db.execute(text(f"""
                UPDATE {SCHEMA}.chat_users SET {', '.join(updates)} WHERE id = :id
            """), params)

            db.execute(text(f"""
                INSERT INTO {SCHEMA}.user_profiles (user_id, phone, country, city, currency, language, updated_at)
                VALUES (:uid, :phone, :country, :city, :currency, :language, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    phone = :phone, country = :country, city = :city,
                    currency = :currency, language = :language, updated_at = NOW()
            """), {"uid": uid, "phone": phone, "country": country, "city": city,
                   "currency": currency, "language": language})
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True})

    @rt("/api/user-profile", methods=["POST"])
    async def update_user_prefs(request, sess):
        from sqlalchemy import text
        import json as _json
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        form = await request.form()

        budget_min = form.get("budget_min") or None
        budget_max = form.get("budget_max") or None
        preferred_makes = _json.dumps(form.getlist("preferred_makes"))
        preferred_body_types = _json.dumps(form.getlist("preferred_body_types"))
        preferred_fuel_types = _json.dumps(form.getlist("preferred_fuel_types"))
        preferred_transmission = form.get("preferred_transmission") or None
        max_mileage_km = form.get("max_mileage_km") or None
        min_year = form.get("min_year") or None
        max_year = form.get("max_year") or None

        notify_new = "notify_new_listings" in form
        notify_price = "notify_price_drops" in form
        notify_digest = "notify_weekly_digest" in form

        db = _get_db()
        try:
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.user_profiles (user_id, budget_min_eur, budget_max_eur,
                    preferred_makes, preferred_body_types, preferred_fuel_types,
                    preferred_transmission, max_mileage_km, min_year, max_year,
                    notify_new_listings, notify_price_drops, notify_weekly_digest, updated_at)
                VALUES (:uid, :bmin, :bmax, :makes, :bodies, :fuels, :trans,
                        :max_km, :min_yr, :max_yr, :n_new, :n_price, :n_digest, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    budget_min_eur = :bmin, budget_max_eur = :bmax,
                    preferred_makes = :makes, preferred_body_types = :bodies,
                    preferred_fuel_types = :fuels, preferred_transmission = :trans,
                    max_mileage_km = :max_km, min_year = :min_yr, max_year = :max_yr,
                    notify_new_listings = :n_new, notify_price_drops = :n_price,
                    notify_weekly_digest = :n_digest, updated_at = NOW()
            """), {
                "uid": uid, "bmin": budget_min, "bmax": budget_max,
                "makes": preferred_makes, "bodies": preferred_body_types,
                "fuels": preferred_fuel_types, "trans": preferred_transmission,
                "max_km": max_mileage_km, "min_yr": min_year, "max_yr": max_year,
                "n_new": notify_new, "n_price": notify_price, "n_digest": notify_digest,
            })
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True})

    # ─── Google OAuth ─────────────────────────────────────────────────────────

    @rt("/auth/google")
    def auth_google_redirect(sess):
        if not GOOGLE_CLIENT_ID:
            return JSONResponse({"error": "Google OAuth not configured"}, status_code=500)

        state = generate_token()
        sess["oauth_state"] = state

        params = urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "state": state,
            "prompt": "select_account",
        })
        return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}", status_code=302)

    @rt("/auth/google/callback")
    def auth_google_callback(request, sess):
        from sqlalchemy import text

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            log.warning(f"Google OAuth error: {error}")
            return RedirectResponse("/app", status_code=303)

        if not code or state != sess.get("oauth_state"):
            log.warning("Google OAuth: invalid state or missing code")
            return RedirectResponse("/app", status_code=303)

        sess.pop("oauth_state", None)

        token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if token_resp.status_code != 200:
            log.error(f"Google token exchange failed: {token_resp.text}")
            return RedirectResponse("/app", status_code=303)

        tokens = token_resp.json()
        access_token = tokens.get("access_token")

        userinfo_resp = http_requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if userinfo_resp.status_code != 200:
            log.error(f"Google userinfo failed: {userinfo_resp.text}")
            return RedirectResponse("/app", status_code=303)

        userinfo = userinfo_resp.json()
        email = userinfo.get("email", "").lower().strip()
        name = userinfo.get("name", "")

        if not email:
            return RedirectResponse("/app", status_code=303)

        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT id, email, name FROM {SCHEMA}.chat_users WHERE email = :email"),
                {"email": email},
            ).fetchone()

            if row:
                if not row.name and name:
                    db.execute(text(f"UPDATE {SCHEMA}.chat_users SET name = :name WHERE id = :id"),
                               {"name": name, "id": row.id})
                    db.commit()
                uid = row.id
            else:
                result = db.execute(text(f"""
                    INSERT INTO {SCHEMA}.chat_users (email, name, is_verified)
                    VALUES (:email, :name, TRUE)
                    RETURNING id
                """), {"email": email, "name": name})
                uid = result.fetchone().id
                db.commit()

            set_user_email(sess, email)
            set_user_id(sess, uid)
        finally:
            db.close()

        return RedirectResponse("/app", status_code=303)
