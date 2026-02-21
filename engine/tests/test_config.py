"""Tests for config.py — loading and saving instance config."""

from __future__ import annotations

from pathlib import Path

from oci_iac.config import ReprovisionConfig


def test_load_from_file(tmp_config: Path) -> None:
    cfg = ReprovisionConfig()
    result = cfg.load_from_file(tmp_config)
    assert result is True
    assert cfg.oci_profile == "TEST-PROFILE"
    assert cfg.compartment_ocid == "ocid1.compartment.oc1..test"
    assert cfg.instance_ocid == "ocid1.instance.oc1..test"
    assert cfg.new_username == "testuser"
    assert cfg.install_cloudpanel is True
    assert cfg.cloudpanel_db_engine == "MYSQL_8.0"
    assert cfg.boot_volume_size_gb == 50


def test_load_missing_file(tmp_path: Path) -> None:
    cfg = ReprovisionConfig()
    result = cfg.load_from_file(tmp_path / "nonexistent")
    assert result is False
    # Defaults should remain
    assert cfg.oci_profile == "DEFAULT"
    assert cfg.new_username == "admin"


def test_cli_flags_override_config(tmp_config: Path) -> None:
    """CLI flags (set before load) should not be overridden by config file."""
    cfg = ReprovisionConfig(
        oci_profile="CLI-PROFILE",
        instance_ocid="ocid1.instance.oc1..cli",
    )
    cfg.load_from_file(tmp_config)
    # CLI values should win
    assert cfg.oci_profile == "CLI-PROFILE"
    assert cfg.instance_ocid == "ocid1.instance.oc1..cli"
    # Config-only values should load
    assert cfg.compartment_ocid == "ocid1.compartment.oc1..test"


def test_save_and_reload(tmp_path: Path) -> None:
    cfg = ReprovisionConfig(
        oci_profile="SAVED",
        compartment_ocid="ocid1.compartment.oc1..saved",
        new_username="saveduser",
        boot_volume_size_gb=100,
    )
    save_path = tmp_path / "saved-config"
    cfg.save_to_file(save_path)

    # Reload
    cfg2 = ReprovisionConfig()
    cfg2.load_from_file(save_path)
    assert cfg2.oci_profile == "SAVED"
    assert cfg2.compartment_ocid == "ocid1.compartment.oc1..saved"
    assert cfg2.new_username == "saveduser"
    assert cfg2.boot_volume_size_gb == 100


def test_comments_and_empty_lines(tmp_path: Path) -> None:
    """Config parser should skip comments and empty lines."""
    cfg_file = tmp_path / "config"
    cfg_file.write_text(
        "# Comment line\n"
        "\n"
        "  # Indented comment\n"
        "NEW_USERNAME=commentuser\n"
        "  \n"
    )
    cfg = ReprovisionConfig()
    cfg.load_from_file(cfg_file)
    assert cfg.new_username == "commentuser"
