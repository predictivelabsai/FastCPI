"""Item-first supplier variance dashboard with country and EU review modes."""

from __future__ import annotations

import json
from urllib.parse import urlencode

from fasthtml.common import (
    A, Body, Button, Div, Form, H2, H3, Html, Input, Label, NotStr,
    Option, P, Script, Select, Span,
)
from starlette.responses import RedirectResponse

from chat.components import left_pane, signin_overlay
from chat.layout import _head
from pricing.analytics import (
    choose_default_market, get_catalog_item, latest_item_offers,
    list_observed_items, summarize_markets, summarize_offers,
)
from pricing.markets import MARKETS
from utils.fastcpi_i18n import app_catalog_item_name, app_market_name, app_tr


def _unit_name(unit: str | None, lang: str) -> str:
    values = {
        "each": ("item", "unité"), "unit": ("unit", "unité"),
        "pack": ("pack", "rame"), "hour": ("hour", "heure"),
    }
    pair = values.get(unit or "unit", (unit or "unit", unit or "unité"))
    return pair[1] if lang == "fr" else pair[0]


def _price(value: float | None, unit: str | None, lang: str) -> str:
    if value is None:
        return "—"
    number = _number(value, lang)
    return f"{number} € / {_unit_name(unit, lang)}" if lang == "fr" else f"€{number} / {_unit_name(unit, lang)}"


def _number(value: float, lang: str) -> str:
    rendered = f"{value:,.2f}"
    return rendered.replace(",", " ").replace(".", ",") if lang == "fr" else rendered


def _percentage(value: float | None, lang: str) -> str:
    if value is None:
        return "—"
    rendered = f"{value:.1f}"
    return f"{rendered.replace('.', ',') if lang == 'fr' else rendered}%"


def _source_count(count: int, lang: str) -> str:
    word = app_tr("source", lang) if count == 1 else app_tr("sources", lang)
    return f"{count} {word}"


def _date(value, lang: str) -> str:
    if not value:
        return "—"
    rendered = value.strftime("%d/%m/%Y %H:%M") if lang == "fr" else value.strftime("%d %b %Y %H:%M")
    return f"{rendered} UTC"


def _safe_source_url(value: str | None) -> str:
    value = (value or "").strip()
    return value if value.startswith(("https://", "http://")) else "#"


def _stat_card(label: str, value: str, detail: str = ""):
    return Div(
        P(label, cls="variance-stat-label"),
        P(value, cls="variance-stat-value"),
        P(detail, cls="variance-stat-detail") if detail else None,
        cls="variance-stat-card",
    )


def _supplier_chart(offers: list[dict], country_name: str, summary: dict, lang: str) -> dict:
    rows = sorted(offers, key=lambda offer: offer["amount_comparable"])
    labels = [
        offer["supplier"] if offer["supplier"] == offer["source_domain"]
        else f"{offer['supplier']} · {offer['source_domain']}"
        for offer in rows
    ]
    title = app_tr("current_supplier_prices", lang)
    figure = {
        "data": [{
            "type": "bar", "orientation": "h",
            "x": [offer["amount_comparable"] for offer in rows], "y": labels,
            "customdata": [[offer["title"], offer["source_domain"], _date(offer["captured_at"], lang)] for offer in rows],
            "marker": {"color": "#147d64"},
            "hovertemplate": "%{y}<br>€%{x:.2f}<br>%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>",
        }],
        "layout": {
            "title": {"text": f"{title} · {country_name}", "x": 0, "font": {"size": 15}},
            "paper_bgcolor": "white", "plot_bgcolor": "white",
            "font": {"family": "Inter, sans-serif", "color": "#17201c"},
            "xaxis": {"title": app_tr("comparable_price_eur", lang), "gridcolor": "#e7ece9", "rangemode": "tozero"},
            "yaxis": {"autorange": "reversed", "automargin": True},
            "margin": {"l": 170, "r": 25, "t": 55, "b": 55},
            "height": max(350, 82 + len(rows) * 48),
            "shapes": [{
                "type": "line", "x0": summary["median"], "x1": summary["median"],
                "y0": -0.5, "y1": len(rows) - 0.5,
                "line": {"color": "#d97706", "width": 2, "dash": "dot"},
            }],
            "annotations": [{
                "x": summary["median"], "y": 1.04, "xref": "x", "yref": "paper",
                "text": app_tr("median_observed", lang), "showarrow": False,
                "font": {"size": 11, "color": "#a15c05"},
            }],
        },
    }
    return figure


