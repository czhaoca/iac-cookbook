"""Action log model — audit trail for all operations performed by Nimbus."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cloud_resources.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # provision, terminate, scale, firewall_update, dns_update, budget_check
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending, running, success, failed
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    initiated_by: Mapped[str] = mapped_column(
        String(32), default="user"
    )  # user, budget_monitor, health_checker, cli
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
