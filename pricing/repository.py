"""Persistence helpers for observed offers and their source evidence."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from sqlalchemy import text

from db import SCHEMA


def persist_search_result(db, result: dict, *, user_id: int | None = None) -> dict:
    identity = result["identity"]
    run = db.execute(text(f"""
        INSERT INTO {SCHEMA}.price_search_runs
            (user_id, query, query_type, query_value, market, cpv_code,
             exa_result_count, extracted_offer_count, status, completed_at)
        VALUES (:uid, :query, :kind, :value, :market, :cpv,
                :discoveries, :offers, 'complete', NOW())
        RETURNING id
    """), {
        "uid": user_id,
        "query": result["query"],
        "kind": identity["kind"],
        "value": identity["value"],
        "market": result["market"],
        "cpv": identity["value"] if identity["kind"] == "cpv" else None,
        "discoveries": len(result.get("discoveries", [])),
        "offers": len(result.get("offers", [])),
    }).fetchone()

    persisted = []
    for offer in result.get("offers", []):
        domain = offer.get("source_domain") or urlparse(offer["url"]).netloc
        source = db.execute(text(f"""
            INSERT INTO {SCHEMA}.price_sources (domain, name, last_success_at)
            VALUES (:domain, :name, NOW())
            ON CONFLICT (domain) DO UPDATE SET last_success_at = NOW()
            RETURNING id
        """), {"domain": domain, "name": offer.get("seller") or domain}).fetchone()
        offer_row = db.execute(text(f"""
            INSERT INTO {SCHEMA}.offers
                (item_id, source_id, seller_name, title, source_url, market, availability, terms, last_seen_at)
            VALUES (:item_id, :source_id, :seller, :title, :url, :market, :availability, CAST(:terms AS jsonb), NOW())
            ON CONFLICT (source_url) DO UPDATE SET
                item_id = COALESCE(EXCLUDED.item_id, offers.item_id),
                seller_name = EXCLUDED.seller_name,
                title = EXCLUDED.title,
                market = EXCLUDED.market,
                availability = EXCLUDED.availability,
                terms = EXCLUDED.terms,
                last_seen_at = NOW(),
                status = 'active'
            RETURNING id
        """), {
            "item_id": result.get("item_id"), "source_id": source.id,
            "seller": offer.get("seller"),
            "title": offer.get("title") or result["query"],
            "url": offer["url"],
            "market": result["market"],
            "availability": offer.get("availability"),
            "terms": json.dumps({"sku": offer.get("sku"), "gtin": offer.get("gtin")}),
        }).fetchone()
        observation = db.execute(text(f"""
            INSERT INTO {SCHEMA}.price_observations
                (offer_id, amount_original, currency_original, amount_comparable,
                 currency_comparable, quantity, unit_original, unit_comparable,
                 vat_included, shipping_included, fx_rate, fx_rate_date,
                 confidence, warnings, captured_at,
                 extraction_method, evidence_excerpt, content_hash)
            VALUES (:offer_id, :amount, :currency, :comparable, :comparable_currency,
                    :quantity, :unit, :comparable_unit, :vat, :shipping,
                    :fx_rate, :fx_rate_date,
                    :confidence, CAST(:warnings AS jsonb), :captured_at,
                    :method, :evidence, :content_hash)
            RETURNING id
        """), {
            "offer_id": offer_row.id,
            "amount": offer["amount"],
            "currency": offer["currency"],
            "comparable": offer.get("comparable_amount"),
            "comparable_currency": offer.get("comparable_currency"),
            "quantity": offer.get("quantity", 1),
            "unit": offer.get("unit", "each"),
            "comparable_unit": offer.get("comparable_unit"),
            "vat": offer.get("vat_included"),
            "shipping": offer.get("shipping_included"),
            "confidence": offer.get("confidence", 0),
            "fx_rate": offer.get("fx_rate"),
            "fx_rate_date": offer.get("fx_rate_date"),
            "warnings": json.dumps(offer.get("warnings", [])),
            "captured_at": offer["captured_at"],
            "method": offer.get("extraction_method"),
            "evidence": offer.get("evidence", "")[:8000],
            "content_hash": offer.get("content_hash"),
        }).fetchone()
        if result.get("watchlist_id"):
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.watchlist_observations (watchlist_id,observation_id)
                VALUES (:watchlist,:observation) ON CONFLICT DO NOTHING
            """), {"watchlist": result["watchlist_id"], "observation": observation.id})
        offer["observation_id"] = observation.id
        persisted.append(observation.id)
    db.commit()
    result["search_run_id"] = str(run.id)
    result["persisted_observation_ids"] = persisted
    return result


def latest_observations(db, *, query: str = "", market: str | None = None, limit: int = 50) -> list[dict]:
    clauses = ["o.status = 'active'"]
    params: dict = {"limit": min(max(limit, 1), 200)}
    if query:
        clauses.append("(o.title ILIKE :query OR o.seller_name ILIKE :query)")
        params["query"] = f"%{query}%"
    if market:
        clauses.append("o.market = :market")
        params["market"] = market
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (o.id)
            po.id AS observation_id, o.id AS offer_id, o.title, o.seller_name,
            o.source_url, o.market, ps.domain AS source_domain,
            po.amount_original, po.currency_original, po.amount_comparable,
            po.currency_comparable, po.unit_original, po.unit_comparable,
            po.vat_included, po.shipping_included, po.confidence, po.warnings,
            po.captured_at, po.extraction_method, po.evidence_excerpt
        FROM {SCHEMA}.offers o
        JOIN {SCHEMA}.price_sources ps ON ps.id = o.source_id
        JOIN {SCHEMA}.price_observations po ON po.offer_id = o.id
        WHERE {' AND '.join(clauses)}
        ORDER BY o.id, po.captured_at DESC
        LIMIT :limit
    """), params).fetchall()
    return [dict(r._mapping) for r in rows]
