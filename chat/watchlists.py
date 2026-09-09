"""Full watchlist workspace: create, edit, pause, run, delete and inspect evidence."""

from __future__ import annotations

import json
from datetime import datetime

from fasthtml.common import (
    A, Body, Button, Div, Form, H2, H3, Html, Input, Label, Option, P,
    Script, Select, Span,
)
from sqlalchemy import text
from starlette.responses import JSONResponse, RedirectResponse

from chat.components import left_pane, signin_overlay
from chat.layout import _head
from db import SCHEMA
from pricing.identifiers import classify_query
from pricing.markets import MARKETS
from utils.fastcpi_i18n import (
    app_catalog_item_name, app_market_name, app_tr, app_watch_name,
)
from utils.session import get_user_id


def _markets(value) -> list[str]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _time(value, lang: str) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value.strftime("%d/%m/%Y %H:%M") if lang == "fr" else value.strftime("%d %b %Y %H:%M")


def _item_options(items: list, selected, lang: str):
    return [
        Option(app_tr("no_catalog_link", lang), value="", selected=selected is None),
        *[
            Option(app_catalog_item_name(row.name, lang), value=str(row.id), selected=row.id == selected)
            for row in items
        ],
    ]


def _market_options(selected: list[str], lang: str):
    return [
        Option(f"{code} · {app_market_name(code, info['name'], lang)}", value=code, selected=code in selected)
        for code, info in MARKETS.items()
    ]


def _watch_card(row, items: list, lang: str):
    markets = _markets(row.markets)
    active_label = app_tr("active", lang) if row.is_active else app_tr("paused", lang)
    toggle_action = "pause" if row.is_active else "resume"
    toggle_label = app_tr("pause_watch", lang) if row.is_active else app_tr("resume_watch", lang)
    return Div(
        Div(
            Div(Span(app_watch_name(row.name, lang), cls="watch-card-title"),
                Span(active_label, cls=f"watch-status {'active' if row.is_active else 'paused'}")),
            P(row.query, cls="watch-card-query"),
            Div(
                Span(f"{app_tr('markets', lang)}: {', '.join(markets)}"),
                Span(f"{app_tr('last_run', lang)}: {_time(row.last_run_at, lang)}"),
                Span(f"{app_tr('next_run', lang)}: {_time(row.next_run_at, lang)}"),
                cls="watch-card-meta",
            ),
            cls="watch-card-summary",
        ),
        Div(
            A(app_tr("view_details", lang), href=f"/app/watchlists/{row.id}", cls="watch-action primary"),
            Button(app_tr("run_now", lang), onclick=f"watchAction({row.id},'run')",
                   disabled=not row.is_active, cls="watch-action"),
            Button(toggle_label, onclick=f"watchAction({row.id},'{toggle_action}')", cls="watch-action"),
            Button(app_tr("edit_watch", lang), onclick=f"toggleWatchEdit({row.id})", cls="watch-action"),
            Button(app_tr("delete_watch", lang), onclick=f"watchAction({row.id},'delete')", cls="watch-action danger"),
            cls="watch-card-actions",
        ),
        Form(
            Div(
                Label(app_tr("watch_name", lang), cls="watch-edit-label"),
                Input(name="name", value=row.name, required=True, cls="watch-edit-input"),
                cls="watch-edit-field",
            ),
            Div(
                Label(app_tr("watch_query", lang), cls="watch-edit-label"),
                Input(name="query", value=row.query, required=True, cls="watch-edit-input"),
                cls="watch-edit-field wide",
            ),
            Div(
                Label(app_tr("catalog_item", lang), cls="watch-edit-label"),
                Select(*_item_options(items, row.item_id, lang), name="item_id", cls="watch-edit-input"),
                cls="watch-edit-field",
            ),
            Div(
                Label(app_tr("selected_markets", lang), cls="watch-edit-label"),
                Select(*_market_options(markets, lang), name="markets", multiple=True, size="4", cls="watch-edit-input multi"),
                cls="watch-edit-field",
            ),
            Div(
                Label(app_tr("target_price", lang), cls="watch-edit-label"),
                Input(name="target_price", type="number", step="0.01", min="0.01",
                      value=str(row.target_price or ""), cls="watch-edit-input"),
                cls="watch-edit-field",
            ),
            Div(
                Label(app_tr("change_threshold", lang), cls="watch-edit-label"),
                Input(name="change_threshold_pct", type="number", step="0.1", min="0.1",
                      value=str(row.change_threshold_pct or ""), cls="watch-edit-input"),
                cls="watch-edit-field",
            ),
            Label(Input(type="checkbox", name="notify_email", checked=bool(row.notify_email)),
                  " ", app_tr("email_alerts", lang), cls="watch-email-toggle"),
            Div(
                Button(app_tr("save_changes", lang), type="button",
                       onclick=f"watchAction({row.id},'save',this.form)", cls="watch-action primary"),
                Button(app_tr("cancel", lang), type="button", onclick=f"toggleWatchEdit({row.id})", cls="watch-action"),
                cls="watch-edit-actions",
            ),
            id=f"watch-edit-{row.id}", cls="watch-edit-form", style="display:none",
        ),
        cls="watch-card",
    )


