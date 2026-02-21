"""Provider registry — discovers, registers, and manages provider adapters."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models.provider import ProviderConfig
from ..providers.base import ProviderAdapter


class ProviderRegistry:
    """Central registry mapping provider_type → adapter class and managing instances."""

    def __init__(self) -> None:
        self._adapter_classes: dict[str, type[ProviderAdapter]] = {}
        self._instances: dict[str, ProviderAdapter] = {}

    # -- Registration --------------------------------------------------------

    def register_adapter(self, provider_type: str, adapter_cls: type[ProviderAdapter]) -> None:
        """Register an adapter class for a provider type (e.g. 'oci' → OCIAdapter)."""
        self._adapter_classes[provider_type] = adapter_cls

    @property
    def supported_types(self) -> list[str]:
        return list(self._adapter_classes.keys())

    # -- Instance management -------------------------------------------------

    def get_adapter(self, provider_id: str, db: Session) -> ProviderAdapter:
        """Get or create an adapter instance for a registered provider config."""
        if provider_id in self._instances:
            return self._instances[provider_id]

        config = db.get(ProviderConfig, provider_id)
        if config is None:
            raise KeyError(f"Provider '{provider_id}' not found in database")

        cls = self._adapter_classes.get(config.provider_type)
        if cls is None:
            raise KeyError(
                f"No adapter registered for type '{config.provider_type}'. "
                f"Supported: {self.supported_types}"
            )

        adapter = cls()
        adapter.authenticate(config.credentials_path, profile=config.id, region=config.region)
        self._instances[provider_id] = adapter
        return adapter

    def clear_cache(self, provider_id: str | None = None) -> None:
        """Clear cached adapter instances (e.g. after credential rotation)."""
        if provider_id:
            self._instances.pop(provider_id, None)
        else:
            self._instances.clear()

    # -- DB operations -------------------------------------------------------

    @staticmethod
    def list_providers(db: Session, active_only: bool = True) -> list[ProviderConfig]:
        """List all provider configs from the database."""
        q = db.query(ProviderConfig)
        if active_only:
            q = q.filter(ProviderConfig.is_active.is_(True))
        return q.all()

    @staticmethod
    def get_provider(db: Session, provider_id: str) -> ProviderConfig | None:
        return db.get(ProviderConfig, provider_id)

    @staticmethod
    def create_provider(db: Session, **kwargs: Any) -> ProviderConfig:
        provider = ProviderConfig(**kwargs)
        db.add(provider)
        db.commit()
        db.refresh(provider)
        return provider

    @staticmethod
    def update_provider(db: Session, provider_id: str, **kwargs: Any) -> ProviderConfig | None:
        provider = db.get(ProviderConfig, provider_id)
        if provider is None:
            return None
        for k, v in kwargs.items():
            if hasattr(provider, k):
                setattr(provider, k, v)
        db.commit()
        db.refresh(provider)
        return provider

    @staticmethod
    def delete_provider(db: Session, provider_id: str) -> bool:
        provider = db.get(ProviderConfig, provider_id)
        if provider is None:
            return False
        db.delete(provider)
        db.commit()
        return True


# -- Singleton ---------------------------------------------------------------

registry = ProviderRegistry()
