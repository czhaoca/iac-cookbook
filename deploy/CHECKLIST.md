# Deployment Checklist

## Pre-Deploy

- [ ] Docker 24+ and Docker Compose V2 installed
- [ ] Git installed on target machine
- [ ] SSH access to target VM configured
- [ ] Provider credentials copied to `local/config/`
- [ ] `local/data/`, `local/config/`, `local/backups/` directories created

## Deploy

```bash
# Option A: Local development
docker compose up -d
./deploy/wait-healthy.sh

# Option B: Remote Proxmox VM
./deploy/proxmox/deploy-nimbus.sh --host <VM_IP> --user root --key ~/.ssh/id_rsa
```

## Post-Deploy Verification

- [ ] Engine health: `curl http://<host>:8000/health`
- [ ] UI accessible: `http://<host>:3000`
- [ ] API docs: `http://<host>:8000/docs`
- [ ] Register a provider: `nimbus providers add --id test --type oci --name "Test"`
- [ ] Create backup: `nimbus backup create`

## Rollback

```bash
# Stop services
docker compose down

# Restore from backup
cp local/backups/<backup-file> local/data/nimbus.db

# Restart
docker compose up -d
```

## Monitoring

```bash
# View logs
docker compose logs -f

# Check resource usage
docker compose stats

# Health endpoint
watch -n 10 curl -s http://localhost:8000/health
```
