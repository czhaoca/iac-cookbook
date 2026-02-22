"""Backup API — trigger and list database backups."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.backup import backup_database, list_backups

router = APIRouter(prefix="/backup", tags=["backup"])


@router.post("")
def create_backup():
    """Trigger a database backup with automatic rotation."""
    return backup_database()


@router.get("")
def get_backups():
    """List existing database backups."""
    return list_backups()
