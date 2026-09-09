"""Garage routes — owned cars, market valuation, TCO calculator."""

from __future__ import annotations

import json
import logging
from datetime import date

from fasthtml.common import (
    Html, Body, Div, H2, H3, P, A, Button, Input, Label, Span, Form, Script, NotStr, Select, Option,
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


def _compute_valuation(make: str, model: str, year: int, mileage_km: int | None) -> dict:
    from sqlalchemy import text
    db = _get_db()
    try:
        row = db.execute(text(f"""
            SELECT COUNT(*) AS cnt,
                   ROUND(AVG(price_eur)::numeric, 0) AS avg_price,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur)::numeric, 0) AS median_price,
                   MIN(price_eur)::integer AS min_price,
                   MAX(price_eur)::integer AS max_price,
                   ROUND(AVG(mileage_km)::numeric, 0) AS avg_mileage
            FROM {SCHEMA}.car_listings
            WHERE status = 'active' AND price_eur > 0
              AND make ILIKE :make AND model ILIKE :model
              AND year BETWEEN :y1 AND :y2
        """), {"make": f"%{make}%", "model": f"%{model}%", "y1": year - 2, "y2": year + 2}).fetchone()
    finally:
        db.close()

    if not row or row.cnt == 0:
        return {"estimated_value": None, "comparable_count": 0}

    median_price = float(row.median_price or 0)
    avg_mileage = float(row.avg_mileage or 80000)

    adjustment = 0
    if mileage_km and avg_mileage > 0:
        mileage_delta = mileage_km - avg_mileage
        adjustment = (mileage_delta / 10000) * 0.025 * median_price

    estimated = max(0, median_price - adjustment)

    return {
        "estimated_value": round(estimated),
        "comparable_count": int(row.cnt),
        "avg_price": round(float(row.avg_price)),
        "median_price": round(median_price),
        "min_price": int(row.min_price),
        "max_price": int(row.max_price),
        "avg_mileage": int(avg_mileage),
    }


def _compute_tco(car: dict, current_value: float | None) -> dict:
    purchase_price = float(car.get("purchase_price_eur") or 0)
    annual_km = int(car.get("annual_km") or 15000)
    fuel_consumption = float(car.get("fuel_consumption_l100km") or 7.0)
    insurance = float(car.get("insurance_annual_eur") or 1200)
    maintenance = float(car.get("maintenance_annual_eur") or 800)
    fuel_price_per_liter = 1.70

    fuel_type = (car.get("fuel_type") or "").lower()
    if "electric" in fuel_type:
        kwh_per_100km = fuel_consumption if fuel_consumption > 0 else 18.0
        electricity_price = 0.30
        fuel_annual = (annual_km / 100) * kwh_per_100km * electricity_price
    else:
        fuel_annual = (annual_km / 100) * fuel_consumption * fuel_price_per_liter

    depreciation_annual = 0
    if purchase_price > 0 and current_value is not None:
        purchase_date = car.get("purchase_date")
        if purchase_date:
            if isinstance(purchase_date, str):
                try:
                    purchase_date = date.fromisoformat(purchase_date)
                except ValueError:
                    purchase_date = None
            if purchase_date:
                days_owned = max(1, (date.today() - purchase_date).days)
                years_owned = days_owned / 365.25
                depreciation_annual = max(0, (purchase_price - current_value) / max(1, years_owned))

    if depreciation_annual == 0 and purchase_price > 0:
        depreciation_annual = purchase_price * 0.10

    total_annual = fuel_annual + insurance + maintenance + depreciation_annual
    total_monthly = total_annual / 12
    cost_per_km = total_annual / annual_km if annual_km > 0 else 0

    return {
        "fuel_annual_eur": round(fuel_annual),
        "insurance_annual_eur": round(insurance),
        "maintenance_annual_eur": round(maintenance),
        "depreciation_annual_eur": round(depreciation_annual),
        "total_annual_eur": round(total_annual),
        "total_monthly_eur": round(total_monthly),
        "cost_per_km_eur": round(cost_per_km, 2),
        "current_market_value_eur": round(current_value) if current_value else None,
    }


def register_garage_routes(rt):

    @rt("/api/garage")
    def list_garage(sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            rows = db.execute(text(f"""
                SELECT * FROM {SCHEMA}.garage_cars WHERE user_id = :uid ORDER BY created_at DESC
            """), {"uid": uid}).fetchall()
        finally:
            db.close()

        cars = []
        for r in rows:
            m = dict(r._mapping)
            val = _compute_valuation(m["make"], m["model"], m["year"], m.get("mileage_km"))
            cars.append({
                "id": m["id"],
                "make": m["make"],
                "model": m["model"],
                "variant": m.get("variant") or "",
                "year": m["year"],
                "mileage_km": m.get("mileage_km"),
                "purchase_price_eur": float(m["purchase_price_eur"]) if m.get("purchase_price_eur") else None,
                "fuel_type": m.get("fuel_type") or "",
                "estimated_value": val.get("estimated_value"),
                "comparable_count": val.get("comparable_count", 0),
            })
        return JSONResponse({"cars": cars})

    @rt("/api/garage", methods=["POST"])
    async def add_garage_car(request, sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        form = await request.form()
        make = (form.get("make") or "").strip()
        model = (form.get("model") or "").strip()
        year = form.get("year")
        if not make or not model or not year:
            return JSONResponse({"error": "Make, model, and year are required"}, status_code=400)

        db = _get_db()
        try:
            row = db.execute(text(f"""
                INSERT INTO {SCHEMA}.garage_cars
                    (user_id, make, model, variant, year, mileage_km, purchase_price_eur,
                     purchase_date, fuel_type, fuel_consumption_l100km, annual_km,
                     insurance_annual_eur, maintenance_annual_eur)
                VALUES (:uid, :make, :model, :variant, :year, :mileage, :price,
                        :pdate, :fuel, :consumption, :km, :ins, :maint)
                RETURNING id
            """), {
                "uid": uid, "make": make, "model": model,
                "variant": (form.get("variant") or "").strip() or None,
                "year": int(year),
                "mileage": int(form.get("mileage_km") or 0) or None,
                "price": float(form.get("purchase_price_eur") or 0) or None,
                "pdate": form.get("purchase_date") or None,
                "fuel": (form.get("fuel_type") or "").strip() or None,
                "consumption": float(form.get("fuel_consumption_l100km") or 0) or None,
                "km": int(form.get("annual_km") or 15000),
                "ins": float(form.get("insurance_annual_eur") or 1200),
                "maint": float(form.get("maintenance_annual_eur") or 800),
            }).fetchone()
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True, "id": row[0] if row else None})

    @rt("/api/garage/{car_id}", methods=["DELETE"])
    def delete_garage_car(car_id: int, sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            db.execute(text(f"""
                DELETE FROM {SCHEMA}.garage_cars WHERE id = :id AND user_id = :uid
            """), {"id": car_id, "uid": uid})
            db.commit()
        finally:
            db.close()

        return JSONResponse({"ok": True})

    @rt("/api/garage/{car_id}/tco")
    def garage_tco(car_id: int, sess):
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "Not logged in"}, status_code=401)

        from sqlalchemy import text
        db = _get_db()
        try:
            row = db.execute(text(f"""
                SELECT * FROM {SCHEMA}.garage_cars WHERE id = :id AND user_id = :uid
            """), {"id": car_id, "uid": uid}).fetchone()
        finally:
            db.close()

        if not row:
            return JSONResponse({"error": "Car not found"}, status_code=404)

        car = dict(row._mapping)
        val = _compute_valuation(car["make"], car["model"], car["year"], car.get("mileage_km"))
        tco = _compute_tco(car, val.get("estimated_value"))
        tco["valuation"] = val
        return JSONResponse(tco)

    @rt("/app/garage")
    def garage_page(sess):
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
                        Span("My Garage", cls="chat-header-title"),
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
                    H2("My Garage", cls="text-xl font-display font-bold mb-1"),
                    P("Track your owned cars, market value, and total cost of ownership.",
                      cls="text-sm text-gray-500 mb-6"),
                    # Add car form
                    Div(
                        H3("Add a car", cls="text-sm font-semibold mb-3"),
                        Div(
                            Input(type="text", id="g-make", placeholder="Make (e.g. BMW)",
                                  cls="text-sm border border-gray-200 rounded px-2 py-1.5"),
                            Input(type="text", id="g-model", placeholder="Model (e.g. X5)",
                                  cls="text-sm border border-gray-200 rounded px-2 py-1.5"),
                            Input(type="number", id="g-year", placeholder="Year",
                                  cls="text-sm border border-gray-200 rounded px-2 py-1.5 w-20"),
                            Input(type="number", id="g-mileage", placeholder="Mileage (km)",
                                  cls="text-sm border border-gray-200 rounded px-2 py-1.5 w-28"),
                            Input(type="number", id="g-price", placeholder="Purchase price (EUR)",
                                  cls="text-sm border border-gray-200 rounded px-2 py-1.5 w-32"),
                            Button("Add", onclick="addGarageCar()",
                                   cls="px-4 py-1.5 text-sm bg-black text-white rounded cursor-pointer border-none"),
                            cls="flex flex-wrap gap-2 items-end",
                        ),
                        cls="mb-8 p-4 bg-gray-50 rounded-lg border border-gray-100",
                    ),
                    # Car list
                    Div(id="garage-list", cls="space-y-4"),
                    Div(id="garage-empty", style="display:none",
                        cls="text-center text-gray-400 py-12"),
                    cls="px-6 py-4 overflow-y-auto flex-1",
                ),
                cls="center-pane",
            ),
            Script(NotStr("""
                async function loadGarage() {
                    const resp = await fetch('/api/garage');
                    if (!resp.ok) { document.getElementById('garage-empty').style.display='block'; document.getElementById('garage-empty').textContent='Sign in to view your garage'; return; }
                    const data = await resp.json();
                    const list = document.getElementById('garage-list');
                    const empty = document.getElementById('garage-empty');
                    if (!data.cars || !data.cars.length) { empty.style.display='block'; empty.textContent='No cars in your garage yet.'; return; }
                    list.innerHTML = data.cars.map(c => {
                        const valStr = c.estimated_value ? 'EUR ' + c.estimated_value.toLocaleString() : 'N/A';
                        const purchStr = c.purchase_price_eur ? 'EUR ' + c.purchase_price_eur.toLocaleString() : '';
                        const mileStr = c.mileage_km ? c.mileage_km.toLocaleString() + ' km' : '';
                        return '<div style="border:1px solid #E5E7EB;border-radius:8px;padding:16px;">' +
                            '<div style="display:flex;justify-content:space-between;align-items:start;">' +
                            '<div><strong style="font-size:15px;">' + c.make + ' ' + c.model + '</strong> ' + (c.variant||'') + '<br>' +
                            '<span style="font-size:12px;color:#6B7280;">' + (c.year||'') + ' | ' + mileStr + ' | ' + c.fuel_type + '</span></div>' +
                            '<button onclick="removeGarageCar(' + c.id + ',this)" style="border:none;background:none;cursor:pointer;color:#DC2626;">&#10005;</button></div>' +
                            '<div style="margin-top:12px;display:flex;gap:24px;font-size:13px;">' +
                            (purchStr ? '<div><span style="color:#6B7280;">Purchased:</span> ' + purchStr + '</div>' : '') +
                            '<div><span style="color:#6B7280;">Market value:</span> <strong>' + valStr + '</strong> <span style="font-size:11px;color:#9CA3AF;">(' + c.comparable_count + ' comparables)</span></div>' +
                            '</div>' +
                            '<div style="margin-top:8px;"><button onclick="showTCO(' + c.id + ')" style="font-size:12px;color:#000;font-weight:600;border:none;background:none;cursor:pointer;text-decoration:underline;">View TCO breakdown</button>' +
                            '<div id="tco-' + c.id + '" style="display:none;margin-top:8px;"></div></div>' +
                            '</div>';
                    }).join('');
                }
                async function addGarageCar() {
                    const body = new URLSearchParams({
                        make: document.getElementById('g-make').value,
                        model: document.getElementById('g-model').value,
                        year: document.getElementById('g-year').value,
                        mileage_km: document.getElementById('g-mileage').value,
                        purchase_price_eur: document.getElementById('g-price').value,
                    });
                    await fetch('/api/garage', { method: 'POST', body });
                    loadGarage();
                }
                async function removeGarageCar(id, btn) {
                    await fetch('/api/garage/' + id, { method: 'DELETE' });
                    btn.closest('div[style*="border"]').remove();
                }
                async function showTCO(id) {
                    const el = document.getElementById('tco-' + id);
                    if (el.style.display !== 'none') { el.style.display = 'none'; return; }
                    const resp = await fetch('/api/garage/' + id + '/tco');
                    const t = await resp.json();
                    el.style.display = 'block';
                    el.innerHTML = '<table style="font-size:12px;border-collapse:collapse;">' +
                        '<tr><td style="padding:2px 12px 2px 0;color:#6B7280;">Fuel/Energy</td><td>EUR ' + (t.fuel_annual_eur||0).toLocaleString() + '/yr</td></tr>' +
                        '<tr><td style="padding:2px 12px 2px 0;color:#6B7280;">Insurance</td><td>EUR ' + (t.insurance_annual_eur||0).toLocaleString() + '/yr</td></tr>' +
                        '<tr><td style="padding:2px 12px 2px 0;color:#6B7280;">Maintenance</td><td>EUR ' + (t.maintenance_annual_eur||0).toLocaleString() + '/yr</td></tr>' +
                        '<tr><td style="padding:2px 12px 2px 0;color:#6B7280;">Depreciation</td><td>EUR ' + (t.depreciation_annual_eur||0).toLocaleString() + '/yr</td></tr>' +
                        '<tr style="font-weight:600;border-top:1px solid #E5E7EB;"><td style="padding:4px 12px 2px 0;">Total</td><td style="padding-top:4px;">EUR ' + (t.total_annual_eur||0).toLocaleString() + '/yr (EUR ' + (t.total_monthly_eur||0).toLocaleString() + '/mo)</td></tr>' +
                        '<tr><td style="padding:2px 12px 2px 0;color:#6B7280;">Cost per km</td><td>EUR ' + (t.cost_per_km_eur||0) + '</td></tr>' +
                        '</table>';
                }
                loadGarage();
            """)),
            Script(src="/static/chat.js"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head("My Garage"), body)