def _eu_chart(market_rows: list[dict], lang: str) -> dict:
    return {
        "data": [{
            "type": "scatter", "mode": "markers",
            "x": [row["market"] for row in market_rows],
            "y": [row["median"] for row in market_rows],
            "marker": {"color": "#147d64", "size": 11},
            "error_y": {
                "type": "data", "symmetric": False, "visible": True,
                "array": [row["highest"] - row["median"] for row in market_rows],
                "arrayminus": [row["median"] - row["lowest"] for row in market_rows],
                "color": "#7cae9e", "thickness": 6, "width": 6,
            },
            "customdata": [[row["offer_count"], row["source_count"], row["spread_pct"] or 0] for row in market_rows],
            "hovertemplate": "%{x}<br>Median €%{y:.2f}<br>%{customdata[0]} offers · %{customdata[1]} sources<br>Range %{customdata[2]:.1f}%<extra></extra>",
        }],
        "layout": {
            "title": {"text": app_tr("eu_price_ranges", lang), "x": 0, "font": {"size": 15}},
            "paper_bgcolor": "white", "plot_bgcolor": "white",
            "font": {"family": "Inter, sans-serif", "color": "#17201c"},
            "xaxis": {"title": app_tr("country", lang), "gridcolor": "#e7ece9"},
            "yaxis": {"title": app_tr("comparable_price_eur", lang), "gridcolor": "#e7ece9", "rangemode": "tozero"},
            "margin": {"l": 65, "r": 25, "t": 55, "b": 50}, "height": 390,
        },
    }


def _source_card(offer: dict, lang: str):
    warnings = offer.get("warnings") or []
    translations = {
        "delivery not confirmed": app_tr("delivery_unknown", lang),
        "VAT status unknown": app_tr("vat_unknown", lang),
    }
    warning_line = " · ".join(translations.get(str(warning), str(warning)) for warning in warnings)
    original = f"{_number(offer['amount_original'], lang)} {offer['currency_original']}"
    return Div(
        Div(
            Div(P(offer["supplier"], cls="source-card-supplier"),
                P(offer["title"], cls="source-card-title")),
            Div(P(_price(offer["amount_comparable"], offer.get("unit_comparable"), lang), cls="source-card-price"),
                P(f"{app_tr('original_price', lang)}: {original}", cls="source-card-original")),
            cls="source-card-head",
        ),
        Div(
            Span(offer["market"], cls="source-pill"),
            Span(offer["source_domain"], cls="source-pill"),
            Span(f"{round(offer['confidence'] * 100)}% {app_tr('confidence', lang)}", cls="source-pill"),
            Span(f"{app_tr('captured', lang)} {_date(offer.get('captured_at'), lang)}", cls="source-card-meta"),
            cls="source-card-meta-row",
        ),
        P(warning_line, cls="source-card-warning") if warning_line else None,
        A(app_tr("open_source", lang), " →", href=_safe_source_url(offer.get("source_url")),
          target="_blank", rel="noopener noreferrer", cls="source-card-link"),
        cls="variance-source-card",
    )


