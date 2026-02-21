"""Configuration dataclass — loads from instance-config key=value files."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

from ...common import print_info, print_success, print_detail
from .helpers import oci_dir

# ---------------------------------------------------------------------------
# Field name mapping: config-file key → dataclass attribute
# ---------------------------------------------------------------------------
_KEY_MAP: dict[str, str] = {
    "OCI_PROFILE": "oci_profile",
    "COMPARTMENT_OCID": "compartment_ocid",
    "INSTANCE_OCID": "instance_ocid",
    "SSH_PUBLIC_KEY_PATH": "ssh_public_key_path",
    "SSH_PRIVATE_KEY_PATH": "ssh_private_key_path",
    "NEW_USERNAME": "new_username",
    "NEW_PASSWORD": "new_password",
    "INSTALL_CLOUDPANEL": "install_cloudpanel",
    "CLOUDPANEL_ADMIN_EMAIL": "cloudpanel_admin_email",
    "CLOUDPANEL_DB_ENGINE": "cloudpanel_db_engine",
    "CLOUD_INIT_PATH": "cloud_init_path",
    "ARCH": "arch",
    "AVAILABILITY_DOMAIN": "availability_domain",
    "BOOT_VOLUME_SIZE_GB": "boot_volume_size_gb",
    "IMAGE_OCID": "image_ocid",
}


@dataclass
class ReprovisionConfig:
    """All parameters for a reprovision operation.

    Values can originate from (highest precedence first):
      1. CLI flags  (set directly on the instance after construction)
      2. Instance config file  (loaded via :meth:`load_from_file`)
      3. Defaults defined here
    """

    # OCI auth
    oci_profile: str = "DEFAULT"
    compartment_ocid: str = ""
    tenancy_ocid: str = ""
    region: str = ""

    # Instance
    instance_ocid: str = ""
    instance_name: str = ""
    arch: str = ""
    availability_domain: str = ""

    # Image
    image_ocid: str = ""

    # Boot volume
    boot_volume_size_gb: int = 0
    current_boot_volume_id: str = ""
    current_boot_attach_id: str = ""
    skip_backup: bool = False
    delete_old_bv: bool = False

    # SSH
    ssh_public_key_path: str = ""
    ssh_private_key_path: str = ""

    # OS user
    new_username: str = "admin"
    new_password: str = ""

    # Cloud-init
    cloud_init_path: str = ""
    cloud_init_prepared: str = ""

    # CloudPanel
    install_cloudpanel: bool = False
    cloudpanel_admin_email: str = ""
    cloudpanel_db_engine: str = "MYSQL_8.4"

    # Runtime
    dry_run: bool = False
    non_interactive: bool = False

    # Network (populated at runtime)
    public_ip: str = ""
    private_ip: str = ""

    # Result
    new_bv_id: str = ""

    # -- loading from file ---------------------------------------------------

    @classmethod
    def default_config_path(cls) -> Path:
        return oci_dir() / "local" / "config" / "instance-config"

    def load_from_file(self, path: Optional[Path] = None) -> bool:
        """Load key=value config from *path*. Returns True if file existed."""
        p = path or self.default_config_path()
        if not p.is_file():
            print_info(f"No instance config found at: {p}")
            print_info("Tip: Copy the template to create your config file:")
            print_detail(
                "cp oci/templates/instance-config.template oci/local/config/instance-config"
            )
            return False

        print_success(f"Loading instance config from: {p}")
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            attr = _KEY_MAP.get(key)
            if attr is None:
                continue
            # Only set if current value is the default (CLI flags take precedence)
            current = getattr(self, attr)
            if isinstance(current, bool):
                if not current:
                    setattr(self, attr, value.lower() in ("true", "1", "yes"))
            elif isinstance(current, int):
                if current == 0:
                    try:
                        setattr(self, attr, int(value))
                    except ValueError:
                        pass
            else:
                if not current or (attr == "oci_profile" and current == "DEFAULT"):
                    setattr(self, attr, value)
        return True

    # -- serialisation -------------------------------------------------------

    def save_to_file(self, path: Optional[Path] = None) -> Path:
        """Persist current config to *path* for future re-use."""
        p = path or self.default_config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        # Build reverse map
        rev = {v: k for k, v in _KEY_MAP.items()}
        lines = [
            "# OCI Instance Reprovisioning Configuration",
            f"# Saved by oci-iac at {__import__('datetime').datetime.now().isoformat()}",
            "",
        ]
        for f in fields(self):
            env_key = rev.get(f.name)
            if env_key is None:
                continue
            val = getattr(self, f.name)
            if isinstance(val, bool):
                val = "true" if val else "false"
            if val:
                lines.append(f"{env_key}={val}")
        p.write_text("\n".join(lines) + "\n")
        print_success(f"Config saved to: {p}")
        return p
