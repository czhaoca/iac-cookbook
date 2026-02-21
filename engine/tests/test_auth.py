"""Tests for auth.py — profile listing and config parsing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from nimbus.providers.oci.auth import list_profiles, get_profile_value


def test_list_profiles(tmp_path: Path) -> None:
    config = tmp_path / "config"
    # configparser treats [DEFAULT] as magic — use a different name
    config.write_text(
        "[MAIN]\n"
        "user=ocid1.user.oc1..default\n"
        "tenancy=ocid1.tenancy.oc1..default\n"
        "\n"
        "[PROD]\n"
        "user=ocid1.user.oc1..prod\n"
        "tenancy=ocid1.tenancy.oc1..prod\n"
    )
    with patch("nimbus.providers.oci.auth.OCI_CONFIG_PATH", config):
        profiles = list_profiles()
    assert profiles == ["MAIN", "PROD"]


def test_list_profiles_no_file(tmp_path: Path) -> None:
    with patch("nimbus.providers.oci.auth.OCI_CONFIG_PATH", tmp_path / "missing"):
        profiles = list_profiles()
    assert profiles == []


def test_get_profile_value(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "[MYPROFILE]\n"
        "user=ocid1.user.oc1..test\n"
        "region=us-ashburn-1\n"
    )
    with patch("nimbus.providers.oci.auth.OCI_CONFIG_PATH", config):
        assert get_profile_value("MYPROFILE", "region") == "us-ashburn-1"
        assert get_profile_value("MYPROFILE", "nonexistent") == ""
