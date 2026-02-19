# OCI VM Reprovisioning Script — Usage Guide

## Overview

`reprovision-vm.sh` is an interactive bash script that reprovisiones an existing OCI compute instance with a fresh Ubuntu image. It swaps the boot volume without deleting the instance, preserving your VNIC, IP address, and instance shape.

## What It Does (Workflow)

1. **Lists your instances** and lets you choose which one to reprovision
2. **Detects architecture** (x86 or ARM) from the instance shape
3. **Queries the latest Ubuntu images** for your architecture
4. **Lets you choose** an SSH key and optionally a cloud-init script
5. **Stops the instance** (if running)
6. **Snapshots the current boot volume** (rollback safety net)
7. **Detaches the current boot volume**
8. **Creates a new boot volume** from the selected Ubuntu image
9. **Attaches the new boot volume** and starts the instance
10. **Verifies SSH connectivity**

## Prerequisites

- OCI CLI installed and configured (`oci --version`)
- `jq` installed (`jq --version`)
- OCI config at `oci/local/config/oci-config` (see [setup-api-key.md](setup-api-key.md))
- SSH key(s) in `oci/local/ssh/`

## Quick Start

```bash
# Interactive mode (recommended for first use)
./oci/scripts/reprovision-vm.sh

# With flags
./oci/scripts/reprovision-vm.sh \
  --instance-id ocid1.instance.oc1... \
  --image-id ocid1.image.oc1... \
  --ssh-key oci/local/ssh/my_key.pub \
  --cloud-init oci/templates/cloud-init/cloudpanel-ubuntu.yaml

# Dry run (see what would happen without executing)
./oci/scripts/reprovision-vm.sh --dry-run
```

## CLI Flags

| Flag | Description |
|------|------------|
| `--config <path>` | Path to OCI config file (default: `oci/local/config/oci-config`) |
| `--instance-config <path>` | Path to instance config file (default: `oci/local/config/instance-config`) |
| `--instance-id <ocid>` | OCI instance OCID (skip instance selection) |
| `--image-id <ocid>` | Ubuntu image OCID (skip image selection) |
| `--ssh-key <path>` | Path to SSH public key file |
| `--cloud-init <path>` | Path to cloud-init YAML file |
| `--arch <x86\|arm>` | Force architecture (auto-detected from shape by default) |
| `--dry-run` | Show what would happen without executing |
| `--non-interactive` | Skip all prompts (requires all flags to be set) |
| `--help` | Show help message |

## Interactive Mode

When run without flags, the script guides you through each step with detailed explanations:

1. **OCI Config Check** — verifies your API config exists and tests connectivity
2. **Instance Selection** — lists all instances with their state, shape, and IP; you choose by number
3. **Architecture Detection** — auto-detects x86 vs ARM from the instance shape
4. **Image Selection** — lists recent Ubuntu images sorted by date; you choose or accept the latest
5. **SSH Key Selection** — lists keys in `oci/local/ssh/`; offers to generate one if none found
6. **Cloud-Init Selection** — optionally choose a cloud-init template for the new OS
7. **New User Setup** — optionally configure a new admin user (username/password stored in local config)
8. **Confirmation** — shows a summary of all actions; you confirm before proceeding
9. **Execution** — runs the workflow with progress indicators and logging
10. **Verification** — waits for the instance to be reachable via SSH

## Cloud-Init Templates

| Template | Description |
|----------|------------|
| `basic-ubuntu.yaml` | Minimal Ubuntu hardening: disable root, SSH key only, updates |
| `cloudpanel-ubuntu.yaml` | Install CloudPanel + hardened Ubuntu setup |

### Custom User Setup

The script can configure a new admin user on the fresh OS:
- Disable the default `ubuntu` user login
- Create a new user with sudo privileges
- Set SSH key-only authentication (password login disabled)
- Optionally set a password for sudo operations

User config is stored in `oci/local/config/instance-config` (gitignored).

## Rollback

The old boot volume is **NOT deleted** after reprovisioning. To rollback:

1. Stop the instance
2. Detach the current (new) boot volume
3. Re-attach the old boot volume (OCID logged during the operation)
4. Start the instance

The script logs all operations to `oci/local/logs/` with timestamps and resource OCIDs.

## Logging

All operations are logged to:
```
oci/local/logs/reprovision-YYYY-MM-DD-HHMMSS.log
```

Logs include: instance details, image selection, boot volume OCIDs, timing, and any errors.
