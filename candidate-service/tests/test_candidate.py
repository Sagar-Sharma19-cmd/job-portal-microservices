import os
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "candidate.db"))
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
PAYLOAD = {"name": "Ananya Rao", "email": "ananya@example.com", "skills": ["Java"], "resume_url": "https://example.com/r.pdf"}

def test_health_and_authentication(client):
    assert client.get("/health").json()["status"] == "UP"
    assert client.get("/api/v1/candidates").status_code == 401

def test_candidate_crud_filter_and_eligibility(client):
    created = client.post("/api/v1/candidates", headers=HEADERS, json=PAYLOAD)
    assert created.status_code == 201
    candidate_id = created.json()["id"]
    assert len(client.get("/api/v1/candidates?skill=java", headers=HEADERS).json()) == 1
    assert client.get(f"/api/v1/candidates/{candidate_id}", headers=HEADERS).status_code == 200
    updated = client.patch(f"/api/v1/candidates/{candidate_id}", headers=HEADERS, json={"skills": [], "resume_url": None})
    assert updated.status_code == 200
    assert client.get(f"/api/v1/candidates/{candidate_id}/eligibility", headers=HEADERS).json()["missing"] == ["resume_url", "skills"]

def test_candidate_validation_not_found_and_duplicate(client):
    assert client.post("/api/v1/candidates", headers=HEADERS, json={"name": "A", "email": "bad"}).status_code == 400
    assert client.get("/api/v1/candidates/99", headers=HEADERS).status_code == 404
    assert client.post("/api/v1/candidates", headers=HEADERS, json=PAYLOAD).status_code == 201
    duplicate = client.post("/api/v1/candidates", headers=HEADERS, json=PAYLOAD)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"
