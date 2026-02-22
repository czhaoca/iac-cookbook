# Nimbus — Personal Multi-Cloud Orchestration Platform

A personal multi-cloud orchestration platform for provisioning, monitoring, and managing infrastructure across OCI, Azure, GCP, AWS, Cloudflare, and self-hosted Proxmox — with budget enforcement, cross-cloud workflows, and a dashboard UI.

## Architecture

```
nimbus/
├── engine/                 # Backend (FastAPI + CLI)
│   ├── nimbus/            # Python package
│   │   ├── api/           # FastAPI routes (health, resources, providers)
│   │   ├── cli/           # Click CLI (nimbus status, nimbus serve)
│   │   ├── providers/     # Cloud provider adapters
│   │   │   ├── base.py    # Abstract provider interface
│   │   │   └── oci/       # OCI adapter (SDK-based)
│   │   ├── models/        # SQLAlchemy models (resource, budget, etc.)
│   │   ├── services/      # Orchestrator, budget monitor, naming
│   │   ├── app.py         # FastAPI application factory
│   │   ├── config.py      # App settings (env vars, .env)
│   │   └── db.py          # Database engine, session factory
│   ├── tests/             # pytest
│   ├── pyproject.toml     # Python project config
│   └── Dockerfile
├── ui/                     # Frontend (React + Vite) — Phase 2
├── deploy/                 # Docker Compose, Proxmox scripts, Nginx
├── oci/                    # OCI-specific scripts & templates
│   ├── oci_iac/           # Python CLI (OCI SDK) — being migrated to engine/
│   ├── lib/               # Bash modules (legacy, functional)
│   ├── scripts/           # Bash orchestrator (reprovision-vm.sh)
│   └── templates/         # OCI config templates
├── docs/                   # Architecture decisions, comparisons
├── templates/              # Global config templates
├── docker-compose.yml      # Dev environment
└── local/                  # YOUR secrets & config (GITIGNORED)
```

## Features

### Engine (Backend)
- **FastAPI REST API** — resource CRUD, provider management, budget rules
- **CLI** — `nimbus status`, `nimbus serve`, provider-specific commands
- **Provider Adapters** — pluggable interface for OCI, Azure, Cloudflare, Proxmox
- **SQLAlchemy ORM** — SQLite (dev) or PostgreSQL (prod), Alembic migrations
- **Budget Enforcement** — spending alerts, auto-terminate ephemeral, firewall lockdown
- **Cross-Cloud Orchestration** — VM+DNS, budget lockdown, DR failover

### OCI Provider
- **VM Reprovisioning** — atomic boot volume replacement (no instance deletion)
- **Free Tier Quota Safeguards** — interactive recovery strategies
- **Multi-Profile Auth** — manage multiple OCI CLI profiles
- **Cloud-Init Templates** — Ubuntu hardening, CloudPanel, custom scripts

### Security
- All secrets in `local/` directories (gitignored, never committed)
- Pre-commit scanning for credentials, OCIDs, private IPs
- Config templates with placeholder values in `templates/`

## Quick Start

### Engine Setup

```bash
cd engine
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start API server
nimbus serve

# Check status
nimbus status
```

### Docker Setup

```bash
docker compose up --build
# Engine: http://localhost:8000
# Health: http://localhost:8000/health
```

### OCI VM Reprovisioning (Legacy CLI)

```bash
cd oci
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
oci-iac reprovision
```

## 🔒 Security & Local Configuration

This is a **public repository**. All secrets, credentials, API keys, and SSH keys are stored in **`local/` directories** which are gitignored and never committed.

### How It Works

```
<provider>/
├── scripts/       # Public scripts (committed) — NO secrets
├── templates/     # Config templates with placeholders (committed)
├── docs/          # Documentation (committed)
└── local/         # YOUR secrets & config (GITIGNORED — never committed)
    ├── api-keys/  # API signing keys
    ├── ssh/       # SSH keys for instances
    ├── config/    # Instance configs, credentials
    └── logs/      # Operation logs
```

### Getting Started (Local Setup)

1. **Copy templates to your local config**:
   ```bash
   mkdir -p oci/local/config oci/local/api-keys oci/local/ssh oci/local/logs
   cp oci/templates/oci-config.template oci/local/config/oci-config
   cp oci/templates/instance-config.template oci/local/config/instance-config
   ```

2. **Edit with your values**:
   ```bash
   nano oci/local/config/oci-config
   ```

3. **Or run the interactive script** — it will guide you through setup:
   ```bash
   ./oci/scripts/reprovision-vm.sh
   ```

### Forking This Repository

You are welcome to **fork** this repo. When you do:

> ⚠️ **WARNING**: This repo is sanitized to keep secrets out. If you fork it:
> - **Do NOT commit** any files in `local/` directories to your fork
> - If your fork is **public**, verify `.gitignore` is intact before pushing
> - If your fork is **private**, you still should not store secrets in git — use the `local/` directory convention
> - Run `git diff --cached | grep -iE 'password|token|secret|key_file|ocid1\.'` before every push

## OCI Provider

### VM Reprovisioning

Atomic boot volume replacement — no instance deletion, supports x86 and ARM.

- **Python CLI** (recommended): `cd oci && pip install -e . && oci-iac reprovision`
- **Bash** (legacy): `./oci/scripts/reprovision-vm.sh`
- **Docs**: [API Key Setup](oci/docs/setup-api-key.md) | [Usage Guide](oci/docs/reprovision-vm.md)

## Roadmap

- [x] OCI VM Reprovisioning (boot volume swap)
- [x] Modular Bash library + Python SDK migration
- [x] Block volume strategy & control panel docs
- [x] Nimbus engine scaffold (FastAPI + SQLAlchemy)
- [x] **Phase 1**: Provider adapter interface, OCI adapter, resource CRUD API
  - [x] Shared utility extraction + import refactor
  - [x] Provider registry + naming service
  - [x] OCI provider adapter (ProviderAdapter interface)
  - [x] Pydantic API schemas (decoupled from ORM)
  - [x] Provider & Resource CRUD API endpoints
  - [x] CLI enhancements (status, providers, resources)
  - [x] Alembic migrations
  - [x] 36 passing tests (API, services, OCI modules)
- [x] **Phase 2**: React + Vite frontend, dashboard, resource cards
  - [x] GitHub Actions CI + security scanning (CodeQL, Dependabot, npm/pip audit)
  - [x] Vite 7 + React 19 scaffold (0 CVEs)
  - [x] Dashboard with stats bar, provider badges, resource cards
  - [x] TypeScript API client + TanStack React Query hooks
  - [x] WebSocket real-time updates
  - [x] Provider add/edit forms
- [x] **Phase 3**: Budget monitoring, spending alerts, auto-enforcement
  - [x] Budget rules CRUD API + CLI
  - [x] Budget monitor service (check/enforce/record)
  - [x] BudgetOverview dashboard component
  - [x] Spending sync from provider APIs (background task)
  - [x] Webhook/email alert dispatch
- [x] **Phase 4**: Cloudflare + Proxmox adapters, cross-cloud workflows
- [x] **Phase 5**: Docker production config, HA/DR, database backup
- [x] **Phase 6**: Spending sync, alerts, provider forms, cloud stubs, Postgres path

## Contributing

1. Fork the repository
2. Create a feature branch
3. **Never commit secrets** — use the `local/` directory convention
4. Submit a pull request

> ⚠️ If your fork is public, verify `.gitignore` is intact before pushing.

## License

MIT License — see LICENSE file for details.

## Disclaimer

These scripts are provided as-is. Always review and test in a development environment first. Be aware of cloud provider pricing and free tier limitations.