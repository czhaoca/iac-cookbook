"""Audit log API — global action history with filtering."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.action_log import ActionLog
from ..models.resource import CloudResource

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    provider_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List global audit log entries with optional filtering."""
    q = db.query(ActionLog)

    if resource_id:
        q = q.filter(ActionLog.resource_id == resource_id)

    if provider_id:
        q = q.join(CloudResource, ActionLog.resource_id == CloudResource.id).filter(
            CloudResource.provider_id == provider_id
        )

    if action_type:
        q = q.filter(ActionLog.action_type == action_type)

    logs = q.order_by(ActionLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "resource_id": log.resource_id,
            "action_type": log.action_type,
            "status": log.status,
            "details": log.details or {},
            "initiated_by": log.initiated_by,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
