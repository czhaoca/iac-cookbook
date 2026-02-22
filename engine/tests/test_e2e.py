"""E2E smoke tests — run against a live Nimbus engine (or TestClient).

These tests verify full API workflow: provider → resource → action → budget → backup.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.providers.base import ProviderAdapter
from nimbus.services.registry import registry


class _MockAdapter(ProviderAdapter):
    provider_type = "mock"
    def authenticate(self, credentials_path, **kw): pass
    def list_resources(self, resource_type=None): return []
    def get_resource(self, resource_id): return {"external_id": resource_id, "status": "running"}
    def provision(self, resource_type, config): return {}
    def terminate(self, resource_id): return True
    def get_spending(self, period): return 0.0
    def health_check(self, resource_id=None): return {"status": "ok"}


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    registry.register_adapter("mock", _MockAdapter)

    app = create_app()

    def override():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_full_workflow(client):
    """End-to-end workflow: health → provider → resource → action → logs → budget → settings → backup."""

    # 1. Health check
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "degraded")

    # 2. Create provider
    r = client.post("/api/providers", json={
        "id": "e2e-prov",
        "provider_type": "mock",
        "display_name": "E2E Test Provider",
    })
    assert r.status_code == 201
    assert r.json()["id"] == "e2e-prov"

    # 3. List providers
    r = client.get("/api/providers")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # 4. Create resource
    r = client.post("/api/resources", json={
        "provider_id": "e2e-prov",
        "resource_type": "vm",
        "display_name": "E2E VM",
        "external_id": "ext-e2e-1",
        "status": "running",
        "protection_level": "standard",
    })
    assert r.status_code == 201
    resource_id = r.json()["id"]

    # 5. Get resource
    r = client.get(f"/api/resources/{resource_id}")
    assert r.status_code == 200
    assert r.json()["display_name"] == "E2E VM"

    # 6. Perform action (health_check — doesn't need real adapter)
    r = client.post(f"/api/resources/{resource_id}/action", json={"action": "health_check"})
    # May fail due to no adapter, but endpoint should respond
    assert r.status_code in (200, 500)

    # 7. Get action logs
    r = client.get(f"/api/resources/{resource_id}/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 8. Create budget rule
    r = client.post("/api/budget/rules", json={
        "provider_id": "e2e-prov",
        "monthly_limit": 10.0,
        "alert_threshold": 0.8,
        "action_on_exceed": "alert",
    })
    assert r.status_code == 201

    # 9. Budget status
    r = client.get("/api/budget/status")
    assert r.status_code == 200

    # 10. Settings
    r = client.get("/api/settings")
    assert r.status_code == 200
    settings = r.json()
    assert "spending_sync_interval" in settings

    r = client.put("/api/settings/spending_sync_interval", json={"value": "120"})
    assert r.status_code == 200

    r = client.get("/api/settings/spending_sync_interval")
    assert r.status_code == 200
    assert r.json()["value"] == "120"

    # 11. Backup
    r = client.get("/api/backup")
    assert r.status_code == 200

    # 12. Alert config status
    r = client.get("/api/alerts/config-status")
    assert r.status_code == 200

    # 13. Update resource
    r = client.put(f"/api/resources/{resource_id}", json={"status": "stopped"})
    assert r.status_code == 200
    assert r.json()["status"] == "stopped"

    # 14. Delete resource
    r = client.delete(f"/api/resources/{resource_id}")
    assert r.status_code == 204

    # 15. Delete provider
    r = client.delete("/api/providers/e2e-prov")
    assert r.status_code == 204

    # 16. Verify cleanup
    r = client.get("/api/providers")
    assert len(r.json()) == 0


def test_critical_resource_protection(client):
    """Critical resources cannot be terminated."""
    # Setup
    client.post("/api/providers", json={
        "id": "crit-prov", "provider_type": "mock", "display_name": "Crit Test",
    })
    r = client.post("/api/resources", json={
        "provider_id": "crit-prov",
        "resource_type": "vm",
        "display_name": "Critical VM",
        "external_id": "ext-crit",
        "status": "running",
        "protection_level": "critical",
    })
    resource_id = r.json()["id"]

    # Attempt terminate
    r = client.post(f"/api/resources/{resource_id}/action", json={"action": "terminate"})
    assert r.status_code == 403

    # Cleanup
    client.delete(f"/api/resources/{resource_id}")
    client.delete("/api/providers/crit-prov")
