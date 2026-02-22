"""Error log API — exposes the in-memory error tracker for the UI."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.resilience import error_tracker

router = APIRouter(prefix="/errors", tags=["errors"])


@router.get("")
def list_errors(source: str | None = None, limit: int = 50):
    """Return recent errors, optionally filtered by source."""
    return {
        "errors": error_tracker.get_errors(source=source, limit=limit),
        "total": error_tracker.count,
    }


@router.delete("", status_code=204)
def clear_errors():
    """Clear all tracked errors."""
    error_tracker.clear()
