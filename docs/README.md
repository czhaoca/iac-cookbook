# Nimbus Documentation

Welcome to the Nimbus documentation — your personal multi-cloud orchestration platform.

## Guides

- [Getting Started](getting-started.md) — Install, configure, and run Nimbus
- [API Reference](api-reference.md) — REST API endpoints
- [Deployment](deployment.md) — Docker, Proxmox, and production setup

## Architecture

- [Provider Adapters](../engine/nimbus/providers/base.py) — Abstract interface for cloud providers
- Cloud Provider Analysis: [OCI](oci/), [Control Panels](control-panels/)

## Quick Links

| Component | Local URL | Description |
|-----------|-----------|-------------|
| Engine API | http://localhost:8000/docs | FastAPI Swagger UI |
| Dashboard | http://localhost:3000 | React frontend |
| Health | http://localhost:8000/health | Health check |
