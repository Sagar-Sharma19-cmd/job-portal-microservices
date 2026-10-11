import json
from datetime import datetime, timezone

from app.database import get_conn
from app.errors import ApiError

try:
    from common.service_client import (
        call_service,
        ServiceUnavailableError,
    )
except ImportError:
    call_service = None

    class ServiceUnavailableError(Exception):
        service = ""
        reason = ""


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_application(application_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM applications
            WHERE id = ?
            """,
            (application_id,),
        ).fetchone()

    return dict(row) if row else None


def update_application_status(
    application_id: int,
    new_status: str,
    reason: str | None = None,
):
    application = get_application(application_id)

    if not application:
        raise ApiError(
            404,
            "APPLICATION_NOT_FOUND",
            f"Application {application_id} not found",
        )

    current = application["status"]

    allowed = {
        "PENDING": {"SUBMITTED", "COMPENSATING"},
        "COMPENSATING": {"CANCELLED"},
        "SUBMITTED": {"SHORTLISTED", "REJECTED"},
        "SHORTLISTED": {"INTERVIEW", "REJECTED"},
        "INTERVIEW": {"OFFERED", "REJECTED"},
        "OFFERED": set(),
        "REJECTED": set(),
        "CANCELLED": set(),
    }

    if new_status not in allowed.get(current, set()):
        raise ApiError(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Cannot change status from {current} to {new_status}",
            {
                "from": current,
                "to": new_status,
            },
        )

    now = utc_now()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE applications
            SET status = ?,
                status_reason = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_status,
                reason,
                now,
                application_id,
            ),
        )

    return get_application(application_id)


def update_saga_status(saga_id: str, status: str):
    now = utc_now()

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE sagas
            SET status = ?,
                updated_at = ?
            WHERE saga_id = ?
            """,
            (
                status,
                now,
                saga_id,
            ),
        )


def log_saga_step(
    saga_id: str,
    step: str,
    status: str,
    error: str | None = None,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO saga_steps
            (saga_id, step, status, error, at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                saga_id,
                step,
                status,
                error,
                utc_now(),
            ),
        )


def get_saga_steps(saga_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT step, status, at, error
            FROM saga_steps
            WHERE saga_id = ?
            ORDER BY id
            """,
            (saga_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def notify(
    recipient_id: int,
    notification_type: str,
    message: str,
    request_id: str | None = None,
):
    payload = {
        "recipient_id": recipient_id,
        "type": notification_type,
        "message": message,
    }

    try:
        response = call_service(
            "notification-service",
            "POST",
            "/api/v1/notifications",
            json=payload,
            request_id=request_id,
        )

        if 200 <= response.status_code < 300:
            return

    except ServiceUnavailableError:
        pass

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pending_notifications
            (payload, attempts, created_at)
            VALUES (?, 0, ?)
            """,
            (
                json.dumps(payload),
                utc_now(),
            ),
        )


def retry_notifications(request_id: str | None = None):
    sent = 0

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM pending_notifications
            ORDER BY id
            """
        ).fetchall()

    for row in rows:
        payload = json.loads(row["payload"])

        try:
            response = call_service(
                "notification-service",
                "POST",
                "/api/v1/notifications",
                json=payload,
                request_id=request_id,
            )

            if not 200 <= response.status_code < 300:
                raise RuntimeError("Notification request failed")

        except Exception:
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE pending_notifications
                    SET attempts = attempts + 1
                    WHERE id = ?
                    """,
                    (row["id"],),
                )

            continue

        with get_conn() as conn:
            conn.execute(
                """
                DELETE FROM pending_notifications
                WHERE id = ?
                """,
                (row["id"],),
            )

        sent += 1

    with get_conn() as conn:
        remaining = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM pending_notifications
            """
        ).fetchone()["count"]

    return {
        "sent": sent,
        "still_pending": remaining,
    }


def create_application_record(
    candidate_id: int,
    job_id: int,
):
    now = utc_now()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO applications
            (
                candidate_id,
                job_id,
                status,
                status_reason,
                saga_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, 'PENDING', NULL, NULL, ?, ?)
            """,
            (
                candidate_id,
                job_id,
                now,
                now,
            ),
        )

        application_id = cursor.lastrowid
        saga_id = f"saga-{application_id}"

        conn.execute(
            """
            UPDATE applications
            SET saga_id = ?
            WHERE id = ?
            """,
            (
                saga_id,
                application_id,
            ),
        )

        conn.execute(
            """
            INSERT INTO sagas
            (
                saga_id,
                application_id,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, 'STARTED', ?, ?)
            """,
            (
                saga_id,
                application_id,
                now,
                now,
            ),
        )

    return application_id, saga_id


