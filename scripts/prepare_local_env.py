#!/usr/bin/env python3
"""Prepare FastCPI's ignored local environment without printing secret values."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import stat
import subprocess
import tempfile
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ensure_ignored(path: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(path.parent), "check-ignore", "-q", str(path)],
        check=False,
    )
    if result.returncode:
        raise ValueError(f"refusing to write unignored environment file: {path}")


def rewrite(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    fd, temporary = tempfile.mkstemp(prefix=".env.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-env", type=Path, required=True)
    parser.add_argument("--database-env", type=Path, required=True)
    parser.add_argument("--target-env", type=Path, default=Path(".env"))
    parser.add_argument("--prompt-exa", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    target = args.target_env.resolve()
    ensure_ignored(target)
    current = read_env(target)
    shared = read_env(args.shared_env)
    database = read_env(args.database_env)
    exa_key = getpass.getpass("EXA_API_KEY: ").strip() if args.prompt_exa else current.get("EXA_API_KEY", "")

    required_shared = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "POSTMARK_API_TOKEN", "XAI_API_KEY")
    missing = [key for key in required_shared if not shared.get(key)]
    if not database.get("DB_URL"):
        missing.append("DB_URL")
    if not exa_key:
        missing.append("EXA_API_KEY")
    if missing:
        raise ValueError("required values unavailable: " + ", ".join(missing))

    values = {
        "PORT": "5011",
        "RELEASE_SHA": subprocess.run(
            ["git", "-C", str(target.parent), "rev-parse", "HEAD"],
            text=True, capture_output=True, check=True,
        ).stdout.strip(),
        "DB_URL": database["DB_URL"],
        "DB_SCHEMA": "fastcpi",
        "APP_SECRET": current.get("APP_SECRET") or secrets.token_urlsafe(48),
        "JWT_SECRET": current.get("JWT_SECRET") or secrets.token_urlsafe(48),
        "LOGIN": "1",
        "INVITE_ONLY": "1",
        "CORS_ALLOWED_ORIGINS": "https://cpi.fastsme.com",
        "SERVICE_URL_FASTCPI": "https://cpi.fastsme.com",
        "EXA_API_KEY": exa_key,
        "LLM_PROVIDER": "xai",
        "XAI_API_KEY": shared["XAI_API_KEY"],
        "XAI_BASE_URL": "https://api.x.ai/v1",
        "GROK_MODEL": "grok-4-1-fast-reasoning",
        "GOOGLE_CLIENT_ID": shared["GOOGLE_CLIENT_ID"],
        "GOOGLE_CLIENT_SECRET": shared["GOOGLE_CLIENT_SECRET"],
        "GOOGLE_REDIRECT_URI": "https://cpi.fastsme.com/auth/google/callback",
        "GOOGLE_ALLOWED_DOMAINS": "",
        "GOOGLE_ALLOWED_EMAILS": "",
        "ADMIN_EMAIL": "kaljuvee@gmail.com",
        "ADMIN_PASSWORD": current.get("ADMIN_PASSWORD") or secrets.token_urlsafe(36),
        "POSTMARK_API_TOKEN": shared["POSTMARK_API_TOKEN"],
        "FROM_EMAIL": "info@fastsme.com",
        "FROM_NAME": "FastCPI",
        "WATCHLIST_SCANS_ENABLED": "1",
        "WATCHLIST_SCAN_INTERVAL_SECONDS": "3600",
        "DIGEST_ENABLED": "0",
    }
    changed = [key for key, value in values.items() if current.get(key) != value]
    print("target=" + str(target))
    print("changes=" + (",".join(changed) if changed else "none"))
    print("mode=" + ("apply" if args.apply else "dry-run"))
    if args.apply:
        rewrite(target, values)
        print("result=updated; values hidden")
    else:
        print("result=no-write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
