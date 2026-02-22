"""Nimbus Engine configuration — loads from environment and local config files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (where CLAUDE.md lives)."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings — populated from env vars or .env file."""

    # App
    app_name: str = "Nimbus"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Database
    database_url: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Auth — set NIMBUS_API_KEY to enable API key auth
    api_key: Optional[str] = None

    # Paths
    repo_root: Path = _find_repo_root()

    model_config = {"env_prefix": "NIMBUS_", "env_file": ".env"}

    @property
    def local_dir(self) -> Path:
        return self.repo_root / "local"

    @property
    def data_dir(self) -> Path:
        d = self.local_dir / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'nimbus.db'}"


settings = Settings()
