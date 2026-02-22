# API Reference

Base URL: `http://localhost:8000`

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check with DB connectivity status |

## Providers (`/api/providers`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/providers` | List all registered providers |
| POST | `/api/providers` | Register a new provider |
| GET | `/api/providers/{id}` | Get provider details |
| PUT | `/api/providers/{id}` | Update provider config |
| DELETE | `/api/providers/{id}` | Remove a provider |
| GET | `/api/providers/health/check` | Check provider health and latency |

### Create Provider

```json
POST /api/providers
{
  "id": "my-oci",
  "provider_type": "oci",
  "display_name": "My OCI Account",
  "region": "us-ashburn-1",
  "credentials_path": "local/config/oci.ini"
}
```

Supported provider types: `oci`, `cloudflare`, `proxmox`, `azure`, `gcp`, `aws`

## Resources (`/api/resources`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/resources` | List resources (optional: `?provider_id=`, `?resource_type=`, `?status=`) |
| POST | `/api/resources` | Create/track a resource |
| GET | `/api/resources/{id}` | Get resource details |
| PUT | `/api/resources/{id}` | Update resource |
| DELETE | `/api/resources/{id}` | Remove resource |
| POST | `/api/resources/{id}/action` | Perform action: `stop`, `start`, `terminate`, `health_check` |
| GET | `/api/resources/{id}/logs` | Get action history |
| POST | `/api/resources/sync/{provider_id}` | Sync resources from cloud provider |

## Budget (`/api/budget`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/budget/rules` | List budget rules |
| POST | `/api/budget/rules` | Create budget rule |
| GET | `/api/budget/rules/{id}` | Get rule details |
| PUT | `/api/budget/rules/{id}` | Update rule |
| DELETE | `/api/budget/rules/{id}` | Delete rule |
| GET | `/api/budget/status` | Check all budget statuses |
| POST | `/api/budget/enforce` | Run budget enforcement |
| GET | `/api/budget/spending` | List spending records |
| POST | `/api/budget/spending` | Record spending |
| POST | `/api/budget/sync-spending` | Trigger spending sync from all providers |

## Orchestration (`/api/orchestrate`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/orchestrate/vm-dns` | Provision VM + create DNS record |
| POST | `/api/orchestrate/lockdown` | Emergency budget lockdown |
| POST | `/api/orchestrate/dns-failover` | Update DNS for failover |

## Settings (`/api/settings`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | List all settings with defaults |
| GET | `/api/settings/{key}` | Get a specific setting |
| PUT | `/api/settings/{key}` | Update a setting |

Default settings: `spending_sync_interval` (300s), `budget_enforce_interval` (600s), `health_check_interval` (120s)

## Alerts (`/api/alerts`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/alerts/test` | Send a test alert |
| GET | `/api/alerts/config-status` | Check alert configuration |

## Backup (`/api/backup`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/backup` | Create database backup |
| GET | `/api/backup` | List existing backups |

## WebSocket (`/ws`)

Connect to `ws://localhost:8000/ws` for real-time resource updates.

Events:
```json
{"type": "resource_change", "action": "terminate", "resource_id": "...", "provider_id": "..."}
```

Send `ping` to receive `{"type": "pong"}`.
