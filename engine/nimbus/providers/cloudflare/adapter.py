"""Cloudflare provider adapter — DNS records and zone management via REST API.

Uses the Cloudflare API v4 (https://developers.cloudflare.com/api/).
Authentication via API Token (recommended) stored in local/config/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ..base import ProviderAdapter

logger = logging.getLogger(__name__)

CF_API = "https://api.cloudflare.com/client/v4"


class CloudflareAdapter(ProviderAdapter):
    """Cloudflare provider — manages DNS records and zone info."""

    _token: str | None = None
    _zones: dict[str, str] = {}  # zone_name -> zone_id cache

    @property
    def provider_type(self) -> str:
        return "cloudflare"

    # ── Auth ──────────────────────────────────────────────────────────────

    def authenticate(self, credentials_path: str, **kwargs) -> None:
        """Load API token from credentials file (single line: token value)."""
        path = Path(credentials_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Cloudflare credentials not found: {path}")
        self._token = path.read_text().strip()
        # Verify token
        resp = self._api("GET", "/user/tokens/verify")
        if resp.get("success"):
            logger.info("Cloudflare authenticated successfully")
        else:
            raise RuntimeError(f"Cloudflare auth failed: {resp.get('errors')}")

    # ── Resource listing ──────────────────────────────────────────────────

    def list_resources(self, resource_type: str | None = None) -> list[dict[str, Any]]:
        """List DNS records across all zones (or zones themselves)."""
        resources: list[dict[str, Any]] = []

        if resource_type == "zone" or resource_type is None:
            zones = self._list_zones()
            for z in zones:
                resources.append({
                    "external_id": z["id"],
                    "resource_type": "zone",
                    "display_name": z["name"],
                    "status": z.get("status", "active"),
                })

        if resource_type == "dns_record" or resource_type is None:
            for zone in self._list_zones():
                records = self._list_dns_records(zone["id"])
                for r in records:
                    resources.append({
                        "external_id": r["id"],
                        "resource_type": "dns_record",
                        "display_name": f"{r['name']} ({r['type']})",
                        "status": "active" if r.get("proxied") else "dns_only",
                        "tags": {
                            "type": r["type"],
                            "content": r["content"],
                            "zone_id": zone["id"],
                            "zone_name": zone["name"],
                            "proxied": str(r.get("proxied", False)),
                            "ttl": str(r.get("ttl", 1)),
                        },
                    })

        return resources

    def get_resource(self, resource_id: str) -> dict[str, Any]:
        """Get a specific DNS record by ID (searches all zones)."""
        for zone in self._list_zones():
            try:
                resp = self._api("GET", f"/zones/{zone['id']}/dns_records/{resource_id}")
                if resp.get("success") and resp.get("result"):
                    r = resp["result"]
                    return {
                        "external_id": r["id"],
                        "resource_type": "dns_record",
                        "display_name": f"{r['name']} ({r['type']})",
                        "status": "active",
                        "tags": {"type": r["type"], "content": r["content"]},
                    }
            except Exception:
                continue
        return {"external_id": resource_id, "status": "not_found"}

    # ── Provisioning (DNS records) ────────────────────────────────────────

    def provision(self, resource_type: str, config: dict[str, Any]) -> dict[str, Any]:
        """Create a DNS record.

        config keys: zone_id, type (A/AAAA/CNAME), name, content, proxied, ttl
        """
        if resource_type != "dns_record":
            raise ValueError(f"Cloudflare provision supports 'dns_record', got '{resource_type}'")

        zone_id = config["zone_id"]
        payload = {
            "type": config["type"],
            "name": config["name"],
            "content": config["content"],
            "proxied": config.get("proxied", True),
            "ttl": config.get("ttl", 1),  # 1 = auto
        }

        resp = self._api("POST", f"/zones/{zone_id}/dns_records", payload)
        if not resp.get("success"):
            raise RuntimeError(f"Failed to create DNS record: {resp.get('errors')}")

        r = resp["result"]
        return {
            "external_id": r["id"],
            "resource_type": "dns_record",
            "display_name": f"{r['name']} ({r['type']})",
            "status": "active",
        }

    def terminate(self, resource_id: str) -> bool:
        """Delete a DNS record."""
        for zone in self._list_zones():
            try:
                resp = self._api("DELETE", f"/zones/{zone['id']}/dns_records/{resource_id}")
                if resp.get("success"):
                    return True
            except Exception:
                continue
        return False

    def get_spending(self, period: str) -> float:
        """Cloudflare free plan has no spending — return 0."""
        return 0.0

    def health_check(self, resource_id: str) -> dict[str, Any]:
        """Check if a DNS record exists."""
        result = self.get_resource(resource_id)
        status = "healthy" if result.get("status") != "not_found" else "unhealthy"
        return {"status": status, "resource_id": resource_id}

    # ── DNS helpers ───────────────────────────────────────────────────────

    def create_dns_record(
        self, zone_id: str, record_type: str, name: str, content: str,
        proxied: bool = True, ttl: int = 1,
    ) -> dict[str, Any]:
        """Convenience method for DNS record creation."""
        return self.provision("dns_record", {
            "zone_id": zone_id, "type": record_type,
            "name": name, "content": content,
            "proxied": proxied, "ttl": ttl,
        })

    def update_dns_record(
        self, zone_id: str, record_id: str, record_type: str,
        name: str, content: str, proxied: bool = True, ttl: int = 1,
    ) -> dict[str, Any]:
        """Update an existing DNS record."""
        payload = {
            "type": record_type, "name": name, "content": content,
            "proxied": proxied, "ttl": ttl,
        }
        resp = self._api("PUT", f"/zones/{zone_id}/dns_records/{record_id}", payload)
        if not resp.get("success"):
            raise RuntimeError(f"Failed to update DNS record: {resp.get('errors')}")
        return resp["result"]

    # ── Internal helpers ──────────────────────────────────────────────────

    def _list_zones(self) -> list[dict[str, Any]]:
        """List all zones (cached after first call)."""
        resp = self._api("GET", "/zones?per_page=50")
        return resp.get("result", [])

    def _list_dns_records(self, zone_id: str) -> list[dict[str, Any]]:
        """List all DNS records in a zone."""
        resp = self._api("GET", f"/zones/{zone_id}/dns_records?per_page=100")
        return resp.get("result", [])

    def _api(self, method: str, path: str, data: dict | None = None) -> dict:
        """Make an authenticated Cloudflare API request."""
        if not self._token:
            raise RuntimeError("Not authenticated — call authenticate() first")

        url = f"{CF_API}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            logger.error("Cloudflare API error %s %s: %s", method, path, error_body)
            try:
                return json.loads(error_body)
            except Exception:
                return {"success": False, "errors": [{"message": error_body}]}

    # -------------------------------------------------------------------
    # WAF / Firewall rules
    # -------------------------------------------------------------------

    def create_firewall_rule(
        self, zone_id: str, expression: str, action: str = "block",
        description: str = "Nimbus budget lockdown",
    ) -> dict:
        """Create a WAF custom rule (Cloudflare Rulesets API).

        Docs: https://developers.cloudflare.com/waf/custom-rules/create-api/
        Actions: block, challenge, js_challenge, managed_challenge, log
        Expression examples:
          - '(ip.src ne 1.2.3.4)' — block all except whitelist
          - '(http.request.uri.path contains "/admin")' — protect admin
        """
        self._check_auth()
        ruleset = self._get_or_create_custom_ruleset(zone_id)
        if not ruleset:
            return {"success": False, "errors": [{"message": "Failed to get/create ruleset"}]}

        rule_data = {
            "rules": [{
                "expression": expression,
                "action": action,
                "description": description,
                "enabled": True,
            }],
        }
        # Append rule to existing ruleset
        result = self._api(
            "POST",
            f"/zones/{zone_id}/rulesets/{ruleset['id']}/rules",
            data=rule_data["rules"][0],
        )
        return result

    def list_firewall_rules(self, zone_id: str) -> list[dict]:
        """List all custom WAF rules for a zone."""
        self._check_auth()
        ruleset = self._get_or_create_custom_ruleset(zone_id)
        if not ruleset:
            return []
        return ruleset.get("rules", [])

    def delete_firewall_rule(self, zone_id: str, rule_id: str) -> bool:
        """Delete a specific WAF rule."""
        self._check_auth()
        ruleset = self._get_or_create_custom_ruleset(zone_id)
        if not ruleset:
            return False
        result = self._api(
            "DELETE",
            f"/zones/{zone_id}/rulesets/{ruleset['id']}/rules/{rule_id}",
        )
        return result.get("success", False)

    def lockdown_zone(self, zone_id: str, whitelist_ips: list[str] | None = None) -> dict:
        """Emergency lockdown — block all traffic except whitelisted IPs.

        Used by budget enforcement to stop serving when costs are exceeded.
        """
        if whitelist_ips:
            ip_expr = " or ".join(f'ip.src eq {ip}' for ip in whitelist_ips)
            expression = f"(not ({ip_expr}))"
        else:
            expression = "(true)"  # Block everything

        return self.create_firewall_rule(
            zone_id, expression, action="block",
            description="Nimbus emergency budget lockdown",
        )

    def _get_or_create_custom_ruleset(self, zone_id: str) -> dict | None:
        """Get the custom phase ruleset, or return None if unavailable."""
        self._check_auth()
        result = self._api("GET", f"/zones/{zone_id}/rulesets")
        if not result.get("success"):
            return None
        rulesets = result.get("result", [])
        for rs in rulesets:
            if rs.get("phase") == "http_request_firewall_custom":
                full = self._api("GET", f"/zones/{zone_id}/rulesets/{rs['id']}")
                return full.get("result", rs)
        return None

    def _check_auth(self) -> None:
        """Ensure authenticated before API calls."""
        if not self._token:
            raise RuntimeError("Not authenticated — call authenticate() first")