def _workspace_shell(email: str, sessions: list, lang: str, title: str, content, header_action=None, scripts=()):
    return Html(_head(title), Body(
        signin_overlay(lang), Div(id="left-overlay", cls="left-overlay", onclick="toggleLeftPane()"),
        left_pane(user_email=email, sessions=sessions, current_sid="", lang=lang),
        Div(
            Div(
                Div(Button("=", cls="mobile-menu-btn", onclick="toggleLeftPane()"),
                    Span(title, cls="chat-header-title"), cls="chat-header-left"),
                Div(header_action, cls="chat-header-actions") if header_action else None,
                cls="chat-header",
            ),
            content,
            cls="center-pane",
        ),
        *[Script(script) for script in scripts],
        Script(src="/static/chat.js?v=4"),
        cls="bg-white text-ink font-sans antialiased app pane-closed",
    ))


def _action_script(lang: str) -> str:
    labels = json.dumps({key: app_tr(key, lang) for key in (
        "confirm_delete_watch", "watch_action_failed", "watch_queued",
    )})
    return f"""
    const WATCH_LABELS={labels};
    function toggleWatchEdit(id){{const el=document.getElementById('watch-edit-'+id);if(el)el.style.display=el.style.display==='none'?'grid':'none';}}
    async function watchAction(id,action,form){{
      if(action==='delete'&&!confirm(WATCH_LABELS.confirm_delete_watch))return;
      const body=form?new FormData(form):new FormData();body.set('action',action);
      const response=await fetch(`/app/watchlists/${{id}}/action`,{{method:'POST',body}});
      const data=await response.json();
      if(!response.ok){{alert(data.error||WATCH_LABELS.watch_action_failed);return;}}
      if(action==='run'&&data.scan_run_id)location.href=`/app/watchlists/${{id}}?queued=${{data.scan_run_id}}`;
      else location.reload();
    }}
    """


