"""Static FastCPI market dashboard using the shared chat chart builders."""

from __future__ import annotations

import json

from fasthtml.common import A, Body, Button, Div, H2, Html, NotStr, P, Script, Span

from charts import DASHBOARD, build_chart
from chat.components import left_pane, signin_overlay
from chat.layout import _head
from starlette.responses import RedirectResponse


def register_market_overview_routes(rt):
    @rt("/app/market-overview")
    def market_overview(sess):
        from chat.routes import _ensure_user, _list_sessions
        uid, email = _ensure_user(sess)
        if not uid or not email:
            return RedirectResponse("/?auth_error=invite_required", status_code=303)
        sessions = _list_sessions(uid) if uid else []
        cards, scripts = [], []
        for name in DASHBOARD:
            chart = build_chart(name)
            if not chart:
                continue
            element_id = f"overview-{name}"
            cards.append(Div(Div(chart["title"], cls="visual-card-title"), Div(id=element_id, cls="visual-plot"), cls="visual-card"))
            scripts.append(
                f"Plotly.newPlot('{element_id}', {json.dumps(chart['figure']['data'])}, "
                f"{json.dumps(chart['figure']['layout'])}, {{responsive:true,displayModeBar:false}});"
            )
        body = Body(
            signin_overlay(), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=sessions, current_sid=""),
            Div(
                Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span("Market Overview", cls="chat-header-title"), cls="chat-header-left"),
                    Div(A("Back to chat", href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2("Observed market intelligence", cls="text-xl font-semibold"),
                    P("Asking-price observations from public B2B sources. Coverage is not the complete market.", cls="text-sm text-gray-500 mb-4"),
                    Div(*cards, cls="visuals-grid"), cls="messages"),
                cls="center-pane"),
            Script(NotStr("\n".join(scripts))), Script(src="/static/chat.js?v=3"),
            cls="bg-white text-ink font-sans antialiased app pane-closed",
        )
        return Html(_head("Market Overview"), body)
