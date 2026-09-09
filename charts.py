"""Shared Plotly builders for streamed chat charts and the market dashboard."""

from __future__ import annotations

import json
import re

import plotly.graph_objects as go
from sqlalchemy import text

from db import SCHEMA, SessionLocal

INK, MUTED, GRID, ACCENT = "#17201c", "#66736d", "#e7ece9", "#147d64"


def _figure(fig: go.Figure) -> dict:
    return json.loads(fig.to_json())


def coverage_by_market() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT o.market, COUNT(DISTINCT o.id) offers, COUNT(po.id) observations,
                   COUNT(DISTINCT ps.domain) sources
            FROM {SCHEMA}.offers o
            JOIN {SCHEMA}.price_sources ps ON ps.id=o.source_id
            JOIN {SCHEMA}.price_observations po ON po.offer_id=o.id
            GROUP BY o.market ORDER BY o.market
        """)).fetchall()
    finally:
        db.close()
    fig = go.Figure()
    fig.add_bar(x=[r.market for r in rows], y=[r.observations for r in rows], name="Observations", marker_color=ACCENT)
    fig.add_scatter(x=[r.market for r in rows], y=[r.sources for r in rows], name="Sources", yaxis="y2", mode="lines+markers")
    fig.update_layout(title="Observed market coverage", paper_bgcolor="white", plot_bgcolor="white",
                      font={"family": "Inter, sans-serif", "color": INK},
                      xaxis={"title": "Market", "gridcolor": GRID},
                      yaxis={"title": "Observations", "gridcolor": GRID},
                      yaxis2={"title": "Sources", "overlaying": "y", "side": "right"},
                      margin={"l": 50, "r": 50, "t": 45, "b": 40}, height=360)
    return _figure(fig)


def index_history() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT series_key, market, period_date, index_value, observation_count
            FROM {SCHEMA}.price_indices ORDER BY series_key, market, period_date
        """)).fetchall()
    finally:
        db.close()
    fig = go.Figure()
    groups: dict[tuple[str, str], list] = {}
    for row in rows:
        groups.setdefault((row.series_key, row.market), []).append(row)
    for (series, market), values in groups.items():
        fig.add_scatter(x=[v.period_date for v in values], y=[v.index_value for v in values],
                        name=f"{series} · {market}", mode="lines+markers",
                        customdata=[v.observation_count for v in values],
                        hovertemplate="%{x}<br>Index %{y:.2f}<br>%{customdata} observations<extra></extra>")
    fig.update_layout(title="Web-observed price indices", paper_bgcolor="white", plot_bgcolor="white",
                      font={"family": "Inter, sans-serif", "color": INK},
                      xaxis={"gridcolor": GRID}, yaxis={"title": "Index (base = 100)", "gridcolor": GRID},
                      margin={"l": 50, "r": 20, "t": 45, "b": 40}, height=360)
    return _figure(fig)


def price_distribution() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT o.market, po.amount_comparable
            FROM {SCHEMA}.offers o JOIN {SCHEMA}.price_observations po ON po.offer_id=o.id
            WHERE po.amount_comparable IS NOT NULL AND po.currency_comparable='EUR'
            ORDER BY o.market
        """)).fetchall()
    finally:
        db.close()
    fig = go.Figure()
    markets = sorted({r.market for r in rows})
    for market in markets:
        values = [float(r.amount_comparable) for r in rows if r.market == market]
        fig.add_box(y=values, name=market, boxpoints="outliers")
    fig.update_layout(title="Comparable EUR price distribution", paper_bgcolor="white", plot_bgcolor="white",
                      font={"family": "Inter, sans-serif", "color": INK},
                      yaxis={"title": "Comparable price (EUR)", "gridcolor": GRID},
                      margin={"l": 60, "r": 20, "t": 45, "b": 40}, height=360)
    return _figure(fig)


CHARTS = {
    "coverage": ("Market coverage", coverage_by_market),
    "index": ("Observed price index", index_history),
    "distribution": ("Price distribution", price_distribution),
}
DASHBOARD = ["coverage", "index", "distribution"]


def build_chart(name: str) -> dict | None:
    entry = CHARTS.get(name)
    if not entry:
        return None
    title, builder = entry
    return {"name": name, "title": title, "figure": builder()}


def detect_charts(message: str) -> list[str]:
    value = (message or "").lower()
    hits = []
    if re.search(r"\bcoverage\b|sources?|markets?", value):
        hits.append("coverage")
    if re.search(r"\bindex\b|trend|over time|history", value):
        hits.append("index")
    if re.search(r"distribution|quartile|median|range|spread", value):
        hits.append("distribution")
    return hits[:2]
