"""Storage operations — quota checks, boot volume replacement, recovery."""

from __future__ import annotations

import time
from typing import Optional

import oci

from .auth import OCIClients
from ...common import (
    TIMESTAMP,
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
# Quota check
# ---------------------------------------------------------------------------

def check_storage_quota(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Check block storage quota and help user free space if needed."""
    print_step("Checking storage quota...")

    tenancy_ocid = cfg.tenancy_ocid

    # Get the first availability domain
    ads = clients.identity.list_availability_domains(tenancy_ocid).data
    ad_name = ads[0].name if ads else cfg.availability_domain

    # Get free-tier storage limit
    storage_limit: Optional[int] = None
    try:
        limit_resp = oci.pagination.list_call_get_all_results(
            clients.limits.list_limit_values,
            tenancy_ocid,
            service_name="block-storage",
        )
        for lv in limit_resp.data:
            if lv.name == "total-free-storage-gb":
                storage_limit = int(lv.value) if lv.value else None
                break
    except oci.exceptions.ServiceError:
        pass

    if storage_limit is None:
        print_info("Could not determine storage quota. Proceeding anyway.")
        return

    # Measure usage: boot volumes + backups + block volumes
    bv_usage = 0
    try:
        bv_list = oci.pagination.list_call_get_all_results(
            clients.blockstorage.list_boot_volumes,
            availability_domain=ad_name,
            compartment_id=tenancy_ocid,
        ).data
        bv_usage = sum(bv.size_in_gbs or 0 for bv in bv_list)
    except oci.exceptions.ServiceError:
        bv_list = []

    backup_usage = 0
    try:
        backup_list = oci.pagination.list_call_get_all_results(
            clients.blockstorage.list_boot_volume_backups,
            compartment_id=tenancy_ocid,
        ).data
        backup_usage = sum(b.size_in_gbs or 0 for b in backup_list)
    except oci.exceptions.ServiceError:
        backup_list = []

    vol_usage = 0
    try:
        vol_list = oci.pagination.list_call_get_all_results(
            clients.blockstorage.list_volumes,
            compartment_id=tenancy_ocid,
            availability_domain=ad_name,
        ).data
        vol_usage = sum(v.size_in_gbs or 0 for v in vol_list)
    except oci.exceptions.ServiceError:
        vol_list = []

    total_used = bv_usage + backup_usage + vol_usage
    available = storage_limit - total_used

    console.print()
    print_info("┌─── Block Storage Quota ─────────────────────────────────┐")
    print_info(f"│ Free tier limit:     {storage_limit} GB")
    print_info(f"│ Boot volumes:        {bv_usage} GB")
    print_info(f"│ Boot vol backups:    {backup_usage} GB")
    print_info(f"│ Block volumes:       {vol_usage} GB")
    print_info(f"│ Total used:          {total_used} GB")
    print_info(f"│ Available:           {available} GB")
    print_info(f"│ Needed for new BV:   {cfg.boot_volume_size_gb} GB")
    print_info("└─────────────────────────────────────────────────────────┘")
    console.print()
    log(f"Storage quota: limit={storage_limit}GB, used={total_used}GB, available={available}GB")

    if available >= cfg.boot_volume_size_gb:
        print_success("Sufficient storage available.")
        return

    # Help user free space
    print_warning(
        f"NOT ENOUGH STORAGE for a new {cfg.boot_volume_size_gb} GB boot volume."
    )
    needed = cfg.boot_volume_size_gb - available
    print_info(f"You need to free up {needed} GB.")
    console.print()

    strategies = [
        "Don't preserve old boot volume (OCI replaces in-place — no rollback)",
    ]
    strategy_keys = ["delete_old_bv"]

    if backup_list:
        strategies.append(
            f"Delete existing backup(s) (frees {backup_usage} GB from {len(backup_list)} backup(s))"
        )
        strategy_keys.append("delete_backups")

    strategies.append("Abort — I'll free space manually")
    strategy_keys.append("abort")

    freed = 0
    while available + freed < cfg.boot_volume_size_gb:
        idx = prompt_selection(strategies, "Free up storage")
        action = strategy_keys[idx]

        if action == "delete_old_bv":
            cfg.delete_old_bv = True
            freed += cfg.boot_volume_size_gb
            print_success(
                f"Will NOT preserve old boot volume — frees {cfg.boot_volume_size_gb} GB"
            )
            print_warning("No rollback possible after replacement.")
            # Remove this option
            strategies = [s for i, s in enumerate(strategies) if strategy_keys[i] != "delete_old_bv"]
            strategy_keys = [k for k in strategy_keys if k != "delete_old_bv"]

        elif action == "delete_backups":
            items = [
                f"{b.display_name or '?'} ({b.size_in_gbs or 0} GB)"
                for b in backup_list
            ]
            items.append("Cancel — don't delete any")
            bidx = prompt_selection(items, "Which backup to delete")
            if bidx < len(backup_list):
                bk = backup_list[bidx]
                if confirm(f"Delete backup '{bk.display_name}'? This cannot be undone."):
                    print_info("Deleting backup...")
                    clients.blockstorage.delete_boot_volume_backup(bk.id)
                    freed += bk.size_in_gbs or 0
                    print_success(f"Deleted. Freed {bk.size_in_gbs} GB.")
                    log(f"Deleted backup {bk.id} ({bk.size_in_gbs} GB)")

        elif action == "abort":
            print_info("Quota management tips:")
            print_detail("• Delete unused boot volumes via OCI Console or CLI")
            print_detail("• Delete backups via OCI Console or CLI")
            die("Not enough storage. Free up space and re-run.")

    print_success(f"Storage strategy set. Proceeding with {available + freed} GB available.")
    log(f"Storage freed: {freed}GB, delete_old_bv={cfg.delete_old_bv}")


# ---------------------------------------------------------------------------
# Boot volume replacement (atomic OCI API)
# ---------------------------------------------------------------------------

def replace_boot_volume(
    clients: OCIClients,
    cfg: ReprovisionConfig,
    metadata: dict,
) -> str:
    """Replace boot volume via UpdateInstance API. Returns new BV OCID."""
    print_step("Replacing boot volume with new Ubuntu image...")
    print_info(
        "Atomic operation: OCI creates new BV from image, "
        "detaches old, attaches new."
    )

    preserve = not cfg.delete_old_bv
    if preserve:
        print_info("Old boot volume will be preserved for rollback.")
    else:
        print_info("Old boot volume will NOT be preserved (quota strategy).")

    source_details = oci.core.models.UpdateInstanceSourceViaImageDetails(
        image_id=cfg.image_ocid,
        boot_volume_size_in_gbs=cfg.boot_volume_size_gb,
        is_preserve_boot_volume_enabled=preserve,
    )
    update_details = oci.core.models.UpdateInstanceDetails(
        source_details=source_details,
        metadata=metadata,
    )

    try:
        clients.compute.update_instance(cfg.instance_ocid, update_details)
    except oci.exceptions.ServiceError as exc:
        print_error(f"Boot volume replacement failed: {exc.message}")
        die("Replace boot volume failed. Check OCI Console and try again.")

    log("Replace boot volume command accepted.")
    print_success("Replace boot volume initiated. Waiting for completion...")

    # Poll for new boot volume attachment
    old_bv = cfg.current_boot_volume_id
    new_bv_id = ""
    wait_max = 1200
    wait_elapsed = 0
    while wait_elapsed < wait_max:
        try:
            attachments = clients.compute.list_boot_volume_attachments(
                cfg.availability_domain,
                cfg.compartment_ocid,
                instance_id=cfg.instance_ocid,
            ).data
            attached = [a for a in attachments if a.lifecycle_state == "ATTACHED"]
            if attached:
                bv_id = attached[0].boot_volume_id
                if bv_id != old_bv:
                    new_bv_id = bv_id
                    break
        except oci.exceptions.ServiceError:
            pass

        console.print(
            f"\r    Replacing boot volume... Elapsed: {wait_elapsed}s / {wait_max}s",
            end="",
        )
        time.sleep(15)
        wait_elapsed += 15

    console.print()

    if not new_bv_id:
        die(f"Timeout waiting for boot volume replacement after {wait_max}s")

    cfg.new_bv_id = new_bv_id
    log(f"Boot volume replaced. New BV: {new_bv_id}")
    print_success(f"Boot volume replaced! New BV: {new_bv_id}")
    return new_bv_id


# ---------------------------------------------------------------------------
# Recovery: re-attach detached boot volume
# ---------------------------------------------------------------------------

def recover_detached_boot_volume(
    clients: OCIClients, cfg: ReprovisionConfig
) -> bool:
    """Re-attach a detached boot volume from a failed run.

    Returns True if replacement should continue, False if user chose to abort.
    """
    print_warning(
        "Recovery detected: Instance is STOPPED with NO boot volume attached."
    )
    print_info("Previous run likely failed after detaching boot volume.")
    print_info("Re-attaching old boot volume so the replace command can proceed.")
    console.print()

    actions = [
        "Re-attach old BV and continue with replacement",
        "Re-attach old BV and abort (restore previous state)",
    ]
    idx = prompt_selection(actions, "How would you like to proceed")

    _reattach_boot_volume(clients, cfg)

    if idx == 1:
        # Abort — just restore
        from .compute import start_instance
        start_instance(clients, cfg)
        print_success("Instance restored to previous state.")
        return False

    print_success("Old boot volume re-attached. Ready for replacement.")
    return True


def _reattach_boot_volume(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Re-attach the current boot volume to the instance."""
    print_step("Re-attaching old boot volume...")
    try:
        attach_details = oci.core.models.AttachBootVolumeDetails(
            boot_volume_id=cfg.current_boot_volume_id,
            instance_id=cfg.instance_ocid,
            display_name=f"recovery-reattach-{TIMESTAMP}",
        )
        clients.compute.attach_boot_volume(attach_details)
    except oci.exceptions.ServiceError as exc:
        print_warning(f"Re-attach call returned: {exc.message}")

    # Wait for attachment
    print_info("Waiting for boot volume to attach...")
    for _ in range(6):
        time.sleep(15)
        attachments = clients.compute.list_boot_volume_attachments(
            cfg.availability_domain,
            cfg.compartment_ocid,
            instance_id=cfg.instance_ocid,
        ).data
        attached = [a for a in attachments if a.lifecycle_state == "ATTACHED"]
        if attached:
            print_success("Boot volume attached.")
            return
    print_warning("Boot volume may still be attaching — check OCI Console.")
