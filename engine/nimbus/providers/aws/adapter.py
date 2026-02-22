"""AWS provider adapter — stub for future implementation.

Docs: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
SDK:  pip install boto3
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import ProviderAdapter

logger = logging.getLogger(__name__)


class AWSAdapter(ProviderAdapter):
    provider_type = "aws"

    def authenticate(self, credentials_path: str, **kwargs: Any) -> None:
        """Authenticate via AWS credentials file or environment variables.

        Expected config: local/config/aws-credentials (INI format)
            [default]
            aws_access_key_id = AKIA...
            aws_secret_access_key = ...
            region = us-east-1
        """
        logger.info("AWS adapter: authentication not yet implemented")

    def list_resources(self, resource_type: str | None = None) -> list[dict]:
        logger.info("AWS adapter: list_resources stub")
        return []

    def get_resource(self, resource_id: str) -> dict:
        return {"external_id": resource_id, "status": "unknown", "provider": "aws"}

    def provision(self, resource_type: str, config: dict) -> dict:
        raise NotImplementedError("AWS provisioning not yet implemented")

    def terminate(self, resource_id: str) -> bool:
        raise NotImplementedError("AWS termination not yet implemented")

    def get_spending(self, period: str) -> float:
        return 0.0
