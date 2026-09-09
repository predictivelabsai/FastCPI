"""Invite-only access checks shared by browser and API authentication."""

from __future__ import annotations

import os

from sqlalchemy import text

from db import SCHEMA


def invite_only_enabled() -> bool:
    """Return whether deployments explicitly opted back into invite-only access."""
    return os.environ.get("INVITE_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}


def pending_invitation(db, email: str):
    return db.execute(text(f"""
        SELECT id, role FROM {SCHEMA}.invitations
        WHERE email=:email AND status='pending'
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY created_at DESC LIMIT 1
    """), {"email": email.strip().lower()}).fetchone()


def invited_or_existing(db, email: str) -> bool:
    existing = db.execute(
        text(f"SELECT 1 FROM {SCHEMA}.chat_users WHERE email=:email"),
        {"email": email.strip().lower()},
    ).fetchone()
    return bool(existing or pending_invitation(db, email))


def consume_invitation(db, email: str) -> None:
    db.execute(text(f"""
        UPDATE {SCHEMA}.invitations SET status='accepted', accepted_at=NOW()
        WHERE id = (
            SELECT id FROM {SCHEMA}.invitations
            WHERE email=:email AND status='pending'
            ORDER BY created_at DESC LIMIT 1
        )
    """), {"email": email.strip().lower()})
