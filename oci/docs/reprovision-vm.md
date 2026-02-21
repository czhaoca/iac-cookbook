# OCI VM Reprovisioning — Usage Guide

## Overview

Reprovision an existing OCI compute instance with a fresh Ubuntu image by replacing the boot volume atomically via the OCI API. The instance is NOT deleted — VNIC, IP address, and shape are preserved.

Two entry points are available:

| Entry Point | Language | Dependencies |
|-------------|----------|-------------|
| `oci-iac reprovision` | Python (OCI SDK) | Python 3.9+, `oci`, `click`, `rich` |
| `./oci/scripts/reprovision-vm.sh` | Bash (OCI CLI) | `oci` CLI, `jq`, `openssl` |

Both provide the same interactive workflow and support the same flags.

## Architecture

### Python CLI (`oci/oci_iac/`)

Uses OCI Python SDK directly — native API waiters, typed error handling, Rich terminal UI.

| Module | Purpose |
|--------|---------|
| `cli.py` | Click CLI entry point with all flags |
| `common.py` | Rich console, logging, prompts, JSON transaction log |
| `config.py` | Dataclass config loader from instance-config files |
| `auth.py` | OCI SDK client factory, multi-profile management |
| `compute.py` | Instance/image selection, state management via SDK |
| `storage.py` | Quota checks, boot volume replacement via SDK |
| `networking.py` | VNIC/IP lookup, SSH verification |
| `cloud_init.py` | SSH key, user config, template processing |

### Bash Script (`oci/lib/` + `oci/scripts/`)

Uses `oci` CLI subprocess calls. No Python required.

| Module | Purpose |
|--------|---------|
| `lib/common.sh` | Colors, logging, prompts, JSON transaction log |
| `lib/auth.sh` | OCI multi-profile management, login, API connectivity |
| `lib/compute.sh` | Instance/image selection, state management |
| `lib/storage.sh` | Quota checks, boot volume replacement |
| `lib/networking.sh` | VNIC/IP lookup, SSH verification |
| `lib/cloud-init.sh` | SSH key, user config, cloud-init template processing |

## What It Does (Workflow)

1. **OCI profile selection** — scans `~/.oci/config`, lets you choose or add a profile
2. **Lists your instances** and lets you choose which one to reprovision
3. **Detects architecture** (x86 or ARM) from the instance shape
4. **Queries the latest Ubuntu images** for your architecture
5. **SSH key selection** — lists keys in `oci/local/ssh/` and `~/.ssh/`, offers generation
6. **User config** — new admin user, password, optional CloudPanel installation
7. **Cloud-init template** — selects and prepares template with variable substitution
8. **Free tier quota check** — verifies storage quota, offers strategies if exceeded
9. **Stops the instance** (if running)
10. **Replaces boot volume atomically** (single OCI API call with image OCID)
11. **Starts the instance** with new OS and cloud-init
12. **Verifies SSH connectivity**

## Prerequisites

### Python CLI (recommended)
```bash
cd oci
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Bash Script
- OCI CLI installed and configured (`oci --version`)
- `jq` installed (`jq --version`)
- `openssl` installed

### Both
- OCI config at `~/.oci/config` with at least one profile
- SSH key(s) — the script can generate one if none exist

## Quick Start

### Python CLI

```bash
# Interactive mode (recommended for first use)
oci-iac reprovision

# With a specific OCI profile
oci-iac reprovision --profile PROD

# Dry run
oci-iac reprovision --dry-run

# See all options
oci-iac reprovision --help

# Fully parameterised
oci-iac reprovision \
  --profile PROD \
  --instance-id ocid1.instance.oc1... \
  --image-id ocid1.image.oc1... \
  --ssh-key oci/local/ssh/my_key.pub \
  --cloud-init oci/templates/cloud-init/cloudpanel-ubuntu.yaml
