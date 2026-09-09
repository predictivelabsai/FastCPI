"""Admin routes: dashboard, invite management, user management."""

from __future__ import annotations

import logging
from datetime import datetime

from fasthtml.common import (
    Html, Head, Body, Div, H1, H2, H3, P, A, Button, Form, Input, Label,
    Table, Thead, Tbody, Tr, Th, Td, Span, Script, Style, NotStr, Textarea,
)
from starlette.responses import RedirectResponse, JSONResponse

from auth.utils import hash_password, generate_token, send_invite_email
from chat.layout import _head
from utils.session import get_user_email, get_user_id

log = logging.getLogger(__name__)

SCHEMA = "carhero"


def _get_db():
    from db import SessionLocal
    return SessionLocal()


def _require_admin(sess):
    from sqlalchemy import text
    uid = get_user_id(sess)
    if not uid:
        return None, RedirectResponse("/app", status_code=303)
    db = _get_db()
    try:
        row = db.execute(
            text(f"SELECT role FROM {SCHEMA}.chat_users WHERE id = :id"),
            {"id": uid},
        ).fetchone()
    finally:
        db.close()
    if not row or row.role != "admin":
        return None, RedirectResponse("/app", status_code=303)
    return uid, None


ADMIN_CSS = """
.admin-wrap { max-width:900px; margin:0 auto; padding:32px 24px; }
.admin-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:32px; }
.admin-header h1 { font-family:'DM Serif Display',Georgia,serif; font-size:28px; color:#1A1A1A; margin:0; }
.admin-card { background:#fff; border:1px solid #E5E5E5; border-radius:8px; padding:24px; margin-bottom:24px; }
.admin-card h2 { font-size:16px; font-weight:600; margin:0 0 16px; color:#1A1A1A; }
.admin-table { width:100%; border-collapse:collapse; font-size:13px; }
.admin-table th { text-align:left; padding:8px 12px; border-bottom:2px solid #E5E5E5; color:#6B7280; font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; }
.admin-table td { padding:8px 12px; border-bottom:1px solid #F3F4F6; color:#374151; }
.admin-table tr:hover td { background:#F9FAFB; }
.badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:500; }
.badge-pending { background:#FEF3C7; color:#92400E; }
.badge-accepted { background:#D1FAE5; color:#065F46; }
.badge-expired { background:#FEE2E2; color:#991B1B; }
.badge-admin { background:#1A1A1A; color:#fff; }
.badge-user { background:#F3F4F6; color:#374151; }
.invite-form { display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; }
.invite-form .field { display:flex; flex-direction:column; gap:4px; }
.invite-form .field label { font-size:11px; color:#6B7280; font-weight:500; text-transform:uppercase; letter-spacing:0.3px; }
.invite-form input, .invite-form textarea, .invite-form select { padding:8px 12px; border:1px solid #E5E5E5; border-radius:6px; font-size:13px; font-family:inherit; }
.invite-form textarea { resize:vertical; min-height:60px; }
.btn-primary { padding:8px 20px; background:#1A1A1A; color:#fff; border:none; border-radius:6px; font-size:13px; font-weight:500; cursor:pointer; }
.btn-primary:hover { background:#333; }
.stat-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px,1fr)); gap:16px; margin-bottom:24px; }
.stat-box { background:#fff; border:1px solid #E5E5E5; border-radius:8px; padding:16px; text-align:center; }
.stat-box .num { font-size:28px; font-weight:700; color:#1A1A1A; }
.stat-box .label { font-size:11px; color:#6B7280; text-transform:uppercase; letter-spacing:0.5px; margin-top:4px; }
.msg-ok { color:#16A34A; font-size:13px; margin-left:12px; }
.msg-err { color:#DC2626; font-size:13px; margin-left:12px; }
"""


