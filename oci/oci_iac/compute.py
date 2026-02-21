"""Compute operations — instance listing, image selection, state management."""

from __future__ import annotations

from typing import Optional

import oci
from rich.table import Table

from .auth import OCIClients
from .common import (
    confirm,
    console,
    die,
    log,
    print_detail,
    print_error,
    print_info,
    print_step,
    print_success,
    print_warning,
    prompt_selection,
)
from .config import ReprovisionConfig

# ---------------------------------------------------------------------------
# Instance selection
# ---------------------------------------------------------------------------

def list_instances(
    clients: OCIClients, compartment_id: str
) -> list[oci.core.models.Instance]:
    """List all non-terminated instances in the compartment."""
    resp = oci.pagination.list_call_get_all_results(
        clients.compute.list_instances,
        compartment_id,
    )
    return [
        i for i in resp.data
        if i.lifecycle_state not in ("TERMINATED", "TERMINATING")
    ]


def select_instance(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Interactively select an instance and populate config with its details."""
    print_step("Listing instances in compartment...")
    instances = list_instances(clients, cfg.compartment_ocid)

    if not instances:
        die("No active instances found in this compartment.")

    if cfg.instance_ocid:
        # Pre-set — validate it exists
        match = [i for i in instances if i.id == cfg.instance_ocid]
        if not match:
            die(f"Instance {cfg.instance_ocid} not found or terminated.")
        inst = match[0]
    else:
        table = Table(title="Instances", show_lines=True)
        table.add_column("No.", style="cyan", width=4)
        table.add_column("Name")
        table.add_column("Shape")
        table.add_column("State", style="bold")
        table.add_column("AD")
        for idx, i in enumerate(instances, 1):
            state_style = "green" if i.lifecycle_state == "RUNNING" else "yellow"
            table.add_row(
                str(idx),
                i.display_name or "(unnamed)",
                i.shape,
                f"[{state_style}]{i.lifecycle_state}[/{state_style}]",
                i.availability_domain,
            )
        console.print(table)
        sel = prompt_selection(
            [f"{i.display_name or '(unnamed)'} — {i.shape}" for i in instances],
            "Select instance",
        )
        inst = instances[sel]

    _populate_instance_details(clients, cfg, inst)


def _populate_instance_details(
    clients: OCIClients, cfg: ReprovisionConfig, inst: oci.core.models.Instance
) -> None:
    """Fill config fields from an instance object + boot volume attachment."""
    cfg.instance_ocid = inst.id
    cfg.instance_name = inst.display_name or "(unnamed)"
    cfg.availability_domain = inst.availability_domain
    cfg.arch = _detect_arch(inst.shape)

    print_success(
        f"Selected: {cfg.instance_name} ({cfg.arch}, {inst.shape})"
    )

    # Fetch boot volume attachment
    print_step("Fetching boot volume attachment...")
    bv_attachments = clients.compute.list_boot_volume_attachments(
        cfg.availability_domain,
        cfg.compartment_ocid,
        instance_id=cfg.instance_ocid,
    ).data
    attached = [
        a for a in bv_attachments if a.lifecycle_state == "ATTACHED"
    ]
    if attached:
        bva = attached[0]
        cfg.current_boot_volume_id = bva.boot_volume_id
        cfg.current_boot_attach_id = bva.id

        # Get boot volume size
        bv = clients.blockstorage.get_boot_volume(bva.boot_volume_id).data
        cfg.boot_volume_size_gb = cfg.boot_volume_size_gb or bv.size_in_gbs
        print_success(
            f"Boot volume: {bva.boot_volume_id} ({bv.size_in_gbs} GB)"
        )
    else:
        print_warning("No attached boot volume found — may be mid-replacement.")

    log(
        f"Instance: id={cfg.instance_ocid}, name={cfg.instance_name}, "
        f"arch={cfg.arch}, ad={cfg.availability_domain}, bv={cfg.current_boot_volume_id}"
    )


def _detect_arch(shape: str) -> str:
    """Detect architecture from OCI shape name."""
    shape_lower = shape.lower()
    if "a1" in shape_lower or "ampere" in shape_lower:
        return "arm"
    return "x86"


# ---------------------------------------------------------------------------
# Image selection
# ---------------------------------------------------------------------------

def list_ubuntu_images(
    clients: OCIClients,
    compartment_id: str,
    arch: str = "x86",
) -> list[oci.core.models.Image]:
    """List Ubuntu images matching the target architecture."""
    resp = oci.pagination.list_call_get_all_results(
        clients.compute.list_images,
        compartment_id,
        operating_system="Canonical Ubuntu",
        sort_by="TIMECREATED",
        sort_order="DESC",
    )
    if arch == "arm":
        return [i for i in resp.data if "aarch64" in (i.display_name or "").lower()]
    else:
        return [
            i for i in resp.data
            if "aarch64" not in (i.display_name or "").lower()
        ]


def select_image(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Interactively select an Ubuntu image."""
    print_step(f"Listing Ubuntu images for {cfg.arch} architecture...")
    images = list_ubuntu_images(clients, cfg.compartment_ocid, cfg.arch)

    if not images:
        die(f"No Ubuntu images found for {cfg.arch} architecture.")

    if cfg.image_ocid:
        match = [i for i in images if i.id == cfg.image_ocid]
        if match:
            print_success(f"Using pre-set image: {match[0].display_name}")
            return
        print_warning(f"Pre-set image {cfg.image_ocid} not found in image list — select manually.")
        cfg.image_ocid = ""

    # Show top 10 most recent
    display_images = images[:10]
    table = Table(title="Ubuntu Images", show_lines=True)
    table.add_column("No.", style="cyan", width=4)
    table.add_column("Name")
    table.add_column("Created")
    table.add_column("Size (GB)")
    for idx, img in enumerate(display_images, 1):
        created = img.time_created.strftime("%Y-%m-%d") if img.time_created else "?"
        size = str(img.size_in_mbs // 1024) if img.size_in_mbs else "?"
        table.add_row(str(idx), img.display_name or "?", created, size)
    console.print(table)

    sel = prompt_selection(
        [img.display_name or "?" for img in display_images],
        "Select Ubuntu image",
    )
    cfg.image_ocid = display_images[sel].id
    print_success(f"Image: {display_images[sel].display_name}")
    log(f"Image selected: {cfg.image_ocid}")


# ---------------------------------------------------------------------------
# Instance state management
# ---------------------------------------------------------------------------

def get_instance_state(clients: OCIClients, instance_id: str) -> str:
    resp = clients.compute.get_instance(instance_id)
    return resp.data.lifecycle_state


def stop_instance(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Stop a running instance and wait for STOPPED state."""
    state = get_instance_state(clients, cfg.instance_ocid)
    if state == "STOPPED":
        print_info("Instance already stopped.")
        return
    if state != "RUNNING":
        die(f"Instance in unexpected state: {state}. Expected RUNNING or STOPPED.")

    print_step("Stopping instance...")
    clients.compute.instance_action(cfg.instance_ocid, "SOFTSTOP")
    _wait_for_instance_state(clients, cfg.instance_ocid, "STOPPED")
    print_success("Instance stopped.")
    log("Instance stopped")


def start_instance(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Start a stopped instance and wait for RUNNING state."""
    state = get_instance_state(clients, cfg.instance_ocid)
    if state == "RUNNING":
        print_info("Instance already running.")
        return

    print_step("Starting instance...")
    try:
        clients.compute.instance_action(cfg.instance_ocid, "START")
    except oci.exceptions.ServiceError as exc:
        if exc.status == 409 and "InvalidatedClientTokens" in str(exc.code):
            print_warning("Re-creating compute client for START action...")
            clients._compute = None  # Force fresh client
            clients.compute.instance_action(cfg.instance_ocid, "START")
        else:
            raise
    _wait_for_instance_state(clients, cfg.instance_ocid, "RUNNING")
    print_success("Instance running.")
    log("Instance started")


def _wait_for_instance_state(
    clients: OCIClients,
    instance_id: str,
    target_state: str,
    max_wait: int = 600,
) -> None:
    """Poll until instance reaches *target_state*."""
    print_info(f"Waiting for instance to reach {target_state}...")
    oci.wait_until(
        clients.compute,
        clients.compute.get_instance(instance_id),
        "lifecycle_state",
        target_state,
        max_wait_seconds=max_wait,
        max_interval_seconds=15,
    )
