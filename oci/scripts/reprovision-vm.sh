#!/usr/bin/env bash
# ============================================================================
# OCI VM Reprovisioning Script — Interactive Boot Volume Swap
# ============================================================================
# Reprovisions an existing OCI compute instance with a fresh Ubuntu image
# by swapping the boot volume. The instance is NOT deleted — preserving
# VNIC, IP address, and shape.
#
# Architecture: Thin orchestrator that sources modular libraries from lib/
#   lib/common.sh     — Colors, logging, prompts, JSON transaction log
#   lib/auth.sh       — OCI profile management, login, connectivity
#   lib/compute.sh    — Instance operations, image selection, state mgmt
#   lib/storage.sh    — Boot/block volume, quota management
#   lib/networking.sh — VNIC, IP, SSH connectivity
#   lib/cloud-init.sh — SSH key, user config, template processing
#
# Usage:
#   ./reprovision-vm.sh                          # Interactive mode
#   ./reprovision-vm.sh --dry-run                # Preview only
#   ./reprovision-vm.sh --instance-id <ocid> ... # Parameterized mode
#   ./reprovision-vm.sh --help                   # Show help
#
# Dependencies: oci CLI, jq, openssl, ssh
# ============================================================================

set -euo pipefail

# --- Error trap: show context on unexpected exit ---
trap_handler() {
    local exit_code=$?
    local line_no=${1:-unknown}
    if [[ $exit_code -ne 0 ]]; then
        echo "" >&2
        echo -e "\033[1;31m  ✖ Script failed at line $line_no (exit code: $exit_code)\033[0m" >&2
        echo -e "\033[1;31m    Check the log file for details.\033[0m" >&2
        if [[ -n "${LOG_FILE:-}" && -f "${LOG_FILE:-}" ]]; then
            echo -e "\033[1;31m    Log: $LOG_FILE\033[0m" >&2
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] FATAL: Script failed at line $line_no (exit code: $exit_code)" >> "$LOG_FILE"
        fi
        echo "" >&2
        echo -e "\033[33m  If this was a quota error, re-run the script — it can recover and resume.\033[0m" >&2
    fi
}
trap 'trap_handler $LINENO' ERR

# --- Paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"

# --- Source modular libraries ---
source "$LIB_DIR/common.sh"
source "$LIB_DIR/auth.sh"
source "$LIB_DIR/compute.sh"
source "$LIB_DIR/storage.sh"
source "$LIB_DIR/networking.sh"
source "$LIB_DIR/cloud-init.sh"

# --- Script-specific defaults ---
DEFAULT_INSTANCE_CONFIG="$REPO_ROOT/oci/local/config/instance-config"
DEFAULT_SSH_DIR="$REPO_ROOT/oci/local/ssh"
INSTANCE_CONFIG_FILE=""
INSTANCE_OCID="${INSTANCE_OCID:-}"
IMAGE_OCID="${IMAGE_OCID:-}"

# ============================================================================
# Help
# ============================================================================

show_help() {
    cat <<'EOF'
OCI VM Reprovisioning Script — Interactive Boot Volume Swap

USAGE:
    reprovision-vm.sh [OPTIONS]

OPTIONS:
    --profile <name>          OCI config profile (default: DEFAULT)
    --instance-config <path>  Instance config file (default: oci/local/config/instance-config)
    --instance-id <ocid>      Instance OCID (skip selection)
    --image-id <ocid>         Ubuntu image OCID (skip selection)
    --ssh-key <path>          SSH public key file path
    --cloud-init <path>       Cloud-init YAML file path
    --arch <x86|arm>          Force architecture (auto-detected if not set)
    --skip-backup             Skip boot volume backup (saves storage quota)
    --dry-run                 Preview operations without executing
    --non-interactive         Skip prompts (requires all IDs via flags/config)
    --help                    Show this help message

INTERACTIVE MODE (default):
    Run without flags for a guided, step-by-step experience.
    The script explains each step and lets you make choices.

PROFILES:
    OCI CLI supports multiple profiles in ~/.oci/config:
      [DEFAULT]     — default profile
      [PROD]        — named profile for production
      [DEV]         — named profile for development

    The script scans ~/.oci/config on startup and lets you choose
    a profile or add a new one interactively.

EXAMPLES:
    # Interactive (recommended for first use)
    ./reprovision-vm.sh

    # Use specific profile
    ./reprovision-vm.sh --profile PROD

    # Dry run
    ./reprovision-vm.sh --dry-run

    # Fully parameterized
    ./reprovision-vm.sh \
      --profile PROD \
      --instance-id ocid1.instance.oc1... \
      --image-id ocid1.image.oc1... \
      --ssh-key oci/local/ssh/my_key.pub \
      --cloud-init oci/templates/cloud-init/cloudpanel-ubuntu.yaml

PREREQUISITES:
    - OCI CLI installed:  oci --version
    - jq installed:       jq --version
    - OCI config:         ~/.oci/config
      (see: oci/docs/setup-api-key.md)

FILES:
    ~/.oci/config                        OCI API profiles (multi-profile)
    ~/.oci/keys/<profile>/               API keys per profile
    oci/local/config/instance-config     Instance & user configuration
    oci/local/ssh/                       SSH keys
    oci/local/logs/                      Operation logs
    oci/templates/                       Config & cloud-init templates
EOF
}

