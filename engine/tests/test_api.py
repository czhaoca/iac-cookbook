"""Tests for FastAPI API endpoints — health, providers, resources."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.providers.base import ProviderAdapter
from nimbus.services.registry import registry


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

class MockAdapter(ProviderAdapter):
    @property
    def provider_type(self) -> str:
        return "mock"

    def authenticate(self, credentials_path, **kwargs):
        pass

    def list_resources(self, resource_type=None):
        return [{"external_id": "mock-vm-1", "display_name": "Mock VM", "resource_type": "vm", "status": "running"}]

    def get_resource(self, resource_id):
        return {"external_id": resource_id, "status": "running"}

    def provision(self, resource_type, config):
        return {}

    def terminate(self, resource_id):
        return True

    def get_spending(self, period):
        return 0.0

    def scale_down(self, resource_id):
        return True

    def health_check(self, resource_id):
        return {"status": "running", "resource_id": resource_id}


@pytest.fixture(autouse=True)
def setup_test_db():
    """Override the DB dependency with an in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    # Register mock adapter on a fresh registry to avoid cross-test pollution
    registry._adapter_classes.clear()
    registry._instances.clear()
    registry.register_adapter("mock", MockAdapter)

    client = TestClient(app, raise_server_exceptions=True)
    yield client

    app.dependency_overrides.clear()
    registry._adapter_classes.clear()
    registry._instances.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(setup_test_db):
    client = setup_test_db
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Providers CRUD
# ---------------------------------------------------------------------------


def test_create_provider(setup_test_db):
    client = setup_test_db
    resp = client.post("/api/providers", json={
        "id": "test-oci",
        "provider_type": "mock",
        "display_name": "Test OCI",
        "region": "us-east-1",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "test-oci"
    assert data["provider_type"] == "mock"


def test_list_providers(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_provider(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.get("/api/providers/p1")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "P1"


def test_get_provider_404(setup_test_db):
    client = setup_test_db
    resp = client.get("/api/providers/nonexistent")
    assert resp.status_code == 404


def test_update_provider(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.put("/api/providers/p1", json={"display_name": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated"


def test_delete_provider(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.delete("/api/providers/p1")
    assert resp.status_code == 204
    resp = client.get("/api/providers/p1")
    assert resp.status_code == 404


def test_create_duplicate_provider(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1 dup"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Resources CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_resources(setup_test_db):
    client = setup_test_db
    # Create provider first
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})

    resp = client.post("/api/resources", json={
        "provider_id": "p1",
        "resource_type": "vm",
        "display_name": "Test VM",
        "external_id": "ext-123",
    })
    assert resp.status_code == 201
    resource_id = resp.json()["id"]

    resp = client.get("/api/resources")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(f"/api/resources/{resource_id}")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Test VM"


def test_update_resource(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.post("/api/resources", json={
        "provider_id": "p1", "resource_type": "vm",
        "display_name": "VM", "external_id": "ext-1",
    })
    rid = resp.json()["id"]

    resp = client.put(f"/api/resources/{rid}", json={"status": "stopped", "protection_level": "critical"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"
    assert resp.json()["protection_level"] == "critical"


def test_delete_resource(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.post("/api/resources", json={
        "provider_id": "p1", "resource_type": "vm",
        "display_name": "VM", "external_id": "ext-1",
    })
    rid = resp.json()["id"]
    resp = client.delete(f"/api/resources/{rid}")
    assert resp.status_code == 204


def test_resource_action_health_check(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.post("/api/resources", json={
        "provider_id": "p1", "resource_type": "vm",
        "display_name": "VM", "external_id": "mock-vm-1",
    })
    rid = resp.json()["id"]

    resp = client.post(f"/api/resources/{rid}/action", json={"action": "health_check"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_resource_sync(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})

    resp = client.post("/api/resources/sync/p1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1
    assert data["synced"] == 1


def test_terminate_critical_blocked(setup_test_db):
    client = setup_test_db
    client.post("/api/providers", json={"id": "p1", "provider_type": "mock", "display_name": "P1"})
    resp = client.post("/api/resources", json={
        "provider_id": "p1", "resource_type": "vm",
        "display_name": "Critical VM", "external_id": "ext-crit",
        "protection_level": "critical",
    })
    rid = resp.json()["id"]

    resp = client.post(f"/api/resources/{rid}/action", json={"action": "terminate"})
    assert resp.status_code == 403
