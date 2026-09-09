"""Chat routes -- 3-pane UI + SSE streaming."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from starlette.requests import Request
from starlette.responses import StreamingResponse, JSONResponse

from chat.layout import chat_page
from chat import sse
from utils.session import (get_user_email, set_user_email, clear_user,
                           get_user_id, set_user_id)

log = logging.getLogger(__name__)

SCHEMA = "carhero"


def _get_db():
    from db import SessionLocal
    return SessionLocal()


def _ensure_user(sess) -> tuple[int | None, str | None]:
    email = get_user_email(sess)
    if not email:
        return None, None
    uid = get_user_id(sess)
    if uid:
        return uid, email
    from sqlalchemy import text
    db = _get_db()
    try:
        row = db.execute(
            text(f"INSERT INTO {SCHEMA}.chat_users (email) VALUES (:email) "
                 "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email "
                 "RETURNING id"),
            {"email": email},
        ).fetchone()
        db.commit()
        uid = row[0]
    finally:
        db.close()
    set_user_id(sess, uid)
    return uid, email


def _ensure_session(user_id, sid, first_message=None):
    from sqlalchemy import text
    db = _get_db()
    try:
        if sid:
            try:
                sid_int = int(sid)
            except (TypeError, ValueError):
                sid_int = 0
            if sid_int:
                row = db.execute(
                    text(f"SELECT id FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
                    {"sid": sid_int, "uid": user_id},
                ).fetchone()
                if row:
                    return sid_int

        title = (first_message or "New chat")[:80]
        row = db.execute(
            text(f"INSERT INTO {SCHEMA}.chat_sessions (user_id, title) VALUES (:uid, :title) RETURNING id"),
            {"uid": user_id, "title": title},
        ).fetchone()
        db.commit()
        return row[0]
    finally:
        db.close()


def _list_sessions(user_id, limit=30):
    from sqlalchemy import text
    db = _get_db()
    try:
        rows = db.execute(
            text(f"SELECT id, title, agent_slug, updated_at FROM {SCHEMA}.chat_sessions "
                 "WHERE user_id = :uid ORDER BY updated_at DESC LIMIT :lim"),
            {"uid": user_id, "lim": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


def _session_messages(session_id):
    from sqlalchemy import text
    db = _get_db()
    try:
        rows = db.execute(
            text(f"SELECT role, content, agent_slug FROM {SCHEMA}.chat_messages "
                 "WHERE session_id = :sid ORDER BY id ASC"),
            {"sid": session_id},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


def _persist_message(session_id, role, content, agent_slug=None, tool_calls=None):
    from sqlalchemy import text
    db = _get_db()
    try:
        db.execute(
            text(f"INSERT INTO {SCHEMA}.chat_messages (session_id, role, content, agent_slug, tool_calls) "
                 "VALUES (:sid, :role, :content, :agent, :tools)"),
            {"sid": session_id, "role": role, "content": content,
             "agent": agent_slug,
             "tools": json.dumps(tool_calls) if tool_calls else None},
        )
        db.execute(
            text(f"UPDATE {SCHEMA}.chat_sessions SET updated_at = now() WHERE id = :sid"),
            {"sid": session_id},
        )
        db.commit()
    finally:
        db.close()


def register_chat_routes(rt):
    """Register all chat routes on the given FastHTML router."""

    @rt("/app")
    def app_home(sess, sid: str = ""):
        uid, email = _ensure_user(sess)
        sessions = _list_sessions(uid) if uid else []
        messages = []
        current_agent = None
        if uid and sid:
            try:
                from sqlalchemy import text
                db = _get_db()
                try:
                    row = db.execute(
                        text(f"SELECT id, agent_slug FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
                        {"sid": int(sid), "uid": uid},
                    ).fetchone()
                    if row:
                        messages = _session_messages(int(sid))
                        current_agent = row._mapping.get("agent_slug")
                finally:
                    db.close()
            except (TypeError, ValueError):
                pass

        from utils.i18n import get_lang
        lang = get_lang(sess)
        return chat_page(
            user_email=email,
            sessions=sessions,
            current_sid=str(sid) if sid else "",
            messages=messages,
            current_agent_slug=current_agent,
            lang=lang,
        )

    @rt("/app/chat", methods=["POST"])
    async def chat_stream(request: Request):
        sess = request.session
        form = await request.form()
        user_msg = (form.get("msg") or "").strip()
        sid_str = form.get("sid") or ""

        if not user_msg:
            return JSONResponse({"error": "empty message"}, status_code=400)

        uid, email = _ensure_user(sess)
        if not uid:
            from sqlalchemy import text
            db = _get_db()
            try:
                row = db.execute(
                    text(f"INSERT INTO {SCHEMA}.chat_users (email) VALUES (:email) "
                         "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id"),
                    {"email": f"guest+{id(sess):x}@carhero.local"},
                ).fetchone()
                db.commit()
                uid = row[0]
            finally:
                db.close()
            set_user_id(sess, uid)

        session_id = _ensure_session(uid, sid_str, first_message=user_msg)

        from agents import router as agent_router
        from agents.registry import by_slug
        agent_slug = agent_router.route(user_msg)
        spec = by_slug(agent_slug)

        _persist_message(session_id, "user", user_msg)
        history = _session_messages(session_id)[:-1]
        stripped_msg = agent_router.strip_prefix(user_msg)

        async def event_stream():
            yield sse.event("session", {"sid": session_id})
            yield sse.event(sse.AGENT_ROUTE, {
                "slug": agent_slug,
                "agent": spec.name if spec else agent_slug,
                "icon": spec.icon if spec else "*",
            })

            from utils.i18n import get_lang, LANGUAGES
            lang = get_lang(sess)
            lang_info = LANGUAGES.get(lang, LANGUAGES["en"])
            lang_directive = ""
            if lang != "en":
                lang_directive = (
                    f"\nUser language: {lang} ({lang_info['name']}). "
                    f"Respond in {lang_info['name']}."
                )
            lc_messages = [SystemMessage(content=f"You are a CarHero car advisor. Respond helpfully and concisely.{lang_directive}")]
            for h in history[-20:]:
                if h["role"] == "user":
                    lc_messages.append(HumanMessage(content=h["content"]))
                elif h["role"] == "assistant":
                    lc_messages.append(AIMessage(content=h["content"]))
            lc_messages.append(HumanMessage(content=stripped_msg))

            accumulated = []
            tool_calls_log = []

            try:
                from agents.base import cached_agent
                graph = cached_agent(agent_slug)

                async for event in graph.astream_events({"messages": lc_messages}, version="v2"):
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        chunk = event["data"].get("chunk")
                        if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                            if not getattr(chunk, "tool_call_chunks", None):
                                accumulated.append(chunk.content)
                                yield sse.event(sse.TOKEN, {"text": chunk.content})
                    elif kind == "on_tool_start":
                        name = event.get("name", "unknown")
                        args = event["data"].get("input", {})
                        tool_calls_log.append({"name": name, "args": args})
                        yield sse.event(sse.TOOL_START, {"name": name, "args": args})
                    elif kind == "on_tool_end":
                        name = event.get("name", "unknown")
                        raw = event["data"].get("output", "")
                        output = getattr(raw, "content", None) or (raw if isinstance(raw, str) else str(raw))
                        yield sse.event(sse.TOOL_END, {"name": name, "output": output[:2000]})

                        if isinstance(output, str) and "__ARTIFACT__" in output:
                            try:
                                artifact_str = output[output.index("__ARTIFACT__") + len("__ARTIFACT__"):]
                                sep = artifact_str.find("\n\n")
                                if sep != -1:
                                    artifact_str = artifact_str[:sep]
                                payload = json.loads(artifact_str)
                                yield sse.event(sse.ARTIFACT, payload)
                            except Exception:
                                pass
            except Exception as e:
                log.exception("chat stream failed")
                yield sse.event(sse.ERROR, {"message": str(e)})

            final = "".join(accumulated) or "(no response)"
            _persist_message(session_id, "assistant", final, agent_slug=agent_slug,
                             tool_calls=tool_calls_log or None)
            from sqlalchemy import text
            db = _get_db()
            try:
                db.execute(text(f"UPDATE {SCHEMA}.chat_sessions SET agent_slug = :slug WHERE id = :sid"),
                           {"slug": agent_slug, "sid": session_id})
                db.commit()
            finally:
                db.close()
            yield sse.event(sse.DONE, {"slug": agent_slug, "tools": len(tool_calls_log)})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @rt("/app/config", methods=["POST"])
    async def app_config(request: Request):
        from utils.i18n import set_lang, get_lang
        form = await request.form()
        lang_code = (form.get("lang") or "").strip()
        if lang_code:
            set_lang(request.session, lang_code)
        return JSONResponse({"ok": True, "lang": get_lang(request.session)})

    @rt("/app/auth/signin", methods=["POST"])
    async def signin(request: Request):
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        if "@" not in email:
            return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)
        set_user_email(request.session, email)
        _ensure_user(request.session)
        return JSONResponse({"ok": True, "email": email})

    @rt("/app/auth/signout", methods=["POST"])
    async def signout(request: Request):
        clear_user(request.session)
        return JSONResponse({"ok": True})

    @rt("/api/share/{sid}", methods=["POST"])
    async def share_session(request: Request, sid: str):
        sess = request.session
        uid, _ = _ensure_user(sess)
        if not uid:
            return JSONResponse({"error": "not signed in"}, status_code=401)
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            return JSONResponse({"error": "invalid session"}, status_code=400)
        from sqlalchemy import text
        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT share_token FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
                {"sid": sid_int, "uid": uid},
            ).fetchone()
            if not row:
                return JSONResponse({"error": "session not found"}, status_code=404)
            token = row[0]
            if not token:
                import secrets
                token = secrets.token_urlsafe(32)
                db.execute(
                    text(f"UPDATE {SCHEMA}.chat_sessions SET share_token = :token WHERE id = :sid"),
                    {"token": token, "sid": sid_int},
                )
                db.commit()
            return JSONResponse({"token": token, "url": f"/shared/{token}"})
        finally:
            db.close()

    @rt("/shared/{token}")
    def shared_chat(token: str):
        from sqlalchemy import text
        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT s.id, s.title, s.agent_slug, u.email "
                     f"FROM {SCHEMA}.chat_sessions s "
                     f"JOIN {SCHEMA}.chat_users u ON u.id = s.user_id "
                     f"WHERE s.share_token = :token"),
                {"token": token},
            ).fetchone()
            if not row:
                from starlette.responses import HTMLResponse
                return HTMLResponse("<h2>Chat not found</h2>", status_code=404)
            sid = row[0]
            messages = _session_messages(sid)
        finally:
            db.close()

        from chat.layout import shared_chat_page
        return shared_chat_page(
            title=row[1] or "Shared Chat",
            messages=messages,
            agent_slug=row[2],
        )

    @rt("/api/deal/{deal_id}")
    def deal_lookup(deal_id: str):
        from sqlalchemy import text
        db = _get_db()
        try:
            row = db.execute(
                text(f"SELECT make, model FROM {SCHEMA}.deals WHERE id = :did AND status = 'active'"),
                {"did": deal_id},
            ).fetchone()
            if not row:
                return JSONResponse({"error": "deal not found"}, status_code=404)
            return JSONResponse({"deal_id": deal_id, "make": row.make, "model": row.model})
        except Exception:
            return JSONResponse({"error": "invalid deal id"}, status_code=400)
        finally:
            db.close()