def register_watchlist_routes(rt):
    @rt("/app/watchlists")
    def watchlists_page(sess):
        from chat.routes import _ensure_user, _get_db, _list_sessions
        from utils.i18n import get_lang
        uid, email = _ensure_user(sess)
        if not uid:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        db = _get_db()
        try:
            rows = db.execute(text(f"""
                SELECT * FROM {SCHEMA}.watchlists WHERE user_id=:uid ORDER BY updated_at DESC
            """), {"uid": uid}).fetchall()
            items = db.execute(text(f"""
                SELECT id,name FROM {SCHEMA}.catalog_items ORDER BY name
            """)).fetchall()
        finally:
            db.close()
        cards = [_watch_card(row, items, lang) for row in rows]
        create_form = Form(
            Input(name="name", placeholder=app_tr("watch_name", lang), required=True, cls="watch-create-input"),
            Input(name="query", placeholder=app_tr("watch_query", lang), required=True, cls="watch-create-input wide"),
            Select(*_item_options(items, None, lang), name="item_id", cls="watch-create-input"),
            Select(*_market_options(["FR"], lang), name="markets", multiple=True, size="4", cls="watch-create-input multi"),
            Input(name="target_price", type="number", step="0.01", min="0.01",
                  placeholder=app_tr("target_price", lang), cls="watch-create-input"),
            Input(name="change_threshold_pct", type="number", step="0.1", min="0.1",
                  placeholder=app_tr("change_threshold", lang), cls="watch-create-input"),
            Label(Input(type="checkbox", name="notify_email", checked=True), " ", app_tr("email_alerts", lang), cls="watch-email-toggle"),
            Button(app_tr("create_watch", lang), type="submit", cls="watch-create-button"),
            id="watch-form", cls="watch-create-form",
        )
        content = Div(
            H2(app_tr("daily_monitoring", lang), cls="text-xl font-semibold mb-1"),
            P(app_tr("watch_intro", lang), cls="text-sm text-gray-500 mb-5"),
            create_form,
            Div(*cards, cls="watch-card-list") if cards else P(app_tr("no_watches", lang), cls="text-sm text-gray-400"),
            cls="messages watch-workspace",
        )
        create_script = f"""
        document.getElementById('watch-form').addEventListener('submit',async function(event){{
          event.preventDefault();const response=await fetch('/app/watchlist-create',{{method:'POST',body:new FormData(this)}});const data=await response.json();
          if(data.ok)location.reload();else alert(data.error||{json.dumps(app_tr('unable_watch', lang))});
        }});
        """
        return _workspace_shell(
            email, _list_sessions(uid), lang, app_tr("watchlists", lang), content,
            A(app_tr("back_to_chat", lang), href="/app", cls="header-action-btn"),
            scripts=(_action_script(lang), create_script),
        )

    @rt("/app/watchlists/{watchlist_id}")
    def watchlist_detail(watchlist_id: int, sess):
        from chat.routes import _ensure_user, _get_db, _list_sessions
        from utils.i18n import get_lang
        uid, email = _ensure_user(sess)
        if not uid:
            return RedirectResponse("/", status_code=303)
        lang = get_lang(sess)
        db = _get_db()
        try:
            watch = db.execute(text(f"""
                SELECT w.*,ci.name AS item_name FROM {SCHEMA}.watchlists w
                LEFT JOIN {SCHEMA}.catalog_items ci ON ci.id=w.item_id
                WHERE w.id=:id AND w.user_id=:uid
            """), {"id": watchlist_id, "uid": uid}).fetchone()
            if not watch:
                return RedirectResponse("/app/watchlists", status_code=303)
            runs = db.execute(text(f"""
                SELECT * FROM {SCHEMA}.scan_runs WHERE watchlist_id=:id AND user_id=:uid
                ORDER BY created_at DESC LIMIT 50
            """), {"id": watchlist_id, "uid": uid}).fetchall()
            observations = db.execute(text(f"""
                SELECT DISTINCT ON (o.id) po.*,o.title,o.source_url,o.market,o.seller_name,
                       ps.domain AS source_domain
                FROM {SCHEMA}.watchlist_observations wo
                JOIN {SCHEMA}.price_observations po ON po.id=wo.observation_id
                JOIN {SCHEMA}.offers o ON o.id=po.offer_id
                JOIN {SCHEMA}.price_sources ps ON ps.id=o.source_id
                WHERE wo.watchlist_id=:id
                ORDER BY o.id,po.captured_at DESC LIMIT 100
            """), {"id": watchlist_id}).fetchall()
        finally:
            db.close()

        run_cards = [Div(
            Div(Span(app_tr(run.status, lang), cls=f"scan-status {run.status}"),
                Span(_time(run.created_at, lang), cls="scan-run-time"), cls="scan-run-head"),
            P(f"{run.observed_count} {app_tr('observations', lang)} · {run.discovered_count} {app_tr('discoveries', lang)} · {app_tr('attempt', lang)} {run.attempt_count}/{run.max_attempts}", cls="scan-run-meta"),
            P(run.error_message, cls="scan-run-error") if run.error_message else None,
            cls="scan-run-card",
        ) for run in runs]
        def evidence_price(row):
            amount = row.amount_comparable if row.amount_comparable is not None else row.amount_original
            currency = row.currency_comparable or row.currency_original
            unit = row.unit_comparable or row.unit_original or "unit"
            return f"{float(amount):,.2f} {currency} / {unit}"

        evidence_cards = [Div(
            Div(Span(row.seller_name or row.source_domain, cls="watch-evidence-supplier"),
                Span(evidence_price(row), cls="watch-evidence-price"),
                cls="watch-evidence-head"),
            P(row.title, cls="watch-evidence-title"),
            P(f"{row.market} · {row.source_domain} · {_time(row.captured_at, lang)}", cls="watch-evidence-meta"),
            A(app_tr("open_source", lang), " →", href=row.source_url, target="_blank", rel="noopener noreferrer", cls="source-card-link"),
            cls="watch-evidence-card",
        ) for row in observations]
        status = app_tr("active", lang) if watch.is_active else app_tr("paused", lang)
        content = Div(
            Div(Span(status, cls=f"watch-status {'active' if watch.is_active else 'paused'}"),
                H2(app_watch_name(watch.name, lang), cls="watch-detail-title"),
                P(watch.query, cls="watch-card-query"),
                P(f"{app_tr('markets', lang)}: {', '.join(_markets(watch.markets))}", cls="watch-card-meta"),
                Button(app_tr("run_now", lang), onclick=f"watchAction({watch.id},'run')",
                       disabled=not watch.is_active, cls="watch-action primary"), cls="watch-detail-hero"),
            H3(app_tr("scan_history", lang), cls="watch-detail-section"),
            Div(*run_cards, cls="scan-run-list") if run_cards else P(app_tr("no_scan_runs", lang), cls="text-sm text-gray-400"),
            H3(app_tr("latest_source_evidence", lang), cls="watch-detail-section"),
            Div(*evidence_cards, cls="watch-evidence-list") if evidence_cards else P(app_tr("no_watch_evidence", lang), cls="text-sm text-gray-400"),
            cls="messages watch-workspace",
        )
        pending = bool(runs and runs[0].status in {"queued", "running", "retry"})
        refresh_script = "setTimeout(()=>location.reload(),5000);" if pending else ""
        return _workspace_shell(
            email, _list_sessions(uid), lang, app_tr("watch_details", lang), content,
            A(app_tr("back_watchlists", lang), href="/app/watchlists", cls="header-action-btn"),
            scripts=(_action_script(lang), refresh_script),
        )

    @rt("/app/watchlist-create", methods=["POST"])
    async def create_watchlist(request, sess):
        from chat.routes import _get_db
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Sign in required"}, status_code=401)
        form = await request.form()
        name, query = (form.get("name") or "").strip(), (form.get("query") or "").strip()
        markets = [value.upper() for value in form.getlist("markets") if value.upper() in MARKETS]
        if not name or not query or not markets:
            return JSONResponse({"error": "Name, query and at least one supported market are required"}, status_code=422)
        identity = classify_query(query)
        try:
            target = float(form.get("target_price")) if form.get("target_price") else None
            change = float(form.get("change_threshold_pct")) if form.get("change_threshold_pct") else None
            item_id = int(form.get("item_id")) if form.get("item_id") else None
        except (TypeError, ValueError):
            return JSONResponse({"error": "Price, threshold or catalogue item is invalid"}, status_code=422)
        db = _get_db()
        try:
            if item_id and not db.execute(text(f"SELECT 1 FROM {SCHEMA}.catalog_items WHERE id=:id"), {"id": item_id}).fetchone():
                return JSONResponse({"error": "Catalogue item not found"}, status_code=422)
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.watchlists
                    (user_id,item_id,name,query,query_type,query_value,markets,cpv_code,
                     target_price,change_threshold_pct,notify_email,next_run_at)
                VALUES (:uid,:item_id,:name,:query,:kind,:value,CAST(:markets AS jsonb),:cpv,
                        :target,:change,:notify,NOW())
            """), {"uid": uid, "item_id": item_id, "name": name, "query": query,
                     "kind": identity.kind, "value": identity.value, "markets": json.dumps(markets),
                     "cpv": identity.value if identity.kind == "cpv" else None, "target": target,
                     "change": change, "notify": "notify_email" in form})
            db.commit()
        finally:
            db.close()
        return JSONResponse({"ok": True})

    @rt("/app/watchlists/{watchlist_id}/action", methods=["POST"])
    async def watchlist_action(watchlist_id: int, request, sess):
        from chat.routes import _get_db
        uid = get_user_id(sess)
        if not uid:
            return JSONResponse({"error": "Sign in required"}, status_code=401)
        form = await request.form()
        action = (form.get("action") or "").lower()
        db = _get_db()
        try:
            watch = db.execute(text(f"""
                SELECT * FROM {SCHEMA}.watchlists WHERE id=:id AND user_id=:uid
            """), {"id": watchlist_id, "uid": uid}).fetchone()
            if not watch:
                return JSONResponse({"error": "Watch not found"}, status_code=404)
            if action == "delete":
                db.execute(text(f"DELETE FROM {SCHEMA}.watchlists WHERE id=:id AND user_id=:uid"), {"id": watchlist_id, "uid": uid})
                db.commit()
                return JSONResponse({"ok": True})
            if action in {"pause", "resume"}:
                active = action == "resume"
                db.execute(text(f"""
                    UPDATE {SCHEMA}.watchlists SET is_active=:active,
                        next_run_at=CASE WHEN :active THEN NOW() ELSE next_run_at END,updated_at=NOW()
                    WHERE id=:id AND user_id=:uid
                """), {"active": active, "id": watchlist_id, "uid": uid})
                db.commit()
                return JSONResponse({"ok": True, "is_active": active})
            if action == "run":
                if not watch.is_active:
                    return JSONResponse({"error": "Paused watch cannot run"}, status_code=409)
                from monitoring.jobs import enqueue_watchlist_scan
                run = enqueue_watchlist_scan(db, watchlist_id, uid, trigger="manual")
                return JSONResponse({"ok": True, "scan_run_id": str(run["id"]), "status": run["status"]}, status_code=202)
            if action == "save":
                name, query = (form.get("name") or "").strip(), (form.get("query") or "").strip()
                markets = [value.upper() for value in form.getlist("markets") if value.upper() in MARKETS]
                if not name or not query or not markets:
                    return JSONResponse({"error": "Name, query and markets are required"}, status_code=422)
                identity = classify_query(query)
                try:
                    target = float(form.get("target_price")) if form.get("target_price") else None
                    change = float(form.get("change_threshold_pct")) if form.get("change_threshold_pct") else None
                    item_id = int(form.get("item_id")) if form.get("item_id") else None
                except (TypeError, ValueError):
                    return JSONResponse({"error": "Invalid numeric or catalogue value"}, status_code=422)
                if item_id and not db.execute(text(f"SELECT 1 FROM {SCHEMA}.catalog_items WHERE id=:id"), {"id": item_id}).fetchone():
                    return JSONResponse({"error": "Catalogue item not found"}, status_code=422)
                db.execute(text(f"""
                    UPDATE {SCHEMA}.watchlists SET item_id=:item_id,name=:name,query=:query,
                        query_type=:kind,query_value=:value,cpv_code=:cpv,markets=CAST(:markets AS jsonb),
                        target_price=:target,change_threshold_pct=:change,notify_email=:notify,
                        next_run_at=NOW(),updated_at=NOW()
                    WHERE id=:id AND user_id=:uid
                """), {"item_id": item_id, "name": name, "query": query, "kind": identity.kind,
                         "value": identity.value, "cpv": identity.value if identity.kind == "cpv" else None,
                         "markets": json.dumps(markets), "target": target, "change": change,
                         "notify": "notify_email" in form, "id": watchlist_id, "uid": uid})
                db.commit()
                return JSONResponse({"ok": True})
            return JSONResponse({"error": "Unsupported action"}, status_code=422)
        finally:
            db.close()
