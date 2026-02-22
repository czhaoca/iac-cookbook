"""Alert API — test alert dispatch and manage configuration."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..services.alerts import AlertConfig, dispatch_alert

router = APIRouter(prefix="/alerts", tags=["alerts"])

_CONFIG_PATH = Path(settings.local_dir / "config" / "alerts.json")


class TestAlertRequest(BaseModel):
    title: str = "Test alert from Nimbus"
    alert_type: str = "test"


class AlertConfigUpdate(BaseModel):
    webhooks: list[str] = []
    email_to: list[str] = []
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587


@router.post("/test")
def test_alert(body: TestAlertRequest):
    """Send a test alert to all configured destinations."""
    config = AlertConfig.from_file(str(_CONFIG_PATH))
    if not config.webhooks and not config.email_to:
        return {"error": "No alert destinations configured. Copy templates/alerts.template.json to local/config/alerts.json"}
    result = dispatch_alert(config, body.alert_type, body.title, {"source": "manual_test"})
    return result


@router.get("/config-status")
def alert_config_status():
    """Check if alert configuration exists and is valid."""
    config = AlertConfig.from_file(str(_CONFIG_PATH))
    return {
        "configured": bool(config.webhooks or config.email_to),
        "webhook_count": len(config.webhooks),
        "email_recipients": len(config.email_to),
        "config_path": str(_CONFIG_PATH),
    }


@router.get("/config")
def get_alert_config():
    """Get current alert configuration."""
    config = AlertConfig.from_file(str(_CONFIG_PATH))
    return {
        "webhooks": config.webhooks,
        "email_to": config.email_to,
        "email_from": config.email_from,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
    }


@router.put("/config")
def update_alert_config(body: AlertConfigUpdate):
    """Update alert configuration."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "webhooks": body.webhooks,
        "email_to": body.email_to,
        "email_from": body.email_from,
        "smtp_host": body.smtp_host,
        "smtp_port": body.smtp_port,
    }
    _CONFIG_PATH.write_text(json.dumps(data, indent=2))
    return {"status": "saved", **data}
