"""HTTP client for communication between job portal microservices."""

import logging
import os
import uuid
from enum import Enum
from pathlib import Path

import requests
from dotenv import load_dotenv

from common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from common.discovery_client import choose_instance


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger(__name__)

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "t16-internal-secret")
HTTP_TIMEOUT_SECONDS = float(
    os.getenv("HTTP_TIMEOUT_SECONDS", "2")
)


class ServiceFailureReason(str, Enum):
    DOWN = "DOWN"
    TIMEOUT = "TIMEOUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    SERVER_ERROR = "SERVER_ERROR"
    NO_INSTANCE = "NO_INSTANCE"


class ServiceUnavailableError(Exception):
    """Raised when a target service cannot be reached successfully."""

    def __init__(self, service: str, reason: ServiceFailureReason):
        self.service = service
        self.reason = reason.value if isinstance(reason, Enum) else reason

        super().__init__(
            f"Service '{service}' unavailable: {self.reason}"
        )


_breakers = {}


def _get_breaker(service_name: str) -> CircuitBreaker:
    """Get or create one circuit breaker per target service."""
    if service_name not in _breakers:
        _breakers[service_name] = CircuitBreaker(service_name)

    return _breakers[service_name]


def call_service(
    service_name: str,
    method: str,
    path: str,
    json=None,
    params=None,
    request_id=None,
    timeout=None,
) -> requests.Response:
    """
    Send an HTTP request to a discovered service instance.

    HTTP 4xx responses are returned normally and do not count as
    service failures. Network failures, timeouts, and HTTP 5xx
    responses count as failures.
    """
    breaker = _get_breaker(service_name)

    try:
        breaker.allow_request()
    except CircuitBreakerOpenError as exc:
        logger.warning(
            "[CALL] service=%s method=%s path=%s reason=CIRCUIT_OPEN",
            service_name,
            method,
            path,
        )
        raise ServiceUnavailableError(
            service_name,
            ServiceFailureReason.CIRCUIT_OPEN,
        ) from exc

    instance = choose_instance(service_name)

    if not instance:
        breaker.record_failure()
        raise ServiceUnavailableError(
            service_name,
            ServiceFailureReason.NO_INSTANCE,
        )

    host = instance["host"]
    port = instance["port"]

    url = f"http://{host}:{port}/{path.lstrip('/')}"

    headers = {
        "X-Internal-Token": INTERNAL_TOKEN,
        "X-Request-ID": request_id or str(uuid.uuid4()),
    }

    request_timeout = (
        timeout if timeout is not None else HTTP_TIMEOUT_SECONDS
    )

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            json=json,
            params=params,
            headers=headers,
            timeout=request_timeout,
        )

        if response.status_code >= 500:
            breaker.record_failure()

            logger.warning(
                "[CALL] service=%s method=%s path=%s status=%s",
                service_name,
                method,
                path,
                response.status_code,
            )

            raise ServiceUnavailableError(
                service_name,
                ServiceFailureReason.SERVER_ERROR,
            )

        # A 4xx response means the target service responded.
        breaker.record_success()

        logger.info(
            "[CALL] service=%s method=%s path=%s status=%s",
            service_name,
            method,
            path,
            response.status_code,
        )

        return response

    except requests.Timeout as exc:
        breaker.record_failure()

        logger.warning(
            "[CALL] service=%s method=%s path=%s reason=TIMEOUT",
            service_name,
            method,
            path,
        )

        raise ServiceUnavailableError(
            service_name,
            ServiceFailureReason.TIMEOUT,
        ) from exc

    except requests.ConnectionError as exc:
        breaker.record_failure()

        logger.warning(
            "[CALL] service=%s method=%s path=%s reason=DOWN",
            service_name,
            method,
            path,
        )

        raise ServiceUnavailableError(
            service_name,
            ServiceFailureReason.DOWN,
        ) from exc


def get_circuit_states() -> dict:
    """Return diagnostic information for all target services."""
    return {
        service_name: breaker.state_info()
        for service_name, breaker in _breakers.items()
    }