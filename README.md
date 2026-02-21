# IaC Cookbook - Multi-Cloud Infrastructure as Code Scripts

A comprehensive collection of Infrastructure as Code (IaC) command scripts for multiple cloud providers including OCI, GCP, Azure, AWS, and Cloudflare.

## Overview

This repository provides ready-to-use IaC scripts and templates for provisioning cloud infrastructure across different cloud providers. Starting with Oracle Cloud Infrastructure (OCI) Free Tier resources, the project aims to simplify cloud resource deployment through reusable, modular scripts.

## Project Structure

```
iac-cookbook/
├── oci/                    # Oracle Cloud Infrastructure
│   ├── lib/               # Reusable Bash modules (sourced by scripts)
│   │   ├── common.sh      # Colors, logging, prompts, JSON transaction log
│   │   ├── auth.sh        # OCI profile management, login, connectivity
│   │   ├── compute.sh     # Instance operations, image selection, state mgmt
│   │   ├── storage.sh     # Boot/block volume, quota management
│   │   ├── networking.sh  # VNIC, IP lookup, SSH verification
│   │   └── cloud-init.sh  # SSH key, user config, template processing
│   ├── scripts/           # Orchestrator scripts (source lib/*)
│   │   └── reprovision-vm.sh
│   ├── templates/         # Config & cloud-init templates (committed)
│   └── local/             # YOUR secrets & config (GITIGNORED)
├── docs/                   # Architecture decisions & comparisons
│   ├── oci/architecture/  # OCI architecture decision records
│   └── control-panels/    # Control panel comparison
├── gcp/                   # Google Cloud Platform scripts (coming soon)
├── azure/                 # Microsoft Azure scripts (coming soon)
├── aws/                   # Amazon Web Services scripts (coming soon)
├── cloudflare/            # Cloudflare services and edge computing
└── common/                # Shared resources across clouds
```

## Features

### OCI Free Tier Resources
- **Compute**: Provision Always Free compute instances (AMD/ARM)
- **Networking**: Setup VCNs, subnets, and security configurations
- **Storage**: Manage block volumes and object storage buckets
- **Database**: Deploy Autonomous Database instances

### Cloudflare Resources
- **DNS**: Manage DNS records and zones
- **Workers**: Deploy serverless functions at the edge
- **Pages**: Static site deployments with CI/CD
- **R2**: S3-compatible object storage
- **D1**: Serverless SQL database
- **KV**: Key-value storage at the edge
- **WAF**: Web Application Firewall rules
- **CDN**: Content delivery and caching

### Prerequisites

#### For OCI:
- OCI CLI installed and configured
- Valid OCI account with Free Tier resources available
- Terraform (optional, for Terraform-based scripts)

#### For Cloudflare:
- Cloudflare account (free tier available)
- Cloudflare API token with appropriate permissions
- Wrangler CLI for Workers deployment (optional)

## Quick Start

### OCI Free Tier Setup

1. **Configure OCI CLI**:
   ```bash
   oci setup config
   ```

2. **Set environment variables**:
   ```bash
   export OCI_TENANCY_OCID="your-tenancy-ocid"
   export OCI_USER_OCID="your-user-ocid"
   export OCI_REGION="your-region"
   ```

3. **Run scripts**:
   ```bash
   cd oci/free-tier/compute
   ./create-free-instance.sh
   ```

## Script Categories

### Infrastructure Provisioning
- Create and manage compute instances
- Network infrastructure setup
- Storage provisioning
- Database deployment

### Configuration Management
- Security configurations
- Resource tagging
- Cost optimization settings

### Maintenance & Operations
- Backup scripts
- Monitoring setup
- Resource cleanup utilities

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

## OCI Scripts

### VM Reprovisioning (`oci/scripts/reprovision-vm.sh`)

Interactive script to reprovision an OCI compute instance with a fresh Ubuntu image by swapping the boot volume — without deleting the instance.

**Architecture**: Thin orchestrator that sources modular libraries from `oci/lib/`:

| Module | Purpose |
|--------|---------|
| `common.sh` | Colors, logging, prompts, JSON transaction log |
| `auth.sh` | OCI multi-profile management, login, connectivity |
| `compute.sh` | Instance/image selection, state management |
| `storage.sh` | Quota checks, boot volume replacement |
| `networking.sh` | VNIC/IP lookup, SSH verification |
| `cloud-init.sh` | SSH key, user config, template processing |

**Features**:
- Interactive or parameterized (CLI flags)
- Auto-detects x86 vs ARM architecture
- Latest Ubuntu image selection
- SSH key management (generate, select, copy)
- Cloud-init templates (basic Ubuntu hardening, CloudPanel)
- Free tier quota safeguards with recovery strategies
- Atomic boot volume replacement (OCI API, no instance deletion)
- New admin user setup (disables default ubuntu user)
- Recovery from failed previous runs
- Dry-run mode, JSON transaction logging

```bash
# Interactive (recommended for first use)
./oci/scripts/reprovision-vm.sh

# Dry run
./oci/scripts/reprovision-vm.sh --dry-run

# See all options
./oci/scripts/reprovision-vm.sh --help
```

**Documentation**:
- [OCI API Key Setup Guide](oci/docs/setup-api-key.md)
- [Reprovisioning Script Usage Guide](oci/docs/reprovision-vm.md)

## Contributing

Contributions are welcome! Please follow these guidelines:
1. Fork the repository
2. Create a feature branch
3. Add your scripts with proper documentation
4. **Never commit secrets** — use the `local/` directory convention
5. Submit a pull request

## Roadmap

- [x] OCI Free Tier scripts
- [x] OCI VM Reprovisioning (boot volume swap)
- [x] Modular Bash library architecture (`oci/lib/`)
- [x] Block volume strategy & control panel comparison docs
- [ ] Block volume provisioning script (`manage-volumes.sh`)
- [ ] New VM provisioning script (`provision-vm.sh`)
- [ ] Cloudflare services scripts
- [ ] Phase 2: Python CLI with OCI SDK (when 5+ scripts needed)
- [ ] Cross-cloud migration scripts
- [ ] Cost optimization utilities

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or contributions:
- Open an issue in the GitHub repository
- Check existing documentation in `/common/docs`
- Review examples in each cloud provider's directory

## Disclaimer

These scripts are provided as-is. Always review and test scripts in a development environment before using in production. Be aware of cloud provider pricing and free tier limitations.