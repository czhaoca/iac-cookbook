# Getting Started

## Prerequisites

- Python 3.12+
- Node.js 22+ (for frontend)
- Docker & Docker Compose (for production)

## Quick Start (Development)

### 1. Clone the repository

```bash
git clone https://github.com/czhaoca/nimbus.git
cd nimbus
```

### 2. Set up the engine

```bash
cd engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Initialize the database

```bash
nimbus status  # Creates local/data/nimbus.db automatically
```

### 4. Start the engine

```bash
nimbus serve
# Engine running at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 5. Start the frontend (separate terminal)

```bash
cd ui
npm install
npm run dev
# Dashboard at http://localhost:5173
```

## Configuration

### Provider Setup

1. Copy the appropriate template from `templates/` to `local/config/`:

```bash
# OCI
cp templates/provider-oci.template local/config/oci.ini

# Cloudflare
cp templates/provider-cloudflare.template local/config/cloudflare-api-token

# Alerts
cp templates/alerts.template.json local/config/alerts.json
```

2. Edit the config file with your credentials.

3. Register the provider:

```bash
nimbus providers add my-oci oci "My OCI Account" \
  --region us-ashburn-1 \
  --credentials-path local/config/oci.ini
```

### Budget Rules

```bash
# Add a $10/month budget with alert at 80%
nimbus budget add --provider my-oci --limit 10.00 --threshold 0.8 --action alert
```

### Database Backup

```bash
nimbus backup create  # Creates timestamped backup in local/backups/
nimbus backup list    # Show existing backups
```

## Security

- **Never commit secrets** — all credentials go in `local/` (gitignored)
- Templates in `templates/` provide placeholder examples
- GitHub Actions runs CodeQL, dependency audits, and secret scanning on every push
- See [CLAUDE.md](../CLAUDE.md) for the full security checklist
