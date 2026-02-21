"""Abstract base class for cloud provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderAdapter(ABC):
    """Interface that all cloud provider adapters must implement."""

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
