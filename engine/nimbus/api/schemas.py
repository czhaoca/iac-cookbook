"""Pydantic schemas for API request/response — decoupled from SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Provider schemas
# ---------------------------------------------------------------------------


class ProviderCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, description="Unique provider ID, e.g. 'oci-main'")
    provider_type: str = Field(..., min_length=1, max_length=32)
    display_name: str = Field(..., min_length=1, max_length=128)
    region: str = ""
    credentials_path: str = ""
    is_active: bool = True


class ProviderUpdate(BaseModel):
    display_name: Optional[str] = None
    region: Optional[str] = None
    credentials_path: Optional[str] = None
    is_active: Optional[bool] = None


class ProviderOut(BaseModel):
    id: str
    provider_type: str
    display_name: str
    region: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Resource schemas
# ---------------------------------------------------------------------------


class ResourceCreate(BaseModel):
    provider_id: str
    resource_type: str
    external_id: str = ""
    display_name: str
    name_prefix: str = ""
    status: str = "unknown"
    tags: dict[str, Any] = Field(default_factory=dict)
    protection_level: str = "standard"
    auto_terminate: bool = False
    monthly_cost_estimate: float = 0.0


class ResourceUpdate(BaseModel):
    display_name: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[dict[str, Any]] = None
    protection_level: Optional[str] = None
    auto_terminate: Optional[bool] = None
    monthly_cost_estimate: Optional[float] = None


class ResourceOut(BaseModel):
    id: str
    provider_id: str
    resource_type: str
    external_id: str
    display_name: str
    name_prefix: str
    status: str
    tags: dict[str, Any]
    protection_level: str
    auto_terminate: bool
    monthly_cost_estimate: float
    created_at: datetime
    updated_at: datetime
    last_seen_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Action schemas
# ---------------------------------------------------------------------------


class ActionRequest(BaseModel):
    action: str = Field(..., description="Action to perform: stop, start, terminate, sync")


class ActionOut(BaseModel):
    id: str
    resource_id: Optional[str]
    action_type: str
    status: str
    details: dict[str, Any]
    initiated_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sync result
# ---------------------------------------------------------------------------


class SyncResult(BaseModel):
    provider_id: str
    synced: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Budget schemas
# ---------------------------------------------------------------------------


class BudgetRuleCreate(BaseModel):
    provider_id: Optional[str] = Field(None, description="Provider ID, null for global rule")
    monthly_limit: float = Field(..., gt=0, description="Monthly spend limit in USD")
    alert_threshold: float = Field(0.8, ge=0.0, le=1.0, description="Alert at this fraction of limit")
    action_on_exceed: str = Field("alert", description="alert | scale_down | terminate_ephemeral | firewall_lockdown")
    is_active: bool = True


class BudgetRuleUpdate(BaseModel):
    monthly_limit: Optional[float] = None
    alert_threshold: Optional[float] = None
    action_on_exceed: Optional[str] = None
    is_active: Optional[bool] = None


class BudgetRuleOut(BaseModel):
    id: str
    provider_id: Optional[str]
    monthly_limit: float
    alert_threshold: float
    action_on_exceed: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SpendingRecordOut(BaseModel):
    id: str
    provider_id: str
    period: str
    amount: float
    currency: str
    recorded_at: datetime

    model_config = {"from_attributes": True}


class BudgetStatus(BaseModel):
    """Aggregated budget health for a provider or globally."""
    provider_id: Optional[str]
    period: str
    total_spent: float
    monthly_limit: float
    utilization: float  # 0.0 - 1.0+
    status: str  # ok | warning | exceeded
    action_on_exceed: str
    alerts: list[str] = Field(default_factory=list)