def register_admin_routes(rt):

    @rt("/admin")
    def admin_dashboard(sess):
        from sqlalchemy import text
        uid, redirect = _require_admin(sess)
        if redirect:
            return redirect

        db = _get_db()
        try:
            total_users = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.chat_users WHERE id > 0")).scalar()
            admin_count = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.chat_users WHERE role = 'admin'")).scalar()
            pending_invites = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.invitations WHERE status = 'pending'")).scalar()
            accepted_invites = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.invitations WHERE status = 'accepted'")).scalar()

            invites = db.execute(text(f"""
                SELECT i.*, u.name AS inviter_name
                FROM {SCHEMA}.invitations i
                LEFT JOIN {SCHEMA}.chat_users u ON u.id = i.invited_by
                ORDER BY i.created_at DESC
                LIMIT 50
            """)).fetchall()

            users = db.execute(text(f"""
                SELECT id, email, name, role, is_verified, created_at
                FROM {SCHEMA}.chat_users
                WHERE id > 0
                ORDER BY created_at DESC
                LIMIT 50
            """)).fetchall()
        finally:
            db.close()

        def _badge(status):
            cls = {"pending": "badge-pending", "accepted": "badge-accepted", "expired": "badge-expired"}.get(status, "badge-pending")
            return Span(status, cls=f"badge {cls}")

        def _role_badge(role):
            cls = "badge-admin" if role == "admin" else "badge-user"
            return Span(role or "user", cls=f"badge {cls}")

        invite_rows = []
        for inv in invites:
            invite_rows.append(Tr(
                Td(inv.email),
                Td(inv.inviter_name or "—"),
                Td(_badge(inv.status)),
                Td(inv.role or "user"),
                Td(str(inv.created_at.strftime("%Y-%m-%d %H:%M")) if inv.created_at else "—"),
            ))

        user_rows = []
        for u in users:
            user_rows.append(Tr(
                Td(u.email),
                Td(u.name or "—"),
                Td(_role_badge(u.role)),
                Td("Yes" if u.is_verified else "No"),
                Td(str(u.created_at.strftime("%Y-%m-%d")) if u.created_at else "—"),
            ))

        return Html(_head("Admin — CarHero"), Body(
            Style(NotStr(ADMIN_CSS)),
            Div(
                Div(
                    H1("CarHero Admin"),
                    A("< Back to app", href="/app", cls="text-sm text-gray-500 no-underline hover:text-black"),
                    cls="admin-header",
                ),

                Div(
                    Div(Div(str(total_users), cls="num"), Div("Total Users", cls="label"), cls="stat-box"),
                    Div(Div(str(admin_count), cls="num"), Div("Admins", cls="label"), cls="stat-box"),
                    Div(Div(str(pending_invites), cls="num"), Div("Pending Invites", cls="label"), cls="stat-box"),
                    Div(Div(str(accepted_invites), cls="num"), Div("Accepted", cls="label"), cls="stat-box"),
                    cls="stat-grid",
                ),

                # Invite form
                Div(
                    H2("Send Invitation"),
                    Form(
                        Div(
                            Div(Label("Email address"), Input(type="email", name="email", placeholder="user@example.com", required=True), cls="field"),
                            Div(Label("Role"), NotStr('<select name="role" style="padding:8px 12px;border:1px solid #E5E5E5;border-radius:6px;font-size:13px;"><option value="user">User</option><option value="admin">Admin</option></select>'), cls="field"),
                            cls="invite-form",
                            style="margin-bottom:12px;",
                        ),
                        Div(
                            Div(Label("Personal message (optional)"), Textarea(name="message", placeholder="Add a welcome note...", rows="2"), cls="field", style="flex:1;"),
                            cls="invite-form",
                            style="margin-bottom:16px;",
                        ),
                        Div(
                            Button("Send Invite", type="submit", cls="btn-primary"),
                            Span(id="invite-msg"),
                            cls="flex items-center",
                        ),
                        id="invite-form",
                        onsubmit="return sendInvite(event)",
                    ),
                    cls="admin-card",
                ),

                # Invitations table
                Div(
                    H2("Invitations"),
                    Table(
                        Thead(Tr(Th("Email"), Th("Invited By"), Th("Status"), Th("Role"), Th("Date"))),
                        Tbody(*invite_rows) if invite_rows else Tbody(Tr(Td("No invitations yet", colspan="5", style="text-align:center;color:#9CA3AF;padding:24px;"))),
                        cls="admin-table",
                    ),
                    cls="admin-card",
                ),

                # Users table
                Div(
                    H2("Users"),
                    Table(
                        Thead(Tr(Th("Email"), Th("Name"), Th("Role"), Th("Verified"), Th("Joined"))),
                        Tbody(*user_rows) if user_rows else Tbody(Tr(Td("No users yet", colspan="5", style="text-align:center;color:#9CA3AF;padding:24px;"))),
                        cls="admin-table",
                    ),
                    cls="admin-card",
                ),

                cls="admin-wrap",
            ),
            Script(NotStr("""
async function sendInvite(e) {
    e.preventDefault();
    var form = document.getElementById('invite-form');
    var msg = document.getElementById('invite-msg');
    msg.className = ''; msg.textContent = 'Sending...';
    try {
        var resp = await fetch('/admin/invite', { method:'POST', body: new FormData(form) });
        var data = await resp.json();
        if (data.ok) {
            msg.className = 'msg-ok';
            msg.textContent = 'Invitation sent!';
            form.reset();
            setTimeout(function(){ location.reload(); }, 1500);
        } else {
            msg.className = 'msg-err';
            msg.textContent = data.error || 'Failed to send';
        }
    } catch(err) {
        msg.className = 'msg-err';
        msg.textContent = 'Network error';
    }
    setTimeout(function(){ msg.textContent = ''; }, 5000);
    return false;
}
""")),
            cls="bg-gray-50 font-sans min-h-screen",
        ))

    @rt("/admin/invite", methods=["POST"])
    async def admin_send_invite(request, sess):
        from sqlalchemy import text
        uid, redirect = _require_admin(sess)
        if redirect:
            return JSONResponse({"error": "Unauthorized"}, status_code=403)

        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        role = form.get("role") or "user"
        message = (form.get("message") or "").strip()

        if not email:
            return JSONResponse({"error": "Email is required"}, status_code=400)
        if role not in ("user", "admin"):
            return JSONResponse({"error": "Invalid role"}, status_code=400)

        db = _get_db()
        try:
            existing_user = db.execute(
                text(f"SELECT id FROM {SCHEMA}.chat_users WHERE email = :email"),
                {"email": email},
            ).fetchone()
            if existing_user:
                return JSONResponse({"error": "This user already has an account"}, status_code=409)

            existing_invite = db.execute(
                text(f"SELECT id FROM {SCHEMA}.invitations WHERE email = :email AND status = 'pending'"),
                {"email": email},
            ).fetchone()
            if existing_invite:
                return JSONResponse({"error": "An invitation is already pending for this email"}, status_code=409)

            token = generate_token()

            inviter = db.execute(
                text(f"SELECT name FROM {SCHEMA}.chat_users WHERE id = :id"),
                {"id": uid},
            ).fetchone()
            inviter_name = inviter.name if inviter and inviter.name else ""

            db.execute(text(f"""
                INSERT INTO {SCHEMA}.invitations (email, token, invited_by, role, message, status)
                VALUES (:email, :token, :uid, :role, :msg, 'pending')
            """), {
                "email": email, "token": token, "uid": uid,
                "role": role, "msg": message or None,
            })
            db.commit()
        finally:
            db.close()

        send_invite_email(email, token, inviter_name, message)
        log.info(f"Invite sent to {email} by user {uid}")
        return JSONResponse({"ok": True})

    @rt("/auth/invite/{token}")
    def accept_invite_page(token: str):
        from sqlalchemy import text
        db = _get_db()
        try:
            inv = db.execute(
                text(f"SELECT * FROM {SCHEMA}.invitations WHERE token = :token AND status = 'pending'"),
                {"token": token},
            ).fetchone()
        finally:
            db.close()

        if not inv:
            return Html(_head("Invitation"), Body(
                Div(H2("Invalid invitation"),
                    P("This invitation link is no longer valid. Please ask for a new one."),
                    A("Go to CarHero", href="/app", cls="text-black font-semibold"),
                    cls="max-w-md mx-auto mt-20 text-center"),
                cls="bg-white font-sans min-h-screen",
            ))

        inp = "w-full px-3 py-2 border border-gray-200 rounded-md text-sm"
        return Html(_head("Join CarHero"), Body(
            Div(
                Div(
                    NotStr('<span style="font-family:\'DM Serif Display\',Georgia,serif;font-size:22px;font-weight:700;color:#1A1A1A;">CarHero</span>'),
                    style="margin-bottom:20px;",
                ),
                H2("Create your account", cls="text-xl font-bold mb-2"),
                P(f"You've been invited to join CarHero.", cls="text-gray-500 text-sm mb-4"),
                Form(
                    Input(type="hidden", name="token", value=token),
                    Div(
                        Label("Email", cls="text-xs text-gray-500 block mb-1"),
                        Input(type="email", value=inv.email, disabled=True, cls=f"{inp} bg-gray-50"),
                        cls="mb-3",
                    ),
                    Div(
                        Label("Your name", cls="text-xs text-gray-500 block mb-1"),
                        Input(type="text", name="name", placeholder="Your name", cls=inp, required=True),
                        cls="mb-3",
                    ),
                    Div(
                        Label("Password", cls="text-xs text-gray-500 block mb-1"),
                        Input(type="password", name="password", placeholder="Min 6 characters", cls=inp, required=True),
                        cls="mb-3",
                    ),
                    Div(
                        Label("Confirm password", cls="text-xs text-gray-500 block mb-1"),
                        Input(type="password", name="password_confirm", placeholder="Confirm password", cls=inp, required=True),
                        cls="mb-4",
                    ),
                    Button("Join CarHero", type="submit",
                           cls="w-full py-2 bg-black text-white rounded-md text-sm cursor-pointer border-none font-semibold"),
                    Div(id="invite-error", cls="text-red-500 text-sm mt-2"),
                    method="POST",
                    action=f"/auth/invite/{token}/accept",
                ),
                cls="max-w-sm mx-auto mt-16 p-6 bg-white rounded-lg border border-gray-200",
            ),
            cls="bg-gray-50 font-sans min-h-screen",
        ))

    @rt("/auth/invite/{token}/accept", methods=["POST"])
    async def accept_invite(token: str, request, sess):
        from sqlalchemy import text
        form = await request.form()
        name = (form.get("name") or "").strip()
        password = form.get("password") or ""
        password_confirm = form.get("password_confirm") or ""

        if len(password) < 6:
            return RedirectResponse(f"/auth/invite/{token}", status_code=303)
        if password != password_confirm:
            return RedirectResponse(f"/auth/invite/{token}", status_code=303)

        db = _get_db()
        try:
            inv = db.execute(
                text(f"SELECT * FROM {SCHEMA}.invitations WHERE token = :token AND status = 'pending'"),
                {"token": token},
            ).fetchone()

            if not inv:
                return RedirectResponse("/app", status_code=303)

            pw_hash = hash_password(password)
            result = db.execute(text(f"""
                INSERT INTO {SCHEMA}.chat_users (email, password_hash, name, is_verified, role)
                VALUES (:email, :pw, :name, TRUE, :role)
                RETURNING id
            """), {"email": inv.email, "pw": pw_hash, "name": name, "role": inv.role or "user"})
            user_id = result.fetchone().id

            db.execute(text(f"""
                UPDATE {SCHEMA}.invitations
                SET status = 'accepted', accepted_at = NOW()
                WHERE id = :id
            """), {"id": inv.id})
            db.commit()

            from utils.session import set_user_email, set_user_id
            set_user_email(sess, inv.email)
            set_user_id(sess, user_id)
        finally:
            db.close()

        return RedirectResponse("/app", status_code=303)