# ============================================================================
# Parse CLI Arguments
# ============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile) OCI_PROFILE="$2"; shift 2 ;;
            --instance-config) INSTANCE_CONFIG_FILE="$2"; shift 2 ;;
            --instance-id) INSTANCE_OCID="$2"; shift 2 ;;
            --image-id) IMAGE_OCID="$2"; shift 2 ;;
            --ssh-key) SSH_PUBLIC_KEY_PATH="$2"; shift 2 ;;
            --cloud-init) CLOUD_INIT_PATH="$2"; shift 2 ;;
            --arch) ARCH="$2"; shift 2 ;;
            --skip-backup) SKIP_BACKUP=true; shift ;;
            --dry-run) DRY_RUN=true; shift ;;
            --non-interactive) NON_INTERACTIVE=true; shift ;;
            --help) show_help; exit 0 ;;
            *) echo "Unknown option: $1. Use --help for usage." >&2; exit 1 ;;
        esac
    done
}

# ============================================================================
# Initialization
# ============================================================================

init() {
    print_header "OCI VM Reprovisioning Script"

    if $DRY_RUN; then
        print_warning "DRY-RUN MODE — no changes will be made"
        echo ""
    fi

    # Set defaults
    [[ -z "$INSTANCE_CONFIG_FILE" ]] && INSTANCE_CONFIG_FILE="$DEFAULT_INSTANCE_CONFIG"

    # Initialize logging (from common.sh)
    init_logging "reprovision"
    json_log_init "reprovision-vm"

    # Check dependencies
    check_dependencies oci jq openssl ssh

    # Load instance config if it exists
    if [[ -f "$INSTANCE_CONFIG_FILE" ]]; then
        print_success "Loading instance config from: $INSTANCE_CONFIG_FILE"
        while IFS='=' read -r key value; do
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)
            [[ -z "$key" || "$key" == \#* ]] && continue
            case "$key" in
                OCI_PROFILE)          [[ "$OCI_PROFILE" == "DEFAULT" ]] && OCI_PROFILE="$value" ;;
                COMPARTMENT_OCID)     [[ -z "$COMPARTMENT_OCID" ]] && COMPARTMENT_OCID="$value" ;;
                INSTANCE_OCID)        [[ -z "$INSTANCE_OCID" ]] && INSTANCE_OCID="$value" ;;
                SSH_PUBLIC_KEY_PATH)   [[ -z "$SSH_PUBLIC_KEY_PATH" ]] && SSH_PUBLIC_KEY_PATH="$value" ;;
                SSH_PRIVATE_KEY_PATH)  [[ -z "$SSH_PRIVATE_KEY_PATH" ]] && SSH_PRIVATE_KEY_PATH="$value" ;;
                NEW_USERNAME)          [[ -z "$NEW_USERNAME" ]] && NEW_USERNAME="$value" ;;
                NEW_PASSWORD)          [[ -z "$NEW_PASSWORD" ]] && NEW_PASSWORD="$value" ;;
                INSTALL_CLOUDPANEL)    INSTALL_CLOUDPANEL="$value" ;;
                CLOUDPANEL_ADMIN_EMAIL) CLOUDPANEL_ADMIN_EMAIL="$value" ;;
                CLOUDPANEL_DB_ENGINE) CLOUDPANEL_DB_ENGINE="$value" ;;
                CLOUD_INIT_PATH)      [[ -z "$CLOUD_INIT_PATH" ]] && CLOUD_INIT_PATH="$value" ;;
                ARCH)                 [[ -z "$ARCH" ]] && ARCH="$value" ;;
                AVAILABILITY_DOMAIN)  [[ -z "$AVAILABILITY_DOMAIN" ]] && AVAILABILITY_DOMAIN="$value" ;;
                BOOT_VOLUME_SIZE_GB)  [[ -z "$BOOT_VOLUME_SIZE_GB" ]] && BOOT_VOLUME_SIZE_GB="$value" ;;
            esac
        done < "$INSTANCE_CONFIG_FILE"
    else
        print_info "No instance config found at: $INSTANCE_CONFIG_FILE"
        print_info "Using interactive prompts for all values."
        print_info "Tip: Copy the template to create your config file:"
        print_detail "cp oci/templates/instance-config.template oci/local/config/instance-config"
    fi
}

