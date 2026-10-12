from datetime import datetime, timezone
import sqlite3

from fastapi import APIRouter, Query

from app.database import get_conn
from app.errors import ApiError
from app.models import CandidateCreate, CandidateUpdate

router = APIRouter()

def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def candidate(conn, candidate_id):
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if not row: return None
    item = dict(row)
    item["skills"] = [r["skill"] for r in conn.execute("SELECT skill FROM candidate_skills WHERE candidate_id = ? ORDER BY skill", (candidate_id,))]
    return item

def missing(candidate_id):
    raise ApiError(404, "CANDIDATE_NOT_FOUND", f"Candidate {candidate_id} not found")

@router.post("/api/v1/candidates", status_code=201)
def create_candidate(body: CandidateCreate):
    try:
        with get_conn() as conn:
            cur = conn.execute("INSERT INTO candidates (name, email, phone, experience_years, resume_url, created_at) VALUES (?, ?, ?, ?, ?, ?)", (body.name, body.email, body.phone, body.experience_years, body.resume_url, now()))
            for skill in body.skills:
                conn.execute("INSERT INTO candidate_skills (candidate_id, skill) VALUES (?, ?)", (cur.lastrowid, skill))
            return candidate(conn, cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        if "candidates.email" in str(exc): raise ApiError(409, "EMAIL_ALREADY_EXISTS", "A candidate with this email already exists")
        raise

@router.get("/api/v1/candidates")
def list_candidates(skill: str | None = Query(default=None)):
    with get_conn() as conn:
        if skill is None:
            rows = conn.execute("SELECT id FROM candidates ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT c.id FROM candidates c JOIN candidate_skills s ON s.candidate_id = c.id WHERE lower(s.skill) = lower(?) ORDER BY c.id DESC", (skill,)).fetchall()
        return [candidate(conn, row["id"]) for row in rows]

@router.get("/api/v1/candidates/{candidate_id}")
def get_candidate(candidate_id: int):
    with get_conn() as conn:
        result = candidate(conn, candidate_id)
    return result if result else missing(candidate_id)

@router.patch("/api/v1/candidates/{candidate_id}")
def update_candidate(candidate_id: int, body: CandidateUpdate):
    updates = body.model_dump(exclude_unset=True)
    skills = updates.pop("skills", None)
    try:
        with get_conn() as conn:
            if not candidate(conn, candidate_id): missing(candidate_id)
            if updates:
                columns = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(f"UPDATE candidates SET {columns} WHERE id = ?", [*updates.values(), candidate_id])
            if "skills" in body.model_fields_set:
                conn.execute("DELETE FROM candidate_skills WHERE candidate_id = ?", (candidate_id,))
                for skill in skills or []:
                    conn.execute("INSERT INTO candidate_skills (candidate_id, skill) VALUES (?, ?)", (candidate_id, skill))
            return candidate(conn, candidate_id)
    except sqlite3.IntegrityError as exc:
        if "candidates.email" in str(exc): raise ApiError(409, "EMAIL_ALREADY_EXISTS", "A candidate with this email already exists")
        raise

@router.get("/api/v1/candidates/{candidate_id}/eligibility")
def eligibility(candidate_id: int):
    with get_conn() as conn:
        result = candidate(conn, candidate_id)
    if not result: missing(candidate_id)
    missing_items = []
    if not result["resume_url"]: missing_items.append("resume_url")
    if not result["skills"]: missing_items.append("skills")
    return {"candidate_id": candidate_id, "eligible": not missing_items, "missing": missing_items}
