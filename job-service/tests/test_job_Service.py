import importlib
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient


# Make the service folder importable when pytest is started
# from the service directory.
sys.path.insert(
    0,
    str(
        pathlib.Path(__file__)
        .resolve()
        .parents[1]
    ),
)


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Each test gets its own temporary SQLite database.
    db_path = tmp_path / "job.db"

    # These must be set before importing the application modules.
    monkeypatch.setenv(
        "DB_PATH",
        str(db_path),
    )
    monkeypatch.setenv(
        "INTERNAL_TOKEN",
        "test-token",
    )
    monkeypatch.setenv(
        "PORT",
        "8002",
    )

    from app import (
        config,
        database,
        routes,
        main,
    )

    # Reload so the test environment values are picked up.
    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(routes)
    importlib.reload(main)

    # If common/ exists in the full repository, do not let tests
    # depend on the registry being available.
    try:
        import common.registration as registration

        monkeypatch.setattr(
            registration,
            "register_service",
            lambda *args: None,
        )

        monkeypatch.setattr(
            registration,
            "deregister_service",
            lambda *args: None,
        )

    except ImportError:
        pass

    with TestClient(main.app) as test_client:
        yield test_client


def auth():
    return {
        "X-Internal-Token": "test-token"
    }


def make_employer(client):
    response = client.post(
        "/api/v1/employers",
        json={
            "name": "Infosys",
            "location": "Bengaluru",
        },
        headers=auth(),
    )

    assert response.status_code == 201

    return response.json()


def make_job(
    client,
    employer_id,
    max_applications=2,
):
    response = client.post(
        "/api/v1/jobs",
        json={
            "employer_id": employer_id,
            "title": "Java Developer",
            "location": "Bengaluru",
            "salary_min": 600000,
            "salary_max": 800000,
            "currency": "INR",
            "skills": [
                "Java",
                "SQL",
            ],
            "max_applications": max_applications,
            "deadline": "2026-11-30",
        },
        headers=auth(),
    )

    assert response.status_code == 201

    return response.json()


def test_health_and_auth(client):
    response = client.get(
        "/health"
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["instance_id"]
        == "job-service-8002"
    )

    assert body["db"] == "UP"

    # Internal API without token must be rejected.
    response = client.get(
        "/api/v1/employers/1"
    )

    assert response.status_code == 401

    assert (
        response.json()["error"]["code"]
        == "UNAUTHORIZED"
    )


def test_employers_success_and_not_found(client):
    employer = make_employer(client)

    response = client.get(
        f"/api/v1/employers/{employer['id']}",
        headers=auth(),
    )

    assert response.status_code == 200
    assert (
        response.json()["name"]
        == "Infosys"
    )

    response = client.get(
        "/api/v1/employers/999",
        headers=auth(),
    )

    assert response.status_code == 404

    assert (
        response.json()["error"]["code"]
        == "EMPLOYER_NOT_FOUND"
    )


def test_jobs_v1_v2_filters_patch_and_headers(client):
    employer = make_employer(client)

    job = make_job(
        client,
        employer["id"],
        5,
    )

    job_id = job["id"]

    # Exact V1 shape.
    assert job == {
        "id": job_id,
        "title": "Java Developer",
        "company": "Infosys",
        "location": "Bengaluru",
        "salary": "6-8 LPA",
        "skills": "Java, SQL",
        "status": "OPEN",
    }

    # Employer does not exist.
    response = client.post(
        "/api/v1/jobs",
        json={
            "employer_id": 999,
            "title": "x",
            "location": "x",
            "salary_min": 1,
            "salary_max": 2,
            "skills": ["x"],
            "max_applications": 1,
        },
        headers=auth(),
    )

    assert response.status_code == 404

    response = client.get(
        "/api/v1/jobs?status=OPEN&skill=Java",
        headers=auth(),
    )

    assert response.status_code == 200

    assert (
        response.headers["Deprecation"]
        == "true"
    )

    assert (
        response.json()[0]["id"]
        == job_id
    )

    response = client.get(
        f"/api/v1/jobs/{job_id}",
        headers=auth(),
    )

    assert response.status_code == 200

    assert (
        response.headers["Deprecation"]
        == "true"
    )

    response = client.get(
        "/api/v2/jobs?skill=SQL",
        headers=auth(),
    )

    assert response.status_code == 200

    body = response.json()[0]

    assert (
        body["employer"]["name"]
        == "Infosys"
    )

    assert (
        body["slots_remaining"]
        == 5
    )

    response = client.get(
        f"/api/v2/jobs/{job_id}",
        headers=auth(),
    )

    assert response.status_code == 200

    assert response.json()["salary"] == {
        "min": 600000,
        "max": 800000,
        "currency": "INR",
    }

    response = client.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "title": "Senior Java Developer",
            "salary_min": 650000,
        },
        headers=auth(),
    )

    assert response.status_code == 200

    assert (
        response.headers["Deprecation"]
        == "true"
    )

    assert (
        response.json()["title"]
        == "Senior Java Developer"
    )

    assert (
        response.json()["salary"]
        == "6.5-8 LPA"
    )


