"""Resilience utilities — retry, circuit breaker, error tracking."""

from __future__ import annotations

import logging
import random
import time
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator: retry a function with exponential backoff.

    Args:
        max_attempts: Total attempts (including first try).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        backoff_factor: Multiplier applied to delay each retry.
        jitter: Add random jitter (±25%) to prevent thundering herd.
        retryable_exceptions: Exception types that trigger retry.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts, e,
                        )
                        raise

                    actual_delay = delay
                    if jitter:
                        actual_delay *= 0.75 + random.random() * 0.5

                    logger.warning(
                        "%s attempt %d/%d failed (%s), retrying in %.1fs",
                        func.__name__, attempt, max_attempts, e, actual_delay,
                    )
                    time.sleep(actual_delay)
                    delay = min(delay * backoff_factor, max_delay)

            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject calls
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit is open and call is rejected."""
    pass


class CircuitBreaker:
    """Circuit breaker pattern for provider adapters.

    - CLOSED: All calls pass through. Track failures.
    - OPEN: Reject calls immediately. After reset_timeout, move to HALF_OPEN.
    - HALF_OPEN: Allow one probe call. Success → CLOSED. Failure → OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker '%s' → HALF_OPEN (probe allowed)", self.name)
            return self._state

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    def record_success(self) -> None:
        """Record a successful call — reset failure count."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker '%s' → CLOSED (probe succeeded)", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call — potentially trip the breaker."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker '%s' → OPEN (probe failed)", self.name)
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' → OPEN (%d failures)",
                    self.name, self._failure_count,
                )

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute func through the circuit breaker."""
        state = self.state
        if state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN — "
                f"rejecting call to {func.__name__}. "
                f"Will retry after {self.reset_timeout}s."
            )

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    def get_status(self) -> dict[str, Any]:
        """Return breaker status for health/monitoring endpoints."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
        }


# ---------------------------------------------------------------------------
# Error Tracker — structured error logging for the error log page
# ---------------------------------------------------------------------------


class ErrorTracker:
    """In-memory ring buffer for recent errors. Queryable via API."""

    def __init__(self, max_entries: int = 500):
        self._entries: list[dict[str, Any]] = []
        self._max = max_entries
        self._lock = Lock()

    def record(
        self,
        source: str,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record an error with source context."""
        entry = {
            "timestamp": time.time(),
            "source": source,
            "error_type": type(error).__name__,
            "message": str(error),
            "context": context or {},
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]

    def get_errors(
        self,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get recent errors, optionally filtered by source."""
        with self._lock:
            entries = list(reversed(self._entries))
        if source:
            entries = [e for e in entries if e["source"] == source]
        return entries[:limit]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def count(self) -> int:
        return len(self._entries)


# Global error tracker instance
error_tracker = ErrorTracker()
