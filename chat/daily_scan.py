"""Daily FastCPI scan dashboard."""

from __future__ import annotations

from fasthtml.common import A, Body, Button, Div, H2, H3, Html, P, Script, Span
from sqlalchemy import text
from starlette.responses import JSONResponse, RedirectResponse

from chat.components import left_pane, signin_overlay
from chat.layout import _head
from db import SCHEMA


def register_daily_scan_routes(rt):
    @rt("/app/daily-scan")
    def daily_scan_page(sess):
        from chat.routes import _ensure_user, _list_sessions
        uid, email = _ensure_user(sess)
        if not uid:
            return RedirectResponse("/", status_code=303)
        body = Body(
            signin_overlay(), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=_list_sessions(uid), current_sid=""),
            Div(
                Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"), Span("Daily Scan", cls="chat-header-title"), cls="chat-header-left"),
                    Div(A("Watchlists", href="/app/watchlists", cls="header-action-btn"), A("Back to chat", href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2("Latest observed movements", cls="text-xl font-semibold mb-1"),
                    P("Daily watchlist results with source-backed observations and threshold events.", cls="text-sm text-gray-500 mb-5"),
                    Div("Loading daily scan…", id="scan-content", cls="text-sm text-gray-400"), cls="messages"),
                cls="center-pane"),
            Script("""
            (async()=>{const host=document.getElementById('scan-content');const r=await fetch('/api/daily-scan');
            if(!r.ok){host.textContent='Unable to load scan.';return;}const d=await r.json();
            let html=`<div class="grid grid-cols-3 gap-3 mb-5"><div class="p-3 border rounded"><strong>${d.summary.active_watches}</strong><br><small>active watches</small></div><div class="p-3 border rounded"><strong>${d.summary.events_24h}</strong><br><small>events in 24h</small></div><div class="p-3 border rounded"><strong>${d.summary.observations_24h}</strong><br><small>observations in 24h</small></div></div>`;
            html+=(d.events||[]).map(e=>`<div class="p-4 border rounded-lg mb-3"><strong>${e.name}</strong><span class="ml-2 text-xs text-emerald-700">${e.event_type}</span><p class="text-xs text-gray-500 mt-1">${e.created_at}</p></div>`).join('')||'<p>No watchlist events in the last 24 hours.</p>';host.innerHTML=html;})();
            """), Script(src="/static/chat.js?v=3"), cls="bg-white text-ink font-sans antialiased app pane-closed")
        return Html(_head("Daily Scan"), body)

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
                    (SELECT COUNT(*) FROM {SCHEMA}.price_observations
                     WHERE captured_at >= NOW()-INTERVAL '24 hours') AS observations_24h
                FROM {SCHEMA}.watchlists WHERE user_id=:uid
            """), {"uid": uid}).fetchone()
            events = db.execute(text(f"""
                SELECT e.event_type, e.payload, e.created_at, w.name
                FROM {SCHEMA}.watchlist_events e JOIN {SCHEMA}.watchlists w ON w.id=e.watchlist_id
                WHERE w.user_id=:uid AND e.created_at >= NOW()-INTERVAL '24 hours'
                ORDER BY e.created_at DESC LIMIT 100
            """), {"uid": uid}).fetchall()
        finally:
            db.close()
        payload = {"summary": dict(summary._mapping), "events": [dict(e._mapping) for e in events]}
        return JSONResponse(json.loads(json.dumps(payload, default=str)))
