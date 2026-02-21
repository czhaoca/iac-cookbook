"""Networking operations — VNIC/IP lookup, SSH connectivity verification."""

from __future__ import annotations

import subprocess
import time
from typing import Optional

import oci

from .auth import OCIClients
from ...common import (
    die,
    log,
    print_detail,
    print_info,
    print_step,
    print_success,
    print_warning,
)
from .config import ReprovisionConfig

# ---------------------------------------------------------------------------
# VNIC / IP lookup
# ---------------------------------------------------------------------------

def fetch_instance_network_info(
    clients: OCIClients, cfg: ReprovisionConfig
) -> None:
    """Populate cfg.public_ip and cfg.private_ip from VNIC attachments."""
    print_step("Fetching network information...")

    try:
        vnic_attachments = oci.pagination.list_call_get_all_results(
            clients.compute.list_vnic_attachments,
            cfg.compartment_ocid,
            instance_id=cfg.instance_ocid,
        ).data
    except oci.exceptions.ServiceError as exc:
        print_warning(f"Could not list VNIC attachments: {exc.message}")
        return

    for va in vnic_attachments:
        if va.lifecycle_state != "ATTACHED":
            continue
        try:
            vnic = clients.vnet.get_vnic(va.vnic_id).data
            cfg.public_ip = vnic.public_ip or ""
            cfg.private_ip = vnic.private_ip or ""
            if cfg.public_ip:
                print_success(f"Public IP:  {cfg.public_ip}")
            if cfg.private_ip:
                print_detail(f"Private IP: {cfg.private_ip}")
            log(f"Network: public={cfg.public_ip}, private={cfg.private_ip}")
            return
        except oci.exceptions.ServiceError:
            continue

    print_warning("No public IP found. Instance may not be accessible via SSH.")


def get_public_ip(clients: OCIClients, cfg: ReprovisionConfig) -> str:
    """Return the public IP, fetching if not already populated."""
    if not cfg.public_ip:
        fetch_instance_network_info(clients, cfg)
    return cfg.public_ip


# ---------------------------------------------------------------------------
# SSH connectivity
# ---------------------------------------------------------------------------

def verify_ssh_connectivity(
    cfg: ReprovisionConfig,
    max_retries: int = 20,
    delay: int = 15,
) -> bool:
    """Test SSH access with retries. Returns True on success."""
    ip = cfg.public_ip
    if not ip:
        print_warning("No public IP — skipping SSH verification.")
        return False

    user = cfg.new_username or "ubuntu"
    key = cfg.ssh_private_key_path

    print_step(f"Verifying SSH connectivity ({user}@{ip})...")
    print_info(
        f"New OS may take a few minutes to boot. Retrying up to {max_retries} times."
    )

    for attempt in range(1, max_retries + 1):
        if _try_ssh(ip, user, key):
            print_success(f"SSH connection successful: {user}@{ip}")
            log(f"SSH verified: {user}@{ip}")
            return True
        print_detail(f"  Attempt {attempt}/{max_retries} — retrying in {delay}s...")
        time.sleep(delay)

    print_warning(
        f"SSH not available after {max_retries} attempts. "
        f"Try manually: ssh -i {key} {user}@{ip}"
    )
    return False


def _try_ssh(ip: str, user: str, key_path: str) -> bool:
    """Single SSH connection attempt."""
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",
        "-i", key_path,
        f"{user}@{ip}",
        "echo ok",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
