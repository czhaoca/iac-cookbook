"""Alert dispatch — webhook and email notifications for budget/resource events."""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """Alert destination configuration. Loaded from local/config/alerts.json."""

    webhooks: list[str] = field(default_factory=list)
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_from: str = ""
    email_to: list[str] = field(default_factory=list)
    email_username: str = ""
    email_password: str = ""
    email_use_tls: bool = True

    @classmethod
    def from_file(cls, path: str) -> "AlertConfig":
        try:
            with open(path) as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except FileNotFoundError:
            logger.info("No alert config at %s — alerts disabled", path)
            return cls()
        except Exception as e:
            logger.warning("Failed to load alert config: %s", e)
            return cls()


def send_webhook(url: str, payload: dict[str, Any]) -> bool:
    """POST JSON payload to a webhook URL."""
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        logger.error("Webhook failed (%s): %s", url, e)
        return False


def send_email(config: AlertConfig, subject: str, body: str) -> bool:
    """Send an email alert via SMTP."""
    if not config.email_smtp_host or not config.email_to:
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = f"[Nimbus] {subject}"
        msg["From"] = config.email_from or "nimbus@localhost"
        msg["To"] = ", ".join(config.email_to)

        with smtplib.SMTP(config.email_smtp_host, config.email_smtp_port) as smtp:
            if config.email_use_tls:
                smtp.starttls()
            if config.email_username:
                smtp.login(config.email_username, config.email_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


def dispatch_alert(
    config: AlertConfig,
    alert_type: str,
    title: str,
    details: dict[str, Any] | None = None,
) -> dict:
    """Send alert to all configured destinations.

    Args:
        config: Alert configuration
        alert_type: e.g. "budget_warning", "budget_exceeded", "resource_down"
        title: Human-readable summary
        details: Extra data payload
    """
    payload = {
        "alert_type": alert_type,
        "title": title,
        "details": details or {},
    }

    results = {"webhooks": [], "email": None}

    for url in config.webhooks:
        ok = send_webhook(url, payload)
        results["webhooks"].append({"url": url, "success": ok})

    if config.email_to:
        body_lines = [title, ""]
        if details:
            for k, v in details.items():
                body_lines.append(f"  {k}: {v}")
        ok = send_email(config, title, "\n".join(body_lines))
        results["email"] = {"success": ok, "recipients": config.email_to}

    return results


def send_alert(level: str, message: str, db: Any = None) -> None:
    """High-level alert dispatcher — loads config and sends to all destinations.

    Args:
        level: "info", "warning", or "critical"
        message: Alert message text
        db: Optional DB session (for future DB-stored config)
    """
    from pathlib import Path

    config_path = Path(__file__).parent.parent.parent.parent / "local" / "config" / "alerts.json"
    config = AlertConfig.from_file(str(config_path))

    if not config.webhooks and not config.email_to:
        logger.debug("No alert destinations configured — skipping alert: %s", message)
        return

    alert_type = f"budget_{level}" if "budget" in message.lower() else f"system_{level}"
    dispatch_alert(config, alert_type, message)
