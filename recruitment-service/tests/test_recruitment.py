import sys
from pathlib import Path

import pytest

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "recruitment.db"))
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
    sys.path.pop(0)

HEADERS = {"X-Internal-Token": "t16-internal-secret"}
PAYLOAD = {"application_id": 41, "job_id": 7, "candidate_id": 12}

def test_health_auth_and_idempotent_screening(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/screenings").status_code == 401
    first = client.post("/api/v1/screenings", headers=HEADERS, json=PAYLOAD)
    again = client.post("/api/v1/screenings", headers=HEADERS, json=PAYLOAD)
    assert first.status_code == 201 and again.status_code == 200 and first.json()["id"] == again.json()["id"]
    assert client.delete("/api/v1/screenings/41", headers=HEADERS).status_code == 204
    assert client.delete("/api/v1/screenings/41", headers=HEADERS).status_code == 204

def test_interviews_filters_and_errors(client):
    screening = client.post("/api/v1/screenings", headers=HEADERS, json=PAYLOAD).json()
    scheduled = client.post(f"/api/v1/screenings/{screening['id']}/interviews", headers=HEADERS, json={"round": 1, "scheduled_at": "2026-10-20T09:30:00Z"})
    assert scheduled.status_code == 201
    assert client.patch(f"/api/v1/interviews/{scheduled.json()['id']}", headers=HEADERS, json={"result": "PASS", "feedback": "Good SQL"}).status_code == 200
    assert len(client.get("/api/v1/screenings?job_id=7&status=ACTIVE", headers=HEADERS).json()) == 1
    assert client.get("/api/v1/screenings/99", headers=HEADERS).status_code == 404
    assert client.patch("/api/v1/interviews/99", headers=HEADERS, json={"result": "PASS"}).status_code == 404
    assert client.post("/api/v1/screenings/99/interviews", headers=HEADERS, json={"round": 1, "scheduled_at": "x"}).status_code == 404

def test_inactive_screening_and_unavailable_decision(client):
    screening = client.post("/api/v1/screenings", headers=HEADERS, json=PAYLOAD).json()
    client.delete("/api/v1/screenings/41", headers=HEADERS)
    assert client.post(f"/api/v1/screenings/{screening['id']}/interviews", headers=HEADERS, json={"round": 1, "scheduled_at": "x"}).status_code == 409
    assert client.post(f"/api/v1/screenings/{screening['id']}/decision", headers=HEADERS, json={"decision": "SHORTLISTED"}).status_code == 409
    active = client.post("/api/v1/screenings", headers=HEADERS, json={"application_id": 42, "job_id": 7, "candidate_id": 12}).json()
    unavailable = client.post(f"/api/v1/screenings/{active['id']}/decision", headers=HEADERS, json={"decision": "SHORTLISTED"})
    assert unavailable.status_code == 503 and unavailable.json()["error"]["code"] == "APPLICATION_SERVICE_UNAVAILABLE"
