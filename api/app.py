"""FastAPI application for the CarHero mobile API.

Mounted at /api/v1 by main.py (dual deploy with FastHTML).
Also runnable standalone: python -m api.app
"""

from __future__ import annotations

import json
import logging
import secrets

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.auth import create_token
from api.account_deletion import delete_user_data
from api.schemas import (
    LoginRequest, RegisterRequest, AuthResponse, UserInfo,
    ChatRequest, SessionSummary, SessionDetail, MessageOut, ShareResponse, SharedSessionOut,
    AgentOut,
    FavoriteOut, AddFavoriteRequest, UpdateNoteRequest,
    SavedSearchOut, CreateSearchRequest,
    GarageCarOut, AddGarageCarRequest, ValuationOut, TcoOut,
    UserProfileOut, UpdateProfileRequest,
    ListingOut,
    AnalyticsRequest, AnalyticsResponse,
    ContactRequest,
)
from api.deps import get_db, get_current_user, get_optional_user
from auth.utils import hash_password, verify_password

log = logging.getLogger(__name__)

SCHEMA = "carhero"


def create_app(root_path: str = "") -> FastAPI:
    """Build the FastAPI app. Routes have no /api/v1 prefix — that comes from the mount point."""
    api = FastAPI(
        title="CarHero API",
        description="Mobile API for CarHero — EU car marketplace with AI advisors",
        version="1.0.0",
        root_path=root_path,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health ────────────────────────────────────────────────────────

    @api.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    # ── Auth ──────────────────────────────────────────────────────────

    @api.post("/auth/register", response_model=AuthResponse, tags=["auth"])
    def register(body: RegisterRequest, db: Session = Depends(get_db)):
        existing = db.execute(
            text(f"SELECT id, password_hash FROM {SCHEMA}.chat_users WHERE email = :email"),
            {"email": body.email},
        ).fetchone()

        if existing and existing.password_hash:
            raise HTTPException(409, "An account with this email already exists")

        pw_hash = hash_password(body.password)

        if existing:
            db.execute(
                text(f"UPDATE {SCHEMA}.chat_users SET password_hash = :pw, name = :name, is_verified = TRUE WHERE email = :email"),
                {"pw": pw_hash, "name": body.name, "email": body.email},
            )
            db.commit()
            uid = existing.id
        else:
            row = db.execute(
                text(f"INSERT INTO {SCHEMA}.chat_users (email, password_hash, name, is_verified) "
                     "VALUES (:email, :pw, :name, TRUE) RETURNING id"),
                {"email": body.email, "pw": pw_hash, "name": body.name},
            ).fetchone()
            db.commit()
            uid = row[0]

        token = create_token(uid, body.email)
        return AuthResponse(token=token, email=body.email, name=body.name, user_id=uid)

    @api.post("/auth/login", response_model=AuthResponse, tags=["auth"])
    def login(body: LoginRequest, db: Session = Depends(get_db)):
        row = db.execute(
            text(f"SELECT id, email, password_hash, name FROM {SCHEMA}.chat_users WHERE email = :email"),
            {"email": body.email},
        ).fetchone()

        if not row or not row.password_hash:
            raise HTTPException(401, "Invalid email or password")
        if not verify_password(body.password, row.password_hash):
            raise HTTPException(401, "Invalid email or password")

        token = create_token(row.id, row.email)
        return AuthResponse(token=token, email=row.email, name=row.name or "", user_id=row.id)

    @api.post("/auth/google", response_model=AuthResponse, tags=["auth"])
    def google_auth(body: dict, db: Session = Depends(get_db)):
        """Validate a Google ID token from mobile app and return a JWT."""
        import urllib.request
        id_token = body.get("id_token")
        if not id_token:
            raise HTTPException(400, "id_token is required")

        try:
            url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                info = json.loads(resp.read())
        except Exception as e:
            raise HTTPException(401, f"Invalid Google token: {e}")

        email = info.get("email")
        if not email or info.get("email_verified") != "true":
            raise HTTPException(401, "Email not verified")

        name = info.get("name", "")

        row = db.execute(
            text(f"SELECT id, name FROM {SCHEMA}.chat_users WHERE email = :email"),
            {"email": email},
        ).fetchone()

        if row:
            uid = row.id
            name = row.name or name
        else:
            r = db.execute(
                text(f"INSERT INTO {SCHEMA}.chat_users (email, name, is_verified) "
                     "VALUES (:email, :name, TRUE) RETURNING id"),
                {"email": email, "name": name},
            ).fetchone()
            db.commit()
            uid = r[0]

        token = create_token(uid, email)
        return AuthResponse(token=token, email=email, name=name, user_id=uid)

    @api.get("/auth/me", response_model=UserInfo, tags=["auth"])
    def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(
            text(f"SELECT id, email, name FROM {SCHEMA}.chat_users WHERE id = :id"),
            {"id": user["user_id"]},
        ).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        return UserInfo(user_id=row.id, email=row.email, name=row.name or "")

    @api.delete("/auth/account", tags=["auth"])
    def delete_account(
        user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not delete_user_data(db, user["user_id"]):
            raise HTTPException(404, "User not found")
        return {"ok": True}

    # ── Agents ────────────────────────────────────────────────────────

    @api.get("/agents", response_model=list[AgentOut], tags=["agents"])
    def list_agents():
        from agents.registry import AGENTS
        return [
            AgentOut(
                slug=a.slug, name=a.name, category=a.category,
                icon=a.icon, one_liner=a.one_liner, prefix=a.prefix,
                example_prompts=list(a.example_prompts),
            )
            for a in AGENTS
        ]

    # ── Sessions ──────────────────────────────────────────────────────

    @api.get("/sessions", response_model=list[SessionSummary], tags=["sessions"])
    def list_sessions(
        limit: int = 30,
        user: dict | None = Depends(get_optional_user),
        db: Session = Depends(get_db),
    ):
        uid = user["sub"] if user else 0
        rows = db.execute(
            text(f"SELECT id, title, agent_slug, updated_at FROM {SCHEMA}.chat_sessions "
                 "WHERE user_id = :uid ORDER BY updated_at DESC LIMIT :lim"),
            {"uid": uid, "lim": limit},
        ).fetchall()
        return [
            SessionSummary(id=r.id, title=r.title, agent_slug=r.agent_slug,
                           updated_at=str(r.updated_at))
            for r in rows
        ]

    @api.get("/sessions/{session_id}", response_model=SessionDetail, tags=["sessions"])
    def get_session(
        session_id: int,
        user: dict | None = Depends(get_optional_user),
        db: Session = Depends(get_db),
    ):
        uid = user["sub"] if user else 0
        row = db.execute(
            text(f"SELECT id, title, agent_slug FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": uid},
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")

        msgs = db.execute(
            text(f"SELECT role, content, agent_slug FROM {SCHEMA}.chat_messages "
                 "WHERE session_id = :sid ORDER BY id ASC"),
            {"sid": session_id},
        ).fetchall()
        return SessionDetail(
            id=row.id, title=row.title, agent_slug=row.agent_slug,
            messages=[MessageOut(role=m.role, content=m.content, agent_slug=m.agent_slug) for m in msgs],
        )

    @api.delete("/sessions/{session_id}", tags=["sessions"])
    def delete_session(
        session_id: int,
        user: dict | None = Depends(get_optional_user),
        db: Session = Depends(get_db),
    ):
        uid = user["sub"] if user else 0
        row = db.execute(
            text(f"SELECT id FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": uid},
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")

        db.execute(text(f"DELETE FROM {SCHEMA}.chat_messages WHERE session_id = :sid"), {"sid": session_id})
        db.execute(text(f"DELETE FROM {SCHEMA}.chat_sessions WHERE id = :sid"), {"sid": session_id})
        db.commit()
        return {"ok": True}

    @api.post("/sessions/{session_id}/share", response_model=ShareResponse, tags=["sessions"])
    def share_session(
        session_id: int,
        user: dict | None = Depends(get_optional_user),
        db: Session = Depends(get_db),
    ):
        uid = user["sub"] if user else 0
        row = db.execute(
            text(f"SELECT share_token FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": uid},
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")

        token = row.share_token
        if not token:
            token = secrets.token_urlsafe(32)
            db.execute(
                text(f"UPDATE {SCHEMA}.chat_sessions SET share_token = :token WHERE id = :sid"),
                {"token": token, "sid": session_id},
            )
            db.commit()
        return ShareResponse(token=token, url=f"/shared/{token}")

    @api.get("/shared/{token}", response_model=SharedSessionOut, tags=["sessions"])
    def get_shared_session(token: str, db: Session = Depends(get_db)):
        row = db.execute(
            text(f"SELECT s.id, s.title, s.agent_slug "
                 f"FROM {SCHEMA}.chat_sessions s "
                 f"WHERE s.share_token = :token"),
            {"token": token},
        ).fetchone()
        if not row:
            raise HTTPException(404, "Shared session not found")
        msgs = db.execute(
            text(f"SELECT role, content, agent_slug FROM {SCHEMA}.chat_messages "
                 "WHERE session_id = :sid ORDER BY id ASC"),
            {"sid": row[0]},
        ).fetchall()
        return SharedSessionOut(
            title=row[1] or "Shared Chat",
            agent_slug=row[2],
            messages=[MessageOut(role=m.role, content=m.content, agent_slug=m.agent_slug) for m in msgs],
        )

    # ── Chat (SSE streaming) ─────────────────────────────────────────

    @api.post("/chat", tags=["chat"],
              responses={200: {"content": {"text/event-stream": {}},
                               "description": "SSE stream of chat events"}})
    def chat(
        body: ChatRequest,
        user: dict | None = Depends(get_optional_user),
        db: Session = Depends(get_db),
    ):
        uid = user["sub"] if user else 0

        if body.session_id:
            row = db.execute(
                text(f"SELECT id FROM {SCHEMA}.chat_sessions WHERE id = :sid AND user_id = :uid"),
                {"sid": body.session_id, "uid": uid},
            ).fetchone()
            session_id = row.id if row else None
        else:
            session_id = None

        if not session_id:
            row = db.execute(
                text(f"INSERT INTO {SCHEMA}.chat_sessions (user_id, title) VALUES (:uid, :title) RETURNING id"),
                {"uid": uid, "title": body.message[:80]},
            ).fetchone()
            db.commit()
            session_id = row[0]

        from agents import router as agent_router
        from agents.registry import by_slug
        agent_slug = agent_router.route(body.message)
        spec = by_slug(agent_slug)

        db.execute(
            text(f"INSERT INTO {SCHEMA}.chat_messages (session_id, role, content) VALUES (:sid, 'user', :content)"),
            {"sid": session_id, "content": body.message},
        )
        db.commit()

        history_rows = db.execute(
            text(f"SELECT role, content FROM {SCHEMA}.chat_messages "
                 "WHERE session_id = :sid ORDER BY id ASC"),
            {"sid": session_id},
        ).fetchall()
        history = [{"role": r.role, "content": r.content} for r in history_rows[:-1]]

        stripped_msg = agent_router.strip_prefix(body.message)

        async def event_stream():
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
            from utils.i18n import LANGUAGES

            yield _sse_event("session", {"sid": session_id})
            yield _sse_event("agent_route", {
                "slug": agent_slug,
                "agent": spec.name if spec else agent_slug,
                "icon": spec.icon if spec else "*",
            })

            lang_info = LANGUAGES.get(body.lang, LANGUAGES["en"])
            lang_directive = ""
            if body.lang != "en":
                lang_directive = f"\nUser language: {body.lang} ({lang_info['name']}). Respond in {lang_info['name']}."

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

                async for ev in graph.astream_events({"messages": lc_messages}, version="v2"):
                    kind = ev["event"]
                    if kind == "on_chat_model_stream":
                        chunk = ev["data"].get("chunk")
                        if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                            if not getattr(chunk, "tool_call_chunks", None):
                                accumulated.append(chunk.content)
                                yield _sse_event("token", {"text": chunk.content})
                    elif kind == "on_tool_start":
                        name = ev.get("name", "unknown")
                        args = ev["data"].get("input", {})
                        tool_calls_log.append({"name": name, "args": args})
                        yield _sse_event("tool_start", {"name": name, "args": args})
                    elif kind == "on_tool_end":
                        name = ev.get("name", "unknown")
                        raw = ev["data"].get("output", "")
                        output = getattr(raw, "content", None) or (raw if isinstance(raw, str) else str(raw))
                        yield _sse_event("tool_end", {"name": name, "output": output[:2000]})

                        if isinstance(output, str) and "__ARTIFACT__" in output:
                            try:
                                artifact_str = output[output.index("__ARTIFACT__") + len("__ARTIFACT__"):]
                                sep = artifact_str.find("\n\n")
                                if sep != -1:
                                    artifact_str = artifact_str[:sep]
                                payload = json.loads(artifact_str)
                                yield _sse_event("artifact_show", payload)
                            except Exception:
                                pass
            except Exception as e:
                log.exception("chat stream failed")
                yield _sse_event("error", {"message": str(e)})

            final = "".join(accumulated) or "(no response)"

            from db import SessionLocal
            persist_db = SessionLocal()
            try:
                persist_db.execute(
                    text(f"INSERT INTO {SCHEMA}.chat_messages (session_id, role, content, agent_slug, tool_calls) "
                         "VALUES (:sid, 'assistant', :content, :agent, :tools)"),
                    {"sid": session_id, "content": final, "agent": agent_slug,
                     "tools": json.dumps(tool_calls_log) if tool_calls_log else None},
                )
                persist_db.execute(
                    text(f"UPDATE {SCHEMA}.chat_sessions SET agent_slug = :slug, updated_at = now() WHERE id = :sid"),
                    {"slug": agent_slug, "sid": session_id},
                )
                persist_db.commit()
            finally:
                persist_db.close()

            yield _sse_event("done", {"slug": agent_slug, "tools": len(tool_calls_log)})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ── Favorites ────────────────────────────────────────────────────

    @api.get("/favorites", response_model=list[FavoriteOut], tags=["favorites"])
    def list_favorites(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        rows = db.execute(text(f"""
            SELECT f.id, f.listing_id, f.price_at_save, f.note, f.created_at,
                   cl.make, cl.model, cl.variant, cl.year, cl.mileage_km,
                   cl.price_eur, cl.fuel_type, cl.transmission, cl.country,
                   cl.provider, cl.source_url
            FROM {SCHEMA}.favorites f
            JOIN {SCHEMA}.car_listings cl ON cl.id = f.listing_id
            WHERE f.user_id = :uid
            ORDER BY f.created_at DESC
        """), {"uid": user["user_id"]}).fetchall()

        result = []
        for r in rows:
            m = dict(r._mapping)
            price_change = None
            if m.get("price_at_save") and m.get("price_eur"):
                price_change = round(float(m["price_eur"]) - float(m["price_at_save"]))
            result.append(FavoriteOut(
                id=m["id"], listing_id=m["listing_id"],
                make=m["make"], model=m["model"],
                variant=m.get("variant") or "",
                year=m.get("year"),
                mileage_km=int(m["mileage_km"]) if m.get("mileage_km") else None,
                price_eur=round(float(m["price_eur"])) if m.get("price_eur") else None,
                price_at_save=round(float(m["price_at_save"])) if m.get("price_at_save") else None,
                price_change=price_change,
                fuel_type=m.get("fuel_type") or "",
                transmission=m.get("transmission") or "",
                country=m.get("country") or "",
                provider=m.get("provider") or "",
                url=m.get("source_url") or "",
                note=m.get("note") or "",
            ))
        return result

    @api.post("/favorites", tags=["favorites"])
    def add_favorite(body: AddFavoriteRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        price = db.execute(
            text(f"SELECT price_eur FROM {SCHEMA}.car_listings WHERE id = :id"),
            {"id": body.listing_id},
        ).scalar()
        db.execute(text(f"""
            INSERT INTO {SCHEMA}.favorites (user_id, listing_id, price_at_save)
            VALUES (:uid, :lid, :price)
            ON CONFLICT (user_id, listing_id) DO NOTHING
        """), {"uid": user["user_id"], "lid": body.listing_id, "price": price})
        db.commit()
        return {"ok": True}

    @api.delete("/favorites/{fav_id}", tags=["favorites"])
    def remove_favorite(fav_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        db.execute(text(f"""
            DELETE FROM {SCHEMA}.favorites WHERE id = :id AND user_id = :uid
        """), {"id": fav_id, "uid": user["user_id"]})
        db.commit()
        return {"ok": True}

    @api.post("/favorites/{fav_id}/note", tags=["favorites"])
    def update_favorite_note(fav_id: int, body: UpdateNoteRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        db.execute(text(f"""
            UPDATE {SCHEMA}.favorites SET note = :note WHERE id = :id AND user_id = :uid
        """), {"note": body.note, "id": fav_id, "uid": user["user_id"]})
        db.commit()
        return {"ok": True}

    # ── Saved Searches ───────────────────────────────────────────────

    @api.get("/saved-searches", response_model=list[SavedSearchOut], tags=["saved-searches"])
    def list_saved_searches(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        rows = db.execute(text(f"""
            SELECT id, name, filters, last_viewed_at, last_count, notify_email, created_at
            FROM {SCHEMA}.saved_searches
            WHERE user_id = :uid ORDER BY created_at DESC
        """), {"uid": user["user_id"]}).fetchall()

        result = []
        for r in rows:
            m = dict(r._mapping)
            filters = m["filters"] if isinstance(m["filters"], dict) else json.loads(m["filters"] or "{}")
            result.append(SavedSearchOut(
                id=m["id"], name=m["name"], filters=filters,
                last_count=m.get("last_count") or 0,
                notify_email=bool(m.get("notify_email")),
                created_at=str(m.get("created_at") or ""),
            ))
        return result

    @api.post("/saved-searches", tags=["saved-searches"])
    def create_saved_search(body: CreateSearchRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(text(f"""
            INSERT INTO {SCHEMA}.saved_searches (user_id, name, filters, notify_email)
            VALUES (:uid, :name, :filters::jsonb, :notify)
            RETURNING id
        """), {
            "uid": user["user_id"], "name": body.name,
            "filters": json.dumps(body.filters), "notify": body.notify_email,
        }).fetchone()
        db.commit()
        return {"ok": True, "id": row[0] if row else None}

    @api.delete("/saved-searches/{search_id}", tags=["saved-searches"])
    def delete_saved_search(search_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        db.execute(text(f"""
            DELETE FROM {SCHEMA}.saved_searches WHERE id = :id AND user_id = :uid
        """), {"id": search_id, "uid": user["user_id"]})
        db.commit()
        return {"ok": True}

    @api.post("/saved-searches/{search_id}/check", tags=["saved-searches"])
    def check_saved_search(search_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(text(f"""
            SELECT filters FROM {SCHEMA}.saved_searches WHERE id = :id AND user_id = :uid
        """), {"id": search_id, "uid": user["user_id"]}).fetchone()
        if not row:
            raise HTTPException(404, "Saved search not found")
        filters = row.filters if isinstance(row.filters, dict) else json.loads(row.filters or "{}")
        conditions = ["status = 'active'", "price_eur > 0"]
        bind = {}
        if filters.get("make"):
            conditions.append("make ILIKE :make")
            bind["make"] = f"%{filters['make']}%"
        if filters.get("model"):
            conditions.append("model ILIKE :model")
            bind["model"] = f"%{filters['model']}%"
        if filters.get("max_price"):
            conditions.append("price_eur <= :max_price")
            bind["max_price"] = float(filters["max_price"])
        if filters.get("min_year"):
            conditions.append("year >= :min_year")
            bind["min_year"] = int(filters["min_year"])
        where = " AND ".join(conditions)
        count = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.car_listings WHERE {where}"), bind).scalar()
        db.execute(text(f"""
            UPDATE {SCHEMA}.saved_searches SET last_count = :cnt, last_viewed_at = now() WHERE id = :id
        """), {"cnt": count, "id": search_id})
        db.commit()
        return {"count": count}

    # ── Garage ───────────────────────────────────────────────────────

    @api.get("/garage", response_model=list[GarageCarOut], tags=["garage"])
    def list_garage(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        rows = db.execute(text(f"""
            SELECT * FROM {SCHEMA}.garage_cars WHERE user_id = :uid ORDER BY created_at DESC
        """), {"uid": user["user_id"]}).fetchall()

        from chat.garage import _compute_valuation
        result = []
        for r in rows:
            m = dict(r._mapping)
            val = _compute_valuation(m["make"], m["model"], m["year"], m.get("mileage_km"))
            result.append(GarageCarOut(
                id=m["id"], make=m["make"], model=m["model"],
                variant=m.get("variant") or "", year=m["year"],
                mileage_km=m.get("mileage_km"),
                purchase_price_eur=float(m["purchase_price_eur"]) if m.get("purchase_price_eur") else None,
                fuel_type=m.get("fuel_type") or "",
                estimated_value=val.get("estimated_value"),
                comparable_count=val.get("comparable_count", 0),
            ))
        return result

    @api.post("/garage", tags=["garage"])
    def add_garage_car(body: AddGarageCarRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(text(f"""
            INSERT INTO {SCHEMA}.garage_cars
                (user_id, make, model, variant, year, mileage_km, purchase_price_eur,
                 purchase_date, fuel_type, fuel_consumption_l100km, annual_km,
                 insurance_annual_eur, maintenance_annual_eur)
            VALUES (:uid, :make, :model, :variant, :year, :mileage, :price,
                    :pdate, :fuel, :consumption, :km, :ins, :maint)
            RETURNING id
        """), {
            "uid": user["user_id"], "make": body.make, "model": body.model,
            "variant": body.variant or None, "year": body.year,
            "mileage": body.mileage_km, "price": body.purchase_price_eur,
            "pdate": body.purchase_date, "fuel": body.fuel_type,
            "consumption": body.fuel_consumption_l100km,
            "km": body.annual_km, "ins": body.insurance_annual_eur,
            "maint": body.maintenance_annual_eur,
        }).fetchone()
        db.commit()
        return {"ok": True, "id": row[0] if row else None}

    @api.delete("/garage/{car_id}", tags=["garage"])
    def delete_garage_car(car_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        db.execute(text(f"""
            DELETE FROM {SCHEMA}.garage_cars WHERE id = :id AND user_id = :uid
        """), {"id": car_id, "uid": user["user_id"]})
        db.commit()
        return {"ok": True}

    @api.get("/garage/{car_id}/valuation", response_model=ValuationOut, tags=["garage"])
    def garage_valuation(car_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(text(f"""
            SELECT make, model, year, mileage_km FROM {SCHEMA}.garage_cars WHERE id = :id AND user_id = :uid
        """), {"id": car_id, "uid": user["user_id"]}).fetchone()
        if not row:
            raise HTTPException(404, "Car not found")
        from chat.garage import _compute_valuation
        val = _compute_valuation(row.make, row.model, row.year, row.mileage_km)
        return ValuationOut(**val)

    @api.get("/garage/{car_id}/tco", response_model=TcoOut, tags=["garage"])
    def garage_tco(car_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(text(f"""
            SELECT * FROM {SCHEMA}.garage_cars WHERE id = :id AND user_id = :uid
        """), {"id": car_id, "uid": user["user_id"]}).fetchone()
        if not row:
            raise HTTPException(404, "Car not found")
        from chat.garage import _compute_valuation, _compute_tco
        car = dict(row._mapping)
        val = _compute_valuation(car["make"], car["model"], car["year"], car.get("mileage_km"))
        tco = _compute_tco(car, val.get("estimated_value"))
        tco["valuation"] = val
        return TcoOut(**tco)

    # ── Profile ──────────────────────────────────────────────────────

    @api.get("/user/profile", response_model=UserProfileOut, tags=["profile"])
    def get_profile(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        u = db.execute(
            text(f"SELECT name, email FROM {SCHEMA}.chat_users WHERE id = :id"),
            {"id": user["user_id"]},
        ).fetchone()
        if not u:
            raise HTTPException(404, "User not found")

        prefs = db.execute(
            text(f"SELECT * FROM {SCHEMA}.user_profiles WHERE user_id = :uid"),
            {"uid": user["user_id"]},
        ).fetchone()

        p = dict(prefs._mapping) if prefs else {}
        return UserProfileOut(
            name=u.name or "",
            email=u.email,
            phone=p.get("phone") or "",
            country=p.get("country") or "",
            city=p.get("city") or "",
            currency=p.get("currency") or "EUR",
            language=p.get("language") or "en",
            budget_min_eur=float(p["budget_min_eur"]) if p.get("budget_min_eur") else None,
            budget_max_eur=float(p["budget_max_eur"]) if p.get("budget_max_eur") else None,
            preferred_makes=json.loads(p["preferred_makes"]) if p.get("preferred_makes") else [],
            preferred_body_types=json.loads(p["preferred_body_types"]) if p.get("preferred_body_types") else [],
            preferred_fuel_types=json.loads(p["preferred_fuel_types"]) if p.get("preferred_fuel_types") else [],
            preferred_transmission=p.get("preferred_transmission"),
            max_mileage_km=p.get("max_mileage_km"),
            min_year=p.get("min_year"),
            max_year=p.get("max_year"),
            notify_new_listings=p.get("notify_new_listings", True),
            notify_price_drops=p.get("notify_price_drops", True),
            notify_weekly_digest=p.get("notify_weekly_digest", True),
        )

    @api.post("/user/profile", tags=["profile"])
    def update_profile(body: UpdateProfileRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        uid = user["user_id"]
        if body.name is not None:
            db.execute(text(f"UPDATE {SCHEMA}.chat_users SET name = :name WHERE id = :id"),
                       {"name": body.name, "id": uid})

        existing = db.execute(
            text(f"SELECT user_id FROM {SCHEMA}.user_profiles WHERE user_id = :uid"),
            {"uid": uid},
        ).fetchone()

        fields = {}
        for field in ["phone", "country", "city", "currency", "language",
                      "budget_min_eur", "budget_max_eur", "preferred_transmission",
                      "max_mileage_km", "min_year", "max_year",
                      "notify_new_listings", "notify_price_drops", "notify_weekly_digest"]:
            val = getattr(body, field, None)
            if val is not None:
                fields[field] = val

        for field in ["preferred_makes", "preferred_body_types", "preferred_fuel_types"]:
            val = getattr(body, field, None)
            if val is not None:
                fields[field] = json.dumps(val)

        if existing:
            if fields:
                set_clause = ", ".join(f"{k} = :{k}" for k in fields)
                db.execute(text(f"UPDATE {SCHEMA}.user_profiles SET {set_clause} WHERE user_id = :uid"),
                           {**fields, "uid": uid})
        else:
            fields["user_id"] = uid
            cols = ", ".join(fields.keys())
            vals = ", ".join(f":{k}" for k in fields)
            db.execute(text(f"INSERT INTO {SCHEMA}.user_profiles ({cols}) VALUES ({vals})"), fields)

        db.commit()
        return {"ok": True}

    # ── Market Map ───────────────────────────────────────────────────

    @api.get("/market-map/filters", tags=["market-map"])
    def market_map_filters(db: Session = Depends(get_db)):
        countries = [r[0] for r in db.execute(text(
            f"SELECT DISTINCT country FROM {SCHEMA}.car_listings WHERE status='active' AND country IS NOT NULL ORDER BY 1"
        ))]
        makes = [r[0] for r in db.execute(text(
            f"SELECT DISTINCT make FROM {SCHEMA}.car_listings WHERE status='active' ORDER BY 1"
        ))]
        fuel_types = [r[0] for r in db.execute(text(
            f"SELECT DISTINCT fuel_type FROM {SCHEMA}.car_listings WHERE status='active' AND fuel_type IS NOT NULL ORDER BY 1"
        ))]
        return {"countries": countries, "makes": makes, "fuel_types": fuel_types}

    @api.get("/market-map/treemap", tags=["market-map"])
    def market_map_treemap(
        country: str = None, make: str = None, fuel_type: str = None,
        min_year: str = None, max_year: str = None,
        format: str = None,
        db: Session = Depends(get_db),
    ):
        from chat.market_map import _fetch_treemap_data, _build_treemap_fig
        params = {k: v for k, v in {"country": country, "make": make, "fuel_type": fuel_type, "min_year": min_year, "max_year": max_year}.items() if v}
        rows = _fetch_treemap_data(params)
        if format == "data":
            return {"data": rows}
        fig = _build_treemap_fig(rows)
        if not fig:
            return {"error": "No data"}
        return json.loads(fig.to_json())

    @api.get("/market-map/trends", tags=["market-map"])
    def market_map_trends(
        country: str = None, make: str = None, fuel_type: str = None,
        min_year: str = None, max_year: str = None,
        format: str = None,
        db: Session = Depends(get_db),
    ):
        from chat.market_map import _fetch_trend_data, _build_trend_fig
        params = {k: v for k, v in {"country": country, "make": make, "fuel_type": fuel_type, "min_year": min_year, "max_year": max_year}.items() if v}
        rows = _fetch_trend_data(params)
        if format == "data":
            return {"data": rows}
        fig = _build_trend_fig(rows)
        if not fig:
            return {"error": "No data"}
        return json.loads(fig.to_json())

    @api.get("/market-map/geo", tags=["market-map"])
    def market_map_geo(
        make: str = None, model: str = None,
        format: str = None,
        db: Session = Depends(get_db),
    ):
        from chat.market_map import _fetch_geo_data, _build_geo_fig
        params = {k: v for k, v in {"make": make, "model": model}.items() if v}
        rows = _fetch_geo_data(params)
        if format == "data":
            return {"data": rows}
        fig = _build_geo_fig(rows)
        if not fig:
            return {"error": "No data"}
        return json.loads(fig.to_json())

    @api.get("/market-map/value-map", tags=["market-map"])
    def market_map_value_map(
        country: str = None, make: str = None, fuel_type: str = None,
        format: str = None,
        db: Session = Depends(get_db),
    ):
        from chat.market_map import _fetch_value_map_data, _build_value_map_fig
        params = {k: v for k, v in {"country": country, "make": make, "fuel_type": fuel_type}.items() if v}
        rows = _fetch_value_map_data(params)
        if format == "data":
            return {"data": rows}
        fig = _build_value_map_fig(rows)
        if not fig:
            return {"error": "No data"}
        return json.loads(fig.to_json())

    @api.get("/market-map/price-index", tags=["market-map"])
    def market_map_price_index(
        make: str = None, base_year: str = "2015",
        format: str = None,
        db: Session = Depends(get_db),
    ):
        from chat.market_map import _fetch_price_index_data, _build_price_index_fig
        params = {k: v for k, v in {"make": make, "base_year": base_year}.items() if v}
        rows, by = _fetch_price_index_data(params)
        if format == "data":
            return {"data": rows, "base_year": by}
        fig = _build_price_index_fig(rows, by)
        if not fig:
            return {"error": "No data"}
        return json.loads(fig.to_json())

    # ── Listings ─────────────────────────────────────────────────────

    @api.get("/listings/search", response_model=list[ListingOut], tags=["listings"])
    def search_listings(
        make: str = None, model: str = None,
        min_price: int = None, max_price: int = None,
        min_year: int = None, max_year: int = None,
        max_mileage: int = None,
        fuel_type: str = None, transmission: str = None,
        body_type: str = None, country: str = None,
        limit: int = 20,
        db: Session = Depends(get_db),
    ):
        conditions = ["status = 'active'", "price_eur > 0"]
        bind: dict = {}
        if make:
            conditions.append("make ILIKE :make")
            bind["make"] = f"%{make}%"
        if model:
            conditions.append("model ILIKE :model")
            bind["model"] = f"%{model}%"
        if min_price:
            conditions.append("price_eur >= :min_price")
            bind["min_price"] = min_price
        if max_price:
            conditions.append("price_eur <= :max_price")
            bind["max_price"] = max_price
        if min_year:
            conditions.append("year >= :min_year")
            bind["min_year"] = min_year
        if max_year:
            conditions.append("year <= :max_year")
            bind["max_year"] = max_year
        if max_mileage:
            conditions.append("mileage_km <= :max_mileage")
            bind["max_mileage"] = max_mileage
        if fuel_type:
            conditions.append("fuel_type ILIKE :fuel_type")
            bind["fuel_type"] = f"%{fuel_type}%"
        if transmission:
            conditions.append("transmission ILIKE :transmission")
            bind["transmission"] = f"%{transmission}%"
        if body_type:
            conditions.append("body_type ILIKE :body_type")
            bind["body_type"] = f"%{body_type}%"
        if country:
            conditions.append("country = :country")
            bind["country"] = country

        where = " AND ".join(conditions)
        bind["lim"] = min(limit, 100)
        rows = db.execute(text(f"""
            SELECT id, make, model, variant, year, price_eur, mileage_km,
                   fuel_type, transmission, body_type, power_hp,
                   country, provider, source_url, image_urls
            FROM {SCHEMA}.car_listings
            WHERE {where}
            ORDER BY price_eur ASC
            LIMIT :lim
        """), bind).fetchall()

        return [ListingOut(
            id=r.id, make=r.make, model=r.model, variant=r.variant or "",
            year=r.year, price_eur=float(r.price_eur) if r.price_eur else None,
            mileage_km=r.mileage_km, fuel_type=r.fuel_type or "",
            transmission=r.transmission or "", body_type=r.body_type or "",
            power_hp=r.power_hp, country=r.country or "",
            provider=r.provider or "", source_url=r.source_url or "",
            image_urls=json.loads(r.image_urls) if r.image_urls and isinstance(r.image_urls, str) else (r.image_urls or None),
        ) for r in rows]

    @api.get("/listings/{listing_id}", response_model=ListingOut, tags=["listings"])
    def get_listing(listing_id: int, db: Session = Depends(get_db)):
        r = db.execute(text(f"""
            SELECT id, make, model, variant, year, price_eur, mileage_km,
                   fuel_type, transmission, body_type, power_hp,
                   country, provider, source_url, image_urls
            FROM {SCHEMA}.car_listings WHERE id = :id
        """), {"id": listing_id}).fetchone()
        if not r:
            raise HTTPException(404, "Listing not found")
        return ListingOut(
            id=r.id, make=r.make, model=r.model, variant=r.variant or "",
            year=r.year, price_eur=float(r.price_eur) if r.price_eur else None,
            mileage_km=r.mileage_km, fuel_type=r.fuel_type or "",
            transmission=r.transmission or "", body_type=r.body_type or "",
            power_hp=r.power_hp, country=r.country or "",
            provider=r.provider or "", source_url=r.source_url or "",
            image_urls=json.loads(r.image_urls) if r.image_urls and isinstance(r.image_urls, str) else (r.image_urls or None),
        )

    @api.get("/listings/trending", response_model=list[ListingOut], tags=["listings"])
    def trending_listings(limit: int = 20, db: Session = Depends(get_db)):
        bind = {"lim": min(limit, 50)}
        rows = db.execute(text(f"""
            SELECT cl.id, cl.make, cl.model, cl.variant, cl.year, cl.price_eur, cl.mileage_km,
                   cl.fuel_type, cl.transmission, cl.body_type, cl.power_hp,
                   cl.country, cl.provider, cl.source_url, cl.image_urls,
                   s.score AS investment_score, s.tier
            FROM {SCHEMA}.car_listings cl
            JOIN {SCHEMA}.investment_scores s ON s.listing_id = cl.id
                AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM {SCHEMA}.investment_scores)
            WHERE cl.status = 'active' AND cl.price_eur > 0
            ORDER BY s.score DESC
            LIMIT :lim
        """), bind).fetchall()

        return [ListingOut(
            id=r.id, make=r.make, model=r.model, variant=r.variant or "",
            year=r.year, price_eur=float(r.price_eur) if r.price_eur else None,
            mileage_km=r.mileage_km, fuel_type=r.fuel_type or "",
            transmission=r.transmission or "", body_type=r.body_type or "",
            power_hp=r.power_hp, country=r.country or "",
            provider=r.provider or "", source_url=r.source_url or "",
            image_urls=json.loads(r.image_urls) if r.image_urls and isinstance(r.image_urls, str) else (r.image_urls or None),
            investment_score=r.investment_score, tier=r.tier,
        ) for r in rows]

    # ── Analytics ────────────────────────────────────────────────────

    @api.post("/analytics/query", response_model=AnalyticsResponse, tags=["analytics"])
    def analytics_query(body: AnalyticsRequest, user: dict = Depends(get_current_user)):
        from chat.analytics import _draft_sql, _run_sql, _guard_sql
        try:
            spec = _draft_sql(body.question)
            sql = spec.get("sql", "").strip().rstrip(";")
        except Exception as e:
            raise HTTPException(400, f"Could not generate SQL: {e}")

        try:
            df = _run_sql(sql)
        except Exception as e:
            raise HTTPException(400, f"SQL execution failed: {e}")

        data = df.head(200).to_dict(orient="records") if not df.empty else None
        return AnalyticsResponse(
            sql=sql,
            title=spec.get("title") or body.question,
            data=data,
            chart_type=spec.get("chart"),
            x_column=spec.get("x"),
            y_column=spec.get("y"),
            color_column=spec.get("color"),
            rows=len(df),
        )

    # ── Daily Scan ───────────────────────────────────────────────────

    @api.get("/daily-scan", tags=["daily-scan"])
    def daily_scan():
        from decimal import Decimal
        from utils.deals_scanner import (
            scan_price_comparisons, scan_price_drops, scan_freshness_stats,
        )

        stats = scan_freshness_stats()
        comparisons = scan_price_comparisons(limit=100)
        price_drops = scan_price_drops(limit=15)

        def _default(o):
            if isinstance(o, Decimal):
                return float(o)
            if hasattr(o, 'isoformat'):
                return o.isoformat()
            raise TypeError

        raw = json.loads(json.dumps({
            "stats": stats,
            "comparisons": comparisons,
            "price_drops": price_drops,
        }, default=_default))

        return raw

    # ── Contact ──────────────────────────────────────────────────────

    @api.post("/contact", tags=["contact"])
    def submit_contact(body: ContactRequest):
        log.info("Contact form: name=%s email=%s message=%s", body.name, body.email, body.message[:200])
        return {"ok": True, "message": "Thank you for your message. We will get back to you soon."}

    return api


def _sse_event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


# App instance for mounting in main.py
api_router = create_app()


if __name__ == "__main__":
    import uvicorn
    standalone = create_app(root_path="/api/v1")
    uvicorn.run(standalone, host="0.0.0.0", port=5012)
