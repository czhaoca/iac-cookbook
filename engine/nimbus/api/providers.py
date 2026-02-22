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
