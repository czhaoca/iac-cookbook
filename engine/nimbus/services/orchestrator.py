"""Orchestrator — cross-cloud workflows that coordinate multiple providers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models.action_log import ActionLog
from ..models.resource import CloudResource
from ..services.registry import registry

logger = logging.getLogger(__name__)


def provision_vm_with_dns(
    db: Session,
    vm_provider_id: str,
    dns_provider_id: str,
    vm_config: dict[str, Any],
    dns_config: dict[str, Any],
) -> dict[str, Any]:
    """Provision a VM and create a DNS record pointing to it.

    Steps:
    1. Provision VM via vm_provider adapter
    2. Extract public IP from result
    3. Create DNS A record via dns_provider adapter
    4. Track both resources in DB
    """
    result: dict[str, Any] = {"steps": [], "success": False}

    # Step 1: Provision VM
    try:
        vm_adapter = registry.get_adapter(vm_provider_id, db)
    except (KeyError, Exception) as e:
        result["steps"].append({"step": "provision_vm", "status": "failed", "error": f"Provider not found: {e}"})
        return result

    try:
        vm_result = vm_adapter.provision("vm", vm_config)
        result["steps"].append({"step": "provision_vm", "status": "success", "data": vm_result})
    except Exception as e:
        result["steps"].append({"step": "provision_vm", "status": "failed", "error": str(e)})
        return result

    # Track VM
    vm_resource = CloudResource(
        provider_id=vm_provider_id,
        resource_type="vm",
        external_id=vm_result.get("external_id", ""),
        display_name=vm_result.get("display_name", ""),
        status=vm_result.get("status", "running"),
    )
    db.add(vm_resource)
    db.flush()

    # Step 2: Create DNS record
    public_ip = vm_result.get("public_ip") or vm_result.get("tags", {}).get("public_ip")
    if public_ip and dns_provider_id:
        try:
            dns_adapter = registry.get_adapter(dns_provider_id, db)
        except (KeyError, Exception) as e:
            result["steps"].append({"step": "create_dns", "status": "failed", "error": f"DNS provider not found: {e}"})
            dns_adapter = None

        if dns_adapter:
            dns_config["content"] = public_ip
            dns_config.setdefault("type", "A")
            try:
                dns_result = dns_adapter.provision("dns_record", dns_config)
                result["steps"].append({"step": "create_dns", "status": "success", "data": dns_result})

                dns_resource = CloudResource(
                    provider_id=dns_provider_id,
                    resource_type="dns_record",
                    external_id=dns_result.get("external_id", ""),
                    display_name=dns_result.get("display_name", ""),
                    status="active",
                )
                db.add(dns_resource)
            except Exception as e:
                result["steps"].append({"step": "create_dns", "status": "failed", "error": str(e)})
    else:
        result["steps"].append({"step": "create_dns", "status": "skipped", "reason": "no public IP or DNS provider"})

    # Log action
    db.add(ActionLog(
        resource_id=vm_resource.id,
        action_type="orchestrate_vm_dns",
        status="success" if all(s["status"] == "success" for s in result["steps"]) else "partial",
        initiated_by="user",
        details=result,
    ))
    db.commit()
    result["success"] = True
    result["vm_resource_id"] = vm_resource.id
    return result


def budget_lockdown(
    db: Session,
    provider_id: str,
    dns_provider_id: str | None = None,
) -> dict[str, Any]:
    """Emergency lockdown: stop ephemeral resources and optionally add firewall rules.

    Steps:
    1. Find all running ephemeral/auto-terminate resources for the provider
    2. Scale them down (stop, not terminate — preserves data)
    3. If dns_provider_id given, could add WAF rules (stub for now)
    """
    result: dict[str, Any] = {"steps": [], "stopped": 0, "skipped": 0}
    now = datetime.now(timezone.utc)

    resources = (
        db.query(CloudResource)
        .filter(
            CloudResource.provider_id == provider_id,
            CloudResource.status == "running",
            CloudResource.protection_level != "critical",
        )
        .order_by(CloudResource.monthly_cost_estimate.desc())
        .all()
    )

    try:
        adapter = registry.get_adapter(provider_id, db)
    except (KeyError, Exception) as e:
        result["steps"].append({"action": "get_adapter", "status": "error", "error": str(e)})
        return result

    for resource in resources:
        if not resource.auto_terminate:
            result["skipped"] += 1
            continue

        try:
            success = adapter.scale_down(resource.external_id)
            if success:
                resource.status = "stopped"
                resource.updated_at = now
                result["stopped"] += 1
                result["steps"].append({
                    "resource_id": resource.id,
                    "display_name": resource.display_name,
                    "action": "scale_down",
                    "status": "success",
                })
            else:
                result["steps"].append({
                    "resource_id": resource.id,
                    "action": "scale_down",
                    "status": "failed",
                })
        except Exception as e:
            result["steps"].append({
                "resource_id": resource.id,
                "action": "scale_down",
                "status": "error",
                "error": str(e),
            })

    db.add(ActionLog(
        action_type="budget_lockdown",
        status="success",
        initiated_by="budget_monitor",
        details=result,
    ))
    db.commit()
    return result


def update_dns_for_resource(
    db: Session,
    resource_id: str,
    dns_provider_id: str,
    zone_id: str,
    record_id: str,
    new_ip: str,
    record_name: str,
) -> dict[str, Any]:
    """Update a DNS record to point to a new IP (e.g., for failover)."""
    dns_adapter = registry.get_adapter(dns_provider_id, db)

    if not hasattr(dns_adapter, "update_dns_record"):
        return {"success": False, "error": "DNS adapter doesn't support update"}

    try:
        result = dns_adapter.update_dns_record(
            zone_id=zone_id, record_id=record_id,
            record_type="A", name=record_name,
            content=new_ip, proxied=True,
        )
        db.add(ActionLog(
            resource_id=resource_id,
            action_type="dns_failover",
            status="success",
            initiated_by="user",
            details={"new_ip": new_ip, "record": record_name},
        ))
        db.commit()
        return {"success": True, "record": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
