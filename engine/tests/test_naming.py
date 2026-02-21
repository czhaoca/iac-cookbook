"""Tests for the naming service — name generation and collision detection."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nimbus.db import Base
from nimbus.models.provider import ProviderConfig
from nimbus.models.resource import CloudResource
from nimbus.services.naming import generate_name, check_collision, _sanitize


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Seed a provider
    session.add(ProviderConfig(
        id="test-oci", provider_type="oci", display_name="Test OCI",
    ))
    session.commit()
    yield session
    session.close()


def test_generate_first_name(db_session):
    name = generate_name("dev", "vm", "web", db_session)
    assert name == "dev-vm-web"


def test_generate_avoids_collision(db_session):
    # Create an existing resource with the base name
    db_session.add(CloudResource(
        provider_id="test-oci", resource_type="vm",
        display_name="dev-vm-web", external_id="ext-1",
    ))
    db_session.commit()

    name = generate_name("dev", "vm", "web", db_session)
    assert name == "dev-vm-web-01"


def test_generate_increments_sequence(db_session):
    for i, dn in enumerate(["dev-vm-web", "dev-vm-web-01", "dev-vm-web-02"]):
        db_session.add(CloudResource(
            provider_id="test-oci", resource_type="vm",
            display_name=dn, external_id=f"ext-{i}",
        ))
    db_session.commit()

    name = generate_name("dev", "vm", "web", db_session)
    assert name == "dev-vm-web-03"


def test_check_collision_true(db_session):
    db_session.add(CloudResource(
        provider_id="test-oci", resource_type="vm",
        display_name="prod-vm-api", external_id="ext-x",
    ))
    db_session.commit()
    assert check_collision("prod-vm-api", db_session) is True


def test_check_collision_false(db_session):
    assert check_collision("nonexistent", db_session) is False


def test_sanitize():
    assert _sanitize("My Resource!!") == "my-resource"
    assert _sanitize("test--double") == "test-double"
    assert _sanitize("  spaces  ") == "spaces"
