"""Shared utilities for Job Portal microservices."""

from common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)
from common.discovery_client import (
    choose_instance,
    get_instances,
)
from common.service_client import (
    ServiceFailureReason,
    ServiceUnavailableError,
    call_service,
    get_circuit_states,
)
from common.registration import (
    register_service,
    deregister_service,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "choose_instance",
    "get_instances",
    "ServiceFailureReason",
    "ServiceUnavailableError",
    "call_service",
    "get_circuit_states",
    "register_service",
    "deregister_service",
]