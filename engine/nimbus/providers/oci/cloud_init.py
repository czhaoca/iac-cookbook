"""Cloud-init — SSH key selection, user config, template processing, metadata."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ...common import (
    confirm,
    console,
    die,
    log,
    log_quiet,
    print_detail,
    print_header,
    print_info,
    print_step,
    print_success,
    print_warning,
    prompt_input,
    prompt_password,
    prompt_selection,
)
from .helpers import oci_dir
from .config import ReprovisionConfig

# ---------------------------------------------------------------------------
# SSH key selection / generation
# ---------------------------------------------------------------------------

def select_ssh_key(cfg: ReprovisionConfig) -> None:
    """Interactively select or generate an SSH key pair."""
    print_header("SSH Key Configuration")
    print_info("The new OS will be configured with SSH key-only authentication.")
    print_info("Password login will be DISABLED for security.")
    console.print()

    ssh_dir = oci_dir() / "local" / "ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    # Already set via config/flag?
    if cfg.ssh_public_key_path and Path(cfg.ssh_public_key_path).is_file():
        print_success(f"SSH public key: {cfg.ssh_public_key_path}")
        _ensure_private_key(cfg)
        return

    # Discover keys
    repo_keys = _find_pub_keys(ssh_dir)
    home_keys = _find_pub_keys(Path.home() / ".ssh")

    all_keys: list[Path] = []
    labels: list[str] = []
    for k in repo_keys:
        all_keys.append(k)
        labels.append(f"[repo] {k}")
    for k in home_keys:
        all_keys.append(k)
        labels.append(f"[home] {k}")
    labels.append("Generate a new SSH key")

    if not repo_keys and not home_keys:
        print_warning(f"No SSH keys found in {ssh_dir} or ~/.ssh/")
        print_info("Let's generate a new SSH key pair.")

    idx = prompt_selection(labels, "Choose an SSH public key")

    if idx == len(all_keys):
        # Generate new key
        _generate_ssh_key(cfg, ssh_dir)
    else:
        cfg.ssh_public_key_path = str(all_keys[idx])
        cfg.ssh_private_key_path = str(all_keys[idx]).removesuffix(".pub")

        # Offer to copy home key to repo
        if all_keys[idx].is_relative_to(Path.home() / ".ssh"):
            if confirm(f"Copy this key to {ssh_dir} for this project?"):
                shutil.copy2(all_keys[idx], ssh_dir)
                priv = Path(cfg.ssh_private_key_path)
                if priv.is_file():
                    shutil.copy2(priv, ssh_dir)
                    os.chmod(ssh_dir / priv.name, 0o600)
                cfg.ssh_public_key_path = str(ssh_dir / all_keys[idx].name)
                cfg.ssh_private_key_path = str(ssh_dir / all_keys[idx].stem)
                print_success(f"Key copied to: {ssh_dir}/")

    _ensure_private_key(cfg)
    log_quiet(f"SSH public key: {cfg.ssh_public_key_path}")
    _show_fingerprint(cfg.ssh_public_key_path)


def _find_pub_keys(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.pub"))


def _generate_ssh_key(cfg: ReprovisionConfig, ssh_dir: Path) -> None:
    from datetime import datetime

    default_name = f"oci_iac_{datetime.now().strftime('%Y%m%d')}"
    print_info(f"Default name: {default_name}")
    key_name = prompt_input("SSH key name", default=default_name)
    key_path = Path.home() / ".ssh" / key_name

    if key_path.exists():
        print_warning(f"Key already exists: {key_path}")
        if confirm("Use existing key instead of overwriting?"):
            cfg.ssh_public_key_path = str(key_path) + ".pub"
            cfg.ssh_private_key_path = str(key_path)
            return

    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-C", key_name],
        check=True,
    )
    cfg.ssh_public_key_path = str(key_path) + ".pub"
    cfg.ssh_private_key_path = str(key_path)
    print_success("SSH key generated:")
    print_detail(f"Private: {cfg.ssh_private_key_path}")
    print_detail(f"Public:  {cfg.ssh_public_key_path}")

    # Copy to repo ssh dir
    shutil.copy2(cfg.ssh_public_key_path, ssh_dir)
    shutil.copy2(cfg.ssh_private_key_path, ssh_dir)
    os.chmod(ssh_dir / key_name, 0o600)
    print_info(f"Key also copied to: {ssh_dir}/ (gitignored)")


def _ensure_private_key(cfg: ReprovisionConfig) -> None:
    if not cfg.ssh_private_key_path:
        cfg.ssh_private_key_path = cfg.ssh_public_key_path.removesuffix(".pub")
    if not Path(cfg.ssh_private_key_path).is_file():
        print_warning(
            f"Private key not found: {cfg.ssh_private_key_path}. "
            f"SSH verification may fail."
        )


def _show_fingerprint(pub_key_path: str) -> None:
    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", pub_key_path],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            fp = result.stdout.strip().split()[1] if result.stdout else "?"
            print_detail(f"Key fingerprint: {fp}")
    except FileNotFoundError:
        pass

# ---------------------------------------------------------------------------
# User & OS configuration
# ---------------------------------------------------------------------------

def configure_user(cfg: ReprovisionConfig) -> None:
    """Prompt for admin username, password, and CloudPanel options."""
    print_header("New User & OS Configuration")
    print_info("Security settings for the new OS:")
    print_detail("• Default 'ubuntu' user will be DISABLED")
    print_detail("• SSH password authentication will be DISABLED")
    print_detail("• Only SSH key login will be allowed")
    print_detail("• A new admin user with sudo access will be created")
    console.print()

    if not cfg.new_username:
        cfg.new_username = prompt_input("New admin username", default="admin")
    print_success(f"Admin username: {cfg.new_username}")

    if not cfg.new_password:
        print_info("Set a password for sudo operations (SSH will use key only).")
        while True:
            pw = prompt_password(f"Password for {cfg.new_username}")
            confirm_pw = prompt_password("Confirm password")
            if pw == confirm_pw:
                cfg.new_password = pw
                break
            print_warning("Passwords don't match. Try again.")
    print_success("Password configured (will be hashed before use)")

    console.print()
    _configure_cloudpanel(cfg)
    log_quiet(
        f"User config: username={cfg.new_username}, cloudpanel={cfg.install_cloudpanel}"
    )


def _configure_cloudpanel(cfg: ReprovisionConfig) -> None:
    print_step("CloudPanel Installation")
    print_info(
        "CloudPanel is a free server control panel for PHP, Node.js, Python apps."
    )
    print_info("It provides a web-based admin UI at https://<your-ip>:8443")
    console.print()

    if not cfg.install_cloudpanel:
        cfg.install_cloudpanel = confirm("Install CloudPanel on the new instance?")
        if cfg.install_cloudpanel:
            print_success("CloudPanel will be installed")
        else:
            print_info("CloudPanel will NOT be installed")

    if cfg.install_cloudpanel and not cfg.cloudpanel_admin_email:
        cfg.cloudpanel_admin_email = prompt_input(
            "CloudPanel admin email", default="admin@example.com"
        )

    if cfg.install_cloudpanel:
        print_info("CloudPanel database engine (per cloudpanel.io docs):")
        engines = [
            "MySQL 8.4 (Recommended)",
            "MySQL 8.0",
            "MariaDB 11.4",
            "MariaDB 10.11",
        ]
        engine_values = ["MYSQL_8.4", "MYSQL_8.0", "MARIADB_11.4", "MARIADB_10.11"]
        idx = prompt_selection(engines, "Choose database engine")
        cfg.cloudpanel_db_engine = engine_values[idx]
        print_success(f"Database engine: {cfg.cloudpanel_db_engine}")

# ---------------------------------------------------------------------------
# Cloud-init template selection & processing
# ---------------------------------------------------------------------------

def select_cloud_init_template(cfg: ReprovisionConfig) -> None:
    """Select a cloud-init YAML template."""
    print_header("Cloud-Init Configuration")
    print_info("Cloud-init runs on first boot to configure the new OS.")
    print_info(
        "It will set up your admin user, SSH keys, and security settings."
    )
    console.print()

    if cfg.cloud_init_path and Path(cfg.cloud_init_path).is_file():
        print_success(f"Cloud-init template: {cfg.cloud_init_path}")
        return

    templates_dir = oci_dir() / "templates" / "cloud-init"
    templates = sorted(templates_dir.glob("*.yaml")) + sorted(
        templates_dir.glob("*.yml")
    )

    if not templates:
        print_warning(f"No cloud-init templates found in {templates_dir}")
        cfg.cloud_init_path = ""
        return

    # Auto-select CloudPanel template if CloudPanel is enabled
    if cfg.install_cloudpanel:
        for t in templates:
            if "cloudpanel" in t.name.lower():
                cfg.cloud_init_path = str(t)
                print_success(f"Auto-selected CloudPanel template: {t.name}")
                return

    labels = []
    for t in templates:
        desc = ""
        with open(t) as f:
            for line in f:
                if line.startswith("# ") and "cloud-config" not in line and "===" not in line:
                    desc = line.lstrip("# ").strip()
                    break
        labels.append(f"{t.name} — {desc}" if desc else t.name)
    labels.append("No cloud-init (manual setup)")

    idx = prompt_selection(labels, "Choose a cloud-init template")
    if idx < len(templates):
        cfg.cloud_init_path = str(templates[idx])
        print_success(f"Selected: {templates[idx].name}")
    else:
        cfg.cloud_init_path = ""
        print_info("No cloud-init template selected")


def prepare_cloud_init(cfg: ReprovisionConfig) -> None:
    """Substitute variables in the cloud-init template."""
    if not cfg.cloud_init_path:
        return

    print_step("Preparing cloud-init with your configuration...")
    prepared_dir = oci_dir() / "local" / "config"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared_file = prepared_dir / "cloud-init-prepared.yaml"

    # Hash password
    result = subprocess.run(
        ["openssl", "passwd", "-6", cfg.new_password],
        capture_output=True,
        text=True,
        check=True,
    )
    password_hash = result.stdout.strip()

    ssh_pub_key = Path(cfg.ssh_public_key_path).read_text().strip()

    template = Path(cfg.cloud_init_path).read_text()
    content = (
        template.replace("__NEW_USERNAME__", cfg.new_username)
        .replace("__NEW_PASSWORD_HASH__", password_hash)
        .replace("__SSH_PUBLIC_KEY__", ssh_pub_key)
        .replace("__CLOUDPANEL_DB_ENGINE__", cfg.cloudpanel_db_engine)
    )
    prepared_file.write_text(content)
    cfg.cloud_init_prepared = str(prepared_file)
    print_success(f"Cloud-init prepared: {prepared_file}")
    log_quiet(f"Cloud-init prepared from {cfg.cloud_init_path}")

# ---------------------------------------------------------------------------
# Build instance metadata dict
# ---------------------------------------------------------------------------

def build_instance_metadata(cfg: ReprovisionConfig) -> dict:
    """Build metadata dict for OCI instance (SSH key + cloud-init user data)."""
    ssh_pub_key = Path(cfg.ssh_public_key_path).read_text().strip()
    metadata: dict[str, str] = {"ssh_authorized_keys": ssh_pub_key}

    if cfg.cloud_init_prepared and Path(cfg.cloud_init_prepared).is_file():
        raw = Path(cfg.cloud_init_prepared).read_bytes()
        metadata["user_data"] = base64.b64encode(raw).decode("ascii")

    return metadata