# ============================================================================
# Step 7: Confirmation & Summary
# ============================================================================

step_confirm() {
    print_header "Review & Confirm"

    echo -e "${BOLD}  The following operations will be performed:${NC}"
    echo ""
    print_detail "┌─────────────────────────────────────────────────────────┐"
    print_detail "│ Instance:     $INSTANCE_OCID"
    print_detail "│ Architecture: $ARCH"
    print_detail "│ New Image:    $IMAGE_OCID"
    print_detail "│ SSH Key:      $SSH_PUBLIC_KEY_PATH"
    print_detail "│ Admin User:   $NEW_USERNAME"
    print_detail "│ CloudPanel:   $INSTALL_CLOUDPANEL"
    [[ -n "${CLOUD_INIT_PREPARED:-}" ]] && \
    print_detail "│ Cloud-Init:   $(basename "${CLOUD_INIT_PREPARED}")"
    print_detail "│ Boot Vol Size: ${BOOT_VOLUME_SIZE_GB} GB"
    print_detail "├─────────────────────────────────────────────────────────┤"
    print_detail "│ WORKFLOW:                                              │"
    print_detail "│ 1. Stop instance (if running)                         │"
    print_detail "│ 2. Replace boot volume via image (atomic OCI API)     │"
    print_detail "│ 3. Start instance with new OS + cloud-init            │"
    print_detail "│ 4. Verify SSH connectivity                            │"
    if $DELETE_OLD_BV; then
    print_detail "│ ⚠ Old boot volume will be DELETED (no rollback)       │"
    else
    print_detail "│ ✔ Old boot volume preserved for rollback              │"
    fi
    print_detail "└─────────────────────────────────────────────────────────┘"
    echo ""

    if $DRY_RUN; then
        print_warning "DRY-RUN: No changes will be made. Exiting."
        log_quiet "DRY-RUN complete. No changes made."
        exit 0
    fi

    if ! confirm "Proceed with reprovisioning? THIS WILL REPLACE THE OS"; then
        print_info "Aborted by user."
        log_quiet "Operation aborted by user"
        exit 0
    fi
}

# ============================================================================
# Step 8: Execute Reprovisioning
# ============================================================================

