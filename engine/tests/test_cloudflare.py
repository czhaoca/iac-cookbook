"""Tests for Cloudflare adapter (mocked API calls)."""

from unittest.mock import patch

from nimbus.providers.cloudflare.adapter import CloudflareAdapter


class TestCloudflareAdapter:
    """Test Cloudflare adapter with mocked HTTP responses."""

    def _make_adapter(self) -> CloudflareAdapter:
        adapter = CloudflareAdapter()
        adapter._token = "test-token"
        return adapter

    def _mock_api(self, adapter, return_value):
        return patch.object(adapter, "_api", return_value=return_value)

    def test_provider_type(self):
        assert CloudflareAdapter().provider_type == "cloudflare"

    def test_list_zones(self):
        adapter = self._make_adapter()
        zones = [{"id": "z1", "name": "example.com", "status": "active"}]
        with self._mock_api(adapter, {"result": zones, "success": True}):
            resources = adapter.list_resources("zone")
        assert len(resources) == 1
        assert resources[0]["display_name"] == "example.com"
        assert resources[0]["resource_type"] == "zone"

    def test_list_dns_records(self):
        adapter = self._make_adapter()
        zones = [{"id": "z1", "name": "example.com"}]
        records = [
            {"id": "r1", "name": "app.example.com", "type": "A", "content": "1.2.3.4", "proxied": True, "ttl": 1},
        ]
        call_count = 0
        def mock_api(method, path, data=None):
            nonlocal call_count
            call_count += 1
            if "dns_records" in path:
                return {"result": records, "success": True}
            return {"result": zones, "success": True}
        with patch.object(adapter, "_api", side_effect=mock_api):
            resources = adapter.list_resources("dns_record")
        assert len(resources) == 1
        assert resources[0]["display_name"] == "app.example.com (A)"
        assert resources[0]["tags"]["content"] == "1.2.3.4"

    def test_provision_dns_record(self):
        adapter = self._make_adapter()
        resp = {"success": True, "result": {"id": "r2", "name": "new.example.com", "type": "A"}}
        with self._mock_api(adapter, resp):
            result = adapter.provision("dns_record", {
                "zone_id": "z1", "type": "A", "name": "new.example.com", "content": "5.6.7.8",
            })
        assert result["external_id"] == "r2"
        assert result["resource_type"] == "dns_record"

    def test_provision_invalid_type(self):
        adapter = self._make_adapter()
        try:
            adapter.provision("vm", {})
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "dns_record" in str(e)

    def test_terminate_dns_record(self):
        adapter = self._make_adapter()
        zones = [{"id": "z1", "name": "example.com"}]
        def mock_api(method, path, data=None):
            if method == "DELETE":
                return {"success": True}
            return {"result": zones, "success": True}
        with patch.object(adapter, "_api", side_effect=mock_api):
            assert adapter.terminate("r1") is True

    def test_health_check_found(self):
        adapter = self._make_adapter()
        zones = [{"id": "z1", "name": "example.com"}]
        record = {"id": "r1", "name": "app", "type": "A", "content": "1.2.3.4"}
        def mock_api(method, path, data=None):
            if "dns_records/r1" in path:
                return {"success": True, "result": record}
            return {"result": zones, "success": True}
        with patch.object(adapter, "_api", side_effect=mock_api):
            health = adapter.health_check("r1")
        assert health["status"] == "healthy"

    def test_spending_zero(self):
        adapter = self._make_adapter()
        assert adapter.get_spending("2026-02") == 0.0

    def test_create_dns_record_convenience(self):
        adapter = self._make_adapter()
        resp = {"success": True, "result": {"id": "r3", "name": "sub.example.com", "type": "CNAME"}}
        with self._mock_api(adapter, resp):
            result = adapter.create_dns_record("z1", "CNAME", "sub.example.com", "target.example.com")
        assert result["external_id"] == "r3"

    def test_update_dns_record(self):
        adapter = self._make_adapter()
        resp = {"success": True, "result": {"id": "r1", "content": "9.8.7.6"}}
        with self._mock_api(adapter, resp):
            result = adapter.update_dns_record("z1", "r1", "A", "app.example.com", "9.8.7.6")
        assert result["content"] == "9.8.7.6"

    def test_lockdown_zone_with_whitelist(self):
        adapter = self._make_adapter()
        # Mock _get_or_create_custom_ruleset and _api
        ruleset = {"id": "rs1", "rules": []}
        with patch.object(adapter, "_get_or_create_custom_ruleset", return_value=ruleset):
            with self._mock_api(adapter, {"success": True}):
                result = adapter.lockdown_zone("z1", whitelist_ips=["1.2.3.4"])
        assert result.get("success") is True

    def test_lockdown_zone_block_all(self):
        adapter = self._make_adapter()
        ruleset = {"id": "rs1", "rules": []}
        with patch.object(adapter, "_get_or_create_custom_ruleset", return_value=ruleset):
            with self._mock_api(adapter, {"success": True}):
                result = adapter.lockdown_zone("z1")
        assert result.get("success") is True