def _country_content(item: dict, market: str, offers: list[dict], lang: str):
    market_offers = [offer for offer in offers if offer["market"] == market]
    summary = summarize_offers(market_offers)
    country_name = app_market_name(market, MARKETS[market]["name"], lang)
    scripts = []
    if market_offers:
        figure = _supplier_chart(market_offers, country_name, summary, lang)
        scripts.append(
            f"Plotly.newPlot('country-supplier-chart', {json.dumps(figure['data'])}, "
            f"{json.dumps(figure['layout'])}, {{responsive:true,displayModeBar:false}});"
        )
    spread = _percentage(summary["spread_pct"], lang)
    stats = Div(
        _stat_card(app_tr("suppliers_sources", lang), str(summary["source_count"]),
                   f"{summary['offer_count']} {app_tr('latest_offers', lang)}"),
        _stat_card(app_tr("lowest_observed", lang), _price(summary["lowest"], summary["unit"], lang)),
        _stat_card(app_tr("median_observed", lang), _price(summary["median"], summary["unit"], lang)),
        _stat_card(app_tr("observed_spread", lang), spread,
                   f"{app_tr('range', lang)} {_price(summary['range'], summary['unit'], lang)}" if summary["range"] is not None else ""),
        cls="variance-stats",
    )
    if not market_offers:
        dashboard = Div(P(app_tr("no_prices_country", lang), cls="variance-empty-title"),
                        P(app_tr("no_prices_country_detail", lang), cls="variance-empty-copy"), cls="variance-empty")
    else:
        coverage_note = app_tr("single_source_warning", lang) if summary["source_count"] < 2 else app_tr("multiple_source_note", lang)
        dashboard = Div(
            Div(id="country-supplier-chart", cls="variance-chart"),
            Div(coverage_note, cls="variance-coverage-note"),
            H3(app_tr("supplier_source_evidence", lang), cls="variance-section-title"),
            P(app_tr("latest_snapshot_note", lang), cls="variance-section-copy"),
            Div(*[_source_card(offer, lang) for offer in market_offers], cls="variance-source-list"),
        )
    heading = Div(
        Span(app_tr("primary_review", lang), cls="review-badge primary"),
        H2(f"{app_catalog_item_name(item['name'], lang)} · {country_name}", cls="variance-heading"),
        P(app_tr("country_review_intro", lang), cls="variance-lead"),
    )
    return Div(heading, stats, dashboard), scripts


def _eu_content(item: dict, offers: list[dict], lang: str):
    rows = summarize_markets(offers)
    overall = summarize_offers(offers)
    scripts = []
    if rows:
        figure = _eu_chart(rows, lang)
        scripts.append(
            f"Plotly.newPlot('eu-variance-chart', {json.dumps(figure['data'])}, "
            f"{json.dumps(figure['layout'])}, {{responsive:true,displayModeBar:false}});"
        )
    stats = Div(
        _stat_card(app_tr("markets_covered", lang), str(len(rows))),
        _stat_card(app_tr("suppliers_sources", lang), str(overall["source_count"]),
                   f"{overall['offer_count']} {app_tr('latest_offers', lang)}"),
        _stat_card(app_tr("lowest_observed", lang), _price(overall["lowest"], overall["unit"], lang)),
        _stat_card(app_tr("observed_spread", lang), _percentage(overall["spread_pct"], lang)),
        cls="variance-stats",
    )
    market_cards = [Div(
        Div(Span(row["market"], cls="source-pill"),
            Span(app_market_name(row["market"], MARKETS[row["market"]]["name"], lang), cls="eu-country-name"),
            Span(_source_count(row["source_count"], lang), cls="eu-source-count"), cls="eu-market-head"),
        Div(
            Div(P(app_tr("lowest_observed", lang), cls="eu-metric-label"), P(_price(row["lowest"], row["unit"], lang), cls="eu-metric-value")),
            Div(P(app_tr("median_observed", lang), cls="eu-metric-label"), P(_price(row["median"], row["unit"], lang), cls="eu-metric-value")),
            Div(P(app_tr("highest_observed", lang), cls="eu-metric-label"), P(_price(row["highest"], row["unit"], lang), cls="eu-metric-value")),
            cls="eu-market-metrics"),
        cls="eu-market-card",
    ) for row in rows]
    heading = Div(
        Span(app_tr("secondary_review", lang), cls="review-badge secondary"),
        H2(f"{app_catalog_item_name(item['name'], lang)} · {app_tr('across_eu', lang)}", cls="variance-heading"),
        P(app_tr("eu_review_intro", lang), cls="variance-lead"),
    )
    dashboard = (
        Div(Div(id="eu-variance-chart", cls="variance-chart"),
            H3(app_tr("country_ranges", lang), cls="variance-section-title"),
            Div(*market_cards, cls="eu-market-list"),
            H3(app_tr("supplier_source_evidence", lang), cls="variance-section-title"),
            Div(*[_source_card(offer, lang) for offer in offers], cls="variance-source-list"))
        if offers else Div(P(app_tr("no_item_observations", lang), cls="variance-empty-title"), cls="variance-empty")
    )
    return Div(heading, stats, dashboard), scripts


