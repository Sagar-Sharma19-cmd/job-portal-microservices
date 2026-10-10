import requests
import pytest

from unittest.mock import Mock

from common import service_client as client
from common.service_client import (
    ServiceFailureReason,
    ServiceUnavailableError,
)


@pytest.fixture(autouse=True)
def reset_breakers():
    client._breakers.clear()


@pytest.fixture
def fake_instance(monkeypatch):
    monkeypatch.setattr(
        client,
        "choose_instance",
        lambda service_name: {
            "instance_id": f"{service_name}-8002",
            "host": "127.0.0.1",
            "port": 8002,
        },
    )


def test_successful_call_returns_response(monkeypatch, fake_instance):
    response = Mock()
    response.status_code = 200

    monkeypatch.setattr(
        client.requests,
        "request",
        lambda **kwargs: response,
    )

    result = client.call_service(
        "job-service", "GET", "/api/v1/jobs"
    )

    assert result.status_code == 200
    assert client.get_circuit_states()["job-service"]["failures"] == 0


def test_4xx_does_not_count_as_failure(monkeypatch, fake_instance):
    response = Mock()
    response.status_code = 404

    monkeypatch.setattr(
        client.requests,
        "request",
        lambda **kwargs: response,
    )

    result = client.call_service(
        "job-service", "GET", "/api/v1/jobs/999"
    )

    assert result.status_code == 404
    assert client.get_circuit_states()["job-service"]["failures"] == 0


def test_timeout_counts_as_failure(monkeypatch, fake_instance):
    def timeout_request(**kwargs):
        raise requests.Timeout("Request timed out")

    monkeypatch.setattr(
        client.requests,
        "request",
        timeout_request,
    )

    with pytest.raises(ServiceUnavailableError) as exc:
        client.call_service(
            "job-service", "GET", "/api/v1/jobs"
        )

    assert exc.value.reason == ServiceFailureReason.TIMEOUT.value
    assert client.get_circuit_states()["job-service"]["failures"] == 1


def test_connection_error_counts_as_failure(
    monkeypatch, fake_instance
):
    def failed_request(**kwargs):
        raise requests.ConnectionError("Connection refused")

    monkeypatch.setattr(
        client.requests,
        "request",
        failed_request,
    )

    with pytest.raises(ServiceUnavailableError) as exc:
        client.call_service(
            "job-service", "GET", "/api/v1/jobs"
        )

    assert exc.value.reason == ServiceFailureReason.DOWN.value
    assert client.get_circuit_states()["job-service"]["failures"] == 1


def test_server_error_counts_as_failure(
    monkeypatch, fake_instance
):
    response = Mock()
    response.status_code = 503

    monkeypatch.setattr(
        client.requests,
        "request",
        lambda **kwargs: response,
    )

    with pytest.raises(ServiceUnavailableError) as exc:
        client.call_service(
            "job-service", "GET", "/api/v1/jobs"
        )

    assert exc.value.reason == ServiceFailureReason.SERVER_ERROR.value
    assert client.get_circuit_states()["job-service"]["failures"] == 1


def test_missing_instance_counts_as_failure(monkeypatch):
    monkeypatch.setattr(
        client,
        "choose_instance",
        lambda service_name: None,
    )

    with pytest.raises(ServiceUnavailableError) as exc:
        client.call_service(
            "job-service", "GET", "/api/v1/jobs"
        )

    assert exc.value.reason == ServiceFailureReason.NO_INSTANCE.value
    assert client.get_circuit_states()["job-service"]["failures"] == 1


def test_internal_token_and_request_id_are_sent(
    monkeypatch, fake_instance
):
    response = Mock()
    response.status_code = 200
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr(
        client.requests,
        "request",
        fake_request,
    )

    client.call_service(
        "job-service",
        "GET",
        "/api/v1/jobs",
        request_id="test-request-123",
    )

    assert captured["headers"]["X-Internal-Token"]
    assert captured["headers"]["X-Request-ID"] == "test-request-123"
    assert captured["timeout"] == client.HTTP_TIMEOUT_SECONDS