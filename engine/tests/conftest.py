"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Create a temporary instance-config file."""
    cfg = tmp_path / "instance-config"
    cfg.write_text(
        "# Test config\n"
        "OCI_PROFILE=TEST-PROFILE\n"
        "COMPARTMENT_OCID=ocid1.compartment.oc1..test\n"
        "INSTANCE_OCID=ocid1.instance.oc1..test\n"
        "NEW_USERNAME=testuser\n"
        "INSTALL_CLOUDPANEL=true\n"
        "CLOUDPANEL_DB_ENGINE=MYSQL_8.0\n"
        "BOOT_VOLUME_SIZE_GB=50\n"
    )
    return cfg


@pytest.fixture
def cloud_init_template(tmp_path: Path) -> Path:
    """Create a minimal cloud-init template."""
    tmpl = tmp_path / "test-cloud-init.yaml"
    tmpl.write_text(
        "#cloud-config\n"
        "users:\n"
        "  - name: __NEW_USERNAME__\n"
        "    passwd: __NEW_PASSWORD_HASH__\n"
        "    ssh_authorized_keys:\n"
        "      - __SSH_PUBLIC_KEY__\n"
    )
    return tmpl
