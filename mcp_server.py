"""Authenticated, read-only MCP surface for FastCPI market intelligence."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlalchemy import text

from db import SCHEMA, SessionLocal


PUBLIC_ORIGIN = "https://cpi.fastsme.com"
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


class FastCPIApiKeyVerifier(TokenVerifier):
    """Accept FastCPI API keys as MCP bearer tokens during the OAuth transition."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token.startswith("fcpi_"):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        db = SessionLocal()
        try:
            row = db.execute(text(f"""
                SELECT k.id,k.user_id,k.key_prefix,k.scopes,k.expires_at
                FROM {SCHEMA}.api_keys k
                WHERE k.key_hash=:digest AND k.revoked_at IS NULL
                  AND (k.expires_at IS NULL OR k.expires_at > NOW())
            """), {"digest": digest}).fetchone()
            if not row:
                return None
            scopes = row.scopes if isinstance(row.scopes, list) else json.loads(row.scopes or "[]")
            db.execute(text(f"UPDATE {SCHEMA}.api_keys SET last_used_at=NOW() WHERE id=:id"), {"id": row.id})
            db.commit()
            return AccessToken(
                token=token,
                client_id=row.key_prefix,
                scopes=scopes,
                expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
                resource=f"{PUBLIC_ORIGIN}/mcp/",
                subject=str(row.user_id),
                claims={"user_id": row.user_id, "api_key_id": row.id},
            )
        finally:
            db.close()


def _user_id() -> int:
    token = get_access_token()
    if not token or not token.subject:
        raise PermissionError("An authenticated FastCPI API key is required")
    return int(token.subject)


mcp = MCPServer(
    name="fastcpi-market-intelligence",
    title="FastCPI Market Price Intelligence",
    description="Source-backed web market observations for goods and services in EU markets.",
    instructions=(
        "Use catalogue or CPV search to resolve an item, then price_variance for same-country "
        "supplier comparison. Treat EU comparison as secondary context. Every offer includes "
        "a public source_url. FastCPI is web market intelligence, not an official CPI."
    ),
    website_url=PUBLIC_ORIGIN,
    version="1.0.0-alpha",
    token_verifier=FastCPIApiKeyVerifier(),
    auth=AuthSettings(
        issuer_url=PUBLIC_ORIGIN,
        service_documentation_url=f"{PUBLIC_ORIGIN}/developers#mcp",
        required_scopes=["prices:read"],
        resource_server_url=f"{PUBLIC_ORIGIN}/mcp/",
        validate_token_resource=False,
    ),
)


