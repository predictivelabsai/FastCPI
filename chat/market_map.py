"""Market Map — interactive treemap + price trends + geographic comparison + value map + price index.

GET /app/market-map              → full-page Market Map with tabs (Overview, Value Map, Price Index)
GET /api/market-map/treemap      → Plotly JSON (supports ?country=&make=&fuel_type=)
GET /api/market-map/trends       → Plotly JSON (supports ?country=&make=&fuel_type=)
GET /api/market-map/geo          → Plotly JSON (supports ?make=&model=)
GET /api/market-map/value-map    → Plotly JSON scatter (score vs price, quadrants)
GET /api/market-map/price-index  → Plotly JSON line (index over time/year)
GET /api/market-map/filters      → available filter values
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fasthtml.common import (
    Html, Head, Body, Script, NotStr,
    Div, Span, H2, H3, P, A, Button, Select, Option, Label, Input,
)
from starlette.requests import Request
from starlette.responses import JSONResponse

from chat.layout import _head
from chat.components import left_pane, signin_overlay
from chat.routes import _ensure_user, _list_sessions

log = logging.getLogger(__name__)

CHART_LAYOUT = dict(
    paper_bgcolor="#FFFFFF", plot_bgcolor="#F5F5F5",
    font=dict(family="Inter, system-ui", color="#1A1A1A"),
    margin=dict(l=40, r=20, t=50, b=40),
    title=dict(font=dict(size=15)),
)

from utils.config import get_all_brands
PREMIUM_BRANDS = get_all_brands()


def _build_where(params: dict) -> tuple[str, dict]:
    conditions = ["status = 'active'", "price_eur > 0"]
    bind = {}
    country = params.get("country", "").strip()
    if country and country != "ALL":
        conditions.append("country = :country")
        bind["country"] = country
    make = params.get("make", "").strip()
    if make and make != "ALL":
        conditions.append("make = :make")
        bind["make"] = make
    fuel_type = params.get("fuel_type", "").strip()
    if fuel_type and fuel_type != "ALL":
        conditions.append("fuel_type ILIKE :fuel_type")
        bind["fuel_type"] = f"%{fuel_type}%"
    min_year = params.get("min_year", "").strip()
    if min_year and min_year.isdigit():
        conditions.append("year >= :min_year")
        bind["min_year"] = int(min_year)
    max_year = params.get("max_year", "").strip()
    if max_year and max_year.isdigit():
        conditions.append("year <= :max_year")
        bind["max_year"] = int(max_year)
    return "WHERE " + " AND ".join(conditions), bind


def _fetch_treemap_data(params: dict):
    """Fetch treemap data with geographic price spread as color.

    For each make/model, computes:
    - listing_count: total listings
    - avg_price: overall average
    - price_spread_pct: (max_country_avg - min_country_avg) / overall_avg * 100
      A high spread means big arbitrage opportunity across countries.
    """
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        where, bind = _build_where(params)
        sql = text(f"""
            WITH by_country AS (
                SELECT make, model, country,
                       COUNT(*) AS cnt,
                       AVG(price_eur) AS country_avg
                FROM carhero.car_listings
                {where}
                GROUP BY make, model, country
                HAVING COUNT(*) >= 1
            ),
            aggregated AS (
                SELECT make, model,
                       SUM(cnt) AS listing_count,
                       ROUND(AVG(country_avg)::numeric, 0) AS avg_price,
                       CASE WHEN COUNT(DISTINCT country) >= 2
                            THEN ROUND(((MAX(country_avg) - MIN(country_avg))
                                  / NULLIF(AVG(country_avg), 0) * 100)::numeric, 1)
                            ELSE 0 END AS price_spread_pct
                FROM by_country
                GROUP BY make, model
            )
            SELECT * FROM aggregated
            ORDER BY listing_count DESC
            LIMIT 100
        """)
        return [dict(r._mapping) for r in db.execute(sql, bind)]
    finally:
        db.close()


def _fetch_trend_data(params: dict):
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        where, bind = _build_where(params)
        where += " AND year IS NOT NULL AND year >= 2005"
        sql = text(f"""
            SELECT year, make,
                   ROUND(AVG(price_eur)::numeric, 0) AS avg_price,
                   COUNT(*) AS listings
            FROM carhero.car_listings
            {where}
            GROUP BY year, make
            HAVING COUNT(*) >= 1
            ORDER BY year
        """)
        return [dict(r._mapping) for r in db.execute(sql, bind)]
    finally:
        db.close()


def _fetch_geo_data(params: dict):
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        conditions = ["status = 'active'", "price_eur > 0"]
        bind = {}
        make = params.get("make", "").strip()
        if make and make != "ALL":
            conditions.append("make = :make")
            bind["make"] = make
        model = params.get("model", "").strip()
        if model:
            conditions.append("model ILIKE :model")
            bind["model"] = f"%{model}%"
        where = "WHERE " + " AND ".join(conditions)
        sql = text(f"""
            SELECT country, provider,
                   COUNT(*) AS listings,
                   ROUND(AVG(price_eur)::numeric, 0) AS avg_price,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur)::numeric, 0) AS median_price
            FROM carhero.car_listings
            {where}
            GROUP BY country, provider
            HAVING COUNT(*) >= 1
            ORDER BY avg_price
        """)
        return [dict(r._mapping) for r in db.execute(sql, bind)]
    finally:
        db.close()


def _fetch_filter_options():
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        countries = [r[0] for r in db.execute(text(
            "SELECT DISTINCT country FROM carhero.car_listings WHERE status='active' AND country IS NOT NULL ORDER BY 1"
        ))]
        makes = [r[0] for r in db.execute(text(
            "SELECT DISTINCT make FROM carhero.car_listings WHERE status='active' ORDER BY 1"
        ))]
        fuel_types = [r[0] for r in db.execute(text(
            "SELECT DISTINCT fuel_type FROM carhero.car_listings WHERE status='active' AND fuel_type IS NOT NULL ORDER BY 1"
        ))]
        return {"countries": countries, "makes": makes, "fuel_types": fuel_types}
    finally:
        db.close()


def _build_treemap_fig(rows):
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["listing_count"] = df["listing_count"].astype(int)
    df["avg_price"] = pd.to_numeric(df["avg_price"], errors="coerce").fillna(0)
    df["price_spread_pct"] = pd.to_numeric(df["price_spread_pct"], errors="coerce").fillna(0)

    has_spread = (df["price_spread_pct"] > 0).sum() > len(df) * 0.2
    if has_spread:
        color_col = "price_spread_pct"
        color_scale = "RdYlGn_r"
        title = "Listings by Brand/Model (color = price spread % across countries)"
    else:
        color_col = "avg_price"
        color_scale = "Viridis"
        title = "Listings by Brand/Model (color = avg price EUR)"

    fig = px.treemap(
        df, path=["make", "model"],
        values="listing_count", color=color_col,
        color_continuous_scale=color_scale,
        title=title,
        hover_data={"avg_price": ":,.0f", "price_spread_pct": ":.1f"},
    )
    fig.update_layout(**CHART_LAYOUT)
    fig.update_layout(margin=dict(t=30, l=0, r=0, b=0))
    return fig


def _build_trend_fig(rows):
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["avg_price"] = pd.to_numeric(df["avg_price"], errors="coerce")
    fig = px.area(
        df, x="year", y="avg_price", color="make",
        title="Average Price by Model Year & Brand", markers=True,
    )
    fig.update_layout(**CHART_LAYOUT)
    return fig


def _build_geo_fig(rows):
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["label"] = df["country"] + " / " + df["provider"]
    fig = px.bar(
        df, x="label", y="avg_price", color="country",
        text="avg_price", title="Average Price by Country & Provider",
    )
    fig.update_traces(texttemplate="EUR %{text:,.0f}", textposition="outside")
    fig.update_layout(**CHART_LAYOUT)
    fig.update_layout(xaxis_title="", yaxis_title="Price (EUR)")
    return fig


def _fetch_value_map_data(params: dict):
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        where, bind = _build_where(params)
        sql = text(f"""
            WITH model_agg AS (
                SELECT cl.make, cl.model,
                       COUNT(*) AS listing_count,
                       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cl.price_eur)::numeric, 0) AS median_price,
                       ROUND(AVG(s.score)::numeric, 1) AS avg_score
                FROM carhero.car_listings cl
                JOIN carhero.investment_scores s ON s.listing_id = cl.id
                    AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM carhero.investment_scores)
                {where.replace('WHERE', 'WHERE', 1) if where else ''}
                GROUP BY cl.make, cl.model
                HAVING COUNT(*) >= 2 AND AVG(s.score) IS NOT NULL
            )
            SELECT * FROM model_agg ORDER BY avg_score DESC LIMIT 80
        """)
        return [dict(r._mapping) for r in db.execute(sql, bind)]
    finally:
        db.close()


def _build_value_map_fig(rows):
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["median_price"] = pd.to_numeric(df["median_price"], errors="coerce")
    df["avg_score"] = pd.to_numeric(df["avg_score"], errors="coerce")
    df["listing_count"] = df["listing_count"].astype(int)

    price_mid = df["median_price"].median()
    score_mid = df["avg_score"].median()

    fig = go.Figure()
    for make in sorted(df["make"].unique()):
        sub = df[df["make"] == make]
        fig.add_trace(go.Scatter(
            x=sub["median_price"], y=sub["avg_score"],
            mode="markers",
            marker=dict(size=np.clip(np.sqrt(sub["listing_count"]) * 4, 8, 50)),
            name=make,
            text=sub["make"] + " " + sub["model"],
            hovertemplate="<b>%{text}</b><br>Price: EUR %{x:,.0f}<br>Score: %{y:.1f}<extra></extra>",
        ))

    fig.add_hline(y=score_mid, line_dash="dot", line_color="gray", opacity=0.4)
    fig.add_vline(x=price_mid, line_dash="dot", line_color="gray", opacity=0.4)

    fig.add_annotation(x=0.03, y=0.97, xref="paper", yref="paper",
                       text="BARGAINS", showarrow=False, font=dict(size=13, color="#16A34A"))
    fig.add_annotation(x=0.97, y=0.97, xref="paper", yref="paper",
                       text="BLUE CHIPS", showarrow=False, font=dict(size=13, color="#2563EB"))
    fig.add_annotation(x=0.03, y=0.03, xref="paper", yref="paper",
                       text="SLEEPERS", showarrow=False, font=dict(size=13, color="#D97706"))
    fig.add_annotation(x=0.97, y=0.03, xref="paper", yref="paper",
                       text="OVERPRICED", showarrow=False, font=dict(size=13, color="#DC2626"))

    fig.update_layout(
        **CHART_LAYOUT,
        title="Value Map: Investment Score vs Median Price",
        xaxis_title="Median Price (EUR)",
        yaxis_title="Investment Score (0-100)",
    )
    return fig


def _fetch_price_index_data(params: dict):
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        base_year = int(params.get("base_year", "2015") or "2015")
        make_filter = params.get("make", "").strip()

        conditions = ["status = 'active'", "price_eur > 0", "year IS NOT NULL", "year >= 2005"]
        bind = {}
        if make_filter and make_filter != "ALL":
            conditions.append("make = :make")
            bind["make"] = make_filter
        where = " AND ".join(conditions)

        sql = text(f"""
            WITH by_year AS (
                SELECT year, make,
                       AVG(price_eur) AS avg_price,
                       COUNT(*) AS cnt
                FROM carhero.car_listings
                WHERE {where}
                GROUP BY year, make
                HAVING COUNT(*) >= 2
            ),
            base AS (
                SELECT make, AVG(avg_price) AS base_price
                FROM by_year WHERE year = :base_year
                GROUP BY make
            )
            SELECT by.year, by.make,
                   ROUND((by.avg_price / NULLIF(b.base_price, 0) * 100)::numeric, 1) AS index_value,
                   by.cnt AS listings
            FROM by_year by
            JOIN base b ON b.make = by.make
            ORDER BY by.year, by.make
        """)
        bind["base_year"] = base_year
        rows = [dict(r._mapping) for r in db.execute(sql, bind)]
        return rows, base_year
    finally:
        db.close()


def _build_price_index_fig(rows, base_year):
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["index_value"] = pd.to_numeric(df["index_value"], errors="coerce")

    fig = px.line(
        df, x="year", y="index_value", color="make",
        title=f"Price Index (base year {base_year} = 100)",
        markers=True,
    )
    fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5,
                  annotation_text=f"Base ({base_year})")
    fig.update_layout(**CHART_LAYOUT)
    fig.update_layout(xaxis_title="Model Year", yaxis_title="Price Index")
    return fig


COUNTRY_NAMES = {"GB": "United Kingdom", "DE": "Germany", "EU": "Other EU"}


def register_market_map_routes(rt):

    @rt("/api/market-map/treemap")
    def treemap_json(request: Request):
        params = dict(request.query_params)
        rows = _fetch_treemap_data(params)
        fig = _build_treemap_fig(rows)
        if not fig:
            return JSONResponse({"error": "No data"})
        return JSONResponse(json.loads(fig.to_json()))

    @rt("/api/market-map/trends")
    def trends_json(request: Request):
        params = dict(request.query_params)
        rows = _fetch_trend_data(params)
        fig = _build_trend_fig(rows)
        if not fig:
            return JSONResponse({"error": "No data"})
        return JSONResponse(json.loads(fig.to_json()))

    @rt("/api/market-map/geo")
    def geo_json(request: Request):
        params = dict(request.query_params)
        rows = _fetch_geo_data(params)
        fig = _build_geo_fig(rows)
        if not fig:
            return JSONResponse({"error": "No data"})
        return JSONResponse(json.loads(fig.to_json()))

    @rt("/api/market-map/value-map")
    def value_map_json(request: Request):
        params = dict(request.query_params)
        rows = _fetch_value_map_data(params)
        fig = _build_value_map_fig(rows)
        if not fig:
            return JSONResponse({"error": "No data"})
        return JSONResponse(json.loads(fig.to_json()))

    @rt("/api/market-map/price-index")
    def price_index_json(request: Request):
        params = dict(request.query_params)
        rows, base_year = _fetch_price_index_data(params)
        fig = _build_price_index_fig(rows, base_year)
        if not fig:
            return JSONResponse({"error": "No data"})
        return JSONResponse(json.loads(fig.to_json()))

    @rt("/api/market-map/filters")
    def filter_options():
        return JSONResponse(_fetch_filter_options())

    @rt("/app/market-map")
    def market_map_page(sess):
        uid, email = _ensure_user(sess)
        sessions = _list_sessions(uid) if uid else []

        country_options = [
            Option("All Countries", value="ALL", selected=True),
            Option("United Kingdom", value="GB"),
            Option("Germany", value="DE"),
            Option("Other EU", value="EU"),
        ]
        make_options = [Option("All Brands", value="ALL", selected=True)] + [
            Option(b, value=b) for b in PREMIUM_BRANDS
        ]
        fuel_options = [
            Option("All Fuels", value="ALL", selected=True),
            Option("Petrol", value="Petrol"),
            Option("Diesel", value="Diesel"),
            Option("Electric", value="Electric"),
            Option("Hybrid", value="Hybrid"),
            Option("Plugin Hybrid", value="Plugin Hybrid"),
        ]

        body = Body(
            signin_overlay(),
            Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid=""),
            Div(
                Div(
                    Div(
                        Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span("Market Map", cls="chat-header-title"),
                        cls="chat-header-left",
                    ),
                    Div(
                        A("Back to chat", href="/app", cls="header-action-btn"),
                        A("Analytics", href="/app/analytics", cls="header-action-btn"),
                        cls="chat-header-actions",
                    ),
                    cls="chat-header",
                ),
                Div(
                    # Tab navigation
                    Div(
                        Button("Overview", id="tab-overview", cls="mm-tab active", onclick="switchTab('overview')"),
                        Button("Value Map", id="tab-valuemap", cls="mm-tab", onclick="switchTab('valuemap')"),
                        Button("Price Index", id="tab-index", cls="mm-tab", onclick="switchTab('index')"),
                        cls="flex gap-1 mb-4 border-b border-gray-200 px-6 pt-4",
                    ),
                    # Filters (shared across tabs)
                    Div(
                        Div(
                            Label("Country", cls="text-xs text-gray-400 block mb-1"),
                            Select(*country_options, id="filter-country",
                                   cls="text-sm border border-gray-200 rounded px-2 py-1.5 bg-white",
                                   onchange="applyFilters()"),
                            cls="flex flex-col",
                        ),
                        Div(
                            Label("Brand", cls="text-xs text-gray-400 block mb-1"),
                            Select(*make_options, id="filter-make",
                                   cls="text-sm border border-gray-200 rounded px-2 py-1.5 bg-white",
                                   onchange="applyFilters()"),
                            cls="flex flex-col",
                        ),
                        Div(
                            Label("Fuel Type", cls="text-xs text-gray-400 block mb-1"),
                            Select(*fuel_options, id="filter-fuel",
                                   cls="text-sm border border-gray-200 rounded px-2 py-1.5 bg-white",
                                   onchange="applyFilters()"),
                            cls="flex flex-col",
                        ),
                        Div(
                            Label("Model (geo)", cls="text-xs text-gray-400 block mb-1"),
                            Input(type="text", id="filter-model", placeholder="e.g. X5, 3 Series...",
                                  cls="text-sm border border-gray-200 rounded px-2 py-1.5 w-36",
                                  onkeydown="if(event.key==='Enter')applyFilters()"),
                            cls="flex flex-col",
                        ),
                        Button("Apply", onclick="applyFilters()",
                               cls="self-end px-4 py-1.5 text-sm bg-black text-white rounded cursor-pointer border-none hover:bg-gray-800"),
                        cls="flex flex-wrap items-end gap-4 mb-4 p-3 bg-gray-50 rounded-lg border border-gray-100 mx-6",
                    ),
                    # Tab: Overview (existing content)
                    Div(
                        H2("Market Overview", cls="text-xl font-display font-bold mb-1"),
                        P("Larger blocks = more listings. Color = price spread across countries.",
                          cls="text-sm text-gray-500 mb-4"),
                        Div(id="treemap-chart", style="width:100%;min-height:500px;"),
                        H3("Price by Model Year", cls="text-lg font-display font-bold mt-8 mb-1"),
                        P("Average asking price by model year and brand.",
                          cls="text-sm text-gray-500 mb-4"),
                        Div(id="trend-chart", style="width:100%;min-height:400px;"),
                        H3("Geographic Price Comparison", cls="text-lg font-display font-bold mt-8 mb-1"),
                        P("Average price for the same brand/model across countries and providers.",
                          cls="text-sm text-gray-500 mb-4"),
                        Div(id="geo-chart", style="width:100%;min-height:400px;"),
                        id="tab-content-overview",
                        cls="px-6 pb-4",
                    ),
                    # Tab: Value Map
                    Div(
                        H2("Value Map", cls="text-xl font-display font-bold mb-1"),
                        P("Investment Score vs Median Price per model. Top-left = bargains, top-right = blue chips.",
                          cls="text-sm text-gray-500 mb-4"),
                        Div(id="value-map-chart", style="width:100%;min-height:550px;"),
                        id="tab-content-valuemap",
                        cls="px-6 pb-4",
                        style="display:none",
                    ),
                    # Tab: Price Index
                    Div(
                        H2("Price Index", cls="text-xl font-display font-bold mb-1"),
                        P("Price index normalized to base year = 100. Shows which brands gain or lose value by model year.",
                          cls="text-sm text-gray-500 mb-4"),
                        Div(id="price-index-chart", style="width:100%;min-height:450px;"),
                        id="tab-content-index",
                        cls="px-6 pb-4",
                        style="display:none",
                    ),
                    cls="overflow-y-auto flex-1",
                ),
                cls="center-pane",
            ),
            Script(NotStr("""
                let currentTab = 'overview';
                const noData = '<p style="color:#888;padding:2rem;text-align:center">No data for these filters.</p>';

                function getFilterParams() {
                    const country = document.getElementById('filter-country').value;
                    const make = document.getElementById('filter-make').value;
                    const fuel = document.getElementById('filter-fuel').value;
                    const model = document.getElementById('filter-model').value.trim();
                    const params = new URLSearchParams();
                    if (country && country !== 'ALL') params.set('country', country);
                    if (make && make !== 'ALL') params.set('make', make);
                    if (fuel && fuel !== 'ALL') params.set('fuel_type', fuel);
                    if (model) params.set('model', model);
                    return params.toString();
                }

                function switchTab(tab) {
                    document.querySelectorAll('[id^="tab-content-"]').forEach(el => el.style.display = 'none');
                    document.querySelectorAll('.mm-tab').forEach(el => el.classList.remove('active'));
                    document.getElementById('tab-content-' + tab).style.display = 'block';
                    document.getElementById('tab-' + tab.replace('valuemap','valuemap').replace('index','index')).classList.add('active');
                    currentTab = tab;
                    applyFilters();
                }

                async function loadOverview(qs) {
                    const [t, r, g] = await Promise.all([
                        fetch('/api/market-map/treemap?' + qs).then(r => r.json()),
                        fetch('/api/market-map/trends?' + qs).then(r => r.json()),
                        fetch('/api/market-map/geo?' + qs).then(r => r.json()),
                    ]);
                    if (t.data) Plotly.newPlot('treemap-chart', t.data, t.layout, {responsive: true});
                    else document.getElementById('treemap-chart').innerHTML = noData;
                    if (r.data) Plotly.newPlot('trend-chart', r.data, r.layout, {responsive: true});
                    else document.getElementById('trend-chart').innerHTML = noData;
                    if (g.data) Plotly.newPlot('geo-chart', g.data, g.layout, {responsive: true});
                    else document.getElementById('geo-chart').innerHTML = noData;
                }

                async function loadValueMap(qs) {
                    const r = await fetch('/api/market-map/value-map?' + qs);
                    const data = await r.json();
                    if (data.data) Plotly.newPlot('value-map-chart', data.data, data.layout, {responsive: true});
                    else document.getElementById('value-map-chart').innerHTML = noData;
                }

                async function loadPriceIndex(qs) {
                    const r = await fetch('/api/market-map/price-index?' + qs);
                    const data = await r.json();
                    if (data.data) Plotly.newPlot('price-index-chart', data.data, data.layout, {responsive: true});
                    else document.getElementById('price-index-chart').innerHTML = noData;
                }

                async function applyFilters() {
                    const qs = getFilterParams();
                    if (currentTab === 'overview') await loadOverview(qs);
                    else if (currentTab === 'valuemap') await loadValueMap(qs);
                    else if (currentTab === 'index') await loadPriceIndex(qs);
                }

                applyFilters();
            """)),
            Script(src="/static/chat.js"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head("Market Map"), body)
