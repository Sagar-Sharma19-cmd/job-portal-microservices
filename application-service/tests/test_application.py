import os
import tempfile

# Use a temporary SQLite file for tests.
# We do NOT use ":memory:" because every database connection
# would otherwise get a separate in-memory database.
TEST_DB = os.path.join(
    tempfile.gettempdir(),
    "application_service_test.db",
)

os.environ["DB_PATH"] = TEST_DB
os.environ["INTERNAL_TOKEN"] = "t16-internal-secret"


from fastapi.testclient import TestClient

from app.database import get_conn, init_db
from app.main import app
import app.saga as saga


HEADERS = {
    "X-Internal-Token": "t16-internal-secret"
}


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


def clear_database():
    init_db()

    with get_conn() as conn:
        conn.execute("DELETE FROM saga_steps")
        conn.execute("DELETE FROM sagas")
        conn.execute("DELETE FROM applications")
        conn.execute("DELETE FROM pending_notifications")


def setup_function():
    clear_database()


def fake_call_service(
    service,
    method,
    path,
    **kwargs,
):
    # Candidate Service
    if service == "candidate-service":
        return FakeResponse(
            200,
            {
                "candidate_id": 12,
                "eligible": True,
                "missing": [],
            },
        )

    # Job Service
    if service == "job-service":
        return FakeResponse(
            201,
            {
                "job_id": 7,
                "application_id": 1,
                "status": "RESERVED",
                "slots_remaining": 3,
            },
        )

    # Recruitment Service
    if service == "recruitment-service":
        return FakeResponse(
            201,
            {
                "application_id": 1,
                "status": "SCREENING_CREATED",
            },
        )

    # Notification Service
    if service == "notification-service":
        return FakeResponse(
            201,
            {
                "id": 1,
            },
        )

    raise AssertionError(
        f"Unexpected service call: {service}"
    )


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "UP"
        assert response.json()["db"] == "UP"


def test_requires_internal_token():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/applications"
        )

        assert response.status_code == 401

        assert (
            response.json()["error"]["code"]
            == "UNAUTHORIZED"
        )


def test_successful_saga(monkeypatch):
    monkeypatch.setattr(
        saga,
        "call_service",
        fake_call_service,
    )

    with TestClient(app) as client:

        response = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 12,
                "job_id": 7,
            },
            headers=HEADERS,
        )

        assert response.status_code == 201

        application = response.json()

        assert application["candidate_id"] == 12
        assert application["job_id"] == 7
        assert application["status"] == "SUBMITTED"

        assert application["saga_id"].startswith(
            "saga-"
        )

        saga_response = client.get(
            f"/api/v1/sagas/{application['saga_id']}",
            headers=HEADERS,
        )

        assert saga_response.status_code == 200

        saga_data = saga_response.json()

        assert saga_data["status"] == "COMPLETED"

        assert len(saga_data["steps"]) == 4

        assert [
            step["step"]
            for step in saga_data["steps"]
        ] == [
            "CREATE_APPLICATION",
            "CHECK_CANDIDATE",
            "RESERVE_JOB_SLOT",
            "CREATE_SCREENING",
        ]

        assert all(
            step["status"] == "DONE"
            for step in saga_data["steps"]
        )


def test_duplicate_application(monkeypatch):
    monkeypatch.setattr(
        saga,
        "call_service",
        fake_call_service,
    )

    with TestClient(app) as client:

        first = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 12,
                "job_id": 7,
            },
            headers=HEADERS,
        )

        assert first.status_code == 201

        second = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 12,
                "job_id": 7,
            },
            headers=HEADERS,
        )

        assert second.status_code == 409

        assert (
            second.json()["error"]["code"]
            == "DUPLICATE_APPLICATION"
        )


def test_get_application():
    with TestClient(app) as client:

        response = client.get(
            "/api/v1/applications/999",
            headers=HEADERS,
        )

        assert response.status_code == 404

        assert (
            response.json()["error"]["code"]
            == "APPLICATION_NOT_FOUND"
        )


def test_get_saga_not_found():
    with TestClient(app) as client:

        response = client.get(
            "/api/v1/sagas/saga-999",
            headers=HEADERS,
        )

        assert response.status_code == 404

        assert (
            response.json()["error"]["code"]
            == "SAGA_NOT_FOUND"
        )


def test_invalid_status_transition(monkeypatch):
    monkeypatch.setattr(
        saga,
        "call_service",
        fake_call_service,
    )

    with TestClient(app) as client:

        response = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 12,
                "job_id": 7,
            },
            headers=HEADERS,
        )

        assert response.status_code == 201

        application_id = response.json()["id"]

        # SUBMITTED -> OFFERED is NOT allowed.
        # It must first go through SHORTLISTED and INTERVIEW.
        response = client.patch(
            f"/api/v1/applications/{application_id}/status",
            json={
                "status": "OFFERED",
            },
            headers=HEADERS,
        )

        assert response.status_code == 409

        assert (
            response.json()["error"]["code"]
            == "INVALID_STATUS_TRANSITION"
        )


def test_status_flow(monkeypatch):
    monkeypatch.setattr(
        saga,
        "call_service",
        fake_call_service,
    )

    with TestClient(app) as client:

        response = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 20,
                "job_id": 10,
            },
            headers=HEADERS,
        )

        assert response.status_code == 201

        application_id = response.json()["id"]

        # SUBMITTED -> SHORTLISTED
        response = client.patch(
            f"/api/v1/applications/{application_id}/status",
            json={
                "status": "SHORTLISTED",
            },
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "SHORTLISTED"

        # SHORTLISTED -> INTERVIEW
        response = client.patch(
            f"/api/v1/applications/{application_id}/status",
            json={
                "status": "INTERVIEW",
            },
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "INTERVIEW"

        # INTERVIEW -> OFFERED
        response = client.patch(
            f"/api/v1/applications/{application_id}/status",
            json={
                "status": "OFFERED",
            },
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "OFFERED"


def test_rejected_status(monkeypatch):
    monkeypatch.setattr(
        saga,
        "call_service",
        fake_call_service,
    )

    with TestClient(app) as client:

        response = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 30,
                "job_id": 20,
            },
            headers=HEADERS,
        )

        application_id = response.json()["id"]

        response = client.patch(
            f"/api/v1/applications/{application_id}/status",
            json={
                "status": "REJECTED",
                "reason": "Skills do not match",
            },
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "REJECTED"


def test_list_applications(monkeypatch):
    monkeypatch.setattr(
        saga,
        "call_service",
        fake_call_service,
    )

    with TestClient(app) as client:

        response = client.post(
            "/api/v1/applications",
            json={
                "candidate_id": 50,
                "job_id": 50,
            },
            headers=HEADERS,
        )

        assert response.status_code == 201

        response = client.get(
            "/api/v1/applications",
            headers=HEADERS,
        )

        assert response.status_code == 200

        applications = response.json()

        assert len(applications) == 1
        assert applications[0]["candidate_id"] == 50

        response = client.get(
            "/api/v1/applications?candidate_id=50",
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert len(response.json()) == 1