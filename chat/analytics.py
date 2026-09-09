"""Analytics page -- natural-language to SQL over carhero schema, rendered as Plotly charts."""

from __future__ import annotations

import json
import logging
import re

import pandas as pd
import plotly.express as px
from fasthtml.common import (
    Html, Head, Body, Script, NotStr,
    Div, Span, H2, P, A, Button, Form, Input,
)
from starlette.requests import Request
from starlette.responses import JSONResponse

from chat.layout import _head
from chat.components import left_pane, signin_overlay
from chat.routes import _ensure_user, _list_sessions
from utils.llm import build_llm

log = logging.getLogger(__name__)


SCHEMA_SNIPPET = """\
-- CarHero read-only PostgreSQL schema.
-- ONLY generate SELECT queries. Use schema-qualified names.

carhero.car_listings (
    id, make VARCHAR(100), model VARCHAR(100), variant VARCHAR(200), generation VARCHAR(100),
    price_eur NUMERIC(12,2), price_original NUMERIC(12,2), currency VARCHAR(3),
    year INTEGER, mileage_km INTEGER,
    fuel_type VARCHAR(50) ('Petrol','Diesel','Electric','Hybrid','Plugin Hybrid'),
    transmission VARCHAR(50) ('Automatic','Manual','Semi-automatic'),
    body_type VARCHAR(50) ('Sedan','Estate','SUV','Coupe','Convertible','Hatchback'),
    engine_size_cc INTEGER, power_hp INTEGER, power_kw INTEGER, torque_nm INTEGER,
    drive_type VARCHAR(20), steering_side VARCHAR(5) ('LHD','RHD'), gears INTEGER,
    co2_grams INTEGER, fuel_consumption_l100km NUMERIC(4,1), emission_class VARCHAR(20),
    doors INTEGER, seats INTEGER, exterior_color VARCHAR(50),
    interior_color VARCHAR(50), interior_material VARCHAR(50),
    condition VARCHAR(20) ('new','used','certified'),
    first_registration_date DATE, owners_count INTEGER,
    accident_free BOOLEAN, service_history BOOLEAN,
    features JSONB, equipment_packages JSONB,
    source_url VARCHAR(500) UNIQUE, provider VARCHAR(50) ('autotrader','mobile_de','autoscout24','autohero','theparking','auto24_ee','auto24_lt','auto24_lv','blocket','otomoto','coches','marktplaats','nettiauto','bilbasen','donedeal','finn','standvirtual','autovit','collectingcars'),
    country VARCHAR(5) ('GB','DE','SE','PL','ES','NL','FI','DK','IE','NO','PT','RO','EE','LT','LV','EU'), city VARCHAR(100),
    seller_type VARCHAR(20) ('dealer','private'), seller_name VARCHAR(200),
    listed_date DATE, scraped_at TIMESTAMPTZ,
    image_urls JSONB, image_count INTEGER,
    status VARCHAR(20) ('active','sold','expired'),
    created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
)
-- Premium/luxury car listings from 19 European marketplaces across 17+ countries.
-- Brands: BMW, Mercedes-Benz, Audi, Porsche, Jaguar, Land Rover, Volvo, Tesla, Lexus, Maserati, Alfa Romeo, Ferrari, Corvette.
-- All prices in EUR. Mileage in km.

carhero.price_history (
    id, listing_id INTEGER, price_eur NUMERIC(12,2), recorded_at TIMESTAMPTZ
)
-- Price change tracking for listings over time.

carhero.market_snapshots (
    id, make VARCHAR(100), model VARCHAR(100), country VARCHAR(5),
    avg_price_eur NUMERIC(12,2), median_price_eur NUMERIC(12,2),
    listing_count INTEGER, avg_mileage_km INTEGER, avg_age_years NUMERIC(4,1),
    snapshot_date DATE, created_at TIMESTAMPTZ
)
-- Daily aggregated market statistics by make/model/country.
"""

SAMPLE_QUERIES = [
    "Average price by brand for active listings",
    "Top 10 cheapest Porsche 911s",
    "BMW X5 average price by country",
    "Listing count by fuel type",
    "Average mileage by brand for SUVs",
    "Price comparison: Audi Q5 vs BMW X3 vs Volvo XC60",
    "Most expensive cars listed on each provider",
    "Average price by model year for Mercedes-Benz C-Class",
]