def test_job_validation_and_not_found(client):
    employer = make_employer(client)

    invalid = {
        "employer_id": employer["id"],
        "title": "x",
        "location": "x",
        "salary_min": 800000,
        "salary_max": 600000,
        "skills": [],
        "max_applications": 1,
    }

    response = client.post(
        "/api/v1/jobs",
        json=invalid,
        headers=auth(),
    )

    assert response.status_code == 400

    assert (
        response.json()["error"]["code"]
        == "VALIDATION_ERROR"
    )

    # max_applications >= 1 is enforced by Pydantic.
    response = client.post(
        "/api/v1/jobs",
        json={
            "employer_id": employer["id"],
            "title": "x",
            "location": "x",
            "salary_min": 1,
            "salary_max": 2,
            "skills": ["x"],
            "max_applications": 0,
        },
        headers=auth(),
    )

    assert response.status_code == 400

    response = client.get(
        "/api/v1/jobs/999",
        headers=auth(),
    )

    assert response.status_code == 404

    assert (
        response.json()["error"]["code"]
        == "JOB_NOT_FOUND"
    )

    response = client.get(
        "/api/v2/jobs/999",
        headers=auth(),
    )

    assert response.status_code == 404

    assert (
        response.json()["error"]["code"]
        == "JOB_NOT_FOUND"
    )


def test_reservation_idempotency_full_closed_and_compensation(
    client,
):
    employer = make_employer(client)

    job = make_job(
        client,
        employer["id"],
        1,
    )

    job_id = job["id"]

    # First reservation.
    response = client.post(
        f"/api/v1/jobs/{job_id}/reservations",
        json={
            "application_id": 41
        },
        headers=auth(),
    )

    assert response.status_code == 201

    assert (
        response.json()["slots_remaining"]
        == 0
    )

    # Same application_id is idempotent.
    response = client.post(
        f"/api/v1/jobs/{job_id}/reservations",
        json={
            "application_id": 41
        },
        headers=auth(),
    )

    assert response.status_code == 200

    assert (
        response.json()["status"]
        == "RESERVED"
    )

    # Another application cannot reserve a full job.
    response = client.post(
        f"/api/v1/jobs/{job_id}/reservations",
        json={
            "application_id": 42
        },
        headers=auth(),
    )

    assert response.status_code == 409

    assert (
        response.json()["error"]["code"]
        == "JOB_FULL"
    )

    # Saga compensation.
    response = client.delete(
        f"/api/v1/jobs/{job_id}/reservations/41",
        headers=auth(),
    )

    assert response.status_code == 204

    # Compensation is idempotent.
    response = client.delete(
        f"/api/v1/jobs/{job_id}/reservations/41",
        headers=auth(),
    )

    assert response.status_code == 204

    # Even a never-existing reservation returns 204.
    response = client.delete(
        f"/api/v1/jobs/{job_id}/reservations/999",
        headers=auth(),
    )

    assert response.status_code == 204

    # Released slot can be reserved again.
    response = client.post(
        f"/api/v1/jobs/{job_id}/reservations",
        json={
            "application_id": 42
        },
        headers=auth(),
    )

    assert response.status_code == 201

    # Pydantic prevents max_applications=0.
    response = client.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "max_applications": 0
        },
        headers=auth(),
    )

    assert response.status_code == 400

    # A separate closed job tests JOB_CLOSED.
    closed_job = make_job(
        client,
        employer["id"],
        2,
    )

    response = client.patch(
        f"/api/v1/jobs/{closed_job['id']}",
        json={
            "status": "CLOSED"
        },
        headers=auth(),
    )

    assert response.status_code == 200

    response = client.post(
        f"/api/v1/jobs/{closed_job['id']}/reservations",
        json={
            "application_id": 43
        },
        headers=auth(),
    )

    assert response.status_code == 409

    assert (
        response.json()["error"]["code"]
        == "JOB_CLOSED"
    )


def test_slots_in_use_conflict_and_method_not_allowed(client):
    employer = make_employer(client)

    job = make_job(
        client,
        employer["id"],
        3,
    )

    job_id = job["id"]

    # Reserve two of three slots.
    response = client.post(
        f"/api/v1/jobs/{job_id}/reservations",
        json={
            "application_id": 50
        },
        headers=auth(),
    )

    assert response.status_code == 201

    response = client.post(
        f"/api/v1/jobs/{job_id}/reservations",
        json={
            "application_id": 51
        },
        headers=auth(),
    )

    assert response.status_code == 201

    # Two slots are currently in use, so max_applications
    # cannot be reduced below 2.
    response = client.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "max_applications": 1
        },
        headers=auth(),
    )

    assert response.status_code == 409

    assert (
        response.json()["error"]["code"]
        == "SLOTS_IN_USE"
    )

    # Unsupported method is converted to the required error format.
    response = client.get(
        "/api/v1/jobs/999/reservations",
        headers=auth(),
    )

    assert response.status_code == 405