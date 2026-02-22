# Deployment Guide

## Docker Compose (Recommended)

### Prerequisites

- Docker 24+ with Compose V2
- Git

### Deploy

```bash
git clone https://github.com/czhaoca/nimbus.git
cd nimbus

# Create local directories
mkdir -p local/data local/config local/backups

# Copy and edit config templates
cp templates/provider-oci.template local/config/oci.ini
# Edit local/config/oci.ini with your credentials

# Build and start
docker compose up -d

# Check status
docker compose ps
curl http://localhost:8000/health
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| engine | 8000 | FastAPI backend + REST API |
| ui | 3000 | Nginx + React dashboard |

### Volumes

- `local/data/` → `/app/data` (SQLite database)
- `local/config/` → `/app/config` (Provider credentials)
- `deploy/nginx/default.conf` → Nginx config (read-only)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NIMBUS_DATABASE_URL` | `sqlite:///data/nimbus.db` | Database URL (SQLite or PostgreSQL) |
| `NIMBUS_ENVIRONMENT` | `production` | Environment name |

### PostgreSQL (Optional)

For production, use PostgreSQL instead of SQLite:

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: nimbus
      POSTGRES_USER: nimbus
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

  engine:
    environment:
      NIMBUS_DATABASE_URL: postgresql://nimbus:${POSTGRES_PASSWORD}@db:5432/nimbus
    depends_on:
      db:
        condition: service_healthy
```

Run migrations:
```bash
docker compose exec engine alembic upgrade head
```

## Proxmox Deployment

Deploy Nimbus to a Proxmox VM automatically:

```bash
./deploy/proxmox/deploy-nimbus.sh --host <VM_IP> --user root --key ~/.ssh/id_rsa
```

This script:
1. Installs Docker if not present
2. Clones/updates the Nimbus repo
3. Sets up local directories
4. Builds and starts containers

## Backup Strategy

### Automatic Backups

```bash
# Create backup (keeps last 10)
nimbus backup create

# Or via API
curl -X POST http://localhost:8000/api/backup
```

### Scheduled Backups (cron)

```bash
# Add to crontab
0 */6 * * * cd /opt/nimbus && docker compose exec engine nimbus backup create
```

## High Availability

### Failover Configuration

1. Deploy Nimbus on 2+ VMs
2. Configure DNS failover via the orchestration API:

```bash
curl -X POST http://localhost:8000/api/orchestrate/dns-failover \
  -H "Content-Type: application/json" \
  -d '{"resource_id": "...", "dns_provider_id": "cf", "zone_id": "...", "record_id": "...", "new_ip": "1.2.3.4", "record_name": "app.example.com"}'
```

### Health Monitoring

```bash
# Check provider health and latency
curl http://localhost:8000/api/providers/health/check
```
