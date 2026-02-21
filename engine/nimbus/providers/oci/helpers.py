"""OCI provider helpers — paths and constants specific to the OCI provider."""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    """Walk up from this file to find the repo root (where CLAUDE.md lives)."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def oci_dir() -> Path:
    """Return the oci/ directory at the repo root."""
    return _repo_root() / "oci"
