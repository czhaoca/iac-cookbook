"""Provider health service — periodic ping/latency check per provider."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.provider import ProviderConfig
from ..services.registry import registry

logger = logging.getLogger(__name__)


def check_provider_health(db: Session, provider_id: str | None = None) -> list[dict]:
    """Check health of registered providers by calling health_check on their adapters.

    Returns list of health status dicts with latency measurements.
    """
    q = db.query(ProviderConfig).filter(ProviderConfig.is_active == True)  # noqa: E712
    if provider_id:
        q = q.filter(ProviderConfig.id == provider_id)
    providers = q.all()

    results = []
    for provider in providers:
        start = time.monotonic()
        status = "unknown"
        error = None
        latency_ms = None

        try:
            adapter = registry.get_adapter(provider.id, db)
            if adapter is None:
                status = "no_adapter"
            else:
                health = adapter.health_check()
                latency_ms = round((time.monotonic() - start) * 1000, 1)
                status = health.get("status", "ok") if isinstance(health, dict) else "ok"
        except NotImplementedError:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            status = "ok"  # Adapter loaded successfully, health_check not implemented
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            status = "error"
            error = str(e)

        results.append({
            "provider_id": provider.id,
            "provider_type": provider.provider_type,
            "display_name": provider.display_name,
            "status": status,
            "latency_ms": latency_ms,
            "error": error,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })

    return results
