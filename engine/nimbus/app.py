"""Nimbus Engine — FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    init_db()
    _register_adapters()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Personal multi-cloud orchestration platform",
        lifespan=lifespan,
    )

    # CORS for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from .api.health import router as health_router
    from .api.providers import router as providers_router
    from .api.resources import router as resources_router
    app.include_router(health_router)
    app.include_router(providers_router, prefix="/api")
    app.include_router(resources_router, prefix="/api")

    return app


def _register_adapters() -> None:
    """Register all available provider adapters."""
    from .services.registry import registry

    try:
        from .providers.oci.adapter import OCIProviderAdapter
        registry.register_adapter("oci", OCIProviderAdapter)
    except ImportError:
        pass  # OCI SDK not installed


app = create_app()
