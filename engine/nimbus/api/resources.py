"""Resource management API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.action_log import ActionLog
from ..models.resource import CloudResource
from ..services.registry import registry
from .schemas import (
    ActionOut,
    ActionRequest,
    ResourceCreate,
    ResourceOut,
    ResourceUpdate,
    SyncResult,
)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceOut])
def list_resources(
    provider_id: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(CloudResource)
    if provider_id:
        q = q.filter(CloudResource.provider_id == provider_id)
    if resource_type:
        q = q.filter(CloudResource.resource_type == resource_type)
    if status:
        q = q.filter(CloudResource.status == status)
    return q.order_by(CloudResource.display_name).all()


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: str, db: Session = Depends(get_db)):
    resource = db.get(CloudResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.post("", response_model=ResourceOut, status_code=201)
def create_resource(body: ResourceCreate, db: Session = Depends(get_db)):
    # Validate provider exists
    provider = registry.get_provider(db, body.provider_id)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Provider '{body.provider_id}' not found")
    resource = CloudResource(**body.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.put("/{resource_id}", response_model=ResourceOut)
def update_resource(resource_id: str, body: ResourceUpdate, db: Session = Depends(get_db)):
    resource = db.get(CloudResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(resource, k, v)
    db.commit()
    db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=204)
def delete_resource(resource_id: str, db: Session = Depends(get_db)):
    resource = db.get(CloudResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    db.delete(resource)
    db.commit()


# ---------------------------------------------------------------------------
# Resource actions
# ---------------------------------------------------------------------------


@router.post("/{resource_id}/action", response_model=ActionOut)
def perform_action(resource_id: str, body: ActionRequest, db: Session = Depends(get_db)):
    """Perform an action on a resource (stop, start, terminate, health_check)."""
    resource = db.get(CloudResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Log the action
    action_log = ActionLog(
        resource_id=resource_id,
        action_type=body.action,
        status="running",
        initiated_by="user",
    )
    db.add(action_log)
    db.commit()

    try:
        adapter = registry.get_adapter(resource.provider_id, db)

        if body.action == "stop":
            success = adapter.scale_down(resource.external_id)
            resource.status = "stopped" if success else resource.status
        elif body.action == "start":
            # Start is provider-specific — not in base interface yet
            action_log.status = "failed"
            action_log.details = {"error": "start action not yet implemented"}
        elif body.action == "terminate":
            if resource.protection_level == "critical":
                action_log.status = "failed"
                action_log.details = {"error": "critical protection prevents termination"}
                db.commit()
                raise HTTPException(
                    status_code=403,
                    detail="Cannot terminate a resource with 'critical' protection level",
                )
            success = adapter.terminate(resource.external_id)
            if success:
                resource.status = "terminated"
        elif body.action == "health_check":
            result = adapter.health_check(resource.external_id)
            resource.status = result.get("status", resource.status)
            resource.last_seen_at = datetime.now(timezone.utc)
            action_log.details = result
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

        action_log.status = "success"

    except HTTPException:
        raise
    except KeyError as e:
        action_log.status = "failed"
        action_log.details = {"error": str(e)}
    except Exception as e:
        action_log.status = "failed"
        action_log.details = {"error": str(e)}

    db.commit()
    db.refresh(action_log)
    return action_log


# ---------------------------------------------------------------------------
# Sync resources from provider
# ---------------------------------------------------------------------------


@router.post("/sync/{provider_id}", response_model=SyncResult)
def sync_resources(provider_id: str, db: Session = Depends(get_db)):
    """Sync resources from a cloud provider into the local database."""
    provider = registry.get_provider(db, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

    result = SyncResult(provider_id=provider_id)

    try:
        adapter = registry.get_adapter(provider_id, db)
        remote_resources = adapter.list_resources()
    except Exception as e:
        result.errors.append(str(e))
        return result

    now = datetime.now(timezone.utc)
    result.synced = len(remote_resources)

    for r in remote_resources:
        existing = (
            db.query(CloudResource)
            .filter(
                CloudResource.provider_id == provider_id,
                CloudResource.external_id == r["external_id"],
            )
            .first()
        )
        if existing:
            existing.status = r.get("status", existing.status)
            existing.display_name = r.get("display_name", existing.display_name)
            existing.last_seen_at = now
            result.updated += 1
        else:
            new_resource = CloudResource(
                provider_id=provider_id,
                resource_type=r.get("resource_type", "unknown"),
                external_id=r["external_id"],
                display_name=r.get("display_name", ""),
                status=r.get("status", "unknown"),
                last_seen_at=now,
            )
            db.add(new_resource)
            result.created += 1

    db.commit()
    return result


# ---------------------------------------------------------------------------
# Action logs
# ---------------------------------------------------------------------------


@router.get("/{resource_id}/logs")
def get_action_logs(
    resource_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get action history for a resource."""
    resource = db.get(CloudResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    logs = (
        db.query(ActionLog)
        .filter(ActionLog.resource_id == resource_id)
        .order_by(ActionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "action_type": log.action_type,
            "status": log.status,
            "details": log.details,
            "initiated_by": log.initiated_by,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