SYSTEM = f"""You translate plain-English questions into a single PostgreSQL SELECT
query against the CarHero schema below, and suggest a chart.

Rules:
- Return ONLY a JSON object with exactly these keys:
  {{ "sql": "...", "chart": "bar|line|scatter|pie|area|treemap|none", "x": "...", "y": "...", "color": "...", "title": "..." }}
- Never modify data. SELECT only.
- Use schema-qualified names (carhero.car_listings, carhero.price_history, etc).
- Limit results sensibly (<=200 rows) unless a time-series needs more.
- For time series, order by the time column.
- Prices are in EUR, mileage in km.

Schema:
{SCHEMA_SNIPPET}
"""


def _draft_sql(question: str) -> dict:
    llm = build_llm()
    resp = llm.invoke(f"{SYSTEM}\n\nQuestion: {question}\n\nJSON:").content
    m = re.search(r"\{.*\}", resp, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON in model response: {resp[:400]}")
    return json.loads(m.group(0))


def _guard_sql(sql: str) -> None:
    s = sql.strip().rstrip(";").strip()
    lowered = s.lower()
    if not lowered.startswith("select") and not lowered.startswith("with"):
        raise ValueError("Only SELECT / WITH queries are allowed.")
    banned = ["insert ", "update ", "delete ", "drop ", "truncate ",
              "alter ", "grant ", "revoke ", "create ", "copy ", ";"]
    for b in banned:
        if b in lowered:
            raise ValueError(f"Disallowed keyword in SQL: {b.strip()}")


def _run_sql(sql: str) -> pd.DataFrame:
    _guard_sql(sql)
    from db import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        result = db.execute(text(sql))
        rows = [dict(r._mapping) for r in result]
        return pd.DataFrame(rows)
    finally:
        db.close()


def _chart_for(df: pd.DataFrame, spec: dict) -> dict | None:
    if df.empty:
        return None
    kind = (spec.get("chart") or "").lower()
    x = spec.get("x")
    y = spec.get("y")
    color = spec.get("color") or None
    title = spec.get("title") or ""

    cols = list(df.columns)
    if x and x not in cols:
        x = cols[0]
    if y and y not in cols:
        y = next((c for c in cols[1:] if pd.api.types.is_numeric_dtype(df[c])), cols[-1])
    if color and color not in cols:
        color = None
    if not x:
        x = cols[0]
    if not y and len(cols) > 1:
        y = cols[1]

    try:
        if kind == "bar":
            fig = px.bar(df, x=x, y=y, color=color, title=title, barmode="group")
        elif kind == "line":
            fig = px.line(df, x=x, y=y, color=color, title=title, markers=True)
        elif kind == "scatter":
            fig = px.scatter(df, x=x, y=y, color=color, title=title)
        elif kind == "pie":
            fig = px.pie(df, names=x, values=y, title=title)
        elif kind == "area":
            fig = px.area(df, x=x, y=y, color=color, title=title)
        elif kind == "treemap" and color:
            fig = px.treemap(df, path=[x], values=y, color=color, title=title)
        else:
            return None
    except Exception as e:
        log.warning("plotly failed: %s", e)
        return None

    fig.update_layout(
        paper_bgcolor="#FFFFFF", plot_bgcolor="#F5F5F5",
        font=dict(family="Inter, system-ui", color="#1A1A1A"),
        margin=dict(l=40, r=20, t=50, b=40),
        title=dict(font=dict(size=15)),
    )
    return json.loads(fig.to_json())


def register_analytics_routes(rt):

    @rt("/app/analytics")
    def analytics_home(sess):
        uid, email = _ensure_user(sess)
        sessions = _list_sessions(uid) if uid else []

        suggestions = Div(
            *[Button(q, cls="analytics-sugg", onclick=f"runAnalytics({q!r})")
              for q in SAMPLE_QUERIES],
            cls="analytics-suggestions",
        )

        body = Body(
            signin_overlay(),
            Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid=""),
            Div(
                Div(
                    Div(
                        Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span("Analytics", cls="chat-header-title"),
                        Span("--", cls="chat-header-dot"),
                        Span("Text to SQL + Charts", cls="chat-header-agent"),
                        cls="chat-header-left",
                    ),
                    Div(
                        A("Back to chat", href="/app", cls="header-action-btn"),
                        A("Market Map", href="/app/market-map", cls="header-action-btn"),
                        cls="chat-header-actions",
                    ),
                    cls="chat-header",
                ),
                Div(
                    Div(
                        H2("Car Market Analytics", cls="text-xl font-display font-bold"),
                        P("Ask questions in plain English. Get SQL + charts.", cls="text-sm text-gray-500"),
                        cls="py-6",
                    ),
                    Form(
                        Input(type="text", id="analytics-q", name="q",
                              placeholder="e.g. Average price by brand for active listings",
                              cls="w-full px-3 py-2 border border-gray-200 rounded-md text-sm",
                              onkeydown="if(event.key==='Enter'){event.preventDefault();runAnalytics()}"),
                        Button("Run", type="button", onclick="runAnalytics()",
                               cls="px-4 py-2 bg-black text-white rounded-md text-sm cursor-pointer border-none mt-2"),
                        cls="mb-4",
                    ),
                    suggestions,
                    Div(id="analytics-result"),
                    cls="px-6 pb-6 overflow-y-auto flex-1",
                ),
                cls="center-pane",
            ),
            Script(NotStr("""
                async function runAnalytics(q) {
                    if (q) document.getElementById('analytics-q').value = q;
                    const question = document.getElementById('analytics-q').value.trim();
                    const out = document.getElementById('analytics-result');
                    if (!question) return;
                    out.innerHTML = '<div style="padding:1rem;color:#6B7280">Thinking...</div>';
                    const r = await fetch('/app/analytics/run', {
                        method: 'POST',
                        body: new URLSearchParams({ q: question })
                    });
                    const data = await r.json();
                    if (data.error) {
                        out.innerHTML = `<div style="padding:1rem;color:#B91C1C"><strong>Error:</strong> ${data.error}<br><pre style="margin-top:.5rem;font-size:.7rem;overflow-x:auto">${data.sql || ''}</pre></div>`;
                        return;
                    }
                    const chartId = 'chart-' + Math.random().toString(36).slice(2, 8);
                    const tableHtml = data.table
                        ? `<div style="overflow-x:auto;margin-top:1rem">${data.table}</div>` : '';
                    out.innerHTML = `
                        <div style="padding:1rem">
                            <h3 style="font-size:1rem;font-weight:600;margin-bottom:.5rem">${data.title || question}</h3>
                            <pre style="font-size:.7rem;color:#6B7280;margin-bottom:1rem;overflow-x:auto">${data.sql}</pre>
                            <div id="${chartId}" style="width:100%;min-height:300px"></div>
                            ${tableHtml}
                        </div>`;
                    if (data.figure) {
                        Plotly.newPlot(chartId, data.figure.data, data.figure.layout, {responsive: true});
                    }
                }
                window.runAnalytics = runAnalytics;
            """)),
            Script(src="/static/chat.js"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head("Analytics"), body)

    @rt("/app/analytics/run", methods=["POST"])
    async def analytics_run(request: Request):
        form = await request.form()
        q = (form.get("q") or "").strip()
        if not q:
            return JSONResponse({"error": "Empty question."})

        try:
            spec = _draft_sql(q)
            sql = spec.get("sql", "").strip().rstrip(";")
        except Exception as e:
            return JSONResponse({"error": f"LLM couldn't draft SQL: {e}"})

        try:
            df = _run_sql(sql)
        except Exception as e:
            return JSONResponse({"error": f"SQL failed: {e}", "sql": sql})

        fig = _chart_for(df, spec)
        table_html = df.head(50).to_html(
            index=False, classes="artifact-table", border=0,
            float_format=lambda x: f"{x:,.2f}" if isinstance(x, float) else str(x))

        return JSONResponse({
            "sql": sql,
            "title": spec.get("title") or q,
            "figure": fig,
            "rows": len(df),
            "table": table_html,
        })
