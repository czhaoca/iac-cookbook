"""API key authentication middleware.

When NIMBUS_API_KEY is set, all /api/* endpoints require the header:
  Authorization: Bearer <api_key>

Health, docs, and WebSocket endpoints are exempt.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from ..config import settings

_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/ws"})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str | None = None) -> None:  # noqa: ANN001
        super().__init__(app)
        self._api_key = api_key if api_key is not None else settings.api_key

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._api_key:
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_PATHS or not path.startswith("/api"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {self._api_key}":
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"},
        )
