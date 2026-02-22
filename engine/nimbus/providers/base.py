"""Abstract base class for cloud provider adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from nimbus.services.resilience import CircuitBreaker, CircuitBreakerError, error_tracker, retry

logger = logging.getLogger(__name__)


class ProviderAdapter(ABC):
    """Interface that all cloud provider adapters must implement.

    Includes built-in resilience: retry with backoff and circuit breaker.
    Subclasses can use ``_resilient_call`` to wrap API calls.
    """

    def __init__(self) -> None:
        # Circuit breaker name is set lazily via provider_type property
        self._circuit_breaker: CircuitBreaker | None = None

    def _get_circuit_breaker(self) -> CircuitBreaker:
        if self._circuit_breaker is None:
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=5,
                reset_timeout=60.0,
                name=self.provider_type,
            )
        return self._circuit_breaker

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Return the provider type identifier (e.g. 'oci', 'azure')."""
        ...

    @abstractmethod
    def authenticate(self, credentials_path: str, **kwargs) -> None:
        """Authenticate with the provider using credentials."""
        ...

    @abstractmethod
    def list_resources(self, resource_type: str | None = None) -> list[dict[str, Any]]:
        """List resources, optionally filtered by type."""
        ...

    @abstractmethod
    def get_resource(self, resource_id: str) -> dict[str, Any]:
        """Get details for a single resource by its external ID."""
        ...

    @abstractmethod
    def provision(self, resource_type: str, config: dict[str, Any]) -> dict[str, Any]:
        """Provision a new resource. Returns resource details dict."""
        ...

    @abstractmethod
    def terminate(self, resource_id: str) -> bool:
        """Terminate/delete a resource. Returns True on success."""
        ...

    @abstractmethod
    def get_spending(self, period: str) -> float:
        """Get spending for a period (e.g. '2026-02'). Returns amount in USD."""
        ...

    def scale_down(self, resource_id: str) -> bool:
        """Optional: scale down a resource. Default returns False (not supported)."""
        return False

    def health_check(self, resource_id: str) -> dict[str, Any]:
        """Optional: check resource health. Default returns unknown status."""
        return {"status": "unknown", "resource_id": resource_id}

    # -- Resilience helpers ------------------------------------------------

    def _resilient_call(self, func, *args, **kwargs):
        """Execute *func* with retry + circuit breaker protection.

        Retries transient failures up to 3 times with exponential backoff.
        Circuit breaker trips after 5 consecutive failures and rejects
        calls for 60 s before probing recovery.
        """
        @retry(max_attempts=3, base_delay=1.0, retryable_exceptions=(Exception,))
        def _inner():
            return self._get_circuit_breaker().call(func, *args, **kwargs)

        try:
            return _inner()
        except CircuitBreakerError:
            raise
        except Exception as e:
            error_tracker.record(
                source=f"provider.{self.provider_type}",
                error=e,
                context={"function": func.__name__, "args_summary": str(args)[:200]},
            )
            raise

    @property
    def circuit_status(self) -> dict[str, Any]:
        """Return the circuit breaker status for monitoring."""
        return self._get_circuit_breaker().get_status()
