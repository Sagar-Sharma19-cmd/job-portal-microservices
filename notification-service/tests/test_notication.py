import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Use a separate temporary database for each test.
    monkeypatch.setenv("DB_PATH", str(tmp_path / "notification-test.db"))
    monkeypatch.setenv("INTERNAL_TOKEN", "test-token")
    monkeypatch.setenv("PORT", "8005")

    # Reload configuration after setting the environment variables.
    for module_name in (
        "app.main",
        "app.routes",
        "app.database",
        "app.config",
        "app.errors",
        "app.models",
    ):
        sys.modules.pop(module_name, None)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def auth_headers():
    return {"X-Internal-Token": "test-token"}


def test_health_is_public(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "notification-service"
    assert response.json()["status"] == "UP"
    assert response.json()["db"] == "UP"


def test_missing_token_returns_401(client):
    response = client.get("/api/v1/notifications")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_notification(client, capsys):
    payload = {
        "recipient_id": 12,
        "type": "APPLICATION_SUBMITTED",
        "message": "Your application for Java Developer was submitted.",
    }

    response = client.post(
        "/api/v1/notifications",
        json=payload,
        headers=auth_headers(),
    )

    assert response.status_code == 201

    saved = response.json()
    assert saved["id"] == 1
    assert saved["recipient_id"] == 12
    assert saved["type"] == "APPLICATION_SUBMITTED"
    assert saved["message"] == payload["message"]
    assert saved["created_at"].endswith("Z")

    output = capsys.readouterr().out
    assert "[NOTIFY] candidate 12 APPLICATION_SUBMITTED:" in output


def test_list_notifications_newest_first(client):
    headers = auth_headers()

    for message in ("First notification", "Second notification"):
        response = client.post(
            "/api/v1/notifications",
            json={
                "recipient_id": 12,
                "type": "STATUS_CHANGED",
                "message": message,
            },
            headers=headers,
        )
        assert response.status_code == 201

    response = client.get("/api/v1/notifications", headers=headers)

    assert response.status_code == 200
    assert [item["message"] for item in response.json()] == [
        "Second notification",
        "First notification",
    ]


def test_filter_notifications_by_recipient(client):
    headers = auth_headers()

    for recipient_id in (12, 25):
        client.post(
            "/api/v1/notifications",
            json={
                "recipient_id": recipient_id,
                "type": "STATUS_CHANGED",
                "message": f"Update for candidate {recipient_id}",
            },
            headers=headers,
        )

    response = client.get(
        "/api/v1/notifications?recipient_id=12",
        headers=headers,
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["recipient_id"] == 12


@pytest.mark.parametrize(
    "payload",
    [
        {
            "recipient_id": 12,
            "type": "INVALID_TYPE",
            "message": "Invalid notification type",
        },
        {
            "recipient_id": 12,
            "type": "STATUS_CHANGED",
            "message": "",
        },
        {
            "recipient_id": 12,
            "type": "STATUS_CHANGED",
            "message": "x" * 501,
        },
        {
            "recipient_id": 12,
            "message": "Missing type",
        },
    ],
)
def test_invalid_payload_returns_400(client, payload):
    response = client.post(
        "/api/v1/notifications",
        json=payload,
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "problems" in response.json()["error"]["details"]


def test_unknown_route_returns_formatted_404(client):
    response = client.get(
        "/api/v1/notifications/999",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_response_has_request_and_service_headers(client):
    response = client.get(
        "/api/v1/notifications",
        headers={
            **auth_headers(),
            "X-Request-ID": "notification-test-123",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "notification-test-123"
    assert response.headers["X-Served-By"] == "notification-service-8005"