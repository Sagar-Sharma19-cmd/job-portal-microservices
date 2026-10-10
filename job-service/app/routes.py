from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from .database import get_conn
from .errors import ApiError
from .models import (
    EmployerCreate,
    JobCreate,
    JobPatch,
    ReservationCreate,
)


router = APIRouter()


def now_utc():
    """
    Return timestamps in the required ISO 8601 UTC format.
    """
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def skills_to_text(skills):
    """
    Store the list of skills as comma-separated text.

    Example:
        ["Java", "SQL"] -> "Java,SQL"
    """
    return ",".join(
        skill.strip()
        for skill in skills
        if skill.strip()
    )


def text_to_skills(value):
    """
    Convert the database representation back to a list.
    """
    return [
        skill.strip()
        for skill in value.split(",")
        if skill.strip()
    ]


def v1_job(row):
    """
    Map a database job row to the old flat V1 response shape.
    """

    def money(value):
        amount = value / 100000
        return (
            f"{amount:.1f}"
            .rstrip("0")
            .rstrip(".")
        )

    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "salary": (
            f"{money(row['salary_min'])}"
            f"-{money(row['salary_max'])} LPA"
        ),
        "skills": ", ".join(
            text_to_skills(row["skills"])
        ),
        "status": row["status"],
    }


def v2_job(row, slots_remaining):
    """
    Map the same database job row to the new structured V2 shape.
    """

    return {
        "id": row["id"],
        "title": row["title"],
        "employer": {
            "id": row["employer_id"],
            "name": row["company"],
            "location": row["employer_location"],
        },
        "location": row["location"],
        "salary": {
            "min": row["salary_min"],
            "max": row["salary_max"],
            "currency": row["currency"],
        },
        "skills": text_to_skills(
            row["skills"]
        ),
        "slots_remaining": slots_remaining,
        "status": row["status"],
        "deadline": row["deadline"],
    }


def get_job_row(conn, job_id):
    """
    Get a job together with its employer information.

    This is still the job-service database only.
    """
    return conn.execute(
        """
        SELECT
            j.*,
            e.name AS company,
            e.location AS employer_location
        FROM jobs j
        JOIN employers e
            ON e.id = j.employer_id
        WHERE j.id = ?
        """,
        (job_id,),
    ).fetchone()


def slots_remaining(conn, job_row):
    """
    Calculate available application slots from the reservations table.
    """
    reserved = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM slot_reservations
        WHERE job_id = ?
          AND status = 'RESERVED'
        """,
        (job_row["id"],),
    ).fetchone()["count"]

    return (
        job_row["max_applications"]
        - reserved
    )


@router.post(
    "/api/v1/employers",
    status_code=201,
)
def create_employer(body: EmployerCreate):
    with get_conn() as conn:
        created_at = now_utc()

        cursor = conn.execute(
            """
            INSERT INTO employers(
                name,
                location,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                body.name,
                body.location,
                created_at,
            ),
        )

        row = conn.execute(
            """
            SELECT *
            FROM employers
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

        return dict(row)


@router.get(
    "/api/v1/employers/{employer_id}"
)
def get_employer(employer_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM employers
            WHERE id = ?
            """,
            (employer_id,),
        ).fetchone()

        if not row:
            raise ApiError(
                404,
                "EMPLOYER_NOT_FOUND",
                f"Employer {employer_id} not found",
            )

        return dict(row)


@router.post(
    "/api/v1/jobs",
    status_code=201,
)
def create_job(body: JobCreate):
    # Pydantic checks numeric minimums; these are cross-field rules.
    if body.salary_max < body.salary_min:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "salary_max must be greater than or equal to salary_min",
            {
                "problems": [
                    {
                        "field": "salary_max",
                        "issue": (
                            "Must be greater than or equal "
                            "to salary_min"
                        ),
                    }
                ]
            },
        )

    if (
        not body.skills
        or not any(
            skill.strip()
            for skill in body.skills
        )
    ):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "At least one skill is required",
            {
                "problems": [
                    {
                        "field": "skills",
                        "issue": "At least one skill is required",
                    }
                ]
            },
        )

    skills = skills_to_text(body.skills)

    if not skills:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "At least one skill is required",
            {
                "problems": [
                    {
                        "field": "skills",
                        "issue": "At least one skill is required",
                    }
                ]
            },
        )

    with get_conn() as conn:
        employer = conn.execute(
            """
            SELECT id
            FROM employers
            WHERE id = ?
            """,
            (body.employer_id,),
        ).fetchone()

        if not employer:
            raise ApiError(
                404,
                "EMPLOYER_NOT_FOUND",
                f"Employer {body.employer_id} not found",
            )

        cursor = conn.execute(
            """
            INSERT INTO jobs(
                employer_id,
                title,
                location,
                salary_min,
                salary_max,
                currency,
                skills,
                max_applications,
                status,
                deadline,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body.employer_id,
                body.title,
                body.location,
                body.salary_min,
                body.salary_max,
                body.currency,
                skills,
                body.max_applications,
                "OPEN",
                body.deadline,
                now_utc(),
            ),
        )

        row = get_job_row(
            conn,
            cursor.lastrowid,
        )

        return v1_job(row)


@router.get("/api/v1/jobs")
def list_jobs_v1(
    status: str | None = None,
    skill: str | None = None,
):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                j.*,
                e.name AS company,
                e.location AS employer_location
            FROM jobs j
            JOIN employers e
                ON e.id = j.employer_id
            ORDER BY j.id
            """
        ).fetchall()

        result = []

        for row in rows:
            if (
                status
                and row["status"] != status
            ):
                continue

            if skill:
                matching_skill = any(
                    current.lower() == skill.lower()
                    for current in text_to_skills(
                        row["skills"]
                    )
                )

                if not matching_skill:
                    continue

            result.append(
                v1_job(row)
            )

        return result


@router.get("/api/v1/jobs/{job_id}")
def get_job_v1(job_id: int):
    with get_conn() as conn:
        row = get_job_row(
            conn,
            job_id,
        )

        if not row:
            raise ApiError(
                404,
                "JOB_NOT_FOUND",
                f"Job {job_id} not found",
            )

        return v1_job(row)


@router.get("/api/v2/jobs")
def list_jobs_v2(
    status: str | None = None,
    skill: str | None = None,
):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                j.*,
                e.name AS company,
                e.location AS employer_location
            FROM jobs j
            JOIN employers e
                ON e.id = j.employer_id
            ORDER BY j.id
            """
        ).fetchall()

        result = []

        for row in rows:
            if (
                status
                and row["status"] != status
            ):
                continue

            if skill:
                matching_skill = any(
                    current.lower() == skill.lower()
                    for current in text_to_skills(
                        row["skills"]
                    )
                )

                if not matching_skill:
                    continue

            result.append(
                v2_job(
                    row,
                    slots_remaining(
                        conn,
                        row,
                    ),
                )
            )

        return result


@router.get("/api/v2/jobs/{job_id}")
def get_job_v2(job_id: int):
    with get_conn() as conn:
        row = get_job_row(
            conn,
            job_id,
        )

        if not row:
            raise ApiError(
                404,
                "JOB_NOT_FOUND",
                f"Job {job_id} not found",
            )

        return v2_job(
            row,
            slots_remaining(
                conn,
                row,
            ),
        )


@router.patch("/api/v1/jobs/{job_id}")
def patch_job(
    job_id: int,
    body: JobPatch,
):
    if hasattr(body, "model_dump"):
        data = body.model_dump(
            exclude_unset=True
        )
    else:
        data = body.dict(
            exclude_unset=True
        )

    if not data:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "At least one field is required",
            {
                "problems": [
                    {
                        "field": "body",
                        "issue": "At least one field is required",
                    }
                ]
            },
        )

    if (
        "status" in data
        and data["status"]
        not in {"OPEN", "CLOSED"}
    ):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "status must be OPEN or CLOSED",
            {
                "problems": [
                    {
                        "field": "status",
                        "issue": "Must be OPEN or CLOSED",
                    }
                ]
            },
        )

    with get_conn() as conn:
        row = get_job_row(
            conn,
            job_id,
        )

        if not row:
            raise ApiError(
                404,
                "JOB_NOT_FOUND",
                f"Job {job_id} not found",
            )

        new_min = data.get(
            "salary_min",
            row["salary_min"],
        )

        new_max = data.get(
            "salary_max",
            row["salary_max"],
        )

        if new_max < new_min:
            raise ApiError(
                400,
                "VALIDATION_ERROR",
                (
                    "salary_max must be greater than "
                    "or equal to salary_min"
                ),
                {
                    "problems": [
                        {
                            "field": "salary_max",
                            "issue": (
                                "Must be greater than or "
                                "equal to salary_min"
                            ),
                        }
                    ],
                },
            )

        if "max_applications" in data:
            reserved = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM slot_reservations
                WHERE job_id = ?
                  AND status = 'RESERVED'
                """,
                (job_id,),
            ).fetchone()["count"]

            if data["max_applications"] < reserved:
                raise ApiError(
                    409,
                    "SLOTS_IN_USE",
                    (
                        "max_applications cannot be below "
                        "the current number of RESERVED slots"
                    ),
                )

        allowed_fields = [
            "title",
            "location",
            "salary_min",
            "salary_max",
            "max_applications",
            "deadline",
            "status",
        ]

        updates = [
            (field, data[field])
            for field in allowed_fields
            if field in data
        ]

        set_clause = ", ".join(
            f"{field} = ?"
            for field, _ in updates
        )

        values = [
            value
            for _, value in updates
        ]

        values.append(job_id)

        conn.execute(
            f"""
            UPDATE jobs
            SET {set_clause}
            WHERE id = ?
            """,
            values,
        )

        return v1_job(
            get_job_row(
                conn,
                job_id,
            )
        )


