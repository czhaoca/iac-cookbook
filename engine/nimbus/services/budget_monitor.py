"""Budget monitor — checks spending against rules and enforces actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models.budget import BudgetRule, SpendingRecord
from ..models.resource import CloudResource
from ..models.action_log import ActionLog
from ..api.schemas import BudgetStatus


def current_period() -> str:
    """Return current billing period as YYYY-MM."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_spending(db: Session, provider_id: str | None, period: str | None = None) -> float:
    """Sum spending for a provider in a period. None provider_id = all providers."""
    period = period or current_period()
    q = db.query(SpendingRecord).filter(SpendingRecord.period == period)
    if provider_id:
        q = q.filter(SpendingRecord.provider_id == provider_id)
    return sum(r.amount for r in q.all())


def record_spending(
    db: Session, provider_id: str, amount: float,
    period: str | None = None, currency: str = "USD",
) -> SpendingRecord:
    """Upsert a spending record for a provider+period."""
    period = period or current_period()
    existing = (
        db.query(SpendingRecord)
        .filter(SpendingRecord.provider_id == provider_id, SpendingRecord.period == period)
        .first()
    )
    if existing:
        existing.amount = amount
        existing.recorded_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    rec = SpendingRecord(
        provider_id=provider_id, period=period,
        amount=amount, currency=currency,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def check_budget(db: Session, provider_id: str | None = None) -> list[BudgetStatus]:
    """Evaluate all active budget rules and return status for each."""
    q = db.query(BudgetRule).filter(BudgetRule.is_active == True)  # noqa: E712
    if provider_id:
        q = q.filter(
            (BudgetRule.provider_id == provider_id) | (BudgetRule.provider_id.is_(None))
        )
    rules = q.all()
    period = current_period()
    results: list[BudgetStatus] = []

    for rule in rules:
        spent = get_spending(db, rule.provider_id, period)
        utilization = spent / rule.monthly_limit if rule.monthly_limit > 0 else 0.0
        alerts: list[str] = []

        if utilization >= 1.0:
            status = "exceeded"
            alerts.append(f"Budget exceeded: ${spent:.2f} / ${rule.monthly_limit:.2f}")
        elif utilization >= rule.alert_threshold:
            status = "warning"
            alerts.append(
                f"Budget warning: ${spent:.2f} / ${rule.monthly_limit:.2f} "
                f"({utilization:.0%} ≥ {rule.alert_threshold:.0%} threshold)"
            )
        else:
            status = "ok"

        results.append(BudgetStatus(
            provider_id=rule.provider_id,
            period=period,
            total_spent=spent,
            monthly_limit=rule.monthly_limit,
            utilization=utilization,
            status=status,
            action_on_exceed=rule.action_on_exceed,
            alerts=alerts,
        ))

    return results


def enforce_budget(db: Session, provider_id: str | None = None) -> list[dict[str, Any]]:
    """Check budgets and enforce actions for exceeded rules. Returns action log."""
    statuses = check_budget(db, provider_id)
    actions_taken: list[dict[str, Any]] = []

    for bs in statuses:
        if bs.status != "exceeded":
            continue

        if bs.action_on_exceed == "alert":
            actions_taken.append({
                "provider_id": bs.provider_id,
                "action": "alert",
                "detail": bs.alerts[0] if bs.alerts else "Budget exceeded",
            })
            continue

        if bs.action_on_exceed in ("scale_down", "terminate_ephemeral"):
            targets = _get_enforceable_resources(db, bs.provider_id, bs.action_on_exceed)
            for resource in targets:
                action_type = "terminate" if bs.action_on_exceed == "terminate_ephemeral" else "scale_down"
                log = ActionLog(
                    resource_id=resource.id,
                    action_type=action_type,
                    status="pending",
                    initiated_by="budget_monitor",
                    details={"reason": bs.alerts[0] if bs.alerts else "Budget exceeded"},
                )
                db.add(log)
                actions_taken.append({
                    "provider_id": bs.provider_id,
                    "resource_id": resource.id,
                    "resource_name": resource.display_name,
                    "action": action_type,
                    "detail": f"{action_type} triggered by budget enforcement",
                })
            db.commit()

    return actions_taken


def _get_enforceable_resources(
    db: Session, provider_id: str | None, action: str,
) -> list[CloudResource]:
    """Find resources eligible for budget enforcement."""
    q = db.query(CloudResource).filter(
        CloudResource.status == "running",
        CloudResource.protection_level != "critical",
    )
    if provider_id:
        q = q.filter(CloudResource.provider_id == provider_id)

    if action == "terminate_ephemeral":
        q = q.filter(
            CloudResource.auto_terminate == True,  # noqa: E712
            CloudResource.protection_level == "ephemeral",
        )
    elif action == "scale_down":
        q = q.filter(CloudResource.auto_terminate == True)  # noqa: E712

    return q.order_by(CloudResource.monthly_cost_estimate.desc()).all()
