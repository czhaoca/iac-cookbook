"""OCI provider adapter — implements the ProviderAdapter interface for Oracle Cloud."""

from __future__ import annotations

from typing import Any, Optional

import oci

from ..base import ProviderAdapter
from .auth import OCIClients, OCI_CONFIG_PATH


class OCIProviderAdapter(ProviderAdapter):
    """Oracle Cloud Infrastructure provider adapter."""

    def __init__(self) -> None:
        self._clients: Optional[OCIClients] = None
        self._compartment_id: str = ""

    @property
    def provider_type(self) -> str:
        return "oci"

    def authenticate(self, credentials_path: str, **kwargs: Any) -> None:
        """Authenticate using OCI CLI profile.

        kwargs:
            profile: OCI CLI profile name (default: 'DEFAULT')
            region: Override region (optional)
        """
        profile = kwargs.get("profile", "DEFAULT")
        self._clients = OCIClients(profile)
        # Trigger config load to validate
        _ = self._clients.config
        self._compartment_id = self._clients.config.get("tenancy", "")

    @property
    def clients(self) -> OCIClients:
        if self._clients is None:
            raise RuntimeError("Not authenticated — call authenticate() first")
        return self._clients

    def list_resources(self, resource_type: str | None = None) -> list[dict[str, Any]]:
        """List OCI resources. Supported types: vm, boot_volume, block_volume."""
        results: list[dict[str, Any]] = []

        if resource_type is None or resource_type == "vm":
            instances = oci.pagination.list_call_get_all_results(
                self.clients.compute.list_instances,
                self._compartment_id,
            ).data
            for inst in instances:
                if inst.lifecycle_state in ("TERMINATED", "TERMINATING"):
                    continue
                results.append({
                    "resource_type": "vm",
                    "external_id": inst.id,
                    "display_name": inst.display_name,
                    "status": _map_lifecycle(inst.lifecycle_state),
                    "details": {
                        "shape": inst.shape,
                        "region": inst.region,
                        "availability_domain": inst.availability_domain,
                        "time_created": inst.time_created.isoformat() if inst.time_created else "",
                    },
                })

        if resource_type is None or resource_type in ("boot_volume", "volume"):
            try:
                ads = self.clients.identity.list_availability_domains(self._compartment_id).data
                for ad in ads:
                    boot_vols = oci.pagination.list_call_get_all_results(
                        self.clients.blockstorage.list_boot_volumes,
                        ad.name,
                        self._compartment_id,
                    ).data
                    for bv in boot_vols:
                        if bv.lifecycle_state in ("TERMINATED", "TERMINATING"):
                            continue
                        results.append({
                            "resource_type": "boot_volume",
                            "external_id": bv.id,
                            "display_name": bv.display_name or f"boot-vol-{bv.id[-8:]}",
                            "status": _map_lifecycle(bv.lifecycle_state),
                            "details": {
                                "size_gb": bv.size_in_gbs,
                                "availability_domain": bv.availability_domain,
                            },
                        })
            except oci.exceptions.ServiceError:
                pass

        return results

    def get_resource(self, resource_id: str) -> dict[str, Any]:
        """Get a single OCI resource by OCID."""
        # Try instance first
        try:
            inst = self.clients.compute.get_instance(resource_id).data
            return {
                "resource_type": "vm",
                "external_id": inst.id,
                "display_name": inst.display_name,
                "status": _map_lifecycle(inst.lifecycle_state),
                "details": {
                    "shape": inst.shape,
                    "region": inst.region,
                },
            }
        except oci.exceptions.ServiceError:
            pass

        # Try boot volume
        try:
            bv = self.clients.blockstorage.get_boot_volume(resource_id).data
            return {
                "resource_type": "boot_volume",
                "external_id": bv.id,
                "display_name": bv.display_name or "",
                "status": _map_lifecycle(bv.lifecycle_state),
                "details": {"size_gb": bv.size_in_gbs},
            }
        except oci.exceptions.ServiceError:
            pass

        raise KeyError(f"OCI resource not found: {resource_id}")

    def provision(self, resource_type: str, config: dict[str, Any]) -> dict[str, Any]:
        """Provision a new OCI resource. Currently supports vm type."""
        raise NotImplementedError("OCI provisioning via adapter is not yet implemented")

    def terminate(self, resource_id: str) -> bool:
        """Terminate an OCI instance."""
        try:
            self.clients.compute.terminate_instance(resource_id, preserve_boot_volume=False)
            return True
        except oci.exceptions.ServiceError:
            return False

    def get_spending(self, period: str) -> float:
        """OCI free tier — always returns 0.0 for now."""
        return 0.0

    def scale_down(self, resource_id: str) -> bool:
        """Stop an OCI instance (scale down equivalent)."""
        try:
            self.clients.compute.instance_action(resource_id, "STOP")
            return True
        except oci.exceptions.ServiceError:
            return False

    def health_check(self, resource_id: str) -> dict[str, Any]:
        """Check if an OCI instance is running."""
        try:
            inst = self.clients.compute.get_instance(resource_id).data
            return {
                "status": _map_lifecycle(inst.lifecycle_state),
                "resource_id": resource_id,
                "shape": inst.shape,
            }
        except oci.exceptions.ServiceError as e:
            return {"status": "error", "resource_id": resource_id, "error": str(e)}


def _map_lifecycle(state: str) -> str:
    """Map OCI lifecycle states to Nimbus status values."""
    mapping = {
        "RUNNING": "running",
        "STOPPED": "stopped",
        "STOPPING": "stopping",
        "STARTING": "starting",
        "PROVISIONING": "provisioning",
        "TERMINATED": "terminated",
        "TERMINATING": "terminating",
        "AVAILABLE": "running",
        "CREATING_IMAGE": "busy",
    }
    return mapping.get(state, "unknown")
