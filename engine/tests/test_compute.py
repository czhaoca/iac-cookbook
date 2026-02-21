"""Tests for compute.py — architecture detection."""

from __future__ import annotations

from nimbus.providers.oci.compute import _detect_arch


def test_detect_arch_arm() -> None:
    assert _detect_arch("VM.Standard.A1.Flex") == "arm"
    assert _detect_arch("VM.Standard.A1.Flex.4") == "arm"


def test_detect_arch_x86() -> None:
    assert _detect_arch("VM.Standard.E2.1.Micro") == "x86"
    assert _detect_arch("VM.Standard.E4.Flex") == "x86"
    assert _detect_arch("VM.Standard3.Flex") == "x86"
