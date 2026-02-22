"""Tests for Phase 7: action logs, settings, provider health, WAF."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.models.provider import ProviderConfig
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
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    registry.register_adapter("mock", _MockAdapter)
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    return TestClient(app)


# ---------------------------------------------------------------------------
# Action logs
# ---------------------------------------------------------------------------


def test_action_logs_empty(client):
    client.post("/api/providers", json={
        "id": "log-prov", "provider_type": "mock", "display_name": "Log Test",
    })
    r = client.post("/api/resources", json={
        "provider_id": "log-prov", "resource_type": "vm",
        "display_name": "Log VM", "external_id": "ext-log",
        "status": "running",
    })
    rid = r.json()["id"]

    r = client.get(f"/api/resources/{rid}/logs")
    assert r.status_code == 200
    assert r.json() == []


def test_action_logs_after_action(client):
    client.post("/api/providers", json={
        "id": "logact-prov", "provider_type": "mock", "display_name": "Logact",
    })
    r = client.post("/api/resources", json={
        "provider_id": "logact-prov", "resource_type": "vm",
        "display_name": "Act VM", "external_id": "ext-act",
        "status": "running",
    })
    rid = r.json()["id"]

    # Perform action (may fail but still creates log)
    client.post(f"/api/resources/{rid}/action", json={"action": "health_check"})

    r = client.get(f"/api/resources/{rid}/logs")
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert r.json()[0]["action_type"] == "health_check"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_defaults(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert "spending_sync_interval" in data
    assert data["spending_sync_interval"] == "300"


def test_settings_update(client):
    r = client.put("/api/settings/spending_sync_interval", json={"value": "60"})
    assert r.status_code == 200

    r = client.get("/api/settings/spending_sync_interval")
    assert r.json()["value"] == "60"


def test_settings_custom_key(client):
    r = client.put("/api/settings/custom_key", json={"value": "hello"})
    assert r.status_code == 200

    r = client.get("/api/settings/custom_key")
    assert r.json()["value"] == "hello"


# ---------------------------------------------------------------------------
# Provider health
# ---------------------------------------------------------------------------


def test_provider_health_no_providers(client):
    r = client.get("/api/providers/health/check")
    assert r.status_code == 200
    assert r.json() == []


def test_provider_health_with_provider(client, db_session):
    db_session.add(ProviderConfig(
        id="hp-prov", provider_type="mock", display_name="Health Test",
    ))
    db_session.commit()

    r = client.get("/api/providers/health/check")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["provider_id"] == "hp-prov"
    assert results[0]["latency_ms"] is not None


# ---------------------------------------------------------------------------
# Cloudflare WAF methods
# ---------------------------------------------------------------------------


def test_cloudflare_waf_methods_exist():
    from nimbus.providers.cloudflare.adapter import CloudflareAdapter
    adapter = CloudflareAdapter()
    assert hasattr(adapter, "create_firewall_rule")
    assert hasattr(adapter, "list_firewall_rules")
    assert hasattr(adapter, "delete_firewall_rule")
    assert hasattr(adapter, "lockdown_zone")


# ---------------------------------------------------------------------------
# Setting model
# ---------------------------------------------------------------------------


def test_setting_model():
    from nimbus.models.setting import Setting
    s = Setting(key="test_key", value="test_value")
    assert s.key == "test_key"
    assert s.value == "test_value"
