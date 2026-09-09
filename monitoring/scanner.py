"""Daily watchlist scanner and alert evaluation."""

from __future__ import annotations

import json
import logging
import threading
import time
from html import escape

from sqlalchemy import text

from db import SCHEMA, SessionLocal
from pricing.repository import persist_search_result
from pricing.service import search_web_prices

log = logging.getLogger(__name__)


def _watchlist_alert_content(watch, events: list[tuple[str, dict]]) -> tuple[str, str, str]:
    """Create one source-backed notification for all events from a scan."""
    subject = f"FastCPI alert: {watch.name}"
    lines = [f"FastCPI found {len(events)} alert(s) for {watch.name}.", ""]
    cards = []
    for event_type, payload in events:
        label = "Target price reached" if event_type == "target_price" else "Price movement threshold reached"
        current = f"{payload['current']:.2f} {payload.get('currency', watch.target_currency)}"
        source_url = payload.get("source_url") or ""
        source_title = payload.get("source_title") or source_url or "Observed source"
        lines.extend([f"{label}: {current}", f"Source: {source_url}", ""])
        source_html = (
            f'<a href="{escape(source_url, quote=True)}">{escape(source_title)}</a>'
            if source_url else escape(source_title)
        )
        cards.append(
            f"<li><strong>{escape(label)}</strong>: {escape(current)}<br>Source: {source_html}</li>"
        )
    html_body = (
        f"<p>FastCPI found {len(events)} alert(s) for <strong>{escape(watch.name)}</strong>.</p>"
        f"<ul>{''.join(cards)}</ul>"
        '<p><a href="https://cpi.fastsme.com/app/daily-scan">Open your Daily Scan</a></p>'
        "<p><small>Observed public web prices are indicative market intelligence, not an official CPI.</small></p>"
    )
    return subject, html_body, "\n".join(lines).strip()


def scan_watchlist(watchlist_id: int) -> dict:
    db = SessionLocal()
    try:
        watch = db.execute(text(f"SELECT * FROM {SCHEMA}.watchlists WHERE id=:id AND is_active=TRUE"),
                           {"id": watchlist_id}).fetchone()
        if not watch:
            raise ValueError("Active watchlist not found")
        markets = watch.markets if isinstance(watch.markets, list) else json.loads(watch.markets or "[]")
        previous = db.execute(text(f"""
            WITH prior AS (
                SELECT MAX(po.captured_at) AS latest
                FROM {SCHEMA}.price_observations po
                JOIN {SCHEMA}.watchlist_observations wo ON wo.observation_id=po.id
                WHERE wo.watchlist_id=:watchlist AND po.currency_comparable=:currency
            )
            SELECT MIN(po.amount_comparable) AS minimum
            FROM {SCHEMA}.price_observations po
            JOIN {SCHEMA}.watchlist_observations wo ON wo.observation_id=po.id
            CROSS JOIN prior
            WHERE wo.watchlist_id=:watchlist AND po.currency_comparable=:currency
              AND po.captured_at >= prior.latest - INTERVAL '10 minutes'
        """), {"watchlist": watchlist_id, "currency": watch.target_currency}).scalar()
        observed = []
        for market in markets:
            result = search_web_prices(watch.query, market, limit=10, fetch_pages=True)
            result["watchlist_id"] = watchlist_id
            result = persist_search_result(db, result, user_id=watch.user_id)
            observed.extend(result.get("offers", []))
        comparable = [o["comparable_amount"] for o in observed
                      if o.get("comparable_amount") is not None
                      and o.get("comparable_currency") == watch.target_currency]
        current = min(comparable) if comparable else None
        events: list[tuple[str, dict]] = []
        best = min(
            (offer for offer in observed if offer.get("comparable_amount") is not None),
            key=lambda offer: offer["comparable_amount"],
            default={},
        )
        provenance = {
            "currency": watch.target_currency,
            "source_url": best.get("url"),
            "source_title": best.get("title") or best.get("seller"),
            "market": best.get("market"),
            "observation_id": best.get("observation_id"),
        }
        if current is not None and watch.target_price is not None and current <= float(watch.target_price):
            events.append(("target_price", {"current": current, "target": float(watch.target_price), **provenance}))
        if current is not None and previous is not None and watch.change_threshold_pct is not None:
            change = ((current - float(previous)) / float(previous)) * 100
            if abs(change) >= float(watch.change_threshold_pct):
                events.append(("price_change", {"current": current, "previous": float(previous), "change_pct": change, **provenance}))
        event_ids = []
        for event_type, payload in events:
            row = db.execute(text(f"""
                INSERT INTO {SCHEMA}.watchlist_events (watchlist_id, event_type, payload)
                VALUES (:id, :event_type, CAST(:payload AS jsonb))
                RETURNING id
            """), {"id": watchlist_id, "event_type": event_type, "payload": json.dumps(payload)}).fetchone()
            event_ids.append(row.id)
        db.execute(text(f"""
            UPDATE {SCHEMA}.watchlists
            SET last_run_at=NOW(), next_run_at=NOW()+INTERVAL '1 day', updated_at=NOW()
            WHERE id=:id
        """), {"id": watchlist_id})
        db.commit()
        notification = "not-requested"
        if events and watch.notify_email:
            user_email = db.execute(text(f"""
                SELECT email FROM {SCHEMA}.chat_users WHERE id=:id
            """), {"id": watch.user_id}).scalar()
            if user_email:
                from utils.email import send_email
                subject, html_body, text_body = _watchlist_alert_content(watch, events)
                email_result = send_email(
                    to=user_email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                    tag="watchlist-alert",
                )
                if email_result.get("ErrorCode") == 0:
                    db.execute(text(f"""
                        UPDATE {SCHEMA}.watchlist_events SET notified_at=NOW()
                        WHERE id = ANY(:ids)
                    """), {"ids": event_ids})
                    db.commit()
                    notification = "sent"
                else:
                    notification = "failed"
            else:
                notification = "missing-recipient"
        return {
            "watchlist_id": watchlist_id,
            "markets": markets,
            "observed_offers": len(observed),
            "events": len(events),
            "notification": notification,
        }
    finally:
        db.close()


def scan_due_watchlists(limit: int = 25) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT id FROM {SCHEMA}.watchlists
            WHERE is_active=TRUE AND (next_run_at IS NULL OR next_run_at <= NOW())
            ORDER BY next_run_at NULLS FIRST LIMIT :limit
        """), {"limit": limit}).fetchall()
    finally:
        db.close()
    results = []
    for row in rows:
        try:
            results.append(scan_watchlist(row.id))
        except Exception as exc:
            log.exception("watchlist %s scan failed", row.id)
            results.append({"watchlist_id": row.id, "error": type(exc).__name__})
    if results:
        try:
            from scripts.compute_price_indices import compute_indices
            compute_indices()
        except Exception:
            log.exception("price index computation failed")
    return results


def start_scheduler(interval_seconds: int = 3600) -> None:
    def loop():
        while True:
            try:
                scan_due_watchlists()
            except Exception:
                log.exception("watchlist scheduler iteration failed")
            time.sleep(max(300, interval_seconds))
    threading.Thread(target=loop, name="fastcpi-watchlists", daemon=True).start()
