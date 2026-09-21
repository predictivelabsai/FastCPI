"""Admin queue-health, usage and dead-letter operations."""

from __future__ import annotations

from fasthtml.common import A, Body, Button, Div, H1, H2, Html, P, Script, Span, Style, Table, Tbody, Td, Th, Thead, Tr, NotStr
from starlette.responses import JSONResponse

from admin.routes import ADMIN_CSS, _get_db, _require_admin
from chat.layout import _head
from monitoring.operations import operations_snapshot, replay_dead_letter


def _time(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "—"


def register_operations_routes(rt):
    @rt("/admin/operations")
    def operations_dashboard(sess):
        _uid, redirect = _require_admin(sess)
        if redirect:
            return redirect
        db = _get_db()
        try:
            snapshot = operations_snapshot(db)
        finally:
            db.close()
        worker = snapshot["worker"]
        rows = [
            Tr(
                Td(row["job_type"]), Td(row["label"]), Td(row["email"]),
                Td(P(row["error_code"] or "Unknown"),
                   P((row["error_message"] or "")[:160], cls="text-xs text-gray-500")),
                Td(f"{row['attempt_count']}/{row['max_attempts']}"), Td(_time(row["completed_at"])),
                Td(Button(
                    "Replay", type="button", cls="btn-primary",
                    onclick=f"replayJob('{row['job_type']}','{row['id']}',this)",
                )),
            ) for row in snapshot["dead_letters"]
        ]
        usage_rows = [
            Tr(Td(row["operation"]), Td(row["status"]), Td(str(row["entries"])), Td(str(row["units"])))
            for row in snapshot["usage"]
        ]
        action_rows = [
            Tr(Td(row["action"]), Td(row["job_type"]), Td(str(row["job_id"])),
               Td(row["actor_email"] or "system"), Td(_time(row["created_at"])))
            for row in snapshot["actions"]
        ]
        alerts = worker.get("alerts", [])
        return Html(_head("Operations — FastCPI"), Body(
            Style(NotStr(ADMIN_CSS + """
                .ops-alert { color:#991B1B;background:#FEE2E2;padding:8px 12px;border-radius:6px; }
                .ops-ok { color:#065F46;background:#D1FAE5;padding:8px 12px;border-radius:6px; }
                .admin-table td { vertical-align:top; }
            """)),
            Div(
                Div(H1("FastCPI Operations"), Div(
                    A("Admin", href="/admin", cls="text-sm text-gray-500 no-underline"),
                    Span(" · "), A("Back to app", href="/app", cls="text-sm text-gray-500 no-underline"),
                ), cls="admin-header"),
                Div(
                    Div(Div(str(worker.get("queue_depth", 0)), cls="num"), Div("Queue depth", cls="label"), cls="stat-box"),
                    Div(Div(str(worker.get("running_jobs", 0)), cls="num"), Div("Running", cls="label"), cls="stat-box"),
                    Div(Div(str(worker.get("stalled_jobs", 0)), cls="num"), Div("Stalled leases", cls="label"), cls="stat-box"),
                    Div(Div(str(worker.get("dead_letters", 0)), cls="num"), Div("Dead letters", cls="label"), cls="stat-box"),
                    cls="stat-grid",
                ),
                P(
                    "Worker ready" if worker.get("ready") else "Worker unavailable",
                    " · ", f"oldest queued {worker.get('oldest_queue_age_seconds', 0)}s",
                    " · ", ("alerts: " + ", ".join(alerts)) if alerts else "no active queue alerts",
                    cls="ops-alert" if alerts or not worker.get("ready") else "ops-ok",
                ),
                Div(H2("Dead-letter jobs"),
                    Table(Thead(Tr(Th("Type"), Th("Work"), Th("Owner"), Th("Error"),
                                          Th("Attempts"), Th("Completed"), Th("Action"))),
                          Tbody(*rows) if rows else Tbody(Tr(Td("No failed jobs", colspan="7"))),
                          cls="admin-table"), cls="admin-card"),
                Div(H2("Paid usage · last 24 hours"),
                    Table(Thead(Tr(Th("Operation"), Th("Status"), Th("Entries"), Th("Units"))),
                          Tbody(*usage_rows) if usage_rows else Tbody(Tr(Td("No paid usage", colspan="4"))),
                          cls="admin-table"), cls="admin-card"),
                Div(H2("Operations audit"),
                    Table(Thead(Tr(Th("Action"), Th("Type"), Th("Job"), Th("Actor"), Th("Time"))),
                          Tbody(*action_rows) if action_rows else Tbody(Tr(Td("No operator actions", colspan="5"))),
                          cls="admin-table"), cls="admin-card"),
                cls="admin-wrap",
            ),
            Script(NotStr("""
                async function replayJob(kind,id,button) {
                  button.disabled=true; button.textContent='Replaying…';
                  const response=await fetch(`/admin/operations/${kind}/${id}/replay`,{method:'POST'});
                  const body=await response.json();
                  if(response.ok){ location.reload(); return; }
                  button.disabled=false; button.textContent=body.error||'Retry failed';
                }
            """)),
            cls="bg-gray-50 font-sans min-h-screen",
        ))

    @rt("/admin/operations/{job_type}/{job_id}/replay", methods=["POST"])
    def replay_job(job_type: str, job_id: str, sess):
        uid, redirect = _require_admin(sess)
        if redirect:
            return JSONResponse({"error": "Unauthorized"}, status_code=403)
        db = _get_db()
        try:
            try:
                result = replay_dead_letter(
                    db, actor_user_id=uid, job_type=job_type, job_id=job_id,
                )
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=422)
        finally:
            db.close()
        if not result:
            return JSONResponse({"error": "Failed job not found or already replayed"}, status_code=409)
        return JSONResponse({"ok": True, **result})
