"""Azure provider adapter — stub for future implementation.

Docs: https://learn.microsoft.com/en-us/python/api/overview/azure/
SDK:  pip install azure-identity azure-mgmt-compute azure-mgmt-resource
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import ProviderAdapter

logger = logging.getLogger(__name__)


class AzureAdapter(ProviderAdapter):
    provider_type = "azure"

    def authenticate(self, credentials_path: str, **kwargs: Any) -> None:
        """Authenticate via Azure service principal or managed identity.

        Expected config (local/config/azure.json):
            AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_SUBSCRIPTION_ID
        """
        logger.info("Azure adapter: authentication not yet implemented")

    def list_resources(self, resource_type: str | None = None) -> list[dict]:
        logger.info("Azure adapter: list_resources stub")
        return []

    def get_resource(self, resource_id: str) -> dict:
        return {"external_id": resource_id, "status": "unknown", "provider": "azure"}

    def provision(self, resource_type: str, config: dict) -> dict:
        raise NotImplementedError("Azure provisioning not yet implemented")

    def terminate(self, resource_id: str) -> bool:
        raise NotImplementedError("Azure termination not yet implemented")

    def get_spending(self, period: str) -> float:
        return 0.0
