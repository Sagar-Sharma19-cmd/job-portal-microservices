import pytest

from common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


class FakeClock:
    """A controllable clock for testing without waiting."""

    def __init__(self):
        self.current_time = 100.0

    def __call__(self):
        return self.current_time

    def advance(self, seconds):
        self.current_time += seconds


def test_initial_state_is_closed():
    breaker = CircuitBreaker("test-service")

    assert breaker.state == CircuitState.CLOSED
    assert breaker.state_info()["failures"] == 0


def test_opens_after_three_failures():
    breaker = CircuitBreaker("test-service", failure_threshold=3)

    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state == CircuitState.CLOSED

    breaker.record_failure()

    assert breaker.state == CircuitState.OPEN
    assert breaker.state_info()["failures"] == 3


def test_open_breaker_blocks_requests():
    breaker = CircuitBreaker("test-service")

    for _ in range(3):
        breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        breaker.allow_request()


def test_half_open_after_timeout():
    clock = FakeClock()
    breaker = CircuitBreaker(
        "test-service",
        failure_threshold=3,
        open_seconds=15,
        clock=clock,
    )

    for _ in range(3):
        breaker.record_failure()

    clock.advance(15)

    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN


def test_only_one_half_open_trial_is_allowed():
    clock = FakeClock()
    breaker = CircuitBreaker(
        "test-service",
        failure_threshold=3,
        open_seconds=15,
        clock=clock,
    )

    for _ in range(3):
        breaker.record_failure()

    clock.advance(15)

    assert breaker.allow_request() is True

    with pytest.raises(CircuitBreakerOpenError):
        breaker.allow_request()


def test_success_closes_breaker():
    clock = FakeClock()
    breaker = CircuitBreaker(
        "test-service",
        failure_threshold=3,
        open_seconds=15,
        clock=clock,
    )

    for _ in range(3):
        breaker.record_failure()

    clock.advance(15)
    breaker.allow_request()
    breaker.record_success()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.state_info()["failures"] == 0
    assert breaker.state_info()["opened_at"] is None


def test_half_open_failure_reopens_breaker():
    clock = FakeClock()
    breaker = CircuitBreaker(
        "test-service",
        failure_threshold=3,
        open_seconds=15,
        clock=clock,
    )

    for _ in range(3):
        breaker.record_failure()

    clock.advance(15)
    breaker.allow_request()
    breaker.record_failure()

    assert breaker.state == CircuitState.OPEN


def test_reset_returns_breaker_to_closed():
    breaker = CircuitBreaker("test-service")

    for _ in range(3):
        breaker.record_failure()

    breaker.reset()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.state_info()["failures"] == 0