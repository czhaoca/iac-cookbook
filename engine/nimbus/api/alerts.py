"""Alert API — test alert dispatch and manage configuration."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..services.alerts import AlertConfig, dispatch_alert

router = APIRouter(prefix="/alerts", tags=["alerts"])

_CONFIG_PATH = str(settings.local_dir / "config" / "alerts.json")


class TestAlertRequest(BaseModel):
    title: str = "Test alert from Nimbus"
    alert_type: str = "test"


@router.post("/test")
def test_alert(body: TestAlertRequest):
    """Send a test alert to all configured destinations."""
    config = AlertConfig.from_file(_CONFIG_PATH)
    if not config.webhooks and not config.email_to:
        return {"error": "No alert destinations configured. Copy templates/alerts.template.json to local/config/alerts.json"}
    result = dispatch_alert(config, body.alert_type, body.title, {"source": "manual_test"})
    return result


@router.get("/config-status")
def alert_config_status():
    """Check if alert configuration exists and is valid."""
    config = AlertConfig.from_file(_CONFIG_PATH)
    return {
        "configured": bool(config.webhooks or config.email_to),
        "webhook_count": len(config.webhooks),
        "email_recipients": len(config.email_to),
        "config_path": _CONFIG_PATH,
    }
