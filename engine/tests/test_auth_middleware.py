"""Tests for API key authentication middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(api_key: str | None):
    """Create a minimal app with ApiKeyMiddleware."""
    from nimbus.middleware import ApiKeyMiddleware

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/test")
    def api_test():
        return {"data": "secret"}

    app.add_middleware(ApiKeyMiddleware, api_key=api_key)
    return app


class TestApiKeyAuth:
    """Test API key authentication middleware."""

    def test_no_auth_when_key_not_set(self):
        """Without API key, all endpoints are accessible."""
        app = _make_app(api_key=None)
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/health").status_code == 200
        assert client.get("/api/test").status_code == 200

    def test_health_exempt_with_auth(self):
        """/health accessible even with API key set."""
        app = _make_app(api_key="test-key-123")
        client = TestClient(app, raise_server_exceptions=False)

        assert client.get("/health").status_code == 200

    def test_api_requires_key(self):
        """API endpoints require valid key."""
        app = _make_app(api_key="test-key-123")
        client = TestClient(app, raise_server_exceptions=False)

        assert client.get("/api/test").status_code == 401

    def test_api_with_valid_key(self):
        """API accessible with correct Bearer token."""
        app = _make_app(api_key="test-key-123")
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/api/test", headers={"Authorization": "Bearer test-key-123"})
        assert resp.status_code == 200
        assert resp.json()["data"] == "secret"

    def test_api_with_wrong_key(self):
        """API rejects wrong key."""
        app = _make_app(api_key="test-key-123")
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/api/test", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401