def duplicate_check(
    candidate_id: int,
    job_id: int,
):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM applications
            WHERE candidate_id = ?
              AND job_id = ?
              AND status != 'CANCELLED'
            LIMIT 1
            """,
            (
                candidate_id,
                job_id,
            ),
        ).fetchone()

    return row


def compensate(
    application_id: int,
    candidate_id: int,
    job_id: int,
    saga_id: str,
    error_code: str,
    request_id: str | None,
    screening_done: bool,
    reservation_done: bool,
):
    update_application_status(
        application_id,
        "COMPENSATING",
        error_code,
    )

    update_saga_status(
        saga_id,
        "COMPENSATING",
    )

    try:
        if screening_done:
            call_service(
                "recruitment-service",
                "DELETE",
                f"/api/v1/screenings/{application_id}",
                request_id=request_id,
            )

            log_saga_step(
                saga_id,
                "CANCEL_SCREENING",
                "DONE",
            )

        if reservation_done:
            call_service(
                "job-service",
                "DELETE",
                f"/api/v1/jobs/{job_id}/reservations/{application_id}",
                request_id=request_id,
            )

            log_saga_step(
                saga_id,
                "RELEASE_JOB_SLOT",
                "DONE",
            )

    except ServiceUnavailableError as exc:
        log_saga_step(
            saga_id,
            "COMPENSATION_FAILED",
            "FAILED",
            f"{exc.service}: {exc.reason}",
        )

        update_saga_status(
            saga_id,
            "FAILED",
        )

        update_application_status(
            application_id,
            "CANCELLED",
            error_code,
        )

        notify(
            candidate_id,
            "APPLICATION_CANCELLED",
            f"Application {application_id} was cancelled.",
            request_id,
        )

        raise ApiError(
            503,
            error_code,
            "Saga compensation failed",
            {
                "application_id": application_id,
                "saga_id": saga_id,
                "status": "CANCELLED",
            },
        )

    update_application_status(
        application_id,
        "CANCELLED",
        error_code,
    )

    log_saga_step(
        saga_id,
        "CANCEL_APPLICATION",
        "DONE",
        error_code,
    )

    update_saga_status(
        saga_id,
        "COMPENSATED",
    )

    notify(
        candidate_id,
        "APPLICATION_CANCELLED",
        f"Application {application_id} was cancelled.",
        request_id,
    )

    raise ApiError(
        409 if error_code in {
            "CANDIDATE_NOT_ELIGIBLE",
            "JOB_FULL",
            "JOB_CLOSED",
        } else 503 if error_code in {
            "CANDIDATE_SERVICE_UNAVAILABLE",
            "JOB_SERVICE_UNAVAILABLE",
            "RECRUITMENT_SERVICE_UNAVAILABLE",
        } else 404,
        error_code,
        f"Application saga failed: {error_code}",
        {
            "application_id": application_id,
            "saga_id": saga_id,
            "status": "CANCELLED",
        },
    )


def run_apply_saga(
    candidate_id: int,
    job_id: int,
    request_id: str | None = None,
):
    duplicate = duplicate_check(
        candidate_id,
        job_id,
    )

    if duplicate:
        raise ApiError(
            409,
            "DUPLICATE_APPLICATION",
            "Candidate already has an application for this job",
        )

    application_id, saga_id = create_application_record(
        candidate_id,
        job_id,
    )

    log_saga_step(
        saga_id,
        "CREATE_APPLICATION",
        "DONE",
    )

    reservation_done = False
    screening_done = False

    # Step 2: Candidate eligibility
    try:
        response = call_service(
            "candidate-service",
            "GET",
            f"/api/v1/candidates/{candidate_id}/eligibility",
            request_id=request_id,
        )

    except ServiceUnavailableError as exc:
        error_code = "CANDIDATE_SERVICE_UNAVAILABLE"

        log_saga_step(
            saga_id,
            "CHECK_CANDIDATE",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    if response.status_code == 404:
        error_code = "CANDIDATE_NOT_FOUND"

        log_saga_step(
            saga_id,
            "CHECK_CANDIDATE",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    if response.status_code >= 500:
        error_code = "CANDIDATE_SERVICE_UNAVAILABLE"

        log_saga_step(
            saga_id,
            "CHECK_CANDIDATE",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    candidate_data = response.json()

    if not candidate_data.get("eligible", False):
        error_code = "CANDIDATE_NOT_ELIGIBLE"

        log_saga_step(
            saga_id,
            "CHECK_CANDIDATE",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    log_saga_step(
        saga_id,
        "CHECK_CANDIDATE",
        "DONE",
    )

    # Step 3: Reserve job slot
    try:
        response = call_service(
            "job-service",
            "POST",
            f"/api/v1/jobs/{job_id}/reservations",
            json={
                "application_id": application_id,
            },
            request_id=request_id,
        )

    except ServiceUnavailableError:
        error_code = "JOB_SERVICE_UNAVAILABLE"

        log_saga_step(
            saga_id,
            "RESERVE_JOB_SLOT",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    if response.status_code == 404:
        error_code = "JOB_NOT_FOUND"

    elif response.status_code == 409:
        try:
            error_code = response.json()["error"]["code"]
        except Exception:
            error_code = "JOB_FULL"

    elif response.status_code >= 500:
        error_code = "JOB_SERVICE_UNAVAILABLE"

    else:
        error_code = None

    if error_code:
        log_saga_step(
            saga_id,
            "RESERVE_JOB_SLOT",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    reservation_done = True

    log_saga_step(
        saga_id,
        "RESERVE_JOB_SLOT",
        "DONE",
    )

    # Step 4: Create screening
    try:
        response = call_service(
            "recruitment-service",
            "POST",
            "/api/v1/screenings",
            json={
                "application_id": application_id,
                "job_id": job_id,
                "candidate_id": candidate_id,
            },
            request_id=request_id,
        )

    except ServiceUnavailableError:
        error_code = "RECRUITMENT_SERVICE_UNAVAILABLE"

        log_saga_step(
            saga_id,
            "CREATE_SCREENING",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    if not 200 <= response.status_code < 300:
        error_code = "BAD_UPSTREAM_RESPONSE"

        log_saga_step(
            saga_id,
            "CREATE_SCREENING",
            "FAILED",
            error_code,
        )

        compensate(
            application_id,
            candidate_id,
            job_id,
            saga_id,
            error_code,
            request_id,
            screening_done,
            reservation_done,
        )

    screening_done = True

    log_saga_step(
        saga_id,
        "CREATE_SCREENING",
        "DONE",
    )

    # Step 5: Saga successful
    update_application_status(
        application_id,
        "SUBMITTED",
    )

    update_saga_status(
        saga_id,
        "COMPLETED",
    )

    application = get_application(application_id)

    notify(
        candidate_id,
        "APPLICATION_SUBMITTED",
        f"Application {application_id} was submitted successfully.",
        request_id,
    )

    return application