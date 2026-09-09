"""Favorites and Saved Searches routes."""

from __future__ import annotations

import json
import logging
import secrets

from fasthtml.common import (
    Html, Body, Div, H2, H3, P, A, Button, Input, Span, Script, NotStr,
)
from starlette.requests import Request
from starlette.responses import JSONResponse

from chat.layout import _head
from chat.components import left_pane, signin_overlay
from chat.routes import _ensure_user, _list_sessions

log = logging.getLogger(__name__)
SCHEMA = "carhero"


def _get_db():
    from db import SessionLocal
    return SessionLocal()


def register_favorites_routes(rt):

    @rt("/api/favorites")
    def list_favorites(sess):
        uid, email = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            rows = db.execute(text(f"""
                SELECT f.id, f.listing_id, f.price_at_save, f.note, f.created_at,
                       cl.make, cl.model, cl.variant, cl.year, cl.mileage_km,
                       cl.price_eur, cl.fuel_type, cl.transmission, cl.country,
                       cl.provider, cl.source_url, cl.image_urls
                FROM {SCHEMA}.favorites f
                JOIN {SCHEMA}.car_listings cl ON cl.id = f.listing_id
                WHERE f.user_id = :uid
                ORDER BY f.created_at DESC
            """), {"uid": uid}).fetchall()
        finally:
            db.close()

        favorites = []
        for r in rows:
            m = dict(r._mapping)
            price_change = None
            if m.get("price_at_save") and m.get("price_eur"):
                price_change = float(m["price_eur"]) - float(m["price_at_save"])
            favorites.append({
                "id": m["id"],
                "listing_id": m["listing_id"],
                "make": m["make"],
                "model": m["model"],
                "variant": m.get("variant") or "",
                "year": m.get("year"),
                "mileage_km": int(m["mileage_km"]) if m.get("mileage_km") else None,
                "price_eur": round(float(m["price_eur"])) if m.get("price_eur") else None,
                "price_at_save": round(float(m["price_at_save"])) if m.get("price_at_save") else None,
                "price_change": round(price_change) if price_change else None,
                "fuel_type": m.get("fuel_type") or "",
                "transmission": m.get("transmission") or "",
                "country": m.get("country") or "",
                "provider": m.get("provider") or "",
                "url": m.get("source_url") or "",
                "note": m.get("note") or "",
            })
        return JSONResponse({"favorites": favorites})

    @rt("/api/favorites", methods=["POST"])
    async def add_favorite(request, sess):
        uid, email = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        form = await request.form()
        listing_id = form.get("listing_id")
        if not listing_id:
            return JSONResponse({"error": "listing_id required"}, status_code=400)

        db = _get_db()
        try:
            price = db.execute(text(f"""
                SELECT price_eur FROM {SCHEMA}.car_listings WHERE id = :id
            """), {"id": int(listing_id)}).scalar()

            db.execute(text(f"""
                INSERT INTO {SCHEMA}.favorites (user_id, listing_id, price_at_save)
                VALUES (:uid, :lid, :price)
                ON CONFLICT (user_id, listing_id) DO NOTHING
            """), {"uid": uid, "lid": int(listing_id), "price": price})
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True})

    @rt("/api/favorites/{fav_id}", methods=["DELETE"])
    def remove_favorite(fav_id: int, sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            db.execute(text(f"""
                DELETE FROM {SCHEMA}.favorites WHERE id = :id AND user_id = :uid
            """), {"id": fav_id, "uid": uid})
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True})

    @rt("/api/saved-searches")
    def list_saved_searches(sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            rows = db.execute(text(f"""
                SELECT id, name, filters, last_viewed_at, last_count, notify_email, created_at
                FROM {SCHEMA}.saved_searches
                WHERE user_id = :uid
                ORDER BY created_at DESC
            """), {"uid": uid}).fetchall()
        finally:
            db.close()

        searches = []
        for r in rows:
            m = dict(r._mapping)
            searches.append({
                "id": m["id"],
                "name": m["name"],
                "filters": m["filters"] if isinstance(m["filters"], dict) else json.loads(m["filters"] or "{}"),
                "last_count": m.get("last_count") or 0,
                "notify_email": bool(m.get("notify_email")),
                "created_at": str(m.get("created_at") or ""),
            })
        return JSONResponse({"searches": searches})

    @rt("/api/saved-searches", methods=["POST"])
    async def create_saved_search(request, sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        form = await request.form()
        name = (form.get("name") or "Untitled Search").strip()
        filters_str = form.get("filters") or "{}"
        try:
            filters = json.loads(filters_str)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid filters JSON"}, status_code=400)

        db = _get_db()
        try:
            row = db.execute(text(f"""
                INSERT INTO {SCHEMA}.saved_searches (user_id, name, filters)
                VALUES (:uid, :name, :filters::jsonb)
                RETURNING id
            """), {"uid": uid, "name": name, "filters": json.dumps(filters)}).fetchone()
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True, "id": row[0] if row else None})

    @rt("/api/saved-searches/{search_id}", methods=["DELETE"])
    def delete_saved_search(search_id: int, sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            db.execute(text(f"""
                DELETE FROM {SCHEMA}.saved_searches WHERE id = :id AND user_id = :uid
            """), {"id": search_id, "uid": uid})
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True})

    @rt("/app/favorites")
    def favorites_page(sess):
        uid, email = _ensure_user(sess)
        sessions = _list_sessions(uid) if uid else []

        body = Body(
            signin_overlay(),
            Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid=""),
            Div(
                Div(
                    Div(
                        Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span("Favorites", cls="chat-header-title"),
                        cls="chat-header-left",
                    ),
                    Div(
                        A("Back to chat", href="/app", cls="header-action-btn"),
                        A("Saved Searches", href="/app/saved-searches", cls="header-action-btn"),
                        cls="chat-header-actions",
                    ),
                    cls="chat-header",
                ),
                Div(
                    H2("My Favorites", cls="text-xl font-display font-bold mb-1"),
                    P("Cars you've saved. Price changes tracked since you favorited them.",
                      cls="text-sm text-gray-500 mb-6"),
                    Div(id="favorites-list", cls="space-y-3"),
                    Div(id="favorites-empty", style="display:none",
                        cls="text-center text-gray-400 py-12"),
                    cls="px-6 py-4 overflow-y-auto flex-1",
                ),
                cls="center-pane",
            ),
            Script(NotStr("""
                async function loadFavorites() {
                    const resp = await fetch('/api/favorites');
                    if (!resp.ok) { document.getElementById('favorites-empty').style.display='block'; document.getElementById('favorites-empty').textContent='Sign in to view favorites'; return; }
                    const data = await resp.json();
                    const list = document.getElementById('favorites-list');
                    const empty = document.getElementById('favorites-empty');
                    if (!data.favorites || !data.favorites.length) { empty.style.display='block'; empty.textContent='No favorites yet. Use the heart button on listings to save them.'; return; }
                    list.innerHTML = data.favorites.map(f => {
                        const priceStr = f.price_eur ? 'EUR ' + f.price_eur.toLocaleString() : 'N/A';
                        const mileStr = f.mileage_km ? f.mileage_km.toLocaleString() + ' km' : '';
                        let changeStr = '';
                        if (f.price_change && f.price_change !== 0) {
                            const sign = f.price_change > 0 ? '+' : '';
                            const color = f.price_change < 0 ? '#16A34A' : '#DC2626';
                            changeStr = '<span style="color:' + color + ';font-size:11px;font-weight:600;margin-left:8px;">' + sign + f.price_change.toLocaleString() + ' EUR</span>';
                        }
                        return '<div style="border:1px solid #E5E7EB;border-radius:8px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;">' +
                            '<div><strong>' + f.make + ' ' + f.model + '</strong> ' + (f.variant||'') + ' (' + (f.year||'') + ')<br>' +
                            '<span style="font-size:12px;color:#6B7280;">' + priceStr + changeStr + ' | ' + mileStr + ' | ' + f.fuel_type + ' ' + f.transmission + '</span></div>' +
                            '<div style="display:flex;gap:8px;align-items:center;">' +
                            (f.url ? '<a href="' + f.url + '" target="_blank" style="font-size:12px;color:#000;">View</a>' : '') +
                            '<button onclick="removeFavorite(' + f.id + ',this)" style="border:none;background:none;cursor:pointer;color:#DC2626;font-size:18px;">&#10005;</button>' +
                            '</div></div>';
                    }).join('');
                }
                async function removeFavorite(id, btn) {
                    await fetch('/api/favorites/' + id, { method: 'DELETE' });
                    btn.closest('div[style*="border"]').remove();
                }
                loadFavorites();
            """)),
            Script(src="/static/chat.js"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head("Favorites"), body)

    @rt("/app/saved-searches")
    def saved_searches_page(sess):
        uid, email = _ensure_user(sess)
        sessions = _list_sessions(uid) if uid else []

        body = Body(
            signin_overlay(),
            Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid=""),
            Div(
                Div(
                    Div(
                        Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span("Saved Searches", cls="chat-header-title"),
                        cls="chat-header-left",
                    ),
                    Div(
                        A("Back to chat", href="/app", cls="header-action-btn"),
                        A("Favorites", href="/app/favorites", cls="header-action-btn"),
                        cls="chat-header-actions",
                    ),
                    cls="chat-header",
                ),
                Div(
                    H2("Saved Searches", cls="text-xl font-display font-bold mb-1"),
                    P("Your saved filter combinations. Quick access to re-run searches.",
                      cls="text-sm text-gray-500 mb-6"),
                    Div(id="searches-list", cls="space-y-3"),
                    Div(id="searches-empty", style="display:none",
                        cls="text-center text-gray-400 py-12"),
                    cls="px-6 py-4 overflow-y-auto flex-1",
                ),
                cls="center-pane",
            ),
            Script(NotStr("""
                async function loadSearches() {
                    const resp = await fetch('/api/saved-searches');
                    if (!resp.ok) { document.getElementById('searches-empty').style.display='block'; document.getElementById('searches-empty').textContent='Sign in to view saved searches'; return; }
                    const data = await resp.json();
                    const list = document.getElementById('searches-list');
                    const empty = document.getElementById('searches-empty');
                    if (!data.searches || !data.searches.length) { empty.style.display='block'; empty.textContent='No saved searches yet.'; return; }
                    list.innerHTML = data.searches.map(s => {
                        const filters = Object.entries(s.filters).filter(([k,v]) => v).map(([k,v]) => k + ': ' + v).join(', ');
                        return '<div style="border:1px solid #E5E7EB;border-radius:8px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;">' +
                            '<div><strong>' + s.name + '</strong><br><span style="font-size:12px;color:#6B7280;">' + filters + '</span></div>' +
                            '<div style="display:flex;gap:8px;align-items:center;">' +
                            '<a href="/app?search=' + encodeURIComponent(JSON.stringify(s.filters)) + '" style="font-size:12px;color:#000;font-weight:600;">Run</a>' +
                            '<button onclick="deleteSearch(' + s.id + ',this)" style="border:none;background:none;cursor:pointer;color:#DC2626;font-size:18px;">&#10005;</button>' +
                            '</div></div>';
                    }).join('');
                }
                async function deleteSearch(id, btn) {
                    await fetch('/api/saved-searches/' + id, { method: 'DELETE' });
                    btn.closest('div[style*="border"]').remove();
                }
                loadSearches();
            """)),
            Script(src="/static/chat.js"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head("Saved Searches"), body)
