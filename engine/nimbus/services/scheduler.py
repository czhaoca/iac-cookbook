"""Scheduled tasks — periodic background jobs for spending sync, budget enforcement, and health checks."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from ..db import SessionLocal, init_db
from ..services.budget_monitor import check_budget, enforce_budget
from ..services.spending_sync import sync_spending_once
from ..services.alerts import send_alert

logger = logging.getLogger(__name__)

# Default intervals (seconds) — configurable via settings
DEFAULT_SPENDING_INTERVAL = 300      # 5 min
DEFAULT_BUDGET_INTERVAL = 600        # 10 min
DEFAULT_HEALTH_INTERVAL = 120        # 2 min


async def budget_enforcement_loop(interval: int = DEFAULT_BUDGET_INTERVAL) -> None:
    """Periodically check budgets and enforce actions on exceeded rules."""
    logger.info("Budget enforcement loop started (interval=%ds)", interval)
    while True:
        try:
            init_db()
            db = SessionLocal()
            try:
                statuses = check_budget(db)
                warnings = [s for s in statuses if s.status in ("warning", "exceeded")]

                if warnings:
                    for s in warnings:
                        logger.warning(
                            "Budget %s for %s: $%.2f / $%.2f (%.0f%%)",
                            s.status, s.provider_id or "global",
                            s.total_spent, s.monthly_limit, s.utilization * 100,
                        )
                        # Send alert for warnings and exceeded
                        try:
                            await _send_budget_alert(db, s)
                        except Exception as e:
                            logger.error("Failed to send budget alert: %s", e)

                # Auto-enforce exceeded budgets
                exceeded = [s for s in statuses if s.status == "exceeded"]
                if exceeded:
                    actions = enforce_budget(db)
                    if actions:
                        logger.warning("Budget enforcement: %d actions taken", len(actions))
            finally:
                db.close()
        except Exception as e:
            logger.error("Budget enforcement loop error: %s", e)
        await asyncio.sleep(interval)


async def health_check_loop(interval: int = DEFAULT_HEALTH_INTERVAL) -> None:
    """Periodically check health of all tracked resources."""
    logger.info("Health check loop started (interval=%ds)", interval)
    while True:
        try:
            init_db()
            db = SessionLocal()
            try:
                from ..models.resource import CloudResource
                from ..services.registry import registry

                resources = (
                    db.query(CloudResource)
                    .filter(CloudResource.status == "running")
                    .all()
                )

                for resource in resources:
                    adapter = registry.get_adapter(resource.provider_id, db)
                    if adapter is None:
                        continue
                    try:
                        health = adapter.health_check(resource.external_id)
                        status = health.get("status", "unknown")
                        if status in ("error", "unhealthy"):
                            logger.warning(
                                "Resource %s (%s) unhealthy: %s",
                                resource.display_name, resource.external_id, health,
                            )
                    except Exception as e:
                        logger.debug("Health check failed for %s: %s", resource.external_id, e)
            finally:
                db.close()
        except Exception as e:
            logger.error("Health check loop error: %s", e)
        await asyncio.sleep(interval)


async def _send_budget_alert(db: Any, status: Any) -> None:
    """Send alert notification for budget warning/exceeded."""
    level = "critical" if status.status == "exceeded" else "warning"
    message = (
        f"Budget {status.status}: "
        f"${status.total_spent:.2f} / ${status.monthly_limit:.2f} "
        f"({status.utilization:.0%}) for {status.provider_id or 'all providers'}"
    )
    await asyncio.to_thread(send_alert, level, message, db)


def get_intervals_from_settings(db: Any) -> dict[str, int]:
    """Read cron intervals from settings table."""
    from ..models.settings import Setting

    intervals = {
        "spending_sync": DEFAULT_SPENDING_INTERVAL,
        "budget_enforce": DEFAULT_BUDGET_INTERVAL,
        "health_check": DEFAULT_HEALTH_INTERVAL,
    }
    for key in intervals:
        setting = db.query(Setting).filter(Setting.key == f"{key}_interval").first()
        if setting:
            try:
                intervals[key] = int(setting.value)
            except ValueError:
                pass
    return intervals