def register_market_overview_routes(rt):
    @rt("/app/market-overview")
    def market_overview(request, sess):
        from chat.routes import _ensure_user, _get_db, _list_sessions
        from utils.i18n import get_lang

        uid, email = _ensure_user(sess)
        if not uid or not email:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        db = _get_db()
        try:
            items = list_observed_items(db)
            requested_item = request.query_params.get("item")
            try:
                item_id = int(requested_item) if requested_item else None
            except (TypeError, ValueError):
                item_id = None
            item_ids = {row["id"] for row in items}
            if item_id not in item_ids:
                item_id = items[0]["id"] if items else None
            item = get_catalog_item(db, item_id) if item_id is not None else None
            offers = latest_item_offers(db, item_id) if item_id is not None else []
        finally:
            db.close()

        requested_market = (request.query_params.get("market") or "").upper()
        market = requested_market if requested_market in MARKETS else choose_default_market(offers)
        view = "eu" if request.query_params.get("view") == "eu" else "country"

        if not item:
            main_content = Div(P(app_tr("no_catalog_items", lang), cls="variance-empty-title"), cls="variance-empty")
            scripts = []
        else:
            market_counts = {row["market"]: row for row in summarize_markets(offers)}
            controls = Form(
                Div(Label(app_tr("item_label", lang), for_="item", cls="variance-control-label"),
                    Select(*[
                        Option(f"{app_catalog_item_name(row['name'], lang)} · {_source_count(row['source_count'], lang)}",
                               value=str(row["id"]), selected=row["id"] == item_id)
                        for row in items
                    ], id="item", name="item", cls="variance-select", onchange="this.form.submit()"),
                    cls="variance-control"),
                Div(Label(app_tr("country_label", lang), for_="market", cls="variance-control-label"),
                    Select(*[
                        Option(f"{code} · {app_market_name(code, info['name'], lang)}"
                               f" ({_source_count(market_counts.get(code, {}).get('source_count', 0), lang)})",
                               value=code, selected=code == market)
                        for code, info in MARKETS.items()
                    ], id="market", name="market", cls="variance-select", onchange="this.form.submit()"),
                    cls="variance-control"),
                Input(type="hidden", name="view", value=view),
                Button(app_tr("update_view", lang), type="submit", cls="variance-update-btn"),
                method="get", action="/app/market-overview", cls="variance-controls",
            )
            country_url = "/app/market-overview?" + urlencode({"item": item_id, "market": market, "view": "country"})
            eu_url = "/app/market-overview?" + urlencode({"item": item_id, "market": market, "view": "eu"})
            tabs = Div(
                A(app_tr("within_country", lang), href=country_url,
                  cls=f"variance-tab{' active' if view == 'country' else ''}"),
                A(app_tr("across_eu", lang), href=eu_url,
                  cls=f"variance-tab{' active' if view == 'eu' else ''}"),
                cls="variance-tabs",
            )
            content, scripts = _eu_content(item, offers, lang) if view == "eu" else _country_content(item, market, offers, lang)
            main_content = Div(controls, tabs, content)

        body = Body(
            signin_overlay(lang), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
            left_pane(user_email=email, sessions=_list_sessions(uid), current_sid="", lang=lang),
            Div(
                Div(Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                        Span(app_tr("market_overview", lang), cls="chat-header-title"), cls="chat-header-left"),
                    Div(A(app_tr("back_to_chat", lang), href="/app", cls="header-action-btn"), cls="chat-header-actions"), cls="chat-header"),
                Div(H2(app_tr("supplier_price_variance", lang), cls="text-xl font-semibold"),
                    P(app_tr("market_item_intro", lang), cls="text-sm text-gray-500 mb-5"),
                    main_content, cls="messages variance-dashboard"),
                cls="center-pane"),
            Script(NotStr("\n".join(scripts))), Script(src="/static/chat.js?v=4"),
            cls="bg-white text-ink font-sans antialiased app pane-closed")
        return Html(_head(app_tr("market_overview", lang)), body)
