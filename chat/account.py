"""FastCPI account and scoped API-key workspace."""

from __future__ import annotations

import hashlib
import json
import secrets

from fasthtml.common import A, Body, Button, Div, Form, H2, Html, Input, P, Script, Span
from sqlalchemy import text
from starlette.responses import JSONResponse, RedirectResponse

from chat.components import left_pane, signin_overlay
from chat.layout import _head
from db import SCHEMA
from utils.fastcpi_i18n import app_tr
from utils.session import get_user_id


def register_account_routes(rt):
    @rt("/app/account")
    def account_page(sess):
        from chat.routes import _ensure_user, _list_sessions, _get_db
        from utils.i18n import get_lang
        uid, email = _ensure_user(sess)
        if not uid:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        db = _get_db()
        try:
            keys = db.execute(text(f"""
                SELECT id,name,key_prefix,scopes,last_used_at,created_at FROM {SCHEMA}.api_keys
                WHERE user_id=:uid AND revoked_at IS NULL ORDER BY created_at DESC
            """), {"uid": uid}).fetchall()
        finally:
            db.close()
        key_cards = [Div(Span(key.name, cls="font-semibold"), P(f"{key.key_prefix}… · {', '.join(key.scopes)}", cls="text-xs text-gray-500"), cls="p-3 border rounded-lg") for key in keys]
        body = Body(
            signin_overlay(lang), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=_list_sessions(uid), current_sid="", lang=lang),
            Div(Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"), Span(app_tr("account_api", lang), cls="chat-header-title"), cls="chat-header-left"),
                    Div(A(app_tr("back_to_chat", lang), href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2(app_tr("account", lang), cls="text-xl font-semibold"), P(email, cls="text-sm text-gray-500 mb-6"),
                    H2(app_tr("scoped_keys", lang), cls="text-lg font-semibold mb-1"),
                    P(app_tr("key_intro", lang), cls="text-sm text-gray-500 mb-3"),
                    Form(Input(name="name", value=app_tr("default", lang), cls="px-3 py-2 border rounded"),
                         Button(app_tr("create_read_key", lang), type="submit", cls="ml-2 px-4 py-2 bg-black text-white rounded border-none"), id="key-form", cls="mb-3"),
                    Div(id="new-key", cls="hidden p-3 mb-4 bg-emerald-50 text-emerald-900 rounded text-xs break-all"),
                    Div(*key_cards, cls="space-y-2") if key_cards else P(app_tr("no_keys", lang), cls="text-sm text-gray-400"),
                    cls="messages"), cls="center-pane"),
            Script(f"""document.getElementById('key-form').addEventListener('submit',async function(e){{e.preventDefault();const r=await fetch('/app/api-keys',{{method:'POST',body:new FormData(this)}});const d=await r.json();const el=document.getElementById('new-key');el.classList.remove('hidden');el.textContent=d.key?{json.dumps(app_tr('copy_now', lang))}+': '+d.key:(d.error||{json.dumps(app_tr('unable_key', lang))});}});"""),
            Script(src="/static/chat.js?v=4"), cls="bg-white text-ink font-sans antialiased app pane-closed")
        return Html(_head(app_tr("account_api", lang)), body)

    @rt("/app/api-keys", methods=["POST"])
    async def create_browser_api_key(request, sess):
        from chat.routes import _get_db
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Sign in required"}, status_code=401)
        form = await request.form()
        name = (form.get("name") or "Default")[:100]
        raw = f"fcpi_{secrets.token_urlsafe(32)}"
        db = _get_db()
        try:
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.api_keys (user_id,name,key_prefix,key_hash,scopes)
                VALUES (:uid,:name,:prefix,:digest,CAST(:scopes AS jsonb))
            """), {"uid": uid, "name": name, "prefix": raw[:16],
                     "digest": hashlib.sha256(raw.encode()).hexdigest(), "scopes": json.dumps(["prices:read"])})
            db.commit()
        finally:
            db.close()
        return JSONResponse({"key": raw, "warning": "This key will not be shown again."})
