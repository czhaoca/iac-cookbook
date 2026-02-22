"""GCP provider adapter — stub for future implementation.

Docs: https://cloud.google.com/python/docs/reference
SDK:  pip install google-cloud-compute google-auth
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import ProviderAdapter

logger = logging.getLogger(__name__)


class GCPAdapter(ProviderAdapter):
    provider_type = "gcp"

    def authenticate(self, credentials_path: str, **kwargs: Any) -> None:
        """Authenticate via GCP service account JSON key.

        Expected config: local/config/gcp-service-account.json
        """
        logger.info("GCP adapter: authentication not yet implemented")

    def list_resources(self, resource_type: str | None = None) -> list[dict]:
        logger.info("GCP adapter: list_resources stub")
        return []

    def get_resource(self, resource_id: str) -> dict:
        return {"external_id": resource_id, "status": "unknown", "provider": "gcp"}

    def provision(self, resource_type: str, config: dict) -> dict:
        raise NotImplementedError("GCP provisioning not yet implemented")

    def terminate(self, resource_id: str) -> bool:
        raise NotImplementedError("GCP termination not yet implemented")

    def get_spending(self, period: str) -> float:
        return 0.0
