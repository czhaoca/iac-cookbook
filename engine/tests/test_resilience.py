"""Tests for nimbus.services.resilience — retry, circuit breaker, error tracker."""

import time
from unittest.mock import MagicMock

import pytest

from nimbus.services.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    ErrorTracker,
    retry,
)


# ── Retry ─────────────────────────────────────────────────────────────────


class TestRetry:
    def test_succeeds_first_try(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, jitter=False)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert flaky() == "recovered"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        @retry(max_attempts=2, base_delay=0.01)
        def always_fail():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fail()

    def test_respects_retryable_exceptions(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, retryable_exceptions=(IOError,))
        def wrong_exception():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            wrong_exception()
        assert call_count == 1  # No retry for non-matching exception


# ── Circuit Breaker ───────────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0, name="test")

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=60.0, name="test")
        cb.record_failure()

        with pytest.raises(CircuitBreakerError, match="OPEN"):
            cb.call(lambda: "should not run")

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_transitions_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01, name="test")

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01, name="test")

        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01, name="test")

        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_call_success(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb._failure_count == 0

    def test_call_failure_recorded(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("boom")))

    def test_get_status(self):
        cb = CircuitBreaker(failure_threshold=5, reset_timeout=30, name="oci")
        status = cb.get_status()
        assert status["name"] == "oci"
        assert status["state"] == "closed"
        assert status["failure_threshold"] == 5


# ── Error Tracker ─────────────────────────────────────────────────────────


class TestErrorTracker:
    def test_record_and_get(self):
        tracker = ErrorTracker(max_entries=100)
        tracker.record("test", ValueError("boom"), {"key": "val"})

        errors = tracker.get_errors()
        assert len(errors) == 1
        assert errors[0]["source"] == "test"
        assert errors[0]["error_type"] == "ValueError"
        assert errors[0]["message"] == "boom"
        assert errors[0]["context"] == {"key": "val"}

    def test_filter_by_source(self):
        tracker = ErrorTracker()
        tracker.record("oci", RuntimeError("a"))
        tracker.record("azure", RuntimeError("b"))
        tracker.record("oci", RuntimeError("c"))

        oci_errors = tracker.get_errors(source="oci")
        assert len(oci_errors) == 2
        assert all(e["source"] == "oci" for e in oci_errors)

    def test_respects_max_entries(self):
        tracker = ErrorTracker(max_entries=5)
        for i in range(10):
            tracker.record("test", RuntimeError(f"err-{i}"))

        assert tracker.count == 5

    def test_limit_parameter(self):
        tracker = ErrorTracker()
        for i in range(20):
            tracker.record("test", RuntimeError(f"err-{i}"))

        result = tracker.get_errors(limit=3)
        assert len(result) == 3

    def test_clear(self):
        tracker = ErrorTracker()
        tracker.record("test", RuntimeError("a"))
        tracker.clear()
        assert tracker.count == 0

    def test_returns_newest_first(self):
        tracker = ErrorTracker()
        tracker.record("test", RuntimeError("first"))
        tracker.record("test", RuntimeError("second"))

        errors = tracker.get_errors()
        assert errors[0]["message"] == "second"
        assert errors[1]["message"] == "first"
