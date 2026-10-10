import threading
from unittest.mock import Mock

import pytest
import requests

from common import registration


def setup_function():
    """Stop and clear any previous registration test sessions."""
    with registration._sessions_lock:
        sessions = list(registration._sessions.values())
        registration._sessions.clear()

    for session in sessions:
        session["stop_event"].set()

        thread = session.get("thread")
        if thread and thread.is_alive():
            thread.join(timeout=1)


def test_register_service_posts_registration(monkeypatch):
    """Verify that a service registers with the registry."""
    response = Mock()
    response.status_code = 201
    response.raise_for_status.return_value = None

    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response

    monkeypatch.setattr(
        registration,
        "_registry_request",
        fake_request,
    )

    # Prevent repeated heartbeat requests during this test.
    monkeypatch.setattr(
        registration,
        "HEARTBEAT_INTERVAL_SECONDS",
        60,
    )

    instance_id = registration.register_service(
        "job-service",
        "127.0.0.1",
        8002,
    )

    try:
        assert instance_id == "job-service-8002"

        # Wait briefly for the registration thread.
        for _ in range(100):
            if calls:
                break
            threading.Event().wait(0.01)

        assert calls

        method, url, kwargs = calls[0]

        assert method == "POST"
        assert url.endswith("/registry/register")

        payload = kwargs["json"]

        assert payload["service_name"] == "job-service"
        assert payload["instance_id"] == "job-service-8002"
        assert payload["host"] == "127.0.0.1"
        assert payload["port"] == 8002

    finally:
        registration.deregister_service(instance_id)


def test_deregister_service_deletes_instance(monkeypatch):
    """Verify that deregistration sends a DELETE request."""
    response = Mock()
    response.status_code = 204

    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return response

    monkeypatch.setattr(
        registration,
        "_registry_request",
        fake_request,
    )

    instance_id = "job-service-8002"

    registration._sessions[instance_id] = {
        "service_name": "job-service",
        "host": "127.0.0.1",
        "port": 8002,
        "stop_event": threading.Event(),
        "thread": None,
    }

    registration.deregister_service(instance_id)

    assert calls == [
        ("DELETE", "/registry/instances/job-service-8002")
    ]

    assert instance_id not in registration._sessions


def test_deregister_unknown_instance_does_not_crash():
    """Verify that deregistering an unknown instance is safe."""
    registration.deregister_service("unknown-service-9999")


def test_registration_survives_registry_connection_error(monkeypatch):
    """Verify that registry connection failures do not crash registration."""

    def failed_request(*args, **kwargs):
        raise requests.ConnectionError("Registry unavailable")

    monkeypatch.setattr(
        registration,
        "_registry_request",
        failed_request,
    )

    monkeypatch.setattr(
        registration,
        "HEARTBEAT_INTERVAL_SECONDS",
        60,
    )

    instance_id = registration.register_service(
        "job-service",
        "127.0.0.1",
        8002,
    )

    try:
        assert instance_id == "job-service-8002"

        # The session should remain tracked even if the registry is down.
        assert instance_id in registration._sessions

    finally:
        registration.deregister_service(instance_id)