"""Nimbus Engine — FastAPI application factory."""

from __future__ import annotations

import asyncio
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
    # Start background spending sync
    from .services.spending_sync import spending_sync_loop
    sync_task = asyncio.create_task(spending_sync_loop())
    yield
    sync_task.cancel()


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

    # API key auth (when NIMBUS_API_KEY is set)
    from .middleware import ApiKeyMiddleware
    app.add_middleware(ApiKeyMiddleware)

    # Register routers
    from .api.health import router as health_router
    from .api.providers import router as providers_router
    from .api.resources import router as resources_router
    from .api.budget import router as budget_router
    from .api.orchestration import router as orchestration_router
    from .api.ws import router as ws_router
    from .api.backup import router as backup_router
    from .api.alerts import router as alerts_router
    from .api.settings import router as settings_router
    app.include_router(health_router)
    app.include_router(providers_router, prefix="/api")
    app.include_router(resources_router, prefix="/api")
    app.include_router(budget_router, prefix="/api")
    app.include_router(orchestration_router, prefix="/api")
    app.include_router(ws_router)
    app.include_router(backup_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    return app


def _register_adapters() -> None:
    """Register all available provider adapters."""
    from .services.registry import registry

    try:
        from .providers.oci.adapter import OCIProviderAdapter
        registry.register_adapter("oci", OCIProviderAdapter)
    except ImportError:
        pass

    try:
        from .providers.cloudflare.adapter import CloudflareAdapter
        registry.register_adapter("cloudflare", CloudflareAdapter)
    except ImportError:
        pass

    try:
        from .providers.proxmox.adapter import ProxmoxAdapter
        registry.register_adapter("proxmox", ProxmoxAdapter)
    except ImportError:
        pass

    try:
        from .providers.azure.adapter import AzureAdapter
        registry.register_adapter("azure", AzureAdapter)
    except ImportError:
        pass

    try:
        from .providers.gcp.adapter import GCPAdapter
        registry.register_adapter("gcp", GCPAdapter)
    except ImportError:
        pass

    try:
        from .providers.aws.adapter import AWSAdapter
        registry.register_adapter("aws", AWSAdapter)
    except ImportError:
        pass


app = create_app()
