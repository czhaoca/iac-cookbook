"""Settings API — manage engine configuration like cron intervals."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.setting import Setting

router = APIRouter(prefix="/settings", tags=["settings"])

# Defaults
DEFAULTS = {
    "spending_sync_interval": "300",
    "budget_enforce_interval": "600",
    "health_check_interval": "120",
}


class SettingUpdate(BaseModel):
    value: str


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    """Get all settings with defaults applied."""
    stored = {s.key: s.value for s in db.query(Setting).all()}
    result = {}
    for key, default in DEFAULTS.items():
        result[key] = stored.get(key, default)
    # Include any extra stored settings
    for key, val in stored.items():
        if key not in result:
            result[key] = val
    return result


@router.get("/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    setting = db.get(Setting, key)
    return {"key": key, "value": setting.value if setting else DEFAULTS.get(key, "")}


@router.put("/{key}")
def update_setting(key: str, body: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.get(Setting, key)
    if setting:
        setting.value = body.value
    else:
        setting = Setting(key=key, value=body.value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": body.value}
