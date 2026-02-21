"""Tests for the provider registry service."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nimbus.db import Base
from nimbus.models.provider import ProviderConfig
from nimbus.providers.base import ProviderAdapter
from nimbus.services.registry import ProviderRegistry


class MockAdapter(ProviderAdapter):
    """Minimal adapter for testing."""

    def __init__(self):
        self._authenticated = False

    @property
    def provider_type(self) -> str:
        return "mock"

    def authenticate(self, credentials_path, **kwargs):
        self._authenticated = True

    def list_resources(self, resource_type=None):
        return [{"external_id": "mock-1", "display_name": "Mock VM", "status": "running"}]

    def get_resource(self, resource_id):
        return {"external_id": resource_id, "status": "running"}

    def provision(self, resource_type, config):
        return {"external_id": "new-mock", "status": "provisioning"}

    def terminate(self, resource_id):
        return True

    def get_spending(self, period):
        return 0.0


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_register_and_list_types():
    reg = ProviderRegistry()
    reg.register_adapter("mock", MockAdapter)
    assert "mock" in reg.supported_types


def test_create_and_list_providers(db_session):
    reg = ProviderRegistry()
    provider = reg.create_provider(
        db_session,
        id="mock-1",
        provider_type="mock",
        display_name="Mock Provider",
        region="us-east-1",
    )
    assert provider.id == "mock-1"

    providers = reg.list_providers(db_session)
    assert len(providers) == 1
    assert providers[0].display_name == "Mock Provider"


def test_get_adapter_authenticates(db_session):
    reg = ProviderRegistry()
    reg.register_adapter("mock", MockAdapter)
    reg.create_provider(db_session, id="mock-1", provider_type="mock", display_name="Mock")

    adapter = reg.get_adapter("mock-1", db_session)
    assert isinstance(adapter, MockAdapter)
    assert adapter._authenticated is True


def test_get_adapter_unknown_provider(db_session):
    reg = ProviderRegistry()
    with pytest.raises(KeyError, match="not found in database"):
        reg.get_adapter("nonexistent", db_session)


def test_get_adapter_unknown_type(db_session):
    reg = ProviderRegistry()
    reg.create_provider(db_session, id="unsupported", provider_type="xcloud", display_name="X")
    with pytest.raises(KeyError, match="No adapter registered"):
        reg.get_adapter("unsupported", db_session)


def test_delete_provider(db_session):
    reg = ProviderRegistry()
    reg.create_provider(db_session, id="del-me", provider_type="mock", display_name="Delete Me")
    assert reg.delete_provider(db_session, "del-me") is True
    assert reg.get_provider(db_session, "del-me") is None
    assert reg.delete_provider(db_session, "del-me") is False
