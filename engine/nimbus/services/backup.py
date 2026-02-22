"""Database backup service — SQLite snapshot with rotation."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

# Default backup dir (gitignored)
_BACKUP_DIR = Path("local/backups")
_MAX_BACKUPS = 10


def backup_database(
    backup_dir: Path | None = None,
    max_backups: int = _MAX_BACKUPS,
) -> dict:
    """Create a timestamped SQLite backup and rotate old copies.

    Returns dict with backup path, size, and rotation info.
    """
    backup_dir = backup_dir or _BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_url = settings.database_url
    if not db_url.startswith("sqlite"):
        return {"error": "Backup only supported for SQLite databases"}

    # Extract file path from sqlite:///path or sqlite:////abs/path
    db_path = db_url.replace("sqlite:///", "", 1)
    if not db_path or not Path(db_path).exists():
        return {"error": f"Database file not found: {db_path}"}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"nimbus_{timestamp}.db"
    backup_path = backup_dir / backup_name

    # Use SQLite online backup API for consistency
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    size = backup_path.stat().st_size

    # Rotate: keep only max_backups most recent
    backups = sorted(backup_dir.glob("nimbus_*.db"), key=lambda p: p.name)
    removed = []
    while len(backups) > max_backups:
        old = backups.pop(0)
        old.unlink()
        removed.append(old.name)

    return {
        "path": str(backup_path),
        "size_bytes": size,
        "timestamp": timestamp,
        "rotated_out": removed,
        "total_backups": len(list(backup_dir.glob("nimbus_*.db"))),
    }


def list_backups(backup_dir: Path | None = None) -> list[dict]:
    """List existing backups sorted newest first."""
    backup_dir = backup_dir or _BACKUP_DIR
    if not backup_dir.exists():
        return []
    backups = sorted(backup_dir.glob("nimbus_*.db"), key=lambda p: p.name, reverse=True)
    return [
        {
            "name": b.name,
            "size_bytes": b.stat().st_size,
            "created": datetime.fromtimestamp(b.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for b in backups
    ]
