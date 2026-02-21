"""FastAPI health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "ok", "service": "nimbus-engine"}
