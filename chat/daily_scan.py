"""Daily FastCPI scan dashboard."""

from __future__ import annotations

import json

from fasthtml.common import A, Body, Button, Div, H2, H3, Html, P, Script, Span
from sqlalchemy import text
from starlette.responses import JSONResponse, RedirectResponse

from chat.components import left_pane, signin_overlay
from chat.layout import _head
from db import SCHEMA
from utils.fastcpi_i18n import app_tr


def register_daily_scan_routes(rt):
    @rt("/app/daily-scan")
    def daily_scan_page(sess):
        from chat.routes import _ensure_user, _list_sessions
        from utils.i18n import get_lang
        uid, email = _ensure_user(sess)
        if not uid:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        labels = {key: app_tr(key, lang) for key in (
            "daily_scan", "watchlists", "back_to_chat", "today_prices", "daily_intro",
            "loading_scan", "unable_scan", "active_watches", "events_24h",
            "observations_24h", "latest_observations", "pending_scan", "no_watches",
            "threshold_events", "no_events", "open_source", "open_evidence",
        )}
        body = Body(
            signin_overlay(lang), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=_list_sessions(uid), current_sid="", lang=lang),
            Div(
                Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"), Span(labels["daily_scan"], cls="chat-header-title"), cls="chat-header-left"),
                    Div(A(labels["watchlists"], href="/app/watchlists", cls="header-action-btn"), A(labels["back_to_chat"], href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2(labels["today_prices"], cls="text-xl font-semibold mb-1"),
                    P(labels["daily_intro"], cls="text-sm text-gray-500 mb-5"),
                    Div(labels["loading_scan"], id="scan-content", cls="text-sm text-gray-400"), cls="messages"),
                cls="center-pane"),
            Script(f"""
            (async()=>{{const L={json.dumps(labels)};const starterNames={json.dumps({'A4 copy paper · France': 'Papier A4 · France', 'HP W2210A toner · Germany': 'Toner HP W2210A · Allemagne', 'Hourly IT support · Estonia': 'Support informatique horaire · Estonie'} if lang == 'fr' else {})};const host=document.getElementById('scan-content');const r=await fetch('/api/daily-scan');
            if(!r.ok){{host.textContent=L.unable_scan;return;}}const d=await r.json();
            const esc=v=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
            const href=v=>{{try{{const u=new URL(v);return ['http:','https:'].includes(u.protocol)?esc(u.href):'#'}}catch(e){{return '#'}}}};
            let html=`<div class="grid grid-cols-3 gap-3 mb-5"><div class="p-3 border rounded"><strong>${{d.summary.active_watches}}</strong><br><small>${{esc(L.active_watches)}}</small></div><div class="p-3 border rounded"><strong>${{d.summary.events_24h}}</strong><br><small>${{esc(L.events_24h)}}</small></div><div class="p-3 border rounded"><strong>${{d.summary.observations_24h}}</strong><br><small>${{esc(L.observations_24h)}}</small></div></div>`;
            html+=`<h3 class="text-sm font-semibold mb-3">${{esc(L.latest_observations)}}</h3>`;
            html+=(d.latest||[]).map(o=>{{const price=o.amount_comparable!=null?`${{Number(o.amount_comparable).toLocaleString()}} ${{esc(o.currency_comparable||'EUR')}} / ${{esc(o.unit_comparable||o.unit_original||'unit')}}`:esc(L.pending_scan);const link=o.source_url?`<a href="${{href(o.source_url)}}" target="_blank" rel="noopener noreferrer" class="text-xs text-emerald-700">${{esc(L.open_source)}} &rarr;</a>`:'';return `<div class="p-4 border rounded-lg mb-3"><div class="flex justify-between gap-3"><strong>${{esc(starterNames[o.name]||o.name)}}</strong><span class="text-xs text-gray-400">${{esc((o.markets||[]).join(', '))}}</span></div><p class="text-lg text-emerald-800 mt-2">${{price}}</p><p class="text-xs text-gray-500 mt-1">${{esc(o.title||o.query)}}${{o.captured_at?' · '+esc(o.captured_at):''}}</p>${{link}}</div>`}}).join('')||`<p>${{esc(L.no_watches)}}</p>`;
            html+=`<h3 class="text-sm font-semibold mt-6 mb-3">${{esc(L.threshold_events)}}</h3>`;
            html+=(d.events||[]).map(e=>{{const url=e.payload&&e.payload.source_url;return `<div class="p-4 border rounded-lg mb-3"><strong>${{esc(e.name)}}</strong><span class="ml-2 text-xs text-emerald-700">${{esc(e.event_type)}}</span><p class="text-xs text-gray-500 mt-1">${{esc(e.created_at)}}</p>${{url?`<a href="${{href(url)}}" target="_blank" rel="noopener noreferrer" class="text-xs text-emerald-700">${{esc(L.open_evidence)}} &rarr;</a>`:''}}</div>`}}).join('')||`<p class="text-sm text-gray-400">${{esc(L.no_events)}}</p>`;host.innerHTML=html;}})();
            """), Script(src="/static/chat.js?v=4"), cls="bg-white text-ink font-sans antialiased app pane-closed")
        return Html(_head(labels["daily_scan"]), body)

    @rt("/api/daily-scan")
    def daily_scan_api(sess):
        import json
        from chat.routes import _get_db
        from utils.session import get_user_id
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Sign in required"}, status_code=401)
        db = _get_db()
        try:
            summary = db.execute(text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE is_active) AS active_watches,
                    (SELECT COUNT(*) FROM {SCHEMA}.watchlist_events e
                     JOIN {SCHEMA}.watchlists w2 ON w2.id=e.watchlist_id
                     WHERE w2.user_id=:uid AND e.created_at >= NOW()-INTERVAL '24 hours') AS events_24h,
                    (SELECT COUNT(DISTINCT wo.observation_id)
                     FROM {SCHEMA}.watchlist_observations wo
                     JOIN {SCHEMA}.watchlists w3 ON w3.id=wo.watchlist_id
                     JOIN {SCHEMA}.price_observations po3 ON po3.id=wo.observation_id
                     WHERE w3.user_id=:uid AND po3.captured_at >= NOW()-INTERVAL '24 hours') AS observations_24h
                FROM {SCHEMA}.watchlists WHERE user_id=:uid
            """), {"uid": uid}).fetchone()
            events = db.execute(text(f"""
                SELECT e.event_type, e.payload, e.created_at, w.name
                FROM {SCHEMA}.watchlist_events e JOIN {SCHEMA}.watchlists w ON w.id=e.watchlist_id
                WHERE w.user_id=:uid AND e.created_at >= NOW()-INTERVAL '24 hours'
                ORDER BY e.created_at DESC LIMIT 100
            """), {"uid": uid}).fetchall()
            latest = db.execute(text(f"""
                SELECT DISTINCT ON (w.id)
                    w.id AS watchlist_id, w.name, w.query, w.markets,
                    w.last_run_at, w.next_run_at, o.title, o.source_url, o.market,
                    po.amount_original, po.currency_original,
                    po.amount_comparable, po.currency_comparable,
                    po.unit_original, po.unit_comparable, po.captured_at,
                    po.confidence, po.warnings
                FROM {SCHEMA}.watchlists w
                LEFT JOIN {SCHEMA}.watchlist_observations wo ON wo.watchlist_id=w.id
                LEFT JOIN {SCHEMA}.price_observations po ON po.id=wo.observation_id
                LEFT JOIN {SCHEMA}.offers o ON o.id=po.offer_id
                WHERE w.user_id=:uid
                ORDER BY w.id, po.captured_at DESC NULLS LAST
            """), {"uid": uid}).fetchall()
        finally:
            db.close()
        payload = {
            "summary": dict(summary._mapping),
            "latest": [dict(row._mapping) for row in latest],
            "events": [dict(e._mapping) for e in events],
        }
        return JSONResponse(json.loads(json.dumps(payload, default=str)))
