"""FastAPI health endpoint with detailed diagnostics."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..db import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Health check endpoint for load balancers and monitoring."""
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        pass

    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "service": "nimbus-engine",
        "checks": {"database": "ok" if db_ok else "unreachable"},
    }
