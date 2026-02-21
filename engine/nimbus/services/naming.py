"""Naming service — prefix-based resource naming with collision prevention."""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models.resource import CloudResource


def generate_name(
    prefix: str,
    resource_type: str,
    label: str,
    db: Session,
    provider_id: Optional[str] = None,
) -> str:
    """Generate a unique resource name: {prefix}-{type}-{label}-{seq}.

    Auto-increments seq if a collision is found in the database.
    """
    base = f"{prefix}-{resource_type}-{label}"
    base = _sanitize(base)

    # Check existing names with this pattern
    pattern = f"{base}-%"
    q = db.query(CloudResource).filter(CloudResource.display_name.like(pattern))
    if provider_id:
        q = q.filter(CloudResource.provider_id == provider_id)
    existing = {r.display_name for r in q.all()}

    # Also check the un-sequenced name
    exact_q = db.query(CloudResource).filter(CloudResource.display_name == base)
    if provider_id:
        exact_q = exact_q.filter(CloudResource.provider_id == provider_id)
    if exact_q.first() is not None:
        existing.add(base)

    if base not in existing and not existing:
        return base

    # Find next sequence number
    seq = 1
    while f"{base}-{seq:02d}" in existing:
        seq += 1
    return f"{base}-{seq:02d}"


def check_collision(name: str, db: Session, provider_id: Optional[str] = None) -> bool:
    """Return True if a resource with this display_name already exists."""
    q = db.query(CloudResource).filter(CloudResource.display_name == name)
    if provider_id:
        q = q.filter(CloudResource.provider_id == provider_id)
    return q.first() is not None


def _sanitize(name: str) -> str:
    """Sanitize a name to lowercase alphanumeric + hyphens."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")
