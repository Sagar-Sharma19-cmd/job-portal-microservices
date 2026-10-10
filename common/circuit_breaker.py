"""
Thread-safe circuit breaker for inter-service HTTP requests.
"""

import logging
import os
import threading
import time

from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from dotenv import load_dotenv


# Load .env from the repository root.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker blocks a request."""


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: Optional[int] = None,
        open_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.name = name
        self.failure_threshold = (
            failure_threshold
            if failure_threshold is not None
            else int(os.getenv("CB_FAILURE_THRESHOLD", "3"))
        )
        self.open_seconds = (
            open_seconds
            if open_seconds is not None
            else float(os.getenv("CB_OPEN_SECONDS", "15"))
        )

        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.open_seconds < 0:
            raise ValueError("open_seconds cannot be negative")

        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = None
        self._trial_in_progress = False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        """Return True when a request is allowed; otherwise raise."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                elapsed = self._clock() - self._opened_at

                if elapsed < self.open_seconds:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )

                self._state = CircuitState.HALF_OPEN
                self._trial_in_progress = True
                logger.warning(
                    "[CIRCUIT] %s OPEN -> HALF_OPEN", self.name
                )
                return True

            if self._state == CircuitState.HALF_OPEN:
                if self._trial_in_progress:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' "
                        "already has a trial request in progress"
                    )

                self._trial_in_progress = True
                return True

            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' blocks requests"
            )

    def record_success(self) -> None:
        """Record success and reset the breaker."""
        with self._lock:
            previous_state = self._state
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._opened_at = None
            self._trial_in_progress = False

            if previous_state != CircuitState.CLOSED:
                logger.info(
                    "[CIRCUIT] %s %s -> CLOSED",
                    self.name,
                    previous_state.value,
                )

    def record_failure(self) -> None:
        """Record failure and open the breaker when necessary."""
        with self._lock:
            previous_state = self._state

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                self._trial_in_progress = False
                logger.warning(
                    "[CIRCUIT] %s HALF_OPEN -> OPEN", self.name
                )
                return

            if self._state == CircuitState.OPEN:
                return

            self._failures += 1

            if self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                self._trial_in_progress = False
                logger.warning(
                    "[CIRCUIT] %s %s -> OPEN after %s failures",
                    self.name,
                    previous_state.value,
                    self._failures,
                )

    def state_info(self) -> dict:
        """Return the current state and diagnostic information."""
        with self._lock:
            opened_at_iso = None

            if self._opened_at is not None:
                # Convert the monotonic timestamp to an approximate UTC time.
                utc_timestamp = time.time() + (
                    self._opened_at - self._clock()
                )
                opened_at_iso = datetime.fromtimestamp(
                    utc_timestamp, tz=timezone.utc
                ).isoformat()

            return {
                "state": self._state.value,
                "failures": self._failures,
                "opened_at": opened_at_iso,
            }

    def reset(self) -> None:
        """Reset the breaker to CLOSED."""
        with self._lock:
            previous_state = self._state
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._opened_at = None
            self._trial_in_progress = False

            if previous_state != CircuitState.CLOSED:
                logger.info(
                    "[CIRCUIT] %s %s -> CLOSED (reset)",
                    self.name,
                    previous_state.value,
                )