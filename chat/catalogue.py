"""Searchable procurement catalogue with concrete product samples."""

from __future__ import annotations

from urllib.parse import urlencode

from fasthtml.common import A, Button, Div, Form, H2, H3, Input, Option, P, Select, Span
from sqlalchemy import text
from starlette.responses import RedirectResponse

from db import SCHEMA
from utils.fastcpi_i18n import app_catalog_item_name, app_sector_name, app_tr


def _line_card(row, lang: str):
    return Div(
        Div(
            Span(row.cpv_code or "—", cls="catalogue-cpv"),
            Span(app_sector_name(row.sector, row.sector_name or row.sector, lang), cls="catalogue-sector"),
            cls="catalogue-card-meta",
        ),
        H3(app_catalog_item_name(row.name, lang, row.display_name_fr), cls="catalogue-card-title"),
        P((row.description_fr or row.description) if lang == "fr" else (row.description or ""),
          cls="catalogue-card-description"),
        Div(
            Span(f"{row.sample_count} {app_tr('sample_items', lang)}", cls="catalogue-count"),
            Span(app_tr("monitored_cohort", lang), cls="catalogue-cohort") if row.cohort_count else None,
            cls="catalogue-card-footer",
        ),
        A(app_tr("view_samples", lang), href="/app/catalogue?" + urlencode({"line": row.id}),
          cls="catalogue-card-link"),
        cls="catalogue-line-card",
    )


def _sample_card(row, lang: str):
    identifier = f"{row.identifier_type.upper()} {row.identifier_value}" if row.identifier_value else ""
    return Div(
        Div(
            Span(row.brand or "", cls="catalogue-sector"),
            Span(app_tr("monitored_cohort", lang), cls="catalogue-cohort") if row.monitoring_cohort else None,
            cls="catalogue-card-meta",
        ),
        H3(app_catalog_item_name(row.name, lang, row.display_name_fr), cls="catalogue-card-title"),
        P(identifier, cls="catalogue-identifier"),
        Div(
            A(app_tr("view_market", lang), href="/app/market-overview?" + urlencode({
                "item": row.id, "market": row.default_market, "view": "country",
            }), cls="catalogue-card-link"),
            A(app_tr("manufacturer_source", lang), " →", href=row.source_url, target="_blank",
              rel="noopener noreferrer", cls="catalogue-card-link"),
            cls="catalogue-card-footer",
        ),
        cls="catalogue-sample-card",
    )


def register_catalogue_routes(rt):
    @rt("/app/catalogue", methods=["GET"])
    def catalogue_page(request, sess):
        from chat.routes import _ensure_user, _get_db, _list_sessions
        from chat.watchlists import _workspace_shell
        from utils.i18n import get_lang

        uid, email = _ensure_user(sess)
        if not uid or not email:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        query = (request.query_params.get("q") or "").strip()[:200]
        sector = (request.query_params.get("sector") or "").strip()[:80]
        try:
            line_id = int(request.query_params.get("line") or 0) or None
        except ValueError:
            line_id = None
        db = _get_db()
        try:
            sectors = db.execute(text(f"""
                SELECT DISTINCT attributes->>'sector' AS code, attributes->>'sector_name' AS name
                FROM {SCHEMA}.catalog_items
                WHERE catalogue_kind='line' AND attributes->>'sector' IS NOT NULL
                ORDER BY name
            """)).fetchall()
            lines = db.execute(text(f"""
                SELECT ci.id,ci.name,ci.description,ci.cpv_code,
                       ci.attributes->>'display_name_fr' AS display_name_fr,
                       ci.attributes->>'cpv_label_fr' AS description_fr,
                       ci.attributes->>'sector' AS sector,
                       ci.attributes->>'sector_name' AS sector_name,
                       COUNT(DISTINCT child.id) AS sample_count,
                       COUNT(DISTINCT child.id) FILTER (
                           WHERE child.attributes->>'monitoring_cohort'='true'
                       ) AS cohort_count
                FROM {SCHEMA}.catalog_items ci
                LEFT JOIN {SCHEMA}.catalog_items child
                  ON child.parent_item_id=ci.id AND child.catalogue_kind='sample_item'
                LEFT JOIN {SCHEMA}.item_identifiers ii ON ii.item_id=child.id
                WHERE ci.catalogue_kind='line'
                  AND (:sector='' OR ci.attributes->>'sector'=:sector)
                  AND (:q='' OR ci.name ILIKE :pattern OR ci.description ILIKE :pattern
                       OR ci.cpv_code ILIKE :pattern
                       OR ci.attributes->>'display_name_fr' ILIKE :pattern
                       OR child.name ILIKE :pattern OR child.attributes->>'display_name_fr' ILIKE :pattern
                       OR ii.identifier_value ILIKE :pattern)
                GROUP BY ci.id ORDER BY sample_count DESC,ci.name
            """), {"q": query, "pattern": f"%{query}%", "sector": sector}).fetchall()
            selected_line = next((row for row in lines if row.id == line_id), None) if line_id else None
            samples = []
            if selected_line:
                samples = db.execute(text(f"""
                    SELECT child.id,child.name,child.attributes->>'display_name_fr' AS display_name_fr,
                           child.attributes->>'brand' AS brand,child.attributes->>'source_url' AS source_url,
                           CAST(COALESCE(child.attributes->>'monitoring_cohort','false') AS boolean) AS monitoring_cohort,
                           child.attributes->>'default_market' AS default_market,
                           ii.identifier_type,ii.identifier_value
                    FROM {SCHEMA}.catalog_items child
                    LEFT JOIN {SCHEMA}.item_identifiers ii ON ii.item_id=child.id
                    WHERE child.parent_item_id=:line AND child.catalogue_kind='sample_item'
                    ORDER BY monitoring_cohort DESC,child.name
                """), {"line": line_id}).fetchall()
        finally:
            db.close()

        controls = Form(
            Input(name="q", value=query, placeholder=app_tr("catalogue_search", lang), cls="catalogue-search-input"),
            Select(
                Option(app_tr("all_sectors", lang), value="", selected=not sector),
                *[
                    Option(app_sector_name(row.code, row.name, lang), value=row.code, selected=row.code == sector)
                    for row in sectors
                ],
                name="sector", cls="catalogue-sector-select",
            ),
            Button(app_tr("update_view", lang), type="submit", cls="catalogue-search-button"),
            A(app_tr("clear_filters", lang), href="/app/catalogue", cls="catalogue-clear-link"),
            method="get", action="/app/catalogue", cls="catalogue-controls",
        )
        if selected_line:
            result_title = app_catalog_item_name(selected_line.name, lang, selected_line.display_name_fr)
            results = Div(*[_sample_card(row, lang) for row in samples], cls="catalogue-grid")
        else:
            result_title = app_tr("catalogue_lines", lang)
            results = (
                Div(*[_line_card(row, lang) for row in lines], cls="catalogue-grid")
                if lines else P(app_tr("no_catalogue_matches", lang), cls="catalogue-empty")
            )
        content = Div(
            H2(app_tr("catalogue_title", lang), cls="text-xl font-semibold mb-1"),
            P(app_tr("catalogue_intro", lang), cls="text-sm text-gray-500 mb-5"),
            controls,
            H3(result_title, cls="catalogue-results-title"),
            results,
            cls="messages catalogue-workspace",
        )
        return _workspace_shell(
            email, _list_sessions(uid), lang, app_tr("catalogue", lang), content,
            A(app_tr("back_to_chat", lang), href="/app", cls="header-action-btn"),
        )
