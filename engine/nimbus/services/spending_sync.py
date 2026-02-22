"""Spending sync — periodic background task to pull spending from provider APIs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db import SessionLocal, init_db
from ..models.provider import ProviderConfig
from ..services.budget_monitor import record_spending, current_period
from ..services.registry import registry

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes


async def sync_spending_once(db: Session | None = None) -> dict:
    """Pull current-period spending from all registered providers.

    Returns summary of what was synced.
    """
    own_session = db is None
    if own_session:
        init_db()
        db = SessionLocal()

    try:
        providers = db.query(ProviderConfig).all()
        results = []

        for provider in providers:
            adapter = registry.get_adapter(provider.id, db)
            if adapter is None:
                results.append({
                    "provider_id": provider.id,
                    "status": "skipped",
                    "reason": "no adapter instance",
                })
                continue

            period = current_period()
            try:
                amount = adapter.get_spending(period)
                if amount is not None and amount >= 0:
                    record_spending(db, provider.id, amount, period)
                    results.append({
                        "provider_id": provider.id,
                        "status": "ok",
                        "period": period,
                        "amount": amount,
                    })
                else:
                    results.append({
                        "provider_id": provider.id,
                        "status": "skipped",
                        "reason": "no spending data",
                    })
            except Exception as e:
                logger.warning("Spending sync failed for %s: %s", provider.id, e)
                results.append({
                    "provider_id": provider.id,
                    "status": "error",
                    "error": str(e),
                })

        return {
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "providers": results,
        }
    finally:
        if own_session:
            db.close()


async def spending_sync_loop(interval: int = DEFAULT_INTERVAL_SECONDS) -> None:
    """Run spending sync in a loop. Intended to be started as a background task."""
    logger.info("Spending sync loop started (interval=%ds)", interval)
    while True:
        try:
            result = await sync_spending_once()
            synced = [r for r in result["providers"] if r["status"] == "ok"]
            if synced:
                logger.info("Spending synced for %d providers", len(synced))
        except Exception as e:
            logger.error("Spending sync loop error: %s", e)
        await asyncio.sleep(interval)
