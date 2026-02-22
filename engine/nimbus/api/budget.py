"""Budget API — CRUD for rules, spending records, and budget status checks."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.budget import BudgetRule, SpendingRecord
from ..services.budget_monitor import (
    check_budget,
    current_period,
    enforce_budget,
    record_spending,
)
from .schemas import (
    BudgetRuleCreate,
    BudgetRuleOut,
    BudgetRuleUpdate,
    BudgetStatus,
    SpendingRecordOut,
)

router = APIRouter(prefix="/budget", tags=["budget"])


# ---------------------------------------------------------------------------
# Budget Rules CRUD
# ---------------------------------------------------------------------------


@router.get("/rules", response_model=list[BudgetRuleOut])
def list_rules(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(BudgetRule)
    if active_only:
        q = q.filter(BudgetRule.is_active == True)  # noqa: E712
    return q.order_by(BudgetRule.created_at.desc()).all()


@router.post("/rules", response_model=BudgetRuleOut, status_code=201)
def create_rule(body: BudgetRuleCreate, db: Session = Depends(get_db)):
    rule = BudgetRule(**body.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/rules/{rule_id}", response_model=BudgetRuleOut)
def get_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = db.get(BudgetRule, rule_id)
    if not rule:
        raise HTTPException(404, "Budget rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=BudgetRuleOut)
def update_rule(rule_id: str, body: BudgetRuleUpdate, db: Session = Depends(get_db)):
    rule = db.get(BudgetRule, rule_id)
    if not rule:
        raise HTTPException(404, "Budget rule not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = db.get(BudgetRule, rule_id)
    if not rule:
        raise HTTPException(404, "Budget rule not found")
    db.delete(rule)
    db.commit()


# ---------------------------------------------------------------------------
# Spending Records
# ---------------------------------------------------------------------------


@router.get("/spending", response_model=list[SpendingRecordOut])
def list_spending(
    provider_id: Optional[str] = None,
    period: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(SpendingRecord)
    if provider_id:
        q = q.filter(SpendingRecord.provider_id == provider_id)
    if period:
        q = q.filter(SpendingRecord.period == period)
    return q.order_by(SpendingRecord.recorded_at.desc()).all()


@router.post("/spending", response_model=SpendingRecordOut, status_code=201)
def upsert_spending(
    provider_id: str,
    amount: float,
    period: Optional[str] = None,
    currency: str = "USD",
    db: Session = Depends(get_db),
):
    return record_spending(db, provider_id, amount, period, currency)


# ---------------------------------------------------------------------------
# Budget Status & Enforcement
# ---------------------------------------------------------------------------


@router.get("/status", response_model=list[BudgetStatus])
def budget_status(provider_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Check current budget status for all active rules."""
    return check_budget(db, provider_id)


@router.post("/enforce")
def enforce(provider_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Run budget enforcement — checks rules and takes action on exceeded budgets."""
    actions = enforce_budget(db, provider_id)
    return {
        "period": current_period(),
        "actions_taken": len(actions),
        "details": actions,
    }