step_execute() {
    print_header "Executing Reprovisioning"
    log "Starting reprovisioning workflow..."

    # --- 8.0: Pre-flight quota check ---
    json_step "8.0-quota-check" "Pre-flight storage quota check"
    check_storage_quota
    json_step_update "done"

    # --- 8.0b: Detect recovery from previous failed run ---
    json_step "8.0b-state-check" "Checking instance and boot volume state"
    print_step "Checking instance state..."
    local instance_state
    instance_state=$(get_instance_state)

    local current_attach_state=""
    current_attach_state=$(oci_cmd compute boot-volume-attachment list \
        --compartment-id "$COMPARTMENT_OCID" \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | length')
    json_step_update "done" "instance_state=${instance_state}, bv_attached=${current_attach_state}"

    if [[ "$instance_state" == "STOPPED" && "$current_attach_state" == "0" ]]; then
        json_step "8.0c-recovery" "Recovery: re-attach boot volume"
        if ! recover_detached_boot_volume; then
            json_step_update "done" "Instance restored; user chose to abort replacement"
            json_finalize "aborted" "User chose to restore previous state instead of replacing"
            exit 0
        fi
        json_step_update "done"
    fi

    # --- 8.2: Prepare metadata ---
    json_step "8.2-metadata" "Preparing instance metadata (SSH key + cloud-init)"
    print_step "Preparing instance metadata..."
    local metadata_json
    metadata_json=$(build_instance_metadata)
    print_success "Metadata prepared (SSH key + cloud-init)"
    json_step_update "done"

    # --- 8.3: Stop instance if running ---
    if [[ "$instance_state" == "RUNNING" ]]; then
        json_step "8.3-stop" "Stopping instance for boot volume replacement"
        stop_instance
        json_step_update "done"
    else
        print_step "Instance already stopped — skipping"
    fi

    # --- 8.4: Replace boot volume via image (single API call) ---
    json_step "8.4-replace-bv" "Replace boot volume via OCI atomic API"
    replace_boot_volume "$metadata_json"
    json_step_update "done" "new_bv=${new_bv_id}"

    # --- 8.5: Start instance if not already running ---
    local new_state
    new_state=$(get_instance_state)
    if [[ "$new_state" != "RUNNING" ]]; then
        json_step "8.5-start" "Starting instance"
        start_instance
        json_step_update "done"
    else
        print_step "Instance already running"
    fi

    # --- 8.6: Verify SSH connectivity ---
    json_step "8.6-ssh-verify" "Verifying SSH connectivity"
    if verify_ssh_connectivity "$NEW_USERNAME" "$SSH_PRIVATE_KEY_PATH"; then
        json_step_update "done" "ssh_ok=${NEW_USERNAME}@${PUBLIC_IP}"
    else
        json_step_update "warning" "SSH not yet available"
    fi

    log "Reprovisioning complete"
}

# ============================================================================
# Step 9: Summary
# ============================================================================

step_summary() {
    print_header "Reprovisioning Complete!"

    echo -e "${GREEN}${BOLD}  Summary:${NC}"
    print_detail "Instance:          $INSTANCE_OCID"
    print_detail "New Image:         $IMAGE_OCID"
    print_detail "New Boot Volume:   ${new_bv_id:-N/A}"
    if $DELETE_OLD_BV; then
        print_detail "Old Boot Volume:   $CURRENT_BOOT_VOLUME_ID (not preserved)"
    else
        print_detail "Old Boot Volume:   $CURRENT_BOOT_VOLUME_ID (preserved)"
    fi
    print_detail "Admin User:        $NEW_USERNAME"
    print_detail "CloudPanel:        $INSTALL_CLOUDPANEL"
    print_detail "Log File:          $LOG_FILE"
    print_detail "JSON Log:          $JSON_LOG_FILE"
    echo ""

    if ! $DELETE_OLD_BV; then
        print_info "ROLLBACK: To revert, use the OCI Console 'Replace boot volume'"
        print_info "          and select the preserved old boot volume: $CURRENT_BOOT_VOLUME_ID"
        echo ""
    else
        print_warning "No rollback available — old boot volume was not preserved."
        echo ""
    fi

    if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
        echo -e "${CYAN}${BOLD}  CloudPanel Access:${NC}"
        print_detail "URL:  https://<instance-public-ip>:8443"
        print_detail "Note: CloudPanel may take 5-10 minutes to finish installing."
        print_detail "      Check: ssh ${NEW_USERNAME}@<ip> 'systemctl status clp'"
        echo ""
    fi

    print_info "SSH access: ssh -i ${SSH_PRIVATE_KEY_PATH} ${NEW_USERNAME}@<instance-public-ip>"
    echo ""
}

# ============================================================================
# Main — Orchestrate workflow using modular libraries
# ============================================================================

main() {
    parse_args "$@"
    init

    json_step "1-oci-auth"   "OCI Profile & API Configuration"
    verify_oci_config                    # auth.sh
    json_step_update "done"

    json_step "2-instance"   "Select Instance to Reprovision"
    select_instance                      # compute.sh
    fetch_instance_network_info          # networking.sh
    json_step_update "done"

    json_step "3-image"      "Select Ubuntu Image"
    select_image                         # compute.sh
    json_step_update "done"

    json_step "4-ssh-key"    "SSH Key Configuration"
    select_ssh_key                       # cloud-init.sh
    json_step_update "done"

    json_step "5-user-config" "OS User & Password Configuration"
    configure_user                       # cloud-init.sh
    save_instance_config "$INSTANCE_CONFIG_FILE"  # cloud-init.sh
    json_step_update "done"

    json_step "6-cloud-init" "Cloud-Init Configuration"
    select_cloud_init_template           # cloud-init.sh
    prepare_cloud_init                   # cloud-init.sh
    json_step_update "done"

    json_step "7-confirm"    "Final Confirmation"
    step_confirm
    json_step_update "done"

    json_step "8-execute"    "Execute Boot Volume Replacement"
    step_execute
    json_step_update "done"

    json_finalize "success" "Boot volume replacement completed"
    json_step "9-summary"    "Summary"
    step_summary
    json_step_update "done"

    print_detail "JSON log: $JSON_LOG_FILE"
}

main "$@"
