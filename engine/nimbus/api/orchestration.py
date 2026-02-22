"""Orchestration API — cross-cloud workflow endpoints."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.orchestrator import (
    budget_lockdown,
    provision_vm_with_dns,
    update_dns_for_resource,
)

router = APIRouter(prefix="/orchestrate", tags=["orchestration"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class VmDnsRequest(BaseModel):
    vm_provider_id: str
    dns_provider_id: Optional[str] = None
    vm_config: dict[str, Any] = Field(default_factory=dict)
    dns_config: dict[str, Any] = Field(default_factory=dict)


class LockdownRequest(BaseModel):
    provider_id: str
    dns_provider_id: Optional[str] = None


class DnsFailoverRequest(BaseModel):
    resource_id: str
    dns_provider_id: str
    zone_id: str
    record_id: str
    new_ip: str
    record_name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/vm-dns")
def orchestrate_vm_dns(body: VmDnsRequest, db: Session = Depends(get_db)):
    """Provision a VM and create a DNS record pointing to it."""
    return provision_vm_with_dns(
        db,
        vm_provider_id=body.vm_provider_id,
        dns_provider_id=body.dns_provider_id,
        vm_config=body.vm_config,
        dns_config=body.dns_config,
    )


@router.post("/lockdown")
def orchestrate_lockdown(body: LockdownRequest, db: Session = Depends(get_db)):
    """Emergency budget lockdown — stop ephemeral resources."""
    return budget_lockdown(db, body.provider_id, body.dns_provider_id)


@router.post("/dns-failover")
def orchestrate_dns_failover(body: DnsFailoverRequest, db: Session = Depends(get_db)):
    """Update DNS record for failover to a new IP."""
    return update_dns_for_resource(
        db,
        resource_id=body.resource_id,
        dns_provider_id=body.dns_provider_id,
        zone_id=body.zone_id,
        record_id=body.record_id,
        new_ip=body.new_ip,
        record_name=body.record_name,
    )
