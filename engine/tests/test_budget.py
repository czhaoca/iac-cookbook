"""Tests for budget API and monitor service."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.services.budget_monitor import (
    check_budget,
    current_period,
    enforce_budget,
    get_spending,
    record_spending,
)


@pytest.fixture()
def db_session():
    """Create an in-memory DB session for service-level tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """TestClient with overridden DB dependency."""
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


def _seed_provider(db):
    from nimbus.models.provider import ProviderConfig
    p = ProviderConfig(id="test-oci", provider_type="oci", display_name="Test OCI")
    db.add(p)
    db.commit()
    return p


def test_record_and_get_spending(db_session):
    _seed_provider(db_session)
    record_spending(db_session, "test-oci", 12.50)
    assert get_spending(db_session, "test-oci") == 12.50


def test_record_spending_upsert(db_session):
    _seed_provider(db_session)
    record_spending(db_session, "test-oci", 10.0)
    record_spending(db_session, "test-oci", 25.0)  # upsert same period
    assert get_spending(db_session, "test-oci") == 25.0


def test_check_budget_ok(db_session):
    _seed_provider(db_session)
    from nimbus.models.budget import BudgetRule
    db_session.add(BudgetRule(
        provider_id="test-oci", monthly_limit=100.0,
        alert_threshold=0.8, action_on_exceed="alert",
    ))
    db_session.commit()
    record_spending(db_session, "test-oci", 50.0)

    statuses = check_budget(db_session, "test-oci")
    assert len(statuses) == 1
    assert statuses[0].status == "ok"
    assert statuses[0].utilization == pytest.approx(0.5)


def test_check_budget_warning(db_session):
    _seed_provider(db_session)
    from nimbus.models.budget import BudgetRule
    db_session.add(BudgetRule(
        provider_id="test-oci", monthly_limit=100.0,
        alert_threshold=0.8, action_on_exceed="alert",
    ))
    db_session.commit()
    record_spending(db_session, "test-oci", 85.0)

    statuses = check_budget(db_session, "test-oci")
    assert statuses[0].status == "warning"
    assert len(statuses[0].alerts) == 1


def test_check_budget_exceeded(db_session):
    _seed_provider(db_session)
    from nimbus.models.budget import BudgetRule
    db_session.add(BudgetRule(
        provider_id="test-oci", monthly_limit=100.0,
        alert_threshold=0.8, action_on_exceed="alert",
    ))
    db_session.commit()
    record_spending(db_session, "test-oci", 120.0)

    statuses = check_budget(db_session, "test-oci")
    assert statuses[0].status == "exceeded"
    assert statuses[0].utilization == pytest.approx(1.2)


def test_enforce_budget_alert_only(db_session):
    _seed_provider(db_session)
    from nimbus.models.budget import BudgetRule
    db_session.add(BudgetRule(
        provider_id="test-oci", monthly_limit=50.0,
        alert_threshold=0.8, action_on_exceed="alert",
    ))
    db_session.commit()
    record_spending(db_session, "test-oci", 60.0)

    actions = enforce_budget(db_session, "test-oci")
    assert len(actions) == 1
    assert actions[0]["action"] == "alert"


def test_enforce_terminate_ephemeral(db_session):
    _seed_provider(db_session)
    from nimbus.models.budget import BudgetRule
    from nimbus.models.resource import CloudResource
    db_session.add(BudgetRule(
        provider_id="test-oci", monthly_limit=10.0,
        action_on_exceed="terminate_ephemeral",
    ))
    db_session.add(CloudResource(
        provider_id="test-oci", resource_type="vm", display_name="Ephemeral VM",
        status="running", protection_level="ephemeral", auto_terminate=True,
        monthly_cost_estimate=5.0,
    ))
    db_session.commit()
    record_spending(db_session, "test-oci", 15.0)

    actions = enforce_budget(db_session, "test-oci")
    assert len(actions) == 1
    assert actions[0]["action"] == "terminate"


