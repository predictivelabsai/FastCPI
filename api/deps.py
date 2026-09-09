"""Shared dependencies for FastAPI endpoints."""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import SCHEMA, SessionLocal
from api.auth import decode_token


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"user_id": payload["sub"], "email": payload["email"]}


def get_optional_user(authorization: str = Header(None)) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return decode_token(token)


def get_api_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Authenticate either a signed-in user JWT or a scoped FastCPI API key."""
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization[7:])
        if payload:
            return {"user_id": payload["sub"], "email": payload["email"], "scopes": ["*"]}
    if x_api_key and x_api_key.startswith("fcpi_"):
        digest = hashlib.sha256(x_api_key.encode()).hexdigest()
        db = SessionLocal()
        try:
            row = db.execute(text(f"""
                SELECT k.id, k.user_id, k.scopes, u.email
                FROM {SCHEMA}.api_keys k
                JOIN {SCHEMA}.chat_users u ON u.id = k.user_id
                WHERE k.key_hash = :digest AND k.revoked_at IS NULL
                  AND (k.expires_at IS NULL OR k.expires_at > NOW())
            """), {"digest": digest}).fetchone()
            if row:
                db.execute(text(f"UPDATE {SCHEMA}.api_keys SET last_used_at = NOW() WHERE id = :id"), {"id": row.id})
                db.commit()
                scopes = row.scopes if isinstance(row.scopes, list) else json.loads(row.scopes or "[]")
                return {"user_id": row.user_id, "email": row.email, "scopes": scopes, "api_key_id": row.id}
        finally:
            db.close()
    raise HTTPException(status_code=401, detail="A valid bearer token or X-API-Key is required")


def require_scope(principal: dict, scope: str) -> None:
    scopes = principal.get("scopes", [])
    if "*" not in scopes and scope not in scopes:
        raise HTTPException(status_code=403, detail=f"API key requires scope {scope}")
