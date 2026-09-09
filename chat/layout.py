"""3-pane chat page wrapper."""

from __future__ import annotations

from fasthtml.common import (
    Html, Head, Body, Meta, Title, Link, Script, NotStr,
    Div, Span,
)

from chat.components import left_pane, center_pane, right_pane, signin_overlay


TAILWIND_CONFIG = """
tailwind.config = {
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: '#1A1A1A', muted: '#6B7280', dim: '#9CA3AF' },
        surface: { DEFAULT: '#FFFFFF', alt: '#F5F5F5' },
        border: '#E5E5E5',
      },
      fontFamily: {
        display: ['DM Serif Display', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
}
"""


def _head(title: str = "CarHero") -> Head:
    return Head(
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1, viewport-fit=cover"),
        Meta(name="theme-color", content="#1A1A1A"),
        Meta(name="apple-mobile-web-app-capable", content="yes"),
        Meta(name="apple-mobile-web-app-status-bar-style", content="black-translucent"),
        Link(rel="icon", href="/static/favicon.svg", type="image/svg+xml"),
        Link(rel="apple-touch-icon", href="/static/favicon.svg"),
        Link(rel="manifest", href="/static/manifest.json"),
        Title(f"{title} -- CarHero"),
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(rel="stylesheet",
             href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=DM+Serif+Display&display=swap"),
        Script(src="https://cdn.tailwindcss.com"),
        Script(NotStr(TAILWIND_CONFIG)),
        Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js"),
        Script(src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"),
        Link(rel="stylesheet", href="/static/app.css"),
    )


def chat_page(user_email=None, sessions=None, current_sid="",
              messages=None, current_agent_slug=None, readonly=False, lang="en"):
    from utils.i18n import js_translations
    import json as _json
    from fasthtml.common import Button
    body = Body(
        signin_overlay(lang=lang),
        Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
        left_pane(user_email=user_email, sessions=sessions, current_sid=current_sid, lang=lang),
        center_pane(messages=messages, current_agent_slug=current_agent_slug, lang=lang),
        Div(id="right-overlay", cls="right-overlay", onclick="toggleArtifactPane()"),
        right_pane(lang=lang),
        Button(
            NotStr('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>'),
            Span("Results", cls="toggle-label"),
            id="right-pane-toggle-btn", cls="right-pane-toggle", onclick="toggleArtifactPane()",
        ),
        Script(_json.dumps(js_translations(lang)), id="i18n-data", type="application/json"),
        Script(src="/static/chat.js?v=2"),
        cls="bg-white text-ink font-sans antialiased app",
    )
    return Html(_head("Car Advisor"), body)


def shared_chat_page(title: str = "Shared Chat", messages=None, agent_slug=None):
    from agents.registry import AGENTS_BY_SLUG

    msg_els = []
    for m in (messages or []):
        role = m.get("role", "user")
        content = m.get("content", "")
        agent = m.get("agent_slug")
        bubble = Div(content, cls="msg-bubble")
        if role == "assistant" and agent:
            spec = AGENTS_BY_SLUG.get(agent)
            agent_label = Div(
                Div(spec.icon if spec else "*", cls="msg-agent-icon"),
                Div(spec.name if spec else agent, cls="msg-agent-label"),
                cls="msg-agent",
            )
            msg_els.append(Div(agent_label, bubble, cls=f"msg msg-{role}"))
        else:
            msg_els.append(Div(bubble, cls=f"msg msg-{role}"))

    body = Body(
        Div(
            Div(
                Div(title, cls="chat-header-title"),
                Div(
                    Div("Shared via CarHero", cls="text-sm text-gray-400"),
                    cls="chat-header-actions",
                ),
                cls="chat-header",
            ),
            Div(*msg_els, id="messages", cls="messages"),
            cls="center-pane",
            style="max-width:800px;margin:0 auto;",
        ),
        Script(src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"),
        Script(NotStr("""
            document.querySelectorAll('.msg-bubble').forEach(b => {
                if (typeof marked !== 'undefined') b.innerHTML = marked.parse(b.textContent);
            });
        """)),
        cls="bg-white text-ink font-sans antialiased",
    )
    return Html(_head(title), body)
