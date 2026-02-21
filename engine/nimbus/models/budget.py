"""Budget models — rules and spending records for cost enforcement."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class BudgetRule(Base):
    __tablename__ = "budget_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("provider_configs.id"), nullable=True
    )  # null = global rule
    monthly_limit: Mapped[float] = mapped_column(Float, nullable=False)
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.8)  # 0.0-1.0
    action_on_exceed: Mapped[str] = mapped_column(
        String(32), default="alert"
    )  # alert, scale_down, terminate_ephemeral, firewall_lockdown
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SpendingRecord(Base):
    __tablename__ = "spending_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("provider_configs.id"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-02"
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
