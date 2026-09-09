"""Account deletion shared by the mobile API and future account-management flows."""

import os

from sqlalchemy import text

SCHEMA = os.environ.get("DB_SCHEMA", "fastcpi")


def delete_user_data(db, user_id: int) -> bool:
    """Permanently delete an account and all user-owned records in one transaction."""
    user = db.execute(
        text(f"SELECT id FROM {SCHEMA}.chat_users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if not user:
        return False

    db.execute(
        text(
            f"DELETE FROM {SCHEMA}.chat_messages "
            f"WHERE session_id IN (SELECT id FROM {SCHEMA}.chat_sessions WHERE user_id = :uid)"
        ),
        {"uid": user_id},
    )
    db.execute(
        text(f"DELETE FROM {SCHEMA}.chat_sessions WHERE user_id = :uid"),
        {"uid": user_id},
    )

    # These tables use ON DELETE CASCADE, but explicit deletion keeps the
    # lifecycle clear and supports databases created before those constraints.
    for table in ("watchlists", "api_keys"):
        db.execute(
            text(f"DELETE FROM {SCHEMA}.{table} WHERE user_id = :uid"),
            {"uid": user_id},
        )

    db.execute(
        text(f"DELETE FROM {SCHEMA}.chat_users WHERE id = :uid"),
        {"uid": user_id},
    )
    db.commit()
    return True
