"""Tests for orchestration service and cross-cloud workflow API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.models.provider import ProviderConfig
from nimbus.models.resource import CloudResource
from nimbus.providers.base import ProviderAdapter
from nimbus.services.registry import registry
from nimbus.services.orchestrator import budget_lockdown


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockVMAdapter(ProviderAdapter):
    provider_type = "mock_vm"

    def authenticate(self, credentials_path, **kwargs):
        pass

    def list_resources(self, resource_type=None):
        return []

    def get_resource(self, resource_id):
        return {"external_id": resource_id, "status": "running"}

    def provision(self, resource_type, config):
        return {
            "external_id": "vm-123",
            "display_name": "Test VM",
            "status": "running",
            "public_ip": "1.2.3.4",
        }

    def terminate(self, resource_id):
        return True

    def get_spending(self, period):
        return 0.0

    def scale_down(self, resource_id):
        return True


class MockDNSAdapter(ProviderAdapter):
    provider_type = "mock_dns"

    def authenticate(self, credentials_path, **kwargs):
        pass

    def list_resources(self, resource_type=None):
        return []

    def get_resource(self, resource_id):
        return {"external_id": resource_id, "status": "active"}

    def provision(self, resource_type, config):
        return {
            "external_id": "dns-456",
            "display_name": f"{config.get('name', 'test')} (A)",
            "status": "active",
        }

    def terminate(self, resource_id):
        return True

    def get_spending(self, period):
        return 0.0


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

    # Seed providers
    session.add(ProviderConfig(id="vm-prov", provider_type="mock_vm", display_name="VM Provider"))
    session.add(ProviderConfig(id="dns-prov", provider_type="mock_dns", display_name="DNS Provider"))
    session.commit()

    # Register mock adapters
    registry.register_adapter("mock_vm", MockVMAdapter)
    registry.register_adapter("mock_dns", MockDNSAdapter)
    registry._instances["vm-prov"] = MockVMAdapter()
    registry._instances["dns-prov"] = MockDNSAdapter()

    try:
        yield session
    finally:
        registry._instances.pop("vm-prov", None)
        registry._instances.pop("dns-prov", None)
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
# Service-level tests
# ---------------------------------------------------------------------------


def test_budget_lockdown_stops_ephemeral(db_session):
    db_session.add(CloudResource(
        provider_id="vm-prov", resource_type="vm", display_name="Ephemeral",
        status="running", protection_level="ephemeral", auto_terminate=True,
        monthly_cost_estimate=5.0, external_id="ext-1",
    ))
    db_session.commit()

    result = budget_lockdown(db_session, "vm-prov")
    assert result["stopped"] == 1
    assert result["skipped"] == 0


def test_budget_lockdown_skips_critical(db_session):
    db_session.add(CloudResource(
        provider_id="vm-prov", resource_type="vm", display_name="Critical",
        status="running", protection_level="critical", auto_terminate=False,
        external_id="ext-2",
    ))
    db_session.commit()

    result = budget_lockdown(db_session, "vm-prov")
    assert result["stopped"] == 0


def test_budget_lockdown_skips_non_auto_terminate(db_session):
    db_session.add(CloudResource(
        provider_id="vm-prov", resource_type="vm", display_name="Standard",
        status="running", protection_level="standard", auto_terminate=False,
        external_id="ext-3",
    ))
    db_session.commit()

    result = budget_lockdown(db_session, "vm-prov")
    assert result["stopped"] == 0
    assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


def test_vm_dns_orchestration(client):
    resp = client.post("/api/orchestrate/vm-dns", json={
        "vm_provider_id": "vm-prov",
        "dns_provider_id": "dns-prov",
        "vm_config": {},
        "dns_config": {"zone_id": "z1", "name": "test.example.com"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["steps"]) == 2
    assert data["steps"][0]["status"] == "success"
    assert data["steps"][1]["status"] == "success"


def test_vm_without_dns(client):
    resp = client.post("/api/orchestrate/vm-dns", json={
        "vm_provider_id": "vm-prov",
        "vm_config": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # DNS step should be skipped when no dns_provider_id
    dns_step = next(s for s in data["steps"] if s["step"] == "create_dns")
    assert dns_step["status"] == "skipped"


def test_lockdown_endpoint(client):
    # Seed an ephemeral resource
    client.post("/api/resources", json={
        "provider_id": "vm-prov", "resource_type": "vm",
        "display_name": "Test", "external_id": "ext-lock",
        "status": "running", "protection_level": "ephemeral",
        "auto_terminate": True,
    })

    resp = client.post("/api/orchestrate/lockdown", json={
        "provider_id": "vm-prov",
    })
    assert resp.status_code == 200
    assert resp.json()["stopped"] == 1


def test_cloudflare_adapter_type():
    from nimbus.providers.cloudflare.adapter import CloudflareAdapter
    adapter = CloudflareAdapter()
    assert adapter.provider_type == "cloudflare"
    assert adapter.get_spending("2026-02") == 0.0


def test_proxmox_adapter_type():
    from nimbus.providers.proxmox.adapter import ProxmoxAdapter
    adapter = ProxmoxAdapter()
    assert adapter.provider_type == "proxmox"
    assert adapter.get_spending("2026-02") == 0.0
