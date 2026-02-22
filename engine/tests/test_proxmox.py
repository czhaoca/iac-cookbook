"""Tests for Proxmox adapter (mocked API calls)."""

import json
from unittest.mock import patch, MagicMock

from nimbus.providers.proxmox.adapter import ProxmoxAdapter


class TestProxmoxAdapter:
    """Test Proxmox adapter with mocked HTTP responses."""

    def _make_adapter(self) -> ProxmoxAdapter:
        adapter = ProxmoxAdapter()
        adapter._base_url = "https://pve.test:8006"
        adapter._token_id = "test@pam!test"
        adapter._token_secret = "test-secret"
        adapter._node = "pve"
        adapter._verify_ssl = False
        return adapter

    def _mock_api(self, adapter: ProxmoxAdapter, data):
        """Patch _api to return given data."""
        return patch.object(adapter, "_api", return_value={"data": data})

    def test_provider_type(self):
        adapter = ProxmoxAdapter()
        assert adapter.provider_type == "proxmox"

    def test_list_vms(self):
        adapter = self._make_adapter()
        vms = [
            {"vmid": 100, "name": "web-server", "status": "running", "cpus": 2, "maxmem": 4294967296, "maxdisk": 32212254720, "uptime": 3600},
            {"vmid": 101, "name": "db-server", "status": "stopped", "cpus": 4, "maxmem": 8589934592, "maxdisk": 64424509440, "uptime": 0},
        ]
        with self._mock_api(adapter, vms):
            resources = adapter.list_resources("vm")
        assert len(resources) == 2
        assert resources[0]["display_name"] == "web-server"
        assert resources[0]["external_id"] == "100"
        assert resources[0]["status"] == "running"
        assert resources[0]["tags"]["cpus"] == "2"

    def test_list_containers(self):
        adapter = self._make_adapter()
        cts = [{"vmid": 200, "name": "nginx-ct", "status": "running", "cpus": 1, "maxmem": 536870912, "maxdisk": 8589934592}]
        with self._mock_api(adapter, cts):
            resources = adapter.list_resources("container")
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "container"
        assert resources[0]["display_name"] == "nginx-ct"

    def test_list_all_resources(self):
        adapter = self._make_adapter()
        call_count = 0
        def mock_api(method, path, data=None):
            nonlocal call_count
            call_count += 1
            if "qemu" in path:
                return {"data": [{"vmid": 100, "name": "vm1", "status": "running"}]}
            elif "lxc" in path:
                return {"data": [{"vmid": 200, "name": "ct1", "status": "running"}]}
            return {"data": []}
        with patch.object(adapter, "_api", side_effect=mock_api):
            resources = adapter.list_resources()
        assert len(resources) == 2
        assert call_count == 2  # qemu + lxc

    def test_get_resource(self):
        adapter = self._make_adapter()
        vm_data = {"name": "web-server", "status": "running", "vmid": 100}
        with self._mock_api(adapter, vm_data):
            result = adapter.get_resource("100")
        assert result["display_name"] == "web-server"
        assert result["status"] == "running"

    def test_health_check(self):
        adapter = self._make_adapter()
        vm_data = {"name": "web-server", "status": "running"}
        with self._mock_api(adapter, vm_data):
            health = adapter.health_check("100")
        assert health["status"] == "running"
        assert health["resource_id"] == "100"

    def test_health_check_error(self):
        adapter = self._make_adapter()
        with patch.object(adapter, "_api", side_effect=Exception("connection refused")):
            health = adapter.health_check("100")
        assert health["status"] == "error"
        assert "connection refused" in health["error"]

    def test_scale_down(self):
        adapter = self._make_adapter()
        with self._mock_api(adapter, "UPID:pve:00001234"):
            result = adapter.scale_down("100")
        assert result is True

    def test_start(self):
        adapter = self._make_adapter()
        with self._mock_api(adapter, "UPID:pve:00001235"):
            result = adapter.start("100")
        assert result is True

    def test_spending_zero(self):
        adapter = self._make_adapter()
        assert adapter.get_spending("2026-02") == 0.0

    def test_node_status(self):
        adapter = self._make_adapter()
        node_data = {
            "uptime": 86400,
            "cpu": 0.15,
            "cpuinfo": {"cores": 4, "sockets": 1},
            "memory": {"total": 17179869184, "used": 8589934592},
        }
        with self._mock_api(adapter, node_data):
            status = adapter.get_node_status()
        assert status["cpu_cores"] == 4
        assert status["cpu_usage"] == 15.0
        assert status["memory_total_gb"] == 16.0
        assert status["memory_usage_pct"] == 50.0

    def test_list_storage(self):
        adapter = self._make_adapter()
        storage_data = [
            {"storage": "local", "type": "dir", "total": 107374182400, "used": 53687091200, "avail": 53687091200, "active": 1},
            {"storage": "local-lvm", "type": "lvmthin", "total": 214748364800, "used": 107374182400, "avail": 107374182400, "active": 1},
        ]
        with self._mock_api(adapter, storage_data):
            result = adapter.list_storage()
        assert len(result) == 2
        assert result[0]["storage"] == "local"
        assert result[0]["active"] is True
        assert result[0]["total_gb"] == 100.0

    def test_provision_vm_from_scratch(self):
        adapter = self._make_adapter()
        calls = []
        def mock_api(method, path, data=None):
            calls.append((method, path))
            if "nextid" in path:
                return {"data": "105"}
            return {"data": "UPID:pve:00001234"}
        with patch.object(adapter, "_api", side_effect=mock_api):
            result = adapter.provision("vm", {
                "name": "test-vm",
                "memory": 4096,
                "cores": 4,
                "storage": "local-lvm",
                "disk_size": 64,
            })
        assert result["external_id"] == "105"
        assert result["display_name"] == "test-vm"
        assert result["resource_type"] == "vm"

    def test_provision_vm_clone(self):
        adapter = self._make_adapter()
        calls = []
        def mock_api(method, path, data=None):
            calls.append((method, path))
            if "nextid" in path:
                return {"data": "106"}
            return {"data": "UPID:pve:clone"}
        with patch.object(adapter, "_api", side_effect=mock_api):
            result = adapter.provision("vm", {
                "name": "cloned-vm",
                "clone": 9000,
            })
        assert result["external_id"] == "106"
        # Should have called clone endpoint
        assert any("clone" in p for _, p in calls)

    def test_provision_vm_cloud_init(self):
        adapter = self._make_adapter()
        calls = []
        def mock_api(method, path, data=None):
            calls.append((method, path, data))
            if "nextid" in path:
                return {"data": "107"}
            return {"data": "UPID:ok"}
        with patch.object(adapter, "_api", side_effect=mock_api):
            adapter.provision("vm", {
                "name": "ci-vm",
                "cloud_init": True,
                "ci_user": "admin",
                "ci_ip": "ip=10.0.0.5/24,gw=10.0.0.1",
                "start": True,
            })
        # Should have config PUT for cloud-init and start POST
        methods = [(m, p) for m, p, _ in calls]
        assert any(m == "PUT" and "config" in p for m, p in methods)
        assert any("start" in p for _, p in methods)

    def test_provision_container(self):
        adapter = self._make_adapter()
        def mock_api(method, path, data=None):
            if "nextid" in path:
                return {"data": "200"}
            return {"data": "UPID:pve:ct"}
        with patch.object(adapter, "_api", side_effect=mock_api):
            result = adapter.provision("container", {
                "hostname": "nginx-ct",
                "ostemplate": "local:vztmpl/ubuntu-22.04.tar.zst",
                "memory": 1024,
                "start": True,
            })
        assert result["external_id"] == "200"
        assert result["resource_type"] == "container"
        assert result["status"] == "running"

    def test_provision_vm_failure(self):
        adapter = self._make_adapter()
        def mock_api(method, path, data=None):
            if "nextid" in path:
                return {"data": "108"}
            return {"data": None, "errors": "insufficient resources"}
        with patch.object(adapter, "_api", side_effect=mock_api):
            try:
                adapter.provision("vm", {"name": "fail-vm"})
                assert False, "Should have raised"
            except RuntimeError as e:
                assert "insufficient resources" in str(e)