@router.post(
    "/api/v1/jobs/{job_id}/reservations",
    status_code=201,
)
def reserve_slot(
    job_id: int,
    body: ReservationCreate,
    request: Request,
    response: Response,
):
    with get_conn() as conn:
        # BEGIN IMMEDIATE serializes writers so two simultaneous
        # requests cannot both consume the last available slot.
        conn.execute("BEGIN IMMEDIATE")

        job = get_job_row(
            conn,
            job_id,
        )

        if not job:
            raise ApiError(
                404,
                "JOB_NOT_FOUND",
                f"Job {job_id} not found",
            )

        existing = conn.execute(
            """
            SELECT *
            FROM slot_reservations
            WHERE application_id = ?
            """,
            (body.application_id,),
        ).fetchone()

        # Idempotency: an already-reserved application does not
        # consume another slot.
        if (
            existing
            and existing["status"] == "RESERVED"
        ):
            remaining = slots_remaining(
                conn,
                job,
            )

            # The route normally returns 201, but an idempotent
            # repeat must return 200.
            response.status_code = 200

            return {
                "job_id": job_id,
                "application_id": body.application_id,
                "status": "RESERVED",
                "slots_remaining": remaining,
            }

        if job["status"] == "CLOSED":
            raise ApiError(
                409,
                "JOB_CLOSED",
                f"Job {job_id} is closed",
            )

        remaining = slots_remaining(
            conn,
            job,
        )

        if remaining == 0:
            raise ApiError(
                409,
                "JOB_FULL",
                f"Job {job_id} is full",
            )

        current_time = now_utc()

        if existing:
            # Reuse a RELEASED reservation.
            conn.execute(
                """
                UPDATE slot_reservations
                SET
                    job_id = ?,
                    status = 'RESERVED',
                    updated_at = ?
                WHERE application_id = ?
                """,
                (
                    job_id,
                    current_time,
                    body.application_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO slot_reservations(
                    application_id,
                    job_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    body.application_id,
                    job_id,
                    "RESERVED",
                    current_time,
                    current_time,
                ),
            )

        return {
            "job_id": job_id,
            "application_id": body.application_id,
            "status": "RESERVED",
            "slots_remaining": remaining - 1,
        }


@router.delete(
    "/api/v1/jobs/{job_id}/reservations/{application_id}",
    status_code=204,
)
def release_slot(
    job_id: int,
    application_id: int,
):
    with get_conn() as conn:
        # Compensation is idempotent: updating an already RELEASED
        # row, or no matching row, still results in 204.
        conn.execute(
            """
            UPDATE slot_reservations
            SET
                status = 'RELEASED',
                updated_at = ?
            WHERE application_id = ?
              AND job_id = ?
            """,
            (
                now_utc(),
                application_id,
                job_id,
            ),
        )

        return None