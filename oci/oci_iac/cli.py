"""CLI entry point — Click-based command line interface for OCI IaC."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__
from .common import (
    TransactionLog,
    console,
    die,
    init_logging,
    log,
    print_detail,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from .config import ReprovisionConfig


@click.group()
@click.version_option(__version__, prog_name="oci-iac")
def cli() -> None:
    """OCI IaC — Interactive infrastructure automation for Oracle Cloud."""


@cli.command()
@click.option("--profile", default="DEFAULT", help="OCI config profile name.")
@click.option(
    "--instance-config",
    type=click.Path(exists=False),
    default=None,
    help="Path to instance config file.",
)
@click.option("--instance-id", default="", help="Instance OCID (skip selection).")
@click.option("--image-id", default="", help="Ubuntu image OCID (skip selection).")
@click.option("--ssh-key", default="", help="SSH public key file path.")
@click.option("--cloud-init", default="", help="Cloud-init YAML file path.")
@click.option(
    "--arch",
    type=click.Choice(["x86", "arm"], case_sensitive=False),
    default=None,
    help="Force architecture (auto-detected if not set).",
)
@click.option("--skip-backup", is_flag=True, help="Skip boot volume backup.")
@click.option("--dry-run", is_flag=True, help="Preview operations without executing.")
@click.option(
    "--non-interactive", is_flag=True, help="Skip prompts (requires all IDs via flags/config)."
)
def reprovision(
    profile: str,
    instance_config: str | None,
    instance_id: str,
    image_id: str,
    ssh_key: str,
    cloud_init: str,
    arch: str | None,
    skip_backup: bool,
    dry_run: bool,
    non_interactive: bool,
) -> None:
    """Reprovision an OCI VM by replacing its boot volume with a fresh Ubuntu image.

    \b
    The instance is NOT deleted — VNIC, IP address, and shape are preserved.
    The old boot volume can be kept for rollback.

    \b
    Run without flags for a fully guided interactive experience.

    \b
    Examples:
        oci-iac reprovision                         # Interactive
        oci-iac reprovision --dry-run               # Preview only
        oci-iac reprovision --profile PROD           # Use specific profile
        oci-iac reprovision --instance-id ocid1...   # Parameterised
    """
    # Lazy imports to keep --help fast
    from .auth import verify_oci_config
    from .cloud_init import (
        build_instance_metadata,
        configure_user,
        prepare_cloud_init,
        select_cloud_init_template,
        select_ssh_key,
    )
    from .compute import (
        get_instance_state,
        select_image,
        select_instance,
        start_instance,
        stop_instance,
    )
    from .networking import fetch_instance_network_info, verify_ssh_connectivity
    from .storage import check_storage_quota, recover_detached_boot_volume, replace_boot_volume

    # --- Build config -------------------------------------------------------
    cfg = ReprovisionConfig(
        oci_profile=profile,
        instance_ocid=instance_id,
        image_ocid=image_id,
        ssh_public_key_path=ssh_key,
        cloud_init_path=cloud_init,
        arch=arch or "",
        skip_backup=skip_backup,
        dry_run=dry_run,
        non_interactive=non_interactive,
    )

    config_path = Path(instance_config) if instance_config else None
    cfg.load_from_file(config_path)

    # --- Initialise ---------------------------------------------------------
    print_header("OCI VM Reprovisioning (Python SDK)")
    if cfg.dry_run:
        print_warning("DRY-RUN MODE — no changes will be made")
        console.print()

    log_file = init_logging("reprovision")
    txlog = TransactionLog("reprovision-vm")

    # --- Step 1: OCI Auth ---------------------------------------------------
    txlog.step("1-oci-auth", "OCI Profile & API Configuration")
    clients = verify_oci_config(cfg)
    txlog.step_update("done")

    # --- Step 2: Select Instance --------------------------------------------
    txlog.step("2-instance", "Select Instance to Reprovision")
    select_instance(clients, cfg)
    fetch_instance_network_info(clients, cfg)
    txlog.step_update("done")

    # --- Step 3: Select Image -----------------------------------------------
    txlog.step("3-image", "Select Ubuntu Image")
    select_image(clients, cfg)
    txlog.step_update("done")

    # --- Step 4: SSH Key ----------------------------------------------------
    txlog.step("4-ssh-key", "SSH Key Configuration")
    select_ssh_key(cfg)
    txlog.step_update("done")

    # --- Step 5: User Config ------------------------------------------------
    txlog.step("5-user-config", "OS User & Password Configuration")
    configure_user(cfg)
    cfg.save_to_file()
    txlog.step_update("done")

    # --- Step 6: Cloud-Init -------------------------------------------------
    txlog.step("6-cloud-init", "Cloud-Init Configuration")
    select_cloud_init_template(cfg)
    prepare_cloud_init(cfg)
    txlog.step_update("done")

    # --- Step 7: Confirmation -----------------------------------------------
    txlog.step("7-confirm", "Final Confirmation")
    _step_confirm(cfg)
    txlog.step_update("done")

    # --- Step 8: Execute ----------------------------------------------------
    txlog.step("8-execute", "Execute Boot Volume Replacement")
    _step_execute(clients, cfg, txlog)
    txlog.step_update("done")

    # --- Done ---------------------------------------------------------------
    txlog.finalize("success", "Boot volume replacement completed")
    txlog.step("9-summary", "Summary")
    _step_summary(cfg, log_file, txlog)
    txlog.step_update("done")

    print_detail(f"JSON log: {txlog.path}")


# ---------------------------------------------------------------------------
# Internal workflow steps
# ---------------------------------------------------------------------------

def _step_confirm(cfg: ReprovisionConfig) -> None:
    from .common import confirm as ask_confirm

    print_header("Review & Confirm")
    console.print("[bold]  The following operations will be performed:[/bold]")
    console.print()

    lines = [
        f"Instance:     {cfg.instance_ocid}",
        f"Architecture: {cfg.arch}",
        f"New Image:    {cfg.image_ocid}",
        f"SSH Key:      {cfg.ssh_public_key_path}",
        f"Admin User:   {cfg.new_username}",
        f"CloudPanel:   {cfg.install_cloudpanel}",
    ]
    if cfg.cloud_init_prepared:
        lines.append(f"Cloud-Init:   {Path(cfg.cloud_init_prepared).name}")
    lines.append(f"Boot Vol Size: {cfg.boot_volume_size_gb} GB")
    lines.append("")
    lines.append("WORKFLOW:")
    lines.append("1. Stop instance (if running)")
    lines.append("2. Replace boot volume via image (atomic OCI API)")
    lines.append("3. Start instance with new OS + cloud-init")
    lines.append("4. Verify SSH connectivity")
    if cfg.delete_old_bv:
        lines.append("⚠ Old boot volume will be DELETED (no rollback)")
    else:
        lines.append("✔ Old boot volume preserved for rollback")

    from rich.panel import Panel

    console.print(Panel("\n".join(lines), border_style="cyan"))
    console.print()

    if cfg.dry_run:
        print_warning("DRY-RUN: No changes will be made. Exiting.")
        log("DRY-RUN complete. No changes made.")
        sys.exit(0)

    if not ask_confirm("Proceed with reprovisioning? THIS WILL REPLACE THE OS"):
        print_info("Aborted by user.")
        log("Operation aborted by user")
        sys.exit(0)


def _step_execute(
    clients,
    cfg: ReprovisionConfig,
    txlog: TransactionLog,
) -> None:
    from .cloud_init import build_instance_metadata
    from .compute import get_instance_state, start_instance, stop_instance
    from .networking import verify_ssh_connectivity
    from .storage import check_storage_quota, recover_detached_boot_volume, replace_boot_volume

    print_header("Executing Reprovisioning")
    log("Starting reprovisioning workflow...")

    # 8.0: Pre-flight quota check
    txlog.step("8.0-quota-check", "Pre-flight storage quota check")
    check_storage_quota(clients, cfg)
    txlog.step_update("done")

    # 8.0b: Recovery check
    txlog.step("8.0b-state-check", "Checking instance and boot volume state")
    state = get_instance_state(clients, cfg.instance_ocid)

    attached_count = 0
    try:
        attachments = clients.compute.list_boot_volume_attachments(
            cfg.availability_domain,
            cfg.compartment_ocid,
            instance_id=cfg.instance_ocid,
        ).data
        attached_count = len(
            [a for a in attachments if a.lifecycle_state == "ATTACHED"]
        )
    except Exception:
        pass
    txlog.step_update("done", f"instance_state={state}, bv_attached={attached_count}")

    if state == "STOPPED" and attached_count == 0:
        txlog.step("8.0c-recovery", "Recovery: re-attach boot volume")
        if not recover_detached_boot_volume(clients, cfg):
            txlog.step_update("done", "User chose to abort replacement")
            txlog.finalize("aborted", "User chose to restore previous state")
            sys.exit(0)
        txlog.step_update("done")

    # 8.2: Prepare metadata
    txlog.step("8.2-metadata", "Preparing instance metadata")
    metadata = build_instance_metadata(cfg)
    print_success("Metadata prepared (SSH key + cloud-init)")
    txlog.step_update("done")

    # 8.3: Stop instance if running
    state = get_instance_state(clients, cfg.instance_ocid)
    if state == "RUNNING":
        txlog.step("8.3-stop", "Stopping instance")
        stop_instance(clients, cfg)
        txlog.step_update("done")

    # 8.4: Replace boot volume
    txlog.step("8.4-replace-bv", "Replace boot volume via OCI atomic API")
    new_bv_id = replace_boot_volume(clients, cfg, metadata)
    txlog.step_update("done", f"new_bv={new_bv_id}")

    # 8.5: Start instance
    new_state = get_instance_state(clients, cfg.instance_ocid)
    if new_state != "RUNNING":
        txlog.step("8.5-start", "Starting instance")
        start_instance(clients, cfg)
        txlog.step_update("done")

    # 8.6: Verify SSH
    from .networking import fetch_instance_network_info

    fetch_instance_network_info(clients, cfg)
    txlog.step("8.6-ssh-verify", "Verifying SSH connectivity")
    if verify_ssh_connectivity(cfg):
        txlog.step_update("done", f"ssh_ok={cfg.new_username}@{cfg.public_ip}")
    else:
        txlog.step_update("warning", "SSH not yet available")

    log("Reprovisioning complete")


def _step_summary(cfg: ReprovisionConfig, log_file, txlog: TransactionLog) -> None:
    print_header("Reprovisioning Complete!")

    console.print("[bold green]  Summary:[/bold green]")
    print_detail(f"Instance:          {cfg.instance_ocid}")
    print_detail(f"New Image:         {cfg.image_ocid}")
    print_detail(f"New Boot Volume:   {cfg.new_bv_id or 'N/A'}")
    if cfg.delete_old_bv:
        print_detail(f"Old Boot Volume:   {cfg.current_boot_volume_id} (not preserved)")
    else:
        print_detail(f"Old Boot Volume:   {cfg.current_boot_volume_id} (preserved)")
    print_detail(f"Admin User:        {cfg.new_username}")
    print_detail(f"CloudPanel:        {cfg.install_cloudpanel}")
    print_detail(f"Log File:          {log_file}")
    print_detail(f"JSON Log:          {txlog.path}")
    console.print()

    if not cfg.delete_old_bv:
        print_info(
            "ROLLBACK: To revert, use OCI Console 'Replace boot volume' "
            f"with: {cfg.current_boot_volume_id}"
        )
        console.print()
    else:
        print_warning("No rollback available — old boot volume was not preserved.")
        console.print()

    if cfg.install_cloudpanel:
        console.print("[bold cyan]  CloudPanel Access:[/bold cyan]")
        print_detail("URL:  https://<instance-public-ip>:8443")
        print_detail("Note: CloudPanel may take 5-10 minutes to finish installing.")
        print_detail(
            f"      Check: ssh {cfg.new_username}@<ip> 'systemctl status clp'"
        )
        console.print()

    ip_display = cfg.public_ip or "<instance-public-ip>"
    print_info(
        f"SSH access: ssh -i {cfg.ssh_private_key_path} {cfg.new_username}@{ip_display}"
    )
    console.print()
