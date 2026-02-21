"""initial schema — providers, resources, budget, action_log

Revision ID: 001
Revises:
Create Date: 2026-02-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("region", sa.String(64), server_default=""),
        sa.Column("credentials_path", sa.Text, server_default=""),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cloud_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(64), sa.ForeignKey("provider_configs.id"), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.Text, server_default=""),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("name_prefix", sa.String(32), server_default=""),
        sa.Column("status", sa.String(32), server_default="unknown"),
        sa.Column("tags", sa.JSON, server_default="{}"),
        sa.Column("protection_level", sa.String(16), server_default="standard"),
        sa.Column("auto_terminate", sa.Boolean, server_default=sa.text("0")),
        sa.Column("monthly_cost_estimate", sa.Float, server_default=sa.text("0.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "budget_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(64), sa.ForeignKey("provider_configs.id"), nullable=True),
        sa.Column("monthly_limit", sa.Float, nullable=False),
        sa.Column("alert_threshold", sa.Float, server_default=sa.text("0.8")),
        sa.Column("action_on_exceed", sa.String(32), server_default="alert"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "spending_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(64), sa.ForeignKey("provider_configs.id"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("amount", sa.Float, server_default=sa.text("0.0")),
        sa.Column("currency", sa.String(3), server_default="USD"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "action_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("cloud_resources.id"), nullable=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("details", sa.JSON, server_default="{}"),
        sa.Column("initiated_by", sa.String(32), server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("action_logs")
    op.drop_table("spending_records")
    op.drop_table("budget_rules")
    op.drop_table("cloud_resources")
    op.drop_table("provider_configs")
