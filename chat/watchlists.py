"""FastHTML watchlist workspace."""

from __future__ import annotations

import json

from fasthtml.common import A, Body, Button, Div, Form, H2, Html, Input, Label, P, Script, Select, Option, Span
from sqlalchemy import text
from starlette.responses import JSONResponse, RedirectResponse

from chat.components import left_pane, signin_overlay
from chat.layout import _head
from db import SCHEMA
from pricing.identifiers import classify_query
from pricing.markets import MARKETS
from utils.fastcpi_i18n import app_market_name, app_tr, app_watch_name
from utils.session import get_user_id


def register_watchlist_routes(rt):
    @rt("/app/watchlists")
    def watchlists_page(sess):
        from chat.routes import _ensure_user, _list_sessions, _get_db
        from utils.i18n import get_lang
        uid, email = _ensure_user(sess)
        if not uid:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        db = _get_db()
        try:
            rows = db.execute(text(f"SELECT * FROM {SCHEMA}.watchlists WHERE user_id=:uid ORDER BY updated_at DESC"), {"uid": uid}).fetchall()
        finally:
            db.close()
        cards = [Div(
            Div(Span(app_watch_name(r.name, lang), cls="font-semibold"), Span(app_tr("active", lang) if r.is_active else app_tr("paused", lang), cls="text-xs text-emerald-700"), cls="flex justify-between"),
            P(r.query, cls="text-sm text-gray-600 mt-1"),
            P(f"{app_tr('markets', lang)}: {', '.join(r.markets if isinstance(r.markets, list) else json.loads(r.markets))} · {app_tr('daily', lang)}",
              cls="text-xs text-gray-400 mt-1"),
            cls="p-4 border border-gray-200 rounded-lg") for r in rows]
        sessions = _list_sessions(uid)
        body = Body(
            signin_overlay(lang), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid="", lang=lang),
            Div(Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"), Span(app_tr("watchlists", lang), cls="chat-header-title"), cls="chat-header-left"),
                    Div(A(app_tr("back_to_chat", lang), href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2(app_tr("daily_monitoring", lang), cls="text-xl font-semibold mb-1"),
                    P(app_tr("watch_intro", lang), cls="text-sm text-gray-500 mb-5"),
                    Form(Input(name="name", placeholder=app_tr("watch_name", lang), required=True, cls="w-full px-3 py-2 border rounded mb-2"),
                         Input(name="query", placeholder=app_tr("watch_query", lang), required=True, cls="w-full px-3 py-2 border rounded mb-2"),
                         Select(*[Option(f"{code} · {app_market_name(code, info['name'], lang)}", value=code) for code, info in MARKETS.items()], name="market", cls="w-full px-3 py-2 border rounded mb-2"),
                         Input(name="target_price", type="number", step="0.01", placeholder=app_tr("target_price", lang), cls="w-full px-3 py-2 border rounded mb-2"),
                         Button(app_tr("create_watch", lang), type="submit", cls="px-4 py-2 bg-black text-white rounded border-none"),
                         id="watch-form", cls="p-4 bg-gray-50 rounded-lg mb-6"),
                    Div(*cards, cls="space-y-3") if cards else P(app_tr("no_watches", lang), cls="text-sm text-gray-400"),
                    cls="messages"), cls="center-pane"),
            Script(f"""document.getElementById('watch-form').addEventListener('submit',async function(e){{e.preventDefault();const r=await fetch('/app/watchlists',{{method:'POST',body:new FormData(this)}});const d=await r.json();if(d.ok)location.reload();else alert(d.error||{json.dumps(app_tr('unable_watch', lang))});}});"""),
            Script(src="/static/chat.js?v=4"), cls="bg-white text-ink font-sans antialiased app pane-closed")
        return Html(_head(app_tr("watchlists", lang)), body)

    @rt("/app/watchlists", methods=["POST"])
    async def create_watchlist(request, sess):
        from chat.routes import _get_db
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Sign in required"}, status_code=401)
        form = await request.form()
        name, query, market = (form.get("name") or "").strip(), (form.get("query") or "").strip(), (form.get("market") or "").upper()
        if not name or not query or market not in MARKETS:
            return JSONResponse({"error": "Name, query and supported market are required"}, status_code=422)
        identity = classify_query(query)
        target = form.get("target_price") or None
        db = _get_db()
        try:
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.watchlists
                    (user_id,name,query,query_type,query_value,markets,cpv_code,target_price,next_run_at)
                VALUES (:uid,:name,:query,:kind,:value,CAST(:markets AS jsonb),:cpv,:target,NOW())
            """), {"uid": uid, "name": name, "query": query, "kind": identity.kind, "value": identity.value,
                     "markets": json.dumps([market]), "cpv": identity.value if identity.kind == "cpv" else None, "target": target})
            db.commit()
        finally:
            db.close()
        return JSONResponse({"ok": True})