@mcp.resource(
    "fastcpi://methodology",
    title="FastCPI observation methodology",
    description="Interpretation and coverage limits for FastCPI results.",
    mime_type="application/json",
)
def methodology() -> str:
    return json.dumps({
        "product": "FastCPI web market observation index and price intelligence",
        "not_official_cpi": True,
        "snapshot": "latest comparable observation per active public offer",
        "default_comparison": "supplier variance for one item within one country",
        "secondary_comparison": "cross-EU market context",
        "provenance": "offer results include the public source URL and capture time",
        "coverage": "observed public sources; not complete market coverage",
    })


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def search_catalog(query: str = "", limit: int = 20) -> dict[str, Any]:
    """Resolve goods/services from plain language, CPV, SKU, MPN, GTIN, EAN or UPC."""
    _user_id()
    q = query.strip()
    size = min(max(limit, 1), 100)
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT ci.id,ci.item_type,ci.name,ci.description,ci.cpv_code,ci.canonical_unit,
                   COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
                     'type',ii.identifier_type,'value',ii.identifier_value,'issuer',ii.issuer
                   )) FILTER (WHERE ii.id IS NOT NULL),'[]'::jsonb) AS identifiers
            FROM {SCHEMA}.catalog_items ci
            LEFT JOIN {SCHEMA}.item_identifiers ii ON ii.item_id=ci.id
            WHERE (:q='' OR ci.name ILIKE :pattern OR ci.description ILIKE :pattern
                   OR ci.cpv_code=:digits OR ii.identifier_value ILIKE :pattern)
            GROUP BY ci.id
            ORDER BY CASE WHEN ci.name ILIKE :starts THEN 0 ELSE 1 END,ci.updated_at DESC
            LIMIT :limit
        """), {
            "q": q, "pattern": f"%{q}%", "starts": f"{q}%",
            "digits": "".join(c for c in q if c.isdigit())[:8], "limit": size,
        }).fetchall()
        return {"query": q, "count": len(rows), "items": _json_ready([dict(r._mapping) for r in rows])}
    finally:
        db.close()


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def search_cpv(query: str, language: str = "en", limit: int = 50) -> dict[str, Any]:
    """Search CPV 2008 and return descendants when query is a CPV code."""
    _user_id()
    from pricing.cpv import concept_uri, search_cpv as lookup
    db = SessionLocal()
    try:
        rows = lookup(db, query, lang=language, limit=min(max(limit, 1), 200))
        return {
            "query": query, "version": "2008", "count": len(rows),
            "concept_uri": concept_uri(query) if query.replace("-", "").isdigit() else None,
            "concepts": _json_ready(rows),
        }
    finally:
        db.close()


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def price_variance(item_id: int, market: str = "FR") -> dict[str, Any]:
    """Compare latest supplier prices for one item within a country; include secondary EU context."""
    _user_id()
    from pricing.analytics import get_catalog_item, latest_item_offers, summarize_markets, summarize_offers
    from pricing.markets import normalize_market
    selected_market = normalize_market(market)
    db = SessionLocal()
    try:
        item = get_catalog_item(db, item_id)
        if not item:
            raise ValueError("Catalogue item not found")
        offers = latest_item_offers(db, item_id)
        country_offers = [offer for offer in offers if offer["market"] == selected_market]
        return _json_ready({
            "item": item,
            "market": selected_market,
            "country_summary": summarize_offers(country_offers),
            "country_offers": country_offers,
            "eu_summary": summarize_offers(offers),
            "eu_markets": summarize_markets(offers),
            "coverage_statement": "Observed public sources; not complete market coverage.",
        })
    finally:
        db.close()


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def market_overview(country: str) -> dict[str, Any]:
    """Return coverage counts and current item series for one EU country."""
    _user_id()
    from pricing.markets import MARKETS, normalize_market
    market = normalize_market(country)
    db = SessionLocal()
    try:
        stats = db.execute(text(f"""
            SELECT COUNT(DISTINCT o.id) AS offers,COUNT(po.id) AS observations,
                   COUNT(DISTINCT ps.domain) AS sources,MAX(po.captured_at) AS latest_observation,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY po.amount_comparable)
                     FILTER (WHERE po.currency_comparable='EUR') AS median_eur
            FROM {SCHEMA}.offers o
            JOIN {SCHEMA}.price_sources ps ON ps.id=o.source_id
            JOIN {SCHEMA}.price_observations po ON po.offer_id=o.id
            WHERE o.market=:market AND o.status='active'
        """), {"market": market}).fetchone()
        items = db.execute(text(f"""
            SELECT ci.id,ci.name,ci.item_type,ci.cpv_code,ci.canonical_unit,
                   COUNT(DISTINCT o.id) AS offers,COUNT(DISTINCT ps.domain) AS sources,
                   MIN(po.amount_comparable) FILTER (WHERE po.currency_comparable='EUR') AS lowest_eur,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY po.amount_comparable)
                     FILTER (WHERE po.currency_comparable='EUR') AS median_eur
            FROM {SCHEMA}.catalog_items ci
            JOIN {SCHEMA}.offers o ON o.item_id=ci.id AND o.market=:market AND o.status='active'
            JOIN {SCHEMA}.price_sources ps ON ps.id=o.source_id
            JOIN {SCHEMA}.price_observations po ON po.offer_id=o.id
            GROUP BY ci.id ORDER BY sources DESC,offers DESC,ci.name LIMIT 100
        """), {"market": market}).fetchall()
        return _json_ready({
            "market": market, **MARKETS[market], **dict(stats._mapping),
            "items": [dict(row._mapping) for row in items],
            "coverage_statement": "Observed public sources; not complete market coverage.",
        })
    finally:
        db.close()


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def list_watchlists(limit: int = 50) -> dict[str, Any]:
    """List watchlists belonging to the authenticated FastCPI API-key owner."""
    user_id = _user_id()
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT w.id,w.name,w.query,w.query_type,w.query_value,w.markets,w.cpv_code,
                   w.target_price,w.target_currency,w.change_threshold_pct,w.cadence,
                   w.notify_email,w.is_active,w.last_run_at,w.next_run_at,w.updated_at,
                   ci.id AS item_id,ci.name AS item_name
            FROM {SCHEMA}.watchlists w
            LEFT JOIN {SCHEMA}.catalog_items ci ON ci.id=w.item_id
            WHERE w.user_id=:uid ORDER BY w.updated_at DESC LIMIT :limit
        """), {"uid": user_id, "limit": min(max(limit, 1), 200)}).fetchall()
        return {"count": len(rows), "watchlists": _json_ready([dict(row._mapping) for row in rows])}
    finally:
        db.close()


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def scan_run_status(scan_run_id: str) -> dict[str, Any]:
    """Read one durable watchlist scan and per-country outcomes for this API-key owner."""
    user_id = _user_id()
    try:
        UUID(scan_run_id)
    except ValueError as exc:
        raise ValueError("scan_run_id must be a UUID") from exc
    db = SessionLocal()
    try:
        run = db.execute(text(f"""
            SELECT * FROM {SCHEMA}.scan_runs WHERE id=CAST(:id AS uuid) AND user_id=:uid
        """), {"id": scan_run_id, "uid": user_id}).fetchone()
        if not run:
            raise ValueError("Scan run not found")
        items = db.execute(text(f"""
            SELECT market,status,attempt_count,discovery_count,observation_count,
                   error_code,error_message,started_at,completed_at
            FROM {SCHEMA}.scan_run_items WHERE scan_run_id=CAST(:id AS uuid) ORDER BY market
        """), {"id": scan_run_id}).fetchall()
        return _json_ready({"run": dict(run._mapping), "countries": [dict(row._mapping) for row in items]})
    finally:
        db.close()


def build_mcp_app():
    """Build the Streamable HTTP transport mounted by the main ASGI application."""
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["cpi.fastsme.com", "localhost:*", "127.0.0.1:*", "testserver"],
        allowed_origins=[PUBLIC_ORIGIN, "http://localhost:*", "http://127.0.0.1:*"],
    )
    return mcp.streamable_http_app(
        streamable_http_path="/", json_response=True, stateless_http=True,
        transport_security=security,
    )
