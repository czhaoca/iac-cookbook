"""Proxmox provider adapter stub — self-hosted VM management.

Uses the Proxmox VE API (https://pve.proxmox.com/pve-docs/api-viewer/).
Authentication via API token stored in local/config/.
"""

from __future__ import annotations

import json
import logging
import ssl
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ..base import ProviderAdapter

logger = logging.getLogger(__name__)


class ProxmoxAdapter(ProviderAdapter):
    """Proxmox VE provider — manages VMs on self-hosted Proxmox clusters."""

    def __init__(self) -> None:
        super().__init__()
        self._base_url: str = ""
        self._token_id: str = ""
        self._token_secret: str = ""
        self._node: str = ""
        self._verify_ssl: bool = False

    @property
    def provider_type(self) -> str:
        return "proxmox"

    def authenticate(self, credentials_path: str, **kwargs) -> None:
        """Load Proxmox API credentials from config file.

        Expected format (one per line):
        PROXMOX_URL=https://pve.example.com:8006
        PROXMOX_TOKEN_ID=user@pam!token-name
        PROXMOX_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        PROXMOX_NODE=pve
        PROXMOX_VERIFY_SSL=false
        """
        path = Path(credentials_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Proxmox credentials not found: {path}")

        config: dict[str, str] = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()

        required = ["PROXMOX_URL", "PROXMOX_TOKEN_ID", "PROXMOX_TOKEN_SECRET"]
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(f"Missing required Proxmox config keys: {', '.join(missing)}")

        self._base_url = config["PROXMOX_URL"].rstrip("/")
        self._token_id = config["PROXMOX_TOKEN_ID"]
        self._token_secret = config["PROXMOX_TOKEN_SECRET"]
        self._node = config.get("PROXMOX_NODE", "pve")
        self._verify_ssl = config.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"

        # Verify connectivity
        resp = self._api("GET", "/version")
        logger.info("Proxmox authenticated: %s v%s", self._base_url, resp.get("data", {}).get("version", "?"))

    def list_resources(self, resource_type: str | None = None) -> list[dict[str, Any]]:
        """List VMs (qemu) and containers (lxc) on the configured node."""
        resources: list[dict[str, Any]] = []

        if resource_type is None or resource_type in ("vm", "qemu"):
            resp = self._api("GET", f"/nodes/{self._node}/qemu")
            for vm in resp.get("data", []):
                resources.append({
                    "external_id": str(vm["vmid"]),
                    "resource_type": "vm",
                    "display_name": vm.get("name", f"VM-{vm['vmid']}"),
                    "status": vm.get("status", "unknown"),
                    "tags": {
                        "vmid": str(vm["vmid"]),
                        "cpus": str(vm.get("cpus", 0)),
                        "maxmem": str(vm.get("maxmem", 0)),
                        "maxdisk": str(vm.get("maxdisk", 0)),
                        "uptime": str(vm.get("uptime", 0)),
                    },
                })

        if resource_type is None or resource_type in ("container", "lxc"):
            resp = self._api("GET", f"/nodes/{self._node}/lxc")
            for ct in resp.get("data", []):
                resources.append({
                    "external_id": str(ct["vmid"]),
                    "resource_type": "container",
                    "display_name": ct.get("name", f"CT-{ct['vmid']}"),
                    "status": ct.get("status", "unknown"),
                    "tags": {
                        "vmid": str(ct["vmid"]),
                        "cpus": str(ct.get("cpus", 0)),
                        "maxmem": str(ct.get("maxmem", 0)),
                        "maxdisk": str(ct.get("maxdisk", 0)),
                    },
                })

        return resources

    def get_resource(self, resource_id: str) -> dict[str, Any]:
        resp = self._api("GET", f"/nodes/{self._node}/qemu/{resource_id}/status/current")
        vm = resp.get("data", {})
        return {
            "external_id": resource_id,
            "resource_type": "vm",
            "display_name": vm.get("name", f"VM-{resource_id}"),
            "status": vm.get("status", "unknown"),
        }

    def provision(self, resource_type: str, config: dict[str, Any]) -> dict[str, Any]:
        """Provision a new VM or container.

        VM config keys:
            vmid (optional), name, memory (MB), cores, sockets (default 1),
            storage (default "local-lvm"), disk_size (GB, default 32),
            iso (for CD install) or clone (template vmid to clone),
            ostype (default "l26"), net (default "virtio,bridge=vmbr0"),
            cloud_init: bool (default False) — if True, adds cloud-init drive
              ci_user, ci_password, ci_sshkeys, ci_ip (DHCP or static)

        Container config keys:
            vmid (optional), hostname, memory (MB), cores,
            storage (default "local-lvm"), rootfs_size (GB, default 8),
            ostemplate (e.g. "local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"),
            net (default "name=eth0,bridge=vmbr0,ip=dhcp"),
            password, ssh_keys
        """
        if resource_type in ("container", "lxc"):
            return self._provision_container(config)
        return self._provision_vm(config)

    def _provision_vm(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create a QEMU VM via Proxmox API."""
        vmid = config.get("vmid") or self._next_vmid()
        params: dict[str, Any] = {
            "vmid": vmid,
            "name": config.get("name", f"vm-{vmid}"),
            "memory": config.get("memory", 2048),
            "cores": config.get("cores", 2),
            "sockets": config.get("sockets", 1),
            "ostype": config.get("ostype", "l26"),
            "net0": config.get("net", "virtio,bridge=vmbr0"),
        }

        storage = config.get("storage", "local-lvm")
        disk_size = config.get("disk_size", 32)

        if "clone" in config:
            # Clone from template
            resp = self._api("POST", f"/nodes/{self._node}/qemu/{config['clone']}/clone", {
                "newid": vmid,
                "name": params["name"],
                "full": 1,
                "storage": storage,
            })
        else:
            # Create from scratch
            params[f"scsi0"] = f"{storage}:{disk_size}"
            params["scsihw"] = "virtio-scsi-single"
            params["boot"] = "order=scsi0"
            if "iso" in config:
                params["cdrom"] = config["iso"]
                params["boot"] = "order=ide2;scsi0"
            resp = self._api("POST", f"/nodes/{self._node}/qemu", params)

        if resp.get("data") is None and resp.get("errors"):
            raise RuntimeError(f"VM provision failed: {resp['errors']}")

        # Cloud-init configuration
        if config.get("cloud_init"):
            ci_params: dict[str, str] = {}
            if "ci_user" in config:
                ci_params["ciuser"] = config["ci_user"]
            if "ci_password" in config:
                ci_params["cipassword"] = config["ci_password"]
            if "ci_sshkeys" in config:
                ci_params["sshkeys"] = config["ci_sshkeys"]
            ci_params["ipconfig0"] = config.get("ci_ip", "ip=dhcp")
            ci_params["ide2"] = f"{storage}:cloudinit"
            if ci_params:
                self._api("PUT", f"/nodes/{self._node}/qemu/{vmid}/config", ci_params)

        # Auto-start if requested
        if config.get("start", False):
            self._api("POST", f"/nodes/{self._node}/qemu/{vmid}/status/start")

        return {
            "external_id": str(vmid),
            "resource_type": "vm",
            "display_name": params["name"],
            "status": "running" if config.get("start") else "stopped",
        }

    def _provision_container(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create an LXC container via Proxmox API."""
        vmid = config.get("vmid") or self._next_vmid()
        storage = config.get("storage", "local-lvm")
        rootfs_size = config.get("rootfs_size", 8)

        params: dict[str, Any] = {
            "vmid": vmid,
            "hostname": config.get("hostname", f"ct-{vmid}"),
            "memory": config.get("memory", 512),
            "cores": config.get("cores", 1),
            "ostemplate": config["ostemplate"],
            "rootfs": f"{storage}:{rootfs_size}",
            "net0": config.get("net", "name=eth0,bridge=vmbr0,ip=dhcp"),
            "unprivileged": config.get("unprivileged", 1),
            "start": 1 if config.get("start", False) else 0,
        }
        if "password" in config:
            params["password"] = config["password"]
        if "ssh_keys" in config:
            params["ssh-public-keys"] = config["ssh_keys"]

        resp = self._api("POST", f"/nodes/{self._node}/lxc", params)
        if resp.get("data") is None and resp.get("errors"):
            raise RuntimeError(f"Container provision failed: {resp['errors']}")

        return {
            "external_id": str(vmid),
            "resource_type": "container",
            "display_name": params["hostname"],
            "status": "running" if config.get("start") else "stopped",
        }

    def _next_vmid(self) -> int:
        """Get next available VMID from Proxmox cluster."""
        resp = self._api("GET", "/cluster/nextid")
        return int(resp.get("data", 100))

    def terminate(self, resource_id: str) -> bool:
        """Stop and destroy a VM."""
        self._api("POST", f"/nodes/{self._node}/qemu/{resource_id}/status/stop")
        resp = self._api("DELETE", f"/nodes/{self._node}/qemu/{resource_id}")
        return resp.get("data") is not None

    def get_spending(self, period: str) -> float:
        return 0.0  # Self-hosted — no cloud spending

    def scale_down(self, resource_id: str) -> bool:
        """Shut down a VM gracefully."""
        resp = self._api("POST", f"/nodes/{self._node}/qemu/{resource_id}/status/shutdown")
        return resp.get("data") is not None

    def start(self, resource_id: str) -> bool:
        """Start a VM."""
        resp = self._api("POST", f"/nodes/{self._node}/qemu/{resource_id}/status/start")
        return resp.get("data") is not None

    def health_check(self, resource_id: str) -> dict[str, Any]:
        try:
            result = self.get_resource(resource_id)
            return {"status": result.get("status", "unknown"), "resource_id": resource_id}
        except Exception as e:
            return {"status": "error", "resource_id": resource_id, "error": str(e)}

    def get_node_status(self) -> dict[str, Any]:
        """Get node resource usage (CPU, memory, storage)."""
        resp = self._api("GET", f"/nodes/{self._node}/status")
        data = resp.get("data", {})
        mem = data.get("memory", {})
        cpu_info = data.get("cpuinfo", {})
        return {
            "node": self._node,
            "uptime": data.get("uptime", 0),
            "cpu_cores": cpu_info.get("cores", 0) * cpu_info.get("sockets", 1),
            "cpu_usage": round(data.get("cpu", 0) * 100, 1),
            "memory_total_gb": round(mem.get("total", 0) / (1024 ** 3), 2),
            "memory_used_gb": round(mem.get("used", 0) / (1024 ** 3), 2),
            "memory_usage_pct": round(mem.get("used", 0) / max(mem.get("total", 1), 1) * 100, 1),
        }

    def list_storage(self) -> list[dict[str, Any]]:
        """List storage pools on the node."""
        resp = self._api("GET", f"/nodes/{self._node}/storage")
        return [
            {
                "storage": s.get("storage", ""),
                "type": s.get("type", ""),
                "total_gb": round(s.get("total", 0) / (1024 ** 3), 2),
                "used_gb": round(s.get("used", 0) / (1024 ** 3), 2),
                "avail_gb": round(s.get("avail", 0) / (1024 ** 3), 2),
                "active": s.get("active", 0) == 1,
            }
            for s in resp.get("data", [])
        ]

    def _api(self, method: str, path: str, data: dict | None = None) -> dict:
        """Make an authenticated Proxmox API request."""
        url = f"{self._base_url}/api2/json{path}"
        headers = {
            "Authorization": f"PVEAPIToken={self._token_id}={self._token_secret}",
            "Content-Type": "application/json",
        }

        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=headers, method=method)

        ctx = ssl.create_default_context()
        if not self._verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        try:
            with urlopen(req, context=ctx) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            logger.error("Proxmox API error %s %s: %s", method, path, error_body)
            return {"data": None, "errors": error_body}
