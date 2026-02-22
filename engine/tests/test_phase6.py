"""Tests for Phase 6: spending sync, alerts, cloud stubs, API."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.models.provider import ProviderConfig
from nimbus.services.alerts import AlertConfig, dispatch_alert, send_webhook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
# Spending sync tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_spending_no_providers(db_session):
    from nimbus.services.spending_sync import sync_spending_once
    result = await sync_spending_once(db_session)
    assert result["providers"] == []


@pytest.mark.asyncio
async def test_sync_spending_with_provider(db_session):
    from nimbus.services.spending_sync import sync_spending_once
    from nimbus.services.registry import registry

    db_session.add(ProviderConfig(
        id="test-sync", provider_type="mock", display_name="Test",
    ))
    db_session.commit()

    mock_adapter = MagicMock()
    mock_adapter.get_spending.return_value = 12.50
    registry._instances["test-sync"] = mock_adapter

    try:
        result = await sync_spending_once(db_session)
        assert len(result["providers"]) == 1
        assert result["providers"][0]["status"] == "ok"
        assert result["providers"][0]["amount"] == 12.50
    finally:
        registry._instances.pop("test-sync", None)


# ---------------------------------------------------------------------------
# Alert tests
# ---------------------------------------------------------------------------


def test_alert_config_from_missing_file():
    config = AlertConfig.from_file("/nonexistent/alerts.json")
    assert config.webhooks == []
    assert config.email_to == []


def test_dispatch_alert_no_destinations():
    config = AlertConfig()
    result = dispatch_alert(config, "test", "Test alert")
    assert result["webhooks"] == []
    assert result["email"] is None


def test_send_webhook_failure():
    ok = send_webhook("http://localhost:99999/nonexistent", {"test": True})
    assert ok is False


def test_alert_config_status_endpoint(client):
    resp = client.get("/api/alerts/config-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert data["webhook_count"] == 0


# ---------------------------------------------------------------------------
# Cloud adapter stub tests
# ---------------------------------------------------------------------------


def test_azure_adapter():
    from nimbus.providers.azure.adapter import AzureAdapter
    a = AzureAdapter()
    assert a.provider_type == "azure"
    assert a.list_resources() == []
    assert a.get_spending("2026-02") == 0.0


def test_gcp_adapter():
    from nimbus.providers.gcp.adapter import GCPAdapter
    a = GCPAdapter()
    assert a.provider_type == "gcp"
    assert a.list_resources() == []
    assert a.get_spending("2026-02") == 0.0


def test_aws_adapter():
    from nimbus.providers.aws.adapter import AWSAdapter
    a = AWSAdapter()
    assert a.provider_type == "aws"
    assert a.list_resources() == []
    assert a.get_spending("2026-02") == 0.0


def test_all_adapters_registered(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    # Verify the 6 cloud adapter types can be imported
    from nimbus.providers.oci.adapter import OCIProviderAdapter
    from nimbus.providers.cloudflare.adapter import CloudflareAdapter
    from nimbus.providers.proxmox.adapter import ProxmoxAdapter
    from nimbus.providers.azure.adapter import AzureAdapter
    from nimbus.providers.gcp.adapter import GCPAdapter
    from nimbus.providers.aws.adapter import AWSAdapter
    for cls in [OCIProviderAdapter, CloudflareAdapter, ProxmoxAdapter, AzureAdapter, GCPAdapter, AWSAdapter]:
        assert hasattr(cls, "provider_type")


# ---------------------------------------------------------------------------
# Spending sync API
# ---------------------------------------------------------------------------


def test_spending_sync_api(client):
    resp = client.post("/api/budget/sync-spending")
    assert resp.status_code == 200
    data = resp.json()
    assert "synced_at" in data
    assert "providers" in data