```

### Bash Script

```bash
./oci/scripts/reprovision-vm.sh
./oci/scripts/reprovision-vm.sh --profile PROD --dry-run
./oci/scripts/reprovision-vm.sh --help
```

## CLI Flags

| Flag | Description |
|------|------------|
| `--profile <name>` | OCI config profile name (default: DEFAULT) |
| `--instance-config <path>` | Path to instance config file (default: `oci/local/config/instance-config`) |
| `--instance-id <ocid>` | OCI instance OCID (skip instance selection) |
| `--image-id <ocid>` | Ubuntu image OCID (skip image selection) |
| `--ssh-key <path>` | Path to SSH public key file |
| `--cloud-init <path>` | Path to cloud-init YAML file |
| `--arch <x86\|arm>` | Force architecture (auto-detected from shape by default) |
| `--skip-backup` | Skip boot volume backup (saves storage quota) |
| `--dry-run` | Show what would happen without executing |
| `--non-interactive` | Skip all prompts (requires all flags to be set) |
| `--help` | Show help message |

## Interactive Mode

When run without flags, the script guides you through each step with detailed explanations:

1. **OCI Profile Selection** — lists profiles from `~/.oci/config` with region and tenancy info; choose one or add a new profile via browser login, interactive CLI, or existing credentials
2. **Compartment Selection** — lists compartments in your tenancy; choose where your instances live
3. **Instance Selection** — lists all instances with state, shape, and IP; you choose by number
4. **Architecture Detection** — auto-detects x86 vs ARM from the instance shape
5. **Image Selection** — lists recent Ubuntu images sorted by date; you choose or accept the latest
6. **SSH Key Selection** — lists keys in `oci/local/ssh/` and `~/.ssh/`; offers to generate one if none found; copies to project-local gitignored directory
7. **User Setup** — configure new admin user (disables default ubuntu user, SSH key-only auth)
8. **CloudPanel** — optionally install CloudPanel with database engine selection
9. **Cloud-Init Selection** — choose a template; auto-selects CloudPanel template if enabled
10. **Quota Check** — checks free tier storage (200 GB total); offers strategies if exceeded (don't preserve old BV, delete backups)
11. **Confirmation** — shows full summary; you confirm before proceeding
12. **Execution** — atomic boot volume replacement with progress indicators
13. **SSH Verification** — waits for instance to be reachable

## Cloud-Init Templates

| Template | Description |
|----------|------------|
| `basic-ubuntu.yaml` | Minimal Ubuntu hardening: disable root, SSH key only, updates |
| `cloudpanel-ubuntu.yaml` | Install CloudPanel + hardened Ubuntu setup |

### Custom User Setup

The script configures a new admin user on the fresh OS:
- Disable the default `ubuntu` user login
- Create a new user with sudo privileges
- Set SSH key-only authentication (password login disabled)
- Set a password for sudo operations (hashed before transmission)

User config is stored in `oci/local/config/instance-config` (gitignored).

## Quota Safeguards

OCI Free Tier has a combined 200 GB limit for boot volumes + block volumes + backups. The script:
- Checks current storage usage before proceeding
- Displays a quota dashboard (used, available, needed)
- If insufficient: offers strategies — don't preserve old BV, delete backups, or abort
- With `--skip-backup`: skips backup entirely to save quota

## Rollback

By default, the old boot volume is preserved after reprovisioning. To rollback:

1. Go to OCI Console → Compute → Instance Details
2. Click "Replace boot volume"
3. Select the preserved old boot volume (OCID logged during operation)

If `DELETE_OLD_BV` was chosen (quota strategy), no rollback is available.

## Recovery from Failed Runs

If a previous run failed mid-operation (e.g., instance STOPPED with detached BV), the script detects this state and offers:
- Re-attach old BV and continue with replacement
- Re-attach old BV and abort (restore previous state)

## Logging

All operations are logged to:
```
oci/local/logs/reprovision-YYYY-MM-DD-HHMMSS.log    # Text log
oci/local/logs/reprovision-YYYY-MM-DD-HHMMSS.json   # JSON transaction log
```

The JSON log includes: session metadata, step-by-step status, timing, resource OCIDs, and final result.
