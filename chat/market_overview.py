"""Static FastCPI market dashboard using the shared chat chart builders."""

from __future__ import annotations

import json

from fasthtml.common import A, Body, Button, Div, H2, Html, NotStr, P, Script, Span

from charts import DASHBOARD, build_chart
from chat.components import left_pane, signin_overlay
from chat.layout import _head
from starlette.responses import RedirectResponse
from utils.fastcpi_i18n import app_tr


def _localize_chart(chart: dict, lang: str) -> dict:
    if lang != "fr":
        return chart
    names = {
        "coverage": "Couverture du marché",
        "index": "Indice de prix observé",
        "distribution": "Distribution des prix",
    }
    chart["title"] = names.get(chart["name"], chart["title"])
    figure = chart["figure"]
    layout = figure.get("layout", {})
    title = layout.get("title")
    if isinstance(title, dict):
        title["text"] = chart["title"]
    elif title:
        layout["title"] = chart["title"]
    replacements = {
        "Market": "Marché", "Observations": "Observations", "Sources": "Sources",
        "Index (base = 100)": "Indice (base = 100)",
        "Comparable price (EUR)": "Prix comparable (EUR)",
    }
    for axis in ("xaxis", "yaxis", "yaxis2"):
        axis_title = layout.get(axis, {}).get("title")
        if isinstance(axis_title, dict) and axis_title.get("text") in replacements:
            axis_title["text"] = replacements[axis_title["text"]]
    for trace in figure.get("data", []):
        trace["name"] = replacements.get(trace.get("name"), trace.get("name"))
        if "hovertemplate" in trace:
            trace["hovertemplate"] = trace["hovertemplate"].replace("Index", "Indice").replace("observations", "observations")
    return chart


def register_market_overview_routes(rt):
    @rt("/app/market-overview")
    def market_overview(sess):
        from chat.routes import _ensure_user, _list_sessions
        from utils.i18n import get_lang
        uid, email = _ensure_user(sess)
        if not uid or not email:
            return RedirectResponse("/", status_code=303)
        sessions = _list_sessions(uid) if uid else []
        lang = get_lang(sess)
        cards, scripts = [], []
        for name in DASHBOARD:
            chart = build_chart(name)
            if not chart:
                continue
            chart = _localize_chart(chart, lang)
            element_id = f"overview-{name}"
            cards.append(Div(Div(chart["title"], cls="visual-card-title"), Div(id=element_id, cls="visual-plot"), cls="visual-card"))
            scripts.append(
                f"Plotly.newPlot('{element_id}', {json.dumps(chart['figure']['data'])}, "
                f"{json.dumps(chart['figure']['layout'])}, {{responsive:true,displayModeBar:false}});"
            )
        body = Body(
            signin_overlay(lang), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid="", lang=lang),
            Div(
                Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span(app_tr("market_overview", lang), cls="chat-header-title"), cls="chat-header-left"),
                    Div(A(app_tr("back_to_chat", lang), href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2(app_tr("observed_market", lang), cls="text-xl font-semibold"),
                    P(app_tr("market_intro", lang), cls="text-sm text-gray-500 mb-4"),
                    Div(*cards, cls="visuals-grid"), cls="messages"),
                cls="center-pane"),
            Script(NotStr("\n".join(scripts))), Script(src="/static/chat.js?v=4"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head(app_tr("market_overview", lang)), body)
