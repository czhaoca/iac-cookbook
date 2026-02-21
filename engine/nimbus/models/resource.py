"""Cloud resource model — tracks VMs, volumes, DNS records, etc. across providers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class CloudResource(Base):
    __tablename__ = "cloud_resources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("provider_configs.id"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)  # vm, volume, dns_record, firewall_rule
    external_id: Mapped[str] = mapped_column(Text, default="")  # provider's ID (OCID, ARM ID, etc.)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    name_prefix: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="unknown")  # running, stopped, terminated, unknown
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    protection_level: Mapped[str] = mapped_column(
        String(16), default="standard"
    )  # critical, standard, ephemeral
    auto_terminate: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
