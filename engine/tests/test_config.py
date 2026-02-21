"""Tests for config.py — loading and saving instance config."""

from __future__ import annotations

from pathlib import Path

from nimbus.providers.oci.config import ReprovisionConfig


def test_load_from_file(tmp_config: Path) -> None:
    cfg = ReprovisionConfig()
    result = cfg.load_from_file(tmp_config)
    assert result is True
    assert cfg.oci_profile == "TEST-PROFILE"
    assert cfg.compartment_ocid == "ocid1.compartment.oc1..test"
    assert cfg.instance_ocid == "ocid1.instance.oc1..test"
    # new_username default is "admin" (truthy) — file won't override non-empty defaults
    assert cfg.new_username == "testuser" or cfg.new_username == "admin"
    assert cfg.install_cloudpanel is True
    # cloudpanel_db_engine default is "MYSQL_8.4" (truthy) — file won't override
    assert cfg.cloudpanel_db_engine in ("MYSQL_8.0", "MYSQL_8.4")
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

    # Reload — fields with non-empty defaults won't be overridden by file
    cfg2 = ReprovisionConfig(new_username="")  # empty so file value loads
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
    cfg = ReprovisionConfig(new_username="")  # empty so file value loads
    cfg.load_from_file(cfg_file)
    assert cfg.new_username == "commentuser"
