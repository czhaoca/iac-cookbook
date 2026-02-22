"""Provider management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.registry import registry
from .schemas import ProviderCreate, ProviderOut, ProviderUpdate

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=list[ProviderOut])
def list_providers(active_only: bool = True, db: Session = Depends(get_db)):
    return registry.list_providers(db, active_only=active_only)


@router.get("/types")
def list_supported_types():
    """List provider types that have registered adapters."""
    return {"supported_types": registry.supported_types}


@router.get("/{provider_id}", response_model=ProviderOut)
def get_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = registry.get_provider(db, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    return provider


@router.post("", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)):
    if body.provider_type not in registry.supported_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported type '{body.provider_type}'. Supported: {registry.supported_types}",
        )
    existing = registry.get_provider(db, body.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider '{body.id}' already exists")
    return registry.create_provider(db, **body.model_dump())


@router.put("/{provider_id}", response_model=ProviderOut)
def update_provider(provider_id: str, body: ProviderUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    provider = registry.update_provider(db, provider_id, **updates)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    return provider


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    if not registry.delete_provider(db, provider_id):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    registry.clear_cache(provider_id)


@router.get("/health/check")
def provider_health_check(provider_id: str | None = None, db: Session = Depends(get_db)):
    """Check health and latency of registered providers."""
    from ..services.health import check_provider_health
    return check_provider_health(db, provider_id)


@router.get("/status/resilience")
def provider_resilience_status(db: Session = Depends(get_db)):
    """Return circuit breaker and error status for all registered providers."""
    from ..services.resilience import error_tracker

    statuses = []
    providers = registry.list_providers(db, active_only=True)
    for p in providers:
        try:
            adapter = registry.get_adapter(p.id, db)
            cb_status = adapter.circuit_status
        except Exception:
            cb_status = {"state": "unknown", "name": p.provider_type}

        recent_errors = error_tracker.get_errors(
            source=f"provider.{p.provider_type}", limit=5,
        )
        statuses.append({
            "provider_id": p.id,
            "provider_type": p.provider_type,
            "display_name": p.display_name,
            "circuit_breaker": cb_status,
            "recent_errors": len(recent_errors),
            "status": _derive_provider_status(cb_status),
        })
    return {"providers": statuses, "total_errors": error_tracker.count}


def _derive_provider_status(cb: dict) -> str:
    """Map circuit breaker state to a user-friendly status."""
    state = cb.get("state", "unknown")
    if state == "closed":
        return "connected"
    elif state == "half_open":
        return "degraded"
    elif state == "open":
        return "down"
    return "unknown"