def test_enforce_skips_critical(db_session):
    _seed_provider(db_session)
    from nimbus.models.budget import BudgetRule
    from nimbus.models.resource import CloudResource
    db_session.add(BudgetRule(
        provider_id="test-oci", monthly_limit=10.0,
        action_on_exceed="terminate_ephemeral",
    ))
    db_session.add(CloudResource(
        provider_id="test-oci", resource_type="vm", display_name="Critical VM",
        status="running", protection_level="critical", auto_terminate=False,
    ))
    db_session.commit()
    record_spending(db_session, "test-oci", 15.0)

    actions = enforce_budget(db_session, "test-oci")
    assert len(actions) == 0  # critical resources are never touched


def test_current_period():
    period = current_period()
    assert len(period) == 7  # YYYY-MM
    assert "-" in period


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


def test_create_and_list_rules(client):
    # Create provider first
    client.post("/api/providers", json={
        "id": "p1", "provider_type": "oci", "display_name": "P1",
    })

    # Create rule
    resp = client.post("/api/budget/rules", json={
        "provider_id": "p1", "monthly_limit": 100.0,
        "alert_threshold": 0.9, "action_on_exceed": "alert",
    })
    assert resp.status_code == 201
    rule = resp.json()
    assert rule["monthly_limit"] == 100.0
    assert rule["alert_threshold"] == 0.9

    # List rules
    resp = client.get("/api/budget/rules")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_rule(client):
    client.post("/api/providers", json={
        "id": "p1", "provider_type": "oci", "display_name": "P1",
    })
    resp = client.post("/api/budget/rules", json={
        "provider_id": "p1", "monthly_limit": 50.0,
    })
    rule_id = resp.json()["id"]

    resp = client.put(f"/api/budget/rules/{rule_id}", json={"monthly_limit": 200.0})
    assert resp.status_code == 200
    assert resp.json()["monthly_limit"] == 200.0


def test_delete_rule(client):
    client.post("/api/providers", json={
        "id": "p1", "provider_type": "oci", "display_name": "P1",
    })
    resp = client.post("/api/budget/rules", json={
        "provider_id": "p1", "monthly_limit": 50.0,
    })
    rule_id = resp.json()["id"]

    resp = client.delete(f"/api/budget/rules/{rule_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/budget/rules/{rule_id}")
    assert resp.status_code == 404


def test_budget_status_endpoint(client):
    client.post("/api/providers", json={
        "id": "p1", "provider_type": "oci", "display_name": "P1",
    })
    client.post("/api/budget/rules", json={
        "provider_id": "p1", "monthly_limit": 100.0,
    })
    client.post("/api/budget/spending", params={
        "provider_id": "p1", "amount": 85.0,
    })

    resp = client.get("/api/budget/status", params={"provider_id": "p1"})
    assert resp.status_code == 200
    statuses = resp.json()
    assert len(statuses) == 1
    assert statuses[0]["status"] == "warning"


def test_enforce_endpoint(client):
    client.post("/api/providers", json={
        "id": "p1", "provider_type": "oci", "display_name": "P1",
    })
    client.post("/api/budget/rules", json={
        "provider_id": "p1", "monthly_limit": 10.0,
        "action_on_exceed": "alert",
    })
    client.post("/api/budget/spending", params={
        "provider_id": "p1", "amount": 15.0,
    })

    resp = client.post("/api/budget/enforce", params={"provider_id": "p1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["actions_taken"] == 1
    assert data["details"][0]["action"] == "alert"


def test_spending_list(client):
    client.post("/api/providers", json={
        "id": "p1", "provider_type": "oci", "display_name": "P1",
    })
    client.post("/api/budget/spending", params={
        "provider_id": "p1", "amount": 42.0,
    })

    resp = client.get("/api/budget/spending", params={"provider_id": "p1"})
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1
    assert records[0]["amount"] == 42.0
