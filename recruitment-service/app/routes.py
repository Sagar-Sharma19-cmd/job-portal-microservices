from datetime import datetime, timezone
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from app.database import get_conn
from app.errors import ApiError
from app.models import DecisionCreate, InterviewCreate, InterviewUpdate, ScreeningCreate
router = APIRouter()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def screening(conn, screening_id):
    row = conn.execute("SELECT * FROM screenings WHERE id = ?", (screening_id,)).fetchone()
    if not row: return None
    result = dict(row); result["interviews"] = [dict(x) for x in conn.execute("SELECT id, round, scheduled_at, result, feedback, created_at FROM interviews WHERE screening_id = ? ORDER BY round", (screening_id,))]
    result.pop("updated_at", None); return result
def require_screening(conn, screening_id):
    result = screening(conn, screening_id)
    if not result: raise ApiError(404, "SCREENING_NOT_FOUND", f"Screening {screening_id} not found")
    return result
@router.post("/api/v1/screenings", status_code=201)
def create_screening(body: ScreeningCreate):
    with get_conn() as conn:
        existing = conn.execute("SELECT id, status FROM screenings WHERE application_id = ?", (body.application_id,)).fetchone()
        if existing:
            if existing["status"] == "CANCELLED": conn.execute("UPDATE screenings SET status = 'ACTIVE', updated_at = ? WHERE id = ?", (now(), existing["id"]))
            result = screening(conn, existing["id"]); return JSONResponse(status_code=200, content=result)
        stamp = now(); cur = conn.execute("INSERT INTO screenings (application_id, job_id, candidate_id, status, created_at, updated_at) VALUES (?, ?, ?, 'ACTIVE', ?, ?)", (body.application_id, body.job_id, body.candidate_id, stamp, stamp))
        return screening(conn, cur.lastrowid)
@router.delete("/api/v1/screenings/{application_id}", status_code=204)
def cancel_screening(application_id: int):
    with get_conn() as conn: conn.execute("UPDATE screenings SET status = 'CANCELLED', updated_at = ? WHERE application_id = ?", (now(), application_id))
@router.get("/api/v1/screenings/{screening_id}")
def get_screening(screening_id: int):
    with get_conn() as conn: return require_screening(conn, screening_id)
@router.get("/api/v1/screenings")
def list_screenings(job_id: int | None = Query(default=None), status: str | None = Query(default=None)):
    query, params = "SELECT id FROM screenings WHERE 1=1", []
    if job_id is not None: query += " AND job_id = ?"; params.append(job_id)
    if status is not None: query += " AND status = ?"; params.append(status)
    query += " ORDER BY id DESC"
    with get_conn() as conn: return [screening(conn, row["id"]) for row in conn.execute(query, params)]
@router.post("/api/v1/screenings/{screening_id}/interviews", status_code=201)
def create_interview(screening_id: int, body: InterviewCreate):
    with get_conn() as conn:
        item = require_screening(conn, screening_id)
        if item["status"] != "ACTIVE": raise ApiError(409, "SCREENING_NOT_ACTIVE", "Screening is not active")
        cur = conn.execute("INSERT INTO interviews (screening_id, round, scheduled_at, result, feedback, created_at) VALUES (?, ?, ?, NULL, NULL, ?)", (screening_id, body.round, body.scheduled_at, now()))
        return dict(conn.execute("SELECT id, round, scheduled_at, result, feedback, created_at FROM interviews WHERE id = ?", (cur.lastrowid,)).fetchone())
@router.patch("/api/v1/interviews/{interview_id}")
def update_interview(interview_id: int, body: InterviewUpdate):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        if not row: raise ApiError(404, "INTERVIEW_NOT_FOUND", f"Interview {interview_id} not found")
        conn.execute("UPDATE interviews SET result = ?, feedback = ? WHERE id = ?", (body.result, body.feedback, interview_id))
        return dict(conn.execute("SELECT id, round, scheduled_at, result, feedback, created_at FROM interviews WHERE id = ?", (interview_id,)).fetchone())
@router.post("/api/v1/screenings/{screening_id}/decision")
def decision(screening_id: int, body: DecisionCreate, request: Request):
    with get_conn() as conn: item = require_screening(conn, screening_id)
    if item["status"] != "ACTIVE": raise ApiError(409, "SCREENING_NOT_ACTIVE", "Screening is not active")
    try:
        from common.service_client import ServiceUnavailableError, call_service
        response = call_service("application-service", "PATCH", f"/api/v1/applications/{item['application_id']}/status", json={"status": body.decision, "reason": body.reason}, request_id=request.state.request_id)
    except ImportError:
        raise ApiError(503, "APPLICATION_SERVICE_UNAVAILABLE", "Application Service is unavailable", {"reason": "DOWN"})
    except ServiceUnavailableError as exc:
        raise ApiError(503, "APPLICATION_SERVICE_UNAVAILABLE", "Application Service is unavailable", {"reason": exc.reason})
    if response.status_code == 409:
        payload = response.json().get("error", {}); raise ApiError(409, payload.get("code", "INVALID_STATUS_TRANSITION"), payload.get("message", "Invalid status transition"), payload.get("details", {}))
    if response.status_code != 200: raise ApiError(response.status_code, "APPLICATION_UPDATE_FAILED", "Application status could not be updated")
    application = response.json()
    if body.decision in {"OFFERED", "REJECTED"}:
        with get_conn() as conn: conn.execute("UPDATE screenings SET status = 'CLOSED', updated_at = ? WHERE id = ?", (now(), screening_id))
    return {"screening_id": screening_id, "application_id": item["application_id"], "decision": body.decision, "application_status": application.get("status", body.decision)}
@router.get("/internal/circuits")
def circuits():
    try:
        from common.service_client import get_circuit_states
        return get_circuit_states()
    except ImportError: return {}
