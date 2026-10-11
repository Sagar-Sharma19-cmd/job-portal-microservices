from fastapi import APIRouter, Query, Request

from app.database import get_conn
from app.errors import ApiError
from app.saga import (
    get_application,
    get_saga_steps,
    notify,
    retry_notifications,
    run_apply_saga,
    update_application_status,
)
from app.models import (
    ApplicationCreate,
    ApplicationStatusUpdate,
)


router = APIRouter()


@router.post("/api/v1/applications", status_code=201)
def create_application(
    body: ApplicationCreate,
    request: Request,
):
    return run_apply_saga(
        candidate_id=body.candidate_id,
        job_id=body.job_id,
        request_id=request.state.request_id,
    )


@router.get("/api/v1/applications/{application_id}")
def get_application_by_id(application_id: int):
    application = get_application(application_id)

    if not application:
        raise ApiError(
            404,
            "APPLICATION_NOT_FOUND",
            f"Application {application_id} not found",
        )

    return application


@router.get("/api/v1/applications")
def list_applications(
    candidate_id: int | None = Query(default=None),
    job_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
):
    query = """
        SELECT *
        FROM applications
        WHERE 1 = 1
    """

    params = []

    if candidate_id is not None:
        query += " AND candidate_id = ?"
        params.append(candidate_id)

    if job_id is not None:
        query += " AND job_id = ?"
        params.append(job_id)

    if status is not None:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY id DESC"

    with get_conn() as conn:
        rows = conn.execute(
            query,
            params,
        ).fetchall()

    return [dict(row) for row in rows]


@router.patch("/api/v1/applications/{application_id}/status")
def change_application_status(
    application_id: int,
    body: ApplicationStatusUpdate,
    request: Request,
):
    application = update_application_status(
        application_id,
        body.status,
        body.reason,
    )

    notify(
        application["candidate_id"],
        "STATUS_CHANGED",
        (
            f"Application {application_id} status changed "
            f"to {body.status}."
        ),
        request.state.request_id,
    )

    return application


@router.get("/api/v1/sagas/{saga_id}")
def get_saga(saga_id: str):
    with get_conn() as conn:
        saga = conn.execute(
            """
            SELECT saga_id, application_id, status
            FROM sagas
            WHERE saga_id = ?
            """,
            (saga_id,),
        ).fetchone()

    if not saga:
        raise ApiError(
            404,
            "SAGA_NOT_FOUND",
            f"Saga {saga_id} not found",
        )

    return {
        "saga_id": saga["saga_id"],
        "application_id": saga["application_id"],
        "status": saga["status"],
        "steps": get_saga_steps(saga_id),
    }


@router.get("/internal/circuits")
def circuits():
    try:
        from common.service_client import get_circuit_states

        return get_circuit_states()
    except ImportError:
        return {}


@router.post("/internal/notifications/retry")
def retry_pending_notifications(request: Request):
    return retry_notifications(
        request.state.request_id,
    )