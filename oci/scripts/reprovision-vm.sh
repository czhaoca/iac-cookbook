#!/usr/bin/env bash
# ============================================================================
# OCI VM Reprovisioning Script — Interactive Boot Volume Swap
# ============================================================================
# Reprovisions an existing OCI compute instance with a fresh Ubuntu image
# by swapping the boot volume. The instance is NOT deleted — preserving
# VNIC, IP address, and shape.
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

# --- Constants & Defaults ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OCI_CONFIG_DIR="$HOME/.oci"
OCI_CONFIG_FILE="$HOME/.oci/config"
DEFAULT_INSTANCE_CONFIG="$REPO_ROOT/oci/local/config/instance-config"
DEFAULT_SSH_DIR="$REPO_ROOT/oci/local/ssh"
DEFAULT_LOG_DIR="$REPO_ROOT/oci/local/logs"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
LOG_FILE=""

# --- Script State ---
DRY_RUN=false
NON_INTERACTIVE=false
OCI_PROFILE="DEFAULT"
INSTANCE_CONFIG_FILE=""
COMPARTMENT_OCID=""
INSTANCE_OCID=""
IMAGE_OCID=""
SSH_PUBLIC_KEY_PATH=""
SSH_PRIVATE_KEY_PATH=""
CLOUD_INIT_PATH=""
ARCH=""
NEW_USERNAME=""
NEW_PASSWORD=""
INSTALL_CLOUDPANEL=false
CLOUDPANEL_ADMIN_EMAIL=""
CLOUDPANEL_DB_ENGINE="MYSQL_8.4"
BOOT_VOLUME_SIZE_GB=""
AVAILABILITY_DOMAIN=""
SKIP_BACKUP=false
DELETE_OLD_BV=false
backup_id=""
new_bv_id=""

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ============================================================================
# Utility Functions
# ============================================================================

print_header() {
    echo ""
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${BOLD}${CYAN}▶ $1${NC}"
}

print_info() {
    echo -e "${BLUE}  ℹ $1${NC}"
}

print_success() {
    echo -e "${GREEN}  ✔ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}  ✘ $1${NC}"
}

print_detail() {
    echo -e "    $1"
}

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    if [[ -n "$LOG_FILE" ]]; then
        echo "$msg" >> "$LOG_FILE"
    fi
    echo -e "  ${msg}"
}

log_quiet() {
    if [[ -n "$LOG_FILE" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
    fi
}

die() {
    print_error "$1"
    log_quiet "FATAL: $1"
    exit 1
}

confirm() {
    local prompt="$1"
    if $NON_INTERACTIVE; then return 0; fi
    echo ""
    read -r -p "$(echo -e "${BOLD}  ? ${prompt} [y/N]: ${NC}")" response </dev/tty
    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

prompt_input() {
    local prompt="$1"
    local default="${2:-}"
    local result
    if [[ -n "$default" ]]; then
        read -r -p "$(echo -e "${BOLD}  ? ${prompt} [${default}]: ${NC}")" result </dev/tty
        echo "${result:-$default}"
    else
        read -r -p "$(echo -e "${BOLD}  ? ${prompt}: ${NC}")" result </dev/tty
        echo "$result"
    fi
}

prompt_password() {
    local prompt="$1"
    local result
    read -r -s -p "$(echo -e "${BOLD}  ? ${prompt}: ${NC}")" result </dev/tty
    echo "" >/dev/tty
    echo "$result"
}

prompt_selection() {
    local prompt="$1"
    shift
    local options=("$@")
    # Display to /dev/tty so menu is visible even when called inside $()
    echo "" >/dev/tty
    echo -e "${BOLD}  ${prompt}${NC}" >/dev/tty
    echo "" >/dev/tty
    for i in "${!options[@]}"; do
        printf "    ${CYAN}%3d)${NC} %s\n" "$((i + 1))" "${options[$i]}" >/dev/tty
    done
    echo "" >/dev/tty
    local selection
    while true; do
        read -r -p "$(echo -e "${BOLD}  Enter number (1-${#options[@]}): ${NC}")" selection </dev/tty
        if [[ "$selection" =~ ^[0-9]+$ ]] && (( selection >= 1 && selection <= ${#options[@]} )); then
            echo "$((selection - 1))"
            return
        fi
        echo -e "${YELLOW}  ⚠ Invalid selection. Please enter a number between 1 and ${#options[@]}.${NC}" >/dev/tty
    done
}

oci_cmd() {
    oci --profile "$OCI_PROFILE" "$@"
}

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
            *) die "Unknown option: $1. Use --help for usage." ;;
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

    # Create log directory
    mkdir -p "$DEFAULT_LOG_DIR"
    LOG_FILE="$DEFAULT_LOG_DIR/reprovision-${TIMESTAMP}.log"
    log_quiet "=== Reprovision session started at $(date) ==="
    log_quiet "Dry-run: $DRY_RUN"

    # Check dependencies
    print_step "Checking dependencies..."
    for cmd in oci jq openssl ssh; do
        if command -v "$cmd" &>/dev/null; then
            print_success "$cmd found: $(command -v "$cmd")"
        else
            die "$cmd is required but not installed. Please install it and try again."
        fi
    done

    # Load instance config if it exists
    if [[ -f "$INSTANCE_CONFIG_FILE" ]]; then
        print_success "Loading instance config from: $INSTANCE_CONFIG_FILE"
        # Source only known variables (safety)
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
# OCI Profile Management — Multi-profile support via ~/.oci/config
# ============================================================================
# OCI CLI uses INI-style config with [PROFILE] sections.
# Standard location: ~/.oci/config
# Keys stored in: ~/.oci/keys/<profile_name>/
# Usage: oci --profile <PROFILE_NAME> <command>
# ============================================================================

# Parse all profile names from ~/.oci/config
list_oci_profiles() {
    if [[ ! -f "$OCI_CONFIG_FILE" ]]; then
        return
    fi
    grep -E '^\[' "$OCI_CONFIG_FILE" | sed 's/\[//;s/\]//' | sort
}

# Get a config value for a specific profile from ~/.oci/config
get_profile_value() {
    local profile="$1" key="$2"
    if [[ ! -f "$OCI_CONFIG_FILE" ]]; then
        return
    fi
    # Use awk to find the value within the profile section
    awk -v profile="[$profile]" -v key="$key" '
        $0 == profile { found=1; next }
        /^\[/ { found=0 }
        found && $0 ~ "^"key"[[:space:]]*=" {
            sub(/^[^=]*=[[:space:]]*/, ""); print; exit
        }
    ' "$OCI_CONFIG_FILE"
}

# Test if a profile can connect to OCI
test_profile_connectivity() {
    local profile="$1"
    oci --profile "$profile" iam region list --output json 2>/dev/null | jq -r '.data[0].name' 2>/dev/null
}

# Append a new profile section to ~/.oci/config
append_profile_to_config() {
    local profile="$1" user="$2" fingerprint="$3" tenancy="$4" region="$5" key_file="$6"

    # Ensure config file exists
    mkdir -p "$OCI_CONFIG_DIR"
    touch "$OCI_CONFIG_FILE"
    chmod 600 "$OCI_CONFIG_FILE"

    # Add a blank line separator if file is not empty
    if [[ -s "$OCI_CONFIG_FILE" ]]; then
        echo "" >> "$OCI_CONFIG_FILE"
    fi

    cat >> "$OCI_CONFIG_FILE" <<EOF
[${profile}]
user=${user}
fingerprint=${fingerprint}
tenancy=${tenancy}
region=${region}
key_file=${key_file}
EOF
    log_quiet "Profile [$profile] added to $OCI_CONFIG_FILE"
}

# --- Step 1a: Select or Create OCI Profile ---
step_select_profile() {
    print_header "Step 1: OCI Profile Selection"

    print_info "OCI CLI supports multiple profiles in ~/.oci/config."
    print_info "Each profile can connect to a different tenancy, region, or user."
    print_info "Config location: ${CYAN}${OCI_CONFIG_FILE}${NC}"
    echo ""

    # Check if config file exists
    if [[ ! -f "$OCI_CONFIG_FILE" ]]; then
        print_warning "No OCI config found at: $OCI_CONFIG_FILE"
        print_info "Let's set up your first OCI profile."
        echo ""
        setup_new_profile "DEFAULT"
        OCI_PROFILE="DEFAULT"
        return
    fi

    # List existing profiles
    local profiles=()
    while IFS= read -r p; do
        profiles+=("$p")
    done < <(list_oci_profiles)

    if [[ ${#profiles[@]} -eq 0 ]]; then
        print_warning "Config file exists but contains no profiles."
        print_info "Let's set up your first OCI profile."
        echo ""
        setup_new_profile "DEFAULT"
        OCI_PROFILE="DEFAULT"
        return
    fi

    # If --profile was provided via CLI, validate and use it
    if [[ "$OCI_PROFILE" != "DEFAULT" ]]; then
        local found=false
        for p in "${profiles[@]}"; do
            if [[ "$p" == "$OCI_PROFILE" ]]; then
                found=true
                break
            fi
        done
        if $found; then
            print_success "Using profile from CLI flag: $OCI_PROFILE"
            return
        else
            print_warning "Profile '$OCI_PROFILE' not found in config."
            print_info "Available profiles: ${profiles[*]}"
            echo ""
        fi
    fi

    # Build selection list with profile details
    local profile_labels=()
    local profile_status=()

    for p in "${profiles[@]}"; do
        local region tenancy_ocid label
        region=$(get_profile_value "$p" "region")
        tenancy_ocid=$(get_profile_value "$p" "tenancy")
        local tenancy_short=""
        if [[ -n "$tenancy_ocid" ]]; then
            tenancy_short="...${tenancy_ocid: -12}"
        fi
        label="[$p]"
        [[ -n "$region" ]] && label="$label  region: $region"
        [[ -n "$tenancy_short" ]] && label="$label  tenancy: $tenancy_short"
        profile_labels+=("$label")
    done
    profile_labels+=("➕ Add a new profile")

    print_info "Found ${#profiles[@]} profile(s) in ~/.oci/config:"
    echo ""

    local idx
    idx=$(prompt_selection "Choose an OCI profile to use:" "${profile_labels[@]}")

    if [[ $idx -lt ${#profiles[@]} ]]; then
        OCI_PROFILE="${profiles[$idx]}"
        print_success "Selected profile: $OCI_PROFILE"
    else
        # Add new profile
        echo ""
        print_info "Let's set up a new OCI profile."
        echo ""

        # Suggest a profile name
        local default_name="PROFILE_$(( ${#profiles[@]} + 1 ))"
        print_info "Profile names are typically uppercase: DEFAULT, PROD, DEV, etc."
        local profile_name
        profile_name=$(prompt_input "Profile name" "$default_name")
        profile_name=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]' | tr ' -' '_')

        # Check for duplicates
        for p in "${profiles[@]}"; do
            if [[ "$p" == "$profile_name" ]]; then
                print_warning "Profile '$profile_name' already exists. Choose a different name."
                profile_name=$(prompt_input "Profile name")
                profile_name=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]' | tr ' -' '_')
                break
            fi
        done

        setup_new_profile "$profile_name"
        OCI_PROFILE="$profile_name"
    fi

    log_quiet "OCI profile selected: $OCI_PROFILE"
}

# --- Setup a new profile interactively ---
setup_new_profile() {
    local profile_name="$1"
    print_step "Setting up profile: [$profile_name]"
    echo ""

    print_info "Choose how you'd like to authenticate with OCI:"
    echo ""

    local method
    method=$(prompt_selection "Choose an authentication method:" \
        "Browser login (easiest — opens browser, auto-configures)" \
        "Interactive CLI setup (step-by-step — paste OCIDs, generate key)" \
        "Use existing credentials (already have OCIDs and key file)")

    echo ""
    case "$method" in
        0) setup_profile_bootstrap "$profile_name" ;;
        1) setup_profile_interactive "$profile_name" ;;
        2) setup_profile_existing "$profile_name" ;;
    esac
}

# --- Auth Method A: Browser-based bootstrap ---
setup_profile_bootstrap() {
    local profile_name="$1"
    print_step "Browser-Based Setup (oci setup bootstrap)"
    echo ""
    print_info "This will open a browser window for you to log into OCI."
    print_info "The CLI will automatically:"
    print_detail "• Generate an API signing key pair"
    print_detail "• Upload the public key to your OCI account"
    print_detail "• Create the config profile"
    echo ""
    print_info "Requirements:"
    print_detail "• A web browser accessible from this machine"
    print_detail "• Port 8181 must be available (used for the auth callback)"
    echo ""

    if ! confirm "Ready to open the browser login?"; then
        die "Setup cancelled."
    fi

    mkdir -p "$OCI_CONFIG_DIR"

    if oci setup bootstrap --config-location "$OCI_CONFIG_FILE" --profile-name "$profile_name" 2>/dev/null; then
        print_success "OCI bootstrap complete! Profile [$profile_name] saved."
        log_quiet "Profile [$profile_name] created via bootstrap"
    else
        # bootstrap may not support --profile-name in all versions, fall back to interactive
        print_warning "Browser bootstrap didn't work. Falling back to interactive setup."
        setup_profile_interactive "$profile_name"
    fi
}

# --- Auth Method B: Interactive CLI setup ---
setup_profile_interactive() {
    local profile_name="$1"
    print_step "Interactive CLI Setup for profile [$profile_name]"
    echo ""
    print_info "You'll need to provide your OCIDs — here's where to find them:"
    echo ""
    echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}  │  HOW TO FIND YOUR OCI IDENTIFIERS                              │${NC}"
    echo -e "${BOLD}  ├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${BOLD}  │                                                                 │${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}User OCID:${NC}                                                    ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    1. Log in to ${YELLOW}https://cloud.oracle.com${NC}                        ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    2. Click your ${CYAN}Profile icon${NC} (top-right corner)                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    3. Click ${CYAN}\"User Settings\"${NC}                                      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    4. Under your username, click ${CYAN}\"Copy\"${NC} next to OCID             ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    → Looks like: ${YELLOW}ocid1.user.oc1..aaaaaa...${NC}                      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}Tenancy OCID:${NC}                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    1. Click your ${CYAN}Profile icon${NC} (top-right corner)                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    2. Click ${CYAN}\"Tenancy: <your-tenancy-name>\"${NC}                       ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    3. Click ${CYAN}\"Copy\"${NC} next to OCID                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    → Looks like: ${YELLOW}ocid1.tenancy.oc1..aaaaaa...${NC}                   ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}Region:${NC}                                                       ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    Shown in the top bar of OCI Console                          ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    → Examples: ${YELLOW}us-ashburn-1${NC}, ${YELLOW}us-phoenix-1${NC}, ${YELLOW}eu-frankfurt-1${NC}      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  └─────────────────────────────────────────────────────────────────┘${NC}"
    echo ""

    if ! confirm "Do you have your User OCID and Tenancy OCID ready?"; then
        print_info "Take your time. Here's what to do:"
        print_detail "1. Open ${YELLOW}https://cloud.oracle.com${NC} in a browser"
        print_detail "2. Sign in with your OCI account"
        print_detail "3. Follow the steps in the box above to copy your OCIDs"
        echo ""
        read -r -p "$(echo -e "${BOLD}  Press Enter when you're ready to continue...${NC}")"
    fi

    # Key directory for this profile
    local profile_key_dir="$OCI_CONFIG_DIR/keys/${profile_name}"
    mkdir -p "$profile_key_dir"

    echo ""
    print_step "Let's configure your OCI access step by step."
    echo ""

    # Tenancy OCID first (most fundamental)
    print_info "${CYAN}Step 1 of 4: Tenancy OCID${NC}"
    print_detail "This identifies your OCI account/organization."
    print_detail "Find it: Profile icon → Tenancy → Copy OCID"
    local tenancy_ocid
    tenancy_ocid=$(prompt_input "Paste your Tenancy OCID")
    while [[ ! "$tenancy_ocid" =~ ^ocid1\.tenancy\. ]]; do
        print_warning "That doesn't look like a tenancy OCID (should start with 'ocid1.tenancy.')"
        tenancy_ocid=$(prompt_input "Paste your Tenancy OCID")
    done
    print_success "Tenancy OCID saved"
    echo ""

    # User OCID
    print_info "${CYAN}Step 2 of 4: User OCID${NC}"
    print_detail "This identifies your OCI user account."
    print_detail "Find it: Profile icon → User Settings → OCID → Copy"
    local user_ocid
    user_ocid=$(prompt_input "Paste your User OCID")
    while [[ ! "$user_ocid" =~ ^ocid1\.user\. ]]; do
        print_warning "That doesn't look like a user OCID (should start with 'ocid1.user.')"
        user_ocid=$(prompt_input "Paste your User OCID")
    done
    print_success "User OCID saved"
    echo ""

    # Region
    print_info "${CYAN}Step 3 of 4: Region${NC}"
    print_detail "Your home region — shown in the OCI Console top bar."
    print_detail "Common regions: us-ashburn-1, us-phoenix-1, us-sanjose-1,"
    print_detail "                eu-frankfurt-1, ap-tokyo-1, uk-london-1, ca-toronto-1"
    local region
    region=$(prompt_input "Enter your region" "us-ashburn-1")
    print_success "Region: $region"
    echo ""

    # API Key
    print_info "${CYAN}Step 4 of 4: API Signing Key${NC}"
    print_detail "OCI uses RSA key pairs for API authentication."
    print_detail "We need a private key on this machine and the matching"
    print_detail "public key uploaded to your OCI user profile."
    print_detail ""
    print_detail "Keys are stored in: ~/.oci/keys/${profile_name}/"
    echo ""

    local default_key_name="oci_api_$(date +%Y%m%d)"
    local key_name key_action

    # Check for existing keys in the profile dir
    if ls "$profile_key_dir"/*.pem 2>/dev/null | grep -v '_public' | head -1 >/dev/null 2>&1; then
        print_info "Existing API key(s) found in $profile_key_dir:"
        ls "$profile_key_dir"/*.pem 2>/dev/null | grep -v '_public' | while read -r f; do print_detail "  $f"; done
        echo ""
    fi

    key_action=$(prompt_selection "How would you like to set up the API key?" \
        "Generate a new key (Recommended)" \
        "I already have a key — let me provide the path")

    local key_path pub_path fingerprint=""

    case "$key_action" in
        0)
            # Generate in profile key directory
            key_name=$(prompt_input "Key name" "$default_key_name")
            key_path="${profile_key_dir}/${key_name}.pem"
            pub_path="${profile_key_dir}/${key_name}_public.pem"

            if [[ -f "$key_path" ]]; then
                print_warning "Key already exists at: $key_path"
                if ! confirm "Overwrite it?"; then
                    print_info "Using existing key."
                else
                    openssl genrsa -out "$key_path" 2048 2>/dev/null
                    chmod 600 "$key_path"
                    openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                    print_success "New key generated at: $key_path"
                fi
            else
                openssl genrsa -out "$key_path" 2048 2>/dev/null
                chmod 600 "$key_path"
                openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                print_success "Key generated at: $key_path"
            fi

            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            ;;
        1)
            # User provides path
            key_path=$(prompt_input "Path to your private key (.pem)")
            while [[ ! -f "$key_path" ]]; do
                print_warning "File not found: $key_path"
                key_path=$(prompt_input "Path to your private key (.pem)")
            done
            pub_path="${key_path%.pem}_public.pem"
            if [[ ! -f "$pub_path" ]]; then
                openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                print_info "Generated public key: $pub_path"
            fi
            # Copy to profile key directory
            local base
            base=$(basename "$key_path")
            cp "$key_path" "$profile_key_dir/$base"
            cp "$pub_path" "$profile_key_dir/$(basename "$pub_path")"
            chmod 600 "$profile_key_dir/$base"
            key_path="$profile_key_dir/$base"
            pub_path="$profile_key_dir/$(basename "$pub_path")"
            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            print_success "Key copied to: $profile_key_dir/"
            ;;
    esac

    print_info "Key fingerprint: $fingerprint"
    echo ""

    # Guide user to upload the public key
    print_step "Now upload the public key to your OCI account"
    echo ""
    echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}  │  UPLOAD YOUR PUBLIC KEY TO OCI                                  │${NC}"
    echo -e "${BOLD}  ├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  1. Go to ${YELLOW}https://cloud.oracle.com${NC}                              ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  2. Click ${CYAN}Profile icon${NC} (top-right) → ${CYAN}\"User Settings\"${NC}           ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  3. Go to ${CYAN}\"Tokens and keys\"${NC} (under Resources, left sidebar)     ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  4. Click ${CYAN}\"Add API Key\"${NC}                                         ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  5. Select ${CYAN}\"Paste a Public Key\"${NC}                                  ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  6. Paste the key shown below                                   ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  7. Click ${CYAN}\"Add\"${NC}                                                  ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  After clicking Add, OCI will show a                             ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${GREEN}\"Configuration File Preview\"${NC} — you don't need to copy it,      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  we already have all the values.                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  └─────────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    echo -e "${BOLD}  Your public key to paste:${NC}"
    echo -e "${YELLOW}"
    cat "$pub_path"
    echo -e "${NC}"

    if ! $NON_INTERACTIVE; then
        read -r -p "$(echo -e "${BOLD}  Press Enter after you've uploaded the key to OCI Console...${NC}")" </dev/tty
    fi

    # Write profile to ~/.oci/config
    append_profile_to_config "$profile_name" "$user_ocid" "$fingerprint" "$tenancy_ocid" "$region" "$key_path"
    print_success "Profile [$profile_name] saved to: $OCI_CONFIG_FILE"
}

# --- Auth Method C: Use existing credentials ---
setup_profile_existing() {
    local profile_name="$1"
    print_step "Use Existing Credentials for profile [$profile_name]"
    echo ""

    print_info "You'll need: User OCID, Tenancy OCID, Region, and key file path."
    echo ""

    local user_ocid tenancy_ocid region key_path fingerprint

    tenancy_ocid=$(prompt_input "Tenancy OCID")
    while [[ ! "$tenancy_ocid" =~ ^ocid1\.tenancy\. ]]; do
        print_warning "Should start with 'ocid1.tenancy.'"
        tenancy_ocid=$(prompt_input "Tenancy OCID")
    done

    user_ocid=$(prompt_input "User OCID")
    while [[ ! "$user_ocid" =~ ^ocid1\.user\. ]]; do
        print_warning "Should start with 'ocid1.user.'"
        user_ocid=$(prompt_input "User OCID")
    done

    region=$(prompt_input "Region" "us-ashburn-1")

    key_path=$(prompt_input "Path to private key (.pem)")
    while [[ ! -f "$key_path" ]]; do
        print_warning "File not found: $key_path"
        key_path=$(prompt_input "Path to private key (.pem)")
    done

    # Copy key to profile key directory
    local profile_key_dir="$OCI_CONFIG_DIR/keys/${profile_name}"
    mkdir -p "$profile_key_dir"
    local base
    base=$(basename "$key_path")
    cp "$key_path" "$profile_key_dir/$base"
    chmod 600 "$profile_key_dir/$base"
    key_path="$profile_key_dir/$base"

    fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')

    append_profile_to_config "$profile_name" "$user_ocid" "$fingerprint" "$tenancy_ocid" "$region" "$key_path"
    print_success "Profile [$profile_name] saved to: $OCI_CONFIG_FILE"
}

# --- Main auth step ---
step_verify_oci_config() {
    print_header "Step 1: OCI Profile & API Configuration"

    # Use step_select_profile which handles scanning, selection, and new profile creation
    step_select_profile

    echo ""
    print_step "Testing OCI API connectivity for profile [$OCI_PROFILE]..."
    if test_profile_connectivity "$OCI_PROFILE"; then
        print_success "OCI API connection successful!"
        log_quiet "OCI API connection verified (profile: $OCI_PROFILE)"
    else
        # Retry once — key propagation can take a few seconds
        print_warning "First attempt failed. Waiting 5 seconds for key propagation..."
        sleep 5
        if test_profile_connectivity "$OCI_PROFILE"; then
            print_success "OCI API connection successful (after retry)!"
            log_quiet "OCI API connection verified (profile: $OCI_PROFILE, retry)"
        else
            print_error "Connection failed. Common issues:"
            print_detail "• API key not uploaded to OCI Console yet"
            print_detail "• Fingerprint mismatch (re-generate and re-upload key)"
            print_detail "• User/Tenancy OCID typo (verify in OCI Console)"
            print_detail "• Region incorrect (check OCI Console top bar)"
            echo ""
            print_info "Your config file: $OCI_CONFIG_FILE"
            print_info "Edit profile [$OCI_PROFILE] with: nano $OCI_CONFIG_FILE"
            die "OCI API connection failed. Fix the config and re-run."
        fi
    fi

    # Get tenancy for later use via profile
    local tenancy_ocid
    tenancy_ocid=$(get_profile_value "$OCI_PROFILE" "tenancy")

    if [[ -z "$tenancy_ocid" ]]; then
        die "Could not read tenancy OCID from profile [$OCI_PROFILE] in $OCI_CONFIG_FILE"
    fi

    # Get or prompt for compartment OCID
    if [[ -z "$COMPARTMENT_OCID" ]]; then
        echo ""
        print_step "Select a compartment"
        print_info "A compartment is an OCI container for organizing your cloud resources."
        print_info "Most users have a 'root' compartment (the tenancy itself) and may"
        print_info "have additional compartments for different projects or environments."
        print_info "Listing compartments in your tenancy..."
        echo ""

        local compartments
        compartments=$(oci_cmd iam compartment list \
            --compartment-id "$tenancy_ocid" \
            --compartment-id-in-subtree true \
            --lifecycle-state ACTIVE \
            --all 2>/dev/null)

        local comp_names=()
        local comp_ids=()

        # Add root compartment (tenancy)
        comp_names+=("Root compartment (tenancy) — use if unsure")
        comp_ids+=("$tenancy_ocid")

        while IFS= read -r line; do
            local name id desc
            name=$(echo "$line" | jq -r '.name')
            id=$(echo "$line" | jq -r '.id')
            desc=$(echo "$line" | jq -r '.description // ""' | head -c 50)
            if [[ -n "$desc" ]]; then
                comp_names+=("$name — $desc")
            else
                comp_names+=("$name")
            fi
            comp_ids+=("$id")
        done < <(echo "$compartments" | jq -c '.data[]')

        local idx
        idx=$(prompt_selection "Choose the compartment where your instances live:" "${comp_names[@]}")
        COMPARTMENT_OCID="${comp_ids[$idx]}"
        print_success "Selected: ${comp_names[$idx]}"
        log_quiet "Compartment: ${comp_names[$idx]} ($COMPARTMENT_OCID)"
    fi
}

# ============================================================================
# Step 2: Select Instance
# ============================================================================

step_select_instance() {
    print_header "Step 2: Select Instance to Reprovision"

    if [[ -n "$INSTANCE_OCID" ]]; then
        print_info "Instance OCID provided: $INSTANCE_OCID"
    else
        print_info "Listing compute instances in your compartment..."
        print_info "The script will show all instances — you choose which one to reprovision."
        echo ""

        local instances
        instances=$(oci_cmd compute instance list \
            --compartment-id "$COMPARTMENT_OCID" \
            --all 2>/dev/null)

        local inst_names=()
        local inst_ids=()
        local inst_details=()

        while IFS= read -r line; do
            local name id state shape
            name=$(echo "$line" | jq -r '.["display-name"]')
            id=$(echo "$line" | jq -r '.id')
            state=$(echo "$line" | jq -r '.["lifecycle-state"]')
            shape=$(echo "$line" | jq -r '.shape')
            inst_names+=("$name")
            inst_ids+=("$id")
            inst_details+=("${name}  |  State: ${state}  |  Shape: ${shape}")
        done < <(echo "$instances" | jq -c '.data[] | select(.["lifecycle-state"] != "TERMINATED")')

        if [[ ${#inst_names[@]} -eq 0 ]]; then
            die "No active instances found in compartment $COMPARTMENT_OCID"
        fi

        local idx
        idx=$(prompt_selection "Choose an instance to reprovision:" "${inst_details[@]}")
        INSTANCE_OCID="${inst_ids[$idx]}"
        print_success "Selected: ${inst_names[$idx]}"
        log_quiet "Instance selected: ${inst_names[$idx]} ($INSTANCE_OCID)"
    fi

    # Get instance details
    print_step "Fetching instance details..."
    local instance_data
    instance_data=$(oci_cmd compute instance get --instance-id "$INSTANCE_OCID" 2>/dev/null)

    local display_name shape lifecycle_state
    display_name=$(echo "$instance_data" | jq -r '.data["display-name"]')
    shape=$(echo "$instance_data" | jq -r '.data.shape')
    lifecycle_state=$(echo "$instance_data" | jq -r '.data["lifecycle-state"]')

    if [[ -z "$AVAILABILITY_DOMAIN" ]]; then
        AVAILABILITY_DOMAIN=$(echo "$instance_data" | jq -r '.data["availability-domain"]')
    fi

    print_detail "Name:        $display_name"
    print_detail "Shape:       $shape"
    print_detail "State:       $lifecycle_state"
    print_detail "AD:          $AVAILABILITY_DOMAIN"
    print_detail "OCID:        $INSTANCE_OCID"

    # Detect architecture from shape
    if [[ -z "$ARCH" ]]; then
        if echo "$shape" | grep -qiE 'A1|Ampere'; then
            ARCH="arm"
        else
            ARCH="x86"
        fi
    fi
    print_detail "Architecture: $ARCH (detected from shape)"
    log_quiet "Instance: $display_name, Shape: $shape, State: $lifecycle_state, Arch: $ARCH"

    # Get VNIC info (for IP address display)
    print_step "Fetching network details..."
    local vnic_attachments
    vnic_attachments=$(oci_cmd compute vnic-attachment list \
        --compartment-id "$COMPARTMENT_OCID" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null)

    local vnic_id public_ip private_ip
    vnic_id=$(echo "$vnic_attachments" | jq -r '.data[0]["vnic-id"]')
    if [[ -n "$vnic_id" && "$vnic_id" != "null" ]]; then
        local vnic_data
        vnic_data=$(oci_cmd network vnic get --vnic-id "$vnic_id" 2>/dev/null)
        public_ip=$(echo "$vnic_data" | jq -r '.data["public-ip"] // "none"')
        private_ip=$(echo "$vnic_data" | jq -r '.data["private-ip"] // "none"')
        print_detail "Public IP:   $public_ip"
        print_detail "Private IP:  $private_ip"
        log_quiet "Public IP: $public_ip, Private IP: $private_ip, VNIC: $vnic_id"
    fi

    # Get current boot volume
    print_step "Fetching current boot volume..."
    local boot_volumes
    boot_volumes=$(oci_cmd compute boot-volume-attachment list \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --compartment-id "$COMPARTMENT_OCID" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null)

    # Prefer ATTACHED, fall back to most recent DETACHED (recovery case)
    local attached_bv
    attached_bv=$(echo "$boot_volumes" | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | .[0]')
    if [[ "$attached_bv" != "null" && -n "$attached_bv" ]]; then
        CURRENT_BOOT_VOLUME_ID=$(echo "$attached_bv" | jq -r '.["boot-volume-id"]')
        CURRENT_BOOT_ATTACH_ID=$(echo "$attached_bv" | jq -r '.id')
    else
        # Recovery: boot volume is detached (previous failed run)
        local detached_bv
        detached_bv=$(echo "$boot_volumes" | jq -r '[.data[] | select(.["lifecycle-state"] == "DETACHED")] | sort_by(.["time-created"]) | last')
        CURRENT_BOOT_VOLUME_ID=$(echo "$detached_bv" | jq -r '.["boot-volume-id"]')
        CURRENT_BOOT_ATTACH_ID=$(echo "$detached_bv" | jq -r '.id')
        print_warning "Boot volume is currently DETACHED (previous run may have failed)"
    fi
    print_detail "Boot Volume: $CURRENT_BOOT_VOLUME_ID"
    log_quiet "Current boot volume: $CURRENT_BOOT_VOLUME_ID"
    log_quiet "Boot volume attachment: $CURRENT_BOOT_ATTACH_ID"

    # Get boot volume size
    if [[ -z "$BOOT_VOLUME_SIZE_GB" ]]; then
        local bv_data
        bv_data=$(oci_cmd bv boot-volume get --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" 2>/dev/null)
        BOOT_VOLUME_SIZE_GB=$(echo "$bv_data" | jq -r '.data["size-in-gbs"]')
        print_detail "Boot Vol Size: ${BOOT_VOLUME_SIZE_GB} GB"
    fi

    # Save instance metadata for backup
    echo "$instance_data" | jq '.data' > "$DEFAULT_LOG_DIR/instance-metadata-${TIMESTAMP}.json"
    print_success "Instance metadata backed up to logs"
}

# ============================================================================
# Step 3: Select Ubuntu Image
# ============================================================================

step_select_image() {
    print_header "Step 3: Select Ubuntu Image"

    if [[ -n "$IMAGE_OCID" ]]; then
        print_info "Image OCID provided: $IMAGE_OCID"
        return
    fi

    print_info "Querying available Ubuntu images for your architecture ($ARCH)..."
    print_info "This searches for official Canonical Ubuntu images in OCI."
    echo ""

    # Determine shape series for image compatibility
    local shape_filter
    if [[ "$ARCH" == "arm" ]]; then
        shape_filter="aarch64"
    else
        shape_filter="x86_64"  # Matches both AMD64 and x86_64
    fi

    # List Ubuntu images
    local images
    images=$(oci_cmd compute image list \
        --compartment-id "$COMPARTMENT_OCID" \
        --operating-system "Canonical Ubuntu" \
        --sort-by TIMECREATED \
        --sort-order DESC \
        --all 2>/dev/null)

    local img_names=()
    local img_ids=()
    local count=0

    while IFS= read -r line; do
        local name id
        name=$(echo "$line" | jq -r '.["display-name"]')
        id=$(echo "$line" | jq -r '.id')

        # Filter by architecture
        if echo "$name" | grep -qi "$shape_filter"; then
            img_names+=("$name")
            img_ids+=("$id")
            count=$((count + 1))
            [[ $count -ge 10 ]] && break
        fi
    done < <(echo "$images" | jq -c '.data[]')

    if [[ ${#img_names[@]} -eq 0 ]]; then
        die "No Ubuntu images found for architecture: $ARCH"
    fi

    print_info "Found ${#img_names[@]} Ubuntu images (most recent first):"

    local idx
    idx=$(prompt_selection "Choose an Ubuntu image:" "${img_names[@]}")
    IMAGE_OCID="${img_ids[$idx]}"
    print_success "Selected: ${img_names[$idx]}"
    log_quiet "Image selected: ${img_names[$idx]} ($IMAGE_OCID)"
}

# ============================================================================
# Step 4: SSH Key Setup
# ============================================================================

step_ssh_key() {
    print_header "Step 4: SSH Key Configuration"

    print_info "The new OS will be configured with SSH key-only authentication."
    print_info "Password login will be DISABLED for security."
    echo ""

    mkdir -p "$DEFAULT_SSH_DIR"

    if [[ -n "$SSH_PUBLIC_KEY_PATH" && -f "$SSH_PUBLIC_KEY_PATH" ]]; then
        print_success "SSH public key: $SSH_PUBLIC_KEY_PATH"
    else
        # Look for keys in oci/local/ssh/
        local pub_keys=()
        if [[ -d "$DEFAULT_SSH_DIR" ]]; then
            while IFS= read -r -d '' keyfile; do
                pub_keys+=("$keyfile")
            done < <(find "$DEFAULT_SSH_DIR" -name "*.pub" -print0 2>/dev/null)
        fi

        # Also look in ~/.ssh/
        local home_keys=()
        if [[ -d "$HOME/.ssh" ]]; then
            while IFS= read -r -d '' keyfile; do
                home_keys+=("$keyfile")
            done < <(find "$HOME/.ssh" -name "*.pub" -print0 2>/dev/null)
        fi

        # Build selection list from all found keys
        local all_keys=()
        local all_labels=()
        for k in "${pub_keys[@]}"; do
            all_keys+=("$k")
            all_labels+=("[repo] $k")
        done
        for k in "${home_keys[@]}"; do
            all_keys+=("$k")
            all_labels+=("[home] $k")
        done
        all_labels+=("Generate a new SSH key")

        if [[ ${#pub_keys[@]} -eq 0 && ${#home_keys[@]} -eq 0 ]]; then
            print_warning "No SSH keys found in $DEFAULT_SSH_DIR or ~/.ssh/"
            echo ""
            print_info "Let's generate a new SSH key pair."
        fi

        local idx
        idx=$(prompt_selection "Choose an SSH public key:" "${all_labels[@]}")

        if [[ $idx -eq ${#all_keys[@]} ]]; then
            # Generate new key in ~/.ssh/ with user-chosen name
            local default_name="oci_bash_$(date +%Y%m%d)"
            echo "" >/dev/tty
            print_info "The key will be generated in ~/.ssh/"
            print_info "Default name: ${CYAN}${default_name}${NC}"
            print_info "Enter a custom name or press Enter for the default."
            echo "" >/dev/tty

            local key_name
            key_name=$(prompt_input "SSH key name" "$default_name")
            local key_path="$HOME/.ssh/${key_name}"

            # Check if key already exists
            if [[ -f "$key_path" ]]; then
                print_warning "Key already exists: $key_path"
                if confirm "Use existing key instead of overwriting?"; then
                    SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                    SSH_PRIVATE_KEY_PATH="$key_path"
                else
                    ssh-keygen -t ed25519 -f "$key_path" -N "" -C "${key_name}" <<< "y"
                    SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                    SSH_PRIVATE_KEY_PATH="$key_path"
                fi
            else
                ssh-keygen -t ed25519 -f "$key_path" -N "" -C "${key_name}"
                SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                SSH_PRIVATE_KEY_PATH="$key_path"
            fi

            print_success "SSH key ready:"
            print_detail "Private: $SSH_PRIVATE_KEY_PATH"
            print_detail "Public:  $SSH_PUBLIC_KEY_PATH"

            # Copy to repo-local ssh dir
            mkdir -p "$DEFAULT_SSH_DIR"
            cp "$SSH_PUBLIC_KEY_PATH" "$DEFAULT_SSH_DIR/"
            cp "$SSH_PRIVATE_KEY_PATH" "$DEFAULT_SSH_DIR/"
            chmod 600 "$DEFAULT_SSH_DIR/$(basename "$SSH_PRIVATE_KEY_PATH")"
            print_info "Key also copied to: $DEFAULT_SSH_DIR/ (gitignored)"
        else
            SSH_PUBLIC_KEY_PATH="${all_keys[$idx]}"
            SSH_PRIVATE_KEY_PATH="${SSH_PUBLIC_KEY_PATH%.pub}"

            # If key is from ~/.ssh, offer to copy to repo local
            if [[ "$SSH_PUBLIC_KEY_PATH" == "$HOME/.ssh/"* ]]; then
                if confirm "Copy this key to $DEFAULT_SSH_DIR for this project?"; then
                    mkdir -p "$DEFAULT_SSH_DIR"
                    cp "$SSH_PUBLIC_KEY_PATH" "$DEFAULT_SSH_DIR/"
                    [[ -f "$SSH_PRIVATE_KEY_PATH" ]] && cp "$SSH_PRIVATE_KEY_PATH" "$DEFAULT_SSH_DIR/"
                    local basename
                    basename=$(basename "$SSH_PUBLIC_KEY_PATH")
                    SSH_PUBLIC_KEY_PATH="$DEFAULT_SSH_DIR/$basename"
                    SSH_PRIVATE_KEY_PATH="${SSH_PUBLIC_KEY_PATH%.pub}"
                    print_success "Key copied to: $DEFAULT_SSH_DIR/"
                fi
            fi
        fi
    fi

    log_quiet "SSH public key: $SSH_PUBLIC_KEY_PATH"
    print_detail "Key fingerprint: $(ssh-keygen -lf "$SSH_PUBLIC_KEY_PATH" 2>/dev/null | awk '{print $2}')"
}

# ============================================================================
# Step 5: New User & OS Configuration
# ============================================================================

step_user_config() {
    print_header "Step 5: New User & OS Configuration"

    print_info "The new OS will be hardened with the following security settings:"
    print_detail "• Default 'ubuntu' user will be DISABLED"
    print_detail "• SSH password authentication will be DISABLED"
    print_detail "• Only SSH key login will be allowed"
    print_detail "• A new admin user with sudo access will be created"
    echo ""

    # New username
    if [[ -z "$NEW_USERNAME" ]]; then
        NEW_USERNAME=$(prompt_input "New admin username" "admin")
    fi
    print_success "Admin username: $NEW_USERNAME"

    # New password (for sudo, not SSH)
    if [[ -z "$NEW_PASSWORD" ]]; then
        print_info "Set a password for sudo operations (SSH will use key only)."
        while true; do
            NEW_PASSWORD=$(prompt_password "Password for $NEW_USERNAME")
            local confirm_pw
            confirm_pw=$(prompt_password "Confirm password")
            if [[ "$NEW_PASSWORD" == "$confirm_pw" ]]; then
                break
            fi
            print_warning "Passwords don't match. Try again."
        done
    fi
    print_success "Password configured (will be hashed before use)"

    # CloudPanel
    echo ""
    print_step "CloudPanel Installation"
    print_info "CloudPanel is a free server control panel for PHP, Node.js, Python apps."
    print_info "It provides a web-based admin UI at https://<your-ip>:8443"
    echo ""

    if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
        print_success "CloudPanel installation: ENABLED (from config)"
    else
        if confirm "Install CloudPanel on the new instance?"; then
            INSTALL_CLOUDPANEL=true
            print_success "CloudPanel will be installed"
        else
            INSTALL_CLOUDPANEL=false
            print_info "CloudPanel will NOT be installed"
        fi
    fi

    if [[ "$INSTALL_CLOUDPANEL" == "true" && -z "$CLOUDPANEL_ADMIN_EMAIL" ]]; then
        CLOUDPANEL_ADMIN_EMAIL=$(prompt_input "CloudPanel admin email" "admin@example.com")
    fi

    if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
        print_info "CloudPanel database engine (per cloudpanel.io docs):"
        local db_idx
        db_idx=$(prompt_selection "Choose database engine:" \
            "MySQL 8.4 (Recommended)" \
            "MySQL 8.0" \
            "MariaDB 11.4" \
            "MariaDB 10.11")
        case "$db_idx" in
            0) CLOUDPANEL_DB_ENGINE="MYSQL_8.4" ;;
            1) CLOUDPANEL_DB_ENGINE="MYSQL_8.0" ;;
            2) CLOUDPANEL_DB_ENGINE="MARIADB_11.4" ;;
            3) CLOUDPANEL_DB_ENGINE="MARIADB_10.11" ;;
        esac
        print_success "Database engine: $CLOUDPANEL_DB_ENGINE"
    fi

    # Save config to local file for future runs
    if ! $NON_INTERACTIVE; then
        if confirm "Save these settings to $INSTANCE_CONFIG_FILE for future runs?"; then
            mkdir -p "$(dirname "$INSTANCE_CONFIG_FILE")"
            cat > "$INSTANCE_CONFIG_FILE" <<EOF
# Instance configuration — generated on $(date)
# This file is gitignored. Do not commit to version control.

COMPARTMENT_OCID=${COMPARTMENT_OCID}
INSTANCE_OCID=${INSTANCE_OCID}
SSH_PUBLIC_KEY_PATH=${SSH_PUBLIC_KEY_PATH}
SSH_PRIVATE_KEY_PATH=${SSH_PRIVATE_KEY_PATH}
NEW_USERNAME=${NEW_USERNAME}
NEW_PASSWORD=${NEW_PASSWORD}
INSTALL_CLOUDPANEL=${INSTALL_CLOUDPANEL}
CLOUDPANEL_ADMIN_EMAIL=${CLOUDPANEL_ADMIN_EMAIL}
CLOUDPANEL_DB_ENGINE=${CLOUDPANEL_DB_ENGINE}
OCI_PROFILE=${OCI_PROFILE}
AVAILABILITY_DOMAIN=${AVAILABILITY_DOMAIN}
BOOT_VOLUME_SIZE_GB=${BOOT_VOLUME_SIZE_GB}
ARCH=${ARCH}
EOF
            chmod 600 "$INSTANCE_CONFIG_FILE"
            print_success "Config saved to: $INSTANCE_CONFIG_FILE"
        fi
    fi

    log_quiet "User config: username=$NEW_USERNAME, cloudpanel=$INSTALL_CLOUDPANEL"
}

# ============================================================================
# Step 6: Select Cloud-Init Template
# ============================================================================

step_cloud_init() {
    print_header "Step 6: Cloud-Init Configuration"

    print_info "Cloud-init runs on first boot to configure the new OS."
    print_info "It will set up your admin user, SSH keys, and security settings."
    echo ""

    if [[ -n "$CLOUD_INIT_PATH" && -f "$CLOUD_INIT_PATH" ]]; then
        print_success "Cloud-init template: $CLOUD_INIT_PATH"
    else
        local templates_dir="$REPO_ROOT/oci/templates/cloud-init"
        local tmpl_files=()
        local tmpl_labels=()

        if [[ -d "$templates_dir" ]]; then
            while IFS= read -r f; do
                tmpl_files+=("$f")
                local basename
                basename=$(basename "$f")
                # Read the description from the file header
                local desc
                desc=$(head -3 "$f" | grep -oP '(?<=# ).*' | head -1)
                tmpl_labels+=("$basename — $desc")
            done < <(find "$templates_dir" -name "*.yaml" -o -name "*.yml" | sort)
        fi

        if [[ ${#tmpl_files[@]} -eq 0 ]]; then
            print_warning "No cloud-init templates found in $templates_dir"
            CLOUD_INIT_PATH=""
        else
            if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
                # Default to cloudpanel template
                for i in "${!tmpl_files[@]}"; do
                    if echo "${tmpl_files[$i]}" | grep -qi "cloudpanel"; then
                        CLOUD_INIT_PATH="${tmpl_files[$i]}"
                        print_success "Auto-selected CloudPanel template: $(basename "$CLOUD_INIT_PATH")"
                        break
                    fi
                done
            fi

            if [[ -z "$CLOUD_INIT_PATH" ]]; then
                tmpl_labels+=("No cloud-init (manual setup)")
                local idx
                idx=$(prompt_selection "Choose a cloud-init template:" "${tmpl_labels[@]}")
                if [[ $idx -lt ${#tmpl_files[@]} ]]; then
                    CLOUD_INIT_PATH="${tmpl_files[$idx]}"
                    print_success "Selected: $(basename "$CLOUD_INIT_PATH")"
                else
                    CLOUD_INIT_PATH=""
                    print_info "No cloud-init template selected"
                fi
            fi
        fi
    fi

    # Prepare cloud-init with variable substitution
    if [[ -n "$CLOUD_INIT_PATH" ]]; then
        print_step "Preparing cloud-init with your configuration..."
        local prepared_dir="$REPO_ROOT/oci/local/config"
        mkdir -p "$prepared_dir"
        local prepared_file="$prepared_dir/cloud-init-prepared.yaml"

        # Hash the password
        local password_hash
        password_hash=$(openssl passwd -6 "$NEW_PASSWORD")

        # Read SSH public key
        local ssh_pub_key
        ssh_pub_key=$(cat "$SSH_PUBLIC_KEY_PATH")

        # Variable substitution
        local db_engine="${CLOUDPANEL_DB_ENGINE:-MYSQL_8.4}"
        sed \
            -e "s|__NEW_USERNAME__|${NEW_USERNAME}|g" \
            -e "s|__NEW_PASSWORD_HASH__|${password_hash}|g" \
            -e "s|__SSH_PUBLIC_KEY__|${ssh_pub_key}|g" \
            -e "s|__CLOUDPANEL_DB_ENGINE__|${db_engine}|g" \
            "$CLOUD_INIT_PATH" > "$prepared_file"

        CLOUD_INIT_PREPARED="$prepared_file"
        print_success "Cloud-init prepared: $prepared_file"
        log_quiet "Cloud-init prepared from $CLOUD_INIT_PATH"
    fi
}

# ============================================================================
# Step 7: Confirmation & Summary
# ============================================================================

step_confirm() {
    print_header "Step 7: Review & Confirm"

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

# --- Helper: run OCI command with error capture (not silencing stderr) ---
oci_cmd_checked() {
    local output
    local err_file
    err_file=$(mktemp)
    if output=$(oci --profile "$OCI_PROFILE" "$@" 2>"$err_file"); then
        rm -f "$err_file"
        echo "$output"
        return 0
    else
        local rc=$?
        local err_msg
        err_msg=$(cat "$err_file")
        rm -f "$err_file"
        echo "" >&2
        print_error "OCI CLI command failed:"
        print_detail "  Command: oci --profile $OCI_PROFILE $*"
        if echo "$err_msg" | grep -qi "LimitExceeded\|QuotaExceeded\|Out of host capacity\|TotalStorageExceeded"; then
            print_error "QUOTA EXCEEDED — You've hit a free tier limit."
            print_detail "$err_msg" | head -5
        elif echo "$err_msg" | grep -qi "NotAuthorized\|NotAuthenticated"; then
            print_error "AUTHENTICATION ERROR"
            print_detail "$err_msg" | head -3
        else
            print_detail "$err_msg" | head -5
        fi
        log "OCI CLI error (rc=$rc): $err_msg"
        return $rc
    fi
}

# --- Pre-flight: check free tier storage quota ---
check_storage_quota() {
    print_step "Checking storage quota..."

    local ad
    ad=$(oci_cmd iam availability-domain list 2>/dev/null | jq -r '.data[0].name')

    # Get free tier limit
    local storage_limit
    storage_limit=$(oci_cmd limits value list \
        --compartment-id "$(get_profile_value "$OCI_PROFILE" "tenancy")" \
        --service-name block-storage --all 2>/dev/null \
        | jq -r '.data[] | select(.name == "total-free-storage-gb") | .value' | head -1)

    if [[ -z "$storage_limit" || "$storage_limit" == "null" ]]; then
        print_info "Could not determine storage quota. Proceeding anyway."
        return 0
    fi

    # Calculate current usage: boot volumes + backups
    local tenancy_ocid
    tenancy_ocid=$(get_profile_value "$OCI_PROFILE" "tenancy")

    local bv_usage=0
    local bv_list
    bv_list=$(oci_cmd bv boot-volume list \
        --compartment-id "$tenancy_ocid" \
        --availability-domain "$ad" 2>/dev/null || echo '{"data":[]}')
    bv_usage=$(echo "$bv_list" | jq '[.data[] | .["size-in-gbs"] // 0] | add // 0')

    local backup_usage=0
    local backup_list
    backup_list=$(oci_cmd bv boot-volume-backup list \
        --compartment-id "$tenancy_ocid" 2>/dev/null || echo '{"data":[]}')
    backup_usage=$(echo "$backup_list" | jq '[.data[] | .["size-in-gbs"] // 0] | add // 0')

    local vol_usage=0
    local vol_list
    vol_list=$(oci_cmd bv volume list \
        --compartment-id "$tenancy_ocid" \
        --availability-domain "$ad" 2>/dev/null || echo '{"data":[]}')
    vol_usage=$(echo "$vol_list" | jq '[.data[] | .["size-in-gbs"] // 0] | add // 0')

    local total_used=$(( bv_usage + backup_usage + vol_usage ))
    local available=$(( storage_limit - total_used ))

    echo ""
    print_info "┌─── Block Storage Quota ─────────────────────────────────┐"
    print_info "│ Free tier limit:     ${storage_limit} GB"
    print_info "│ Boot volumes:        ${bv_usage} GB"
    print_info "│ Boot vol backups:    ${backup_usage} GB"
    print_info "│ Block volumes:       ${vol_usage} GB"
    print_info "│ Total used:          ${total_used} GB"
    print_info "│ Available:           ${available} GB"
    print_info "│ Needed for new BV:   ${BOOT_VOLUME_SIZE_GB} GB"
    print_info "└─────────────────────────────────────────────────────────┘"
    echo ""
    log "Storage quota: limit=${storage_limit}GB, used=${total_used}GB, available=${available}GB, needed=${BOOT_VOLUME_SIZE_GB}GB"

    # Check if we have enough space
    if (( available >= BOOT_VOLUME_SIZE_GB )); then
        print_success "Sufficient storage available."
        return 0
    fi

    # Not enough space — help the user
    # With the replace-boot-volume API, setting preserve=false avoids needing
    # extra space because OCI replaces in-place (old BV deleted automatically).
    print_warning "NOT ENOUGH STORAGE for a new ${BOOT_VOLUME_SIZE_GB} GB boot volume."
    print_info "You need to free up $(( BOOT_VOLUME_SIZE_GB - available )) GB."
    echo ""

    # Offer strategies
    local strategies=()
    local strategy_actions=()

    # Strategy 1: Don't preserve old boot volume (OCI deletes it in the replace)
    strategies+=("Don't preserve old boot volume (OCI replaces in-place — no rollback)")
    strategy_actions+=("delete_old_bv")

    # Strategy 2: Delete existing backups
    local backup_count
    backup_count=$(echo "$backup_list" | jq '.data | length')
    if (( backup_count > 0 )); then
        strategies+=("Delete existing backup(s) (frees ${backup_usage} GB from ${backup_count} backup(s))")
        strategy_actions+=("delete_backups")
    fi

    # Strategy 3: Abort
    strategies+=("Abort — I'll free space manually")
    strategy_actions+=("abort")

    print_info "Choose a strategy to free storage:"
    echo ""

    local freed=0
    while (( available + freed < BOOT_VOLUME_SIZE_GB )); do
        local idx
        idx=$(prompt_selection "Free up storage (still need $(( BOOT_VOLUME_SIZE_GB - available - freed )) GB more):" "${strategies[@]}")
        local action="${strategy_actions[$idx]}"

        case "$action" in
            delete_backups)
                print_info "Existing backups:"
                local backup_names=()
                local backup_ids=()
                local backup_sizes=()
                while IFS= read -r line; do
                    local bname bsize bid
                    bname=$(echo "$line" | jq -r '.["display-name"]')
                    bsize=$(echo "$line" | jq -r '.["size-in-gbs"]')
                    bid=$(echo "$line" | jq -r '.id')
                    backup_names+=("$bname (${bsize} GB)")
                    backup_ids+=("$bid")
                    backup_sizes+=("$bsize")
                done < <(echo "$backup_list" | jq -c '.data[]')

                backup_names+=("Cancel — don't delete any")

                local bidx
                bidx=$(prompt_selection "Which backup to delete?" "${backup_names[@]}")
                if (( bidx < ${#backup_ids[@]} )); then
                    local del_id="${backup_ids[$bidx]}"
                    local del_size="${backup_sizes[$bidx]}"
                    if confirm "Delete backup '${backup_names[$bidx]}'? This cannot be undone."; then
                        print_info "Deleting backup..."
                        oci_cmd bv boot-volume-backup delete \
                            --boot-volume-backup-id "$del_id" --force 2>/dev/null
                        freed=$((freed + del_size))
                        print_success "Deleted. Freed ${del_size} GB."
                        log "Deleted backup $del_id (${del_size} GB)"
                    fi
                fi
                ;;
            delete_old_bv)
                DELETE_OLD_BV=true
                freed=$((freed + BOOT_VOLUME_SIZE_GB))
                print_success "Will NOT preserve old boot volume — OCI replaces in-place, frees ${BOOT_VOLUME_SIZE_GB} GB"
                print_warning "No rollback possible after replacement."
                # Remove this option
                local new_strategies=()
                local new_actions=()
                for i in "${!strategy_actions[@]}"; do
                    if [[ "${strategy_actions[$i]}" != "delete_old_bv" ]]; then
                        new_strategies+=("${strategies[$i]}")
                        new_actions+=("${strategy_actions[$i]}")
                    fi
                done
                strategies=("${new_strategies[@]}")
                strategy_actions=("${new_actions[@]}")
                ;;
            abort)
                print_info "Quota management tips:"
                print_detail "• Delete unused boot volumes: oci bv boot-volume delete --boot-volume-id <OCID>"
                print_detail "• Delete backups: oci bv boot-volume-backup delete --boot-volume-backup-id <OCID>"
                print_detail "• Check usage: oci bv boot-volume list --compartment-id <tenancy>"
                die "Not enough storage. Free up space and re-run."
                ;;
        esac
    done

    echo ""
    print_success "Storage strategy set. Proceeding with $(( available + freed )) GB available."
    log "Storage freed: ${freed}GB (skip_backup=$SKIP_BACKUP, delete_old_bv=$DELETE_OLD_BV)"
}

wait_for_state() {
    local resource_type="$1"  # instance, boot-volume, etc.
    local resource_id="$2"
    local target_state="$3"
    local max_wait="${4:-600}"  # default 10 minutes
    local interval=15
    local elapsed=0

    print_info "Waiting for $resource_type to reach state: $target_state ..."

    while (( elapsed < max_wait )); do
        local current_state
        case "$resource_type" in
            instance)
                current_state=$(oci_cmd compute instance get \
                    --instance-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
            boot-volume)
                current_state=$(oci_cmd bv boot-volume get \
                    --boot-volume-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
            boot-volume-attachment)
                current_state=$(oci_cmd compute boot-volume-attachment get \
                    --boot-volume-attachment-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
            boot-volume-backup)
                current_state=$(oci_cmd bv boot-volume-backup get \
                    --boot-volume-backup-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
        esac

        if [[ "$current_state" == "$target_state" ]]; then
            print_success "$resource_type reached state: $target_state (${elapsed}s)"
            return 0
        fi

        printf "\r    State: %-20s Elapsed: %ds / %ds" "$current_state" "$elapsed" "$max_wait"
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    echo ""
    die "Timeout waiting for $resource_type to reach $target_state after ${max_wait}s"
}

step_execute() {
    print_header "Step 8: Executing Reprovisioning"
    log "Starting reprovisioning workflow..."

    # --- 8.0: Pre-flight quota check ---
    check_storage_quota

    # --- 8.0b: Detect recovery from previous failed run ---
    print_step "Checking instance state..."
    local instance_state
    instance_state=$(oci_cmd compute instance get \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '.data["lifecycle-state"]')

    local current_attach_state=""
    current_attach_state=$(oci_cmd compute boot-volume-attachment list \
        --compartment-id "$COMPARTMENT_OCID" \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | length')

    if [[ "$instance_state" == "STOPPED" && "$current_attach_state" == "0" ]]; then
        print_warning "Recovery detected: Instance is STOPPED with NO boot volume attached."
        print_info "This looks like a previous run failed after detaching the boot volume."
        print_info "The replace-boot-volume API requires an attached boot volume."
        print_info "Re-attaching old boot volume first so the replace command can proceed."
        echo ""

        local recovery_action
        recovery_action=$(prompt_selection "How would you like to proceed?" \
            "Re-attach old BV and continue with replacement" \
            "Re-attach old BV and abort (restore previous state)")

        if [[ "$recovery_action" == "2" ]]; then
            print_info "Re-attaching old boot volume..."
            oci_cmd_checked compute boot-volume-attachment attach \
                --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" \
                --instance-id "$INSTANCE_OCID" \
                --display-name "recovery-reattach-${TIMESTAMP}" >/dev/null || true
            sleep 15
            print_success "Old boot volume re-attached. Starting instance..."
            oci_cmd compute instance action \
                --instance-id "$INSTANCE_OCID" \
                --action START 2>/dev/null >/dev/null
            wait_for_state "instance" "$INSTANCE_OCID" "RUNNING"
            print_success "Instance restored to previous state."
            exit 0
        fi

        # Re-attach old BV so the replace API works
        print_step "8.1 Re-attaching old boot volume for replacement..."
        oci_cmd_checked compute boot-volume-attachment attach \
            --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" \
            --instance-id "$INSTANCE_OCID" \
            --display-name "pre-replace-reattach-${TIMESTAMP}" >/dev/null || true
        # Wait for attachment
        sleep 15
        local reattach_state
        reattach_state=$(oci_cmd compute boot-volume-attachment list \
            --compartment-id "$COMPARTMENT_OCID" \
            --availability-domain "$AVAILABILITY_DOMAIN" \
            --instance-id "$INSTANCE_OCID" 2>/dev/null \
            | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | length')
        if [[ "$reattach_state" == "0" ]]; then
            print_info "Waiting for boot volume to attach..."
            sleep 30
        fi
        print_success "Old boot volume re-attached. Ready for replacement."
    fi

    # --- 8.2: Prepare metadata ---
    print_step "8.2 Preparing instance metadata..."
    local ssh_pub_key
    ssh_pub_key=$(cat "$SSH_PUBLIC_KEY_PATH")

    local metadata_json
    if [[ -n "${CLOUD_INIT_PREPARED:-}" && -f "${CLOUD_INIT_PREPARED}" ]]; then
        local user_data_b64
        user_data_b64=$(base64 -w 0 "$CLOUD_INIT_PREPARED")
        metadata_json=$(jq -n \
            --arg ssh "$ssh_pub_key" \
            --arg ud "$user_data_b64" \
            '{"ssh_authorized_keys": $ssh, "user_data": $ud}')
    else
        metadata_json=$(jq -n \
            --arg ssh "$ssh_pub_key" \
            '{"ssh_authorized_keys": $ssh}')
    fi
    print_success "Metadata prepared (SSH key + cloud-init)"

    # --- 8.3: Stop instance if running ---
    if [[ "$instance_state" == "RUNNING" ]]; then
        print_step "8.3 Stopping instance for boot volume replacement..."
        oci_cmd compute instance action \
            --instance-id "$INSTANCE_OCID" \
            --action SOFTSTOP 2>/dev/null >/dev/null
        log "Stop command sent"
        wait_for_state "instance" "$INSTANCE_OCID" "STOPPED"
    else
        print_step "8.3 Instance already stopped — skipping"
    fi

    # --- 8.4: Replace boot volume via image (single API call) ---
    print_step "8.4 Replacing boot volume with new Ubuntu image..."
    print_info "This is an atomic operation: OCI will create a new boot volume from the image,"
    print_info "detach the old one, attach the new one, and start the instance."

    local preserve_old_bv="true"
    if $DELETE_OLD_BV; then
        preserve_old_bv="false"
        print_info "Old boot volume will NOT be preserved (quota strategy)."
    else
        print_info "Old boot volume will be preserved for rollback."
    fi

    local replace_result
    replace_result=$(oci_cmd_checked compute instance \
        update-instance-update-instance-source-via-image-details \
        --instance-id "$INSTANCE_OCID" \
        --source-details-image-id "$IMAGE_OCID" \
        --source-details-boot-volume-size-in-gbs "$BOOT_VOLUME_SIZE_GB" \
        --source-details-is-preserve-boot-volume-enabled "$preserve_old_bv" \
        --metadata "$metadata_json" \
        --force) || true

    if [[ -z "$replace_result" ]]; then
        print_error "Boot volume replacement failed."
        print_info "Your instance should still have its old boot volume attached."
        print_info "Check the OCI Console for details."
        print_detail "  Instance: $INSTANCE_OCID"
        die "Replace boot volume failed. Check OCI Console and try again."
    fi

    log "Replace boot volume command accepted."
    print_success "Replace boot volume initiated. Waiting for completion..."

    # Wait for the instance to finish the replace cycle
    # The instance goes: STOPPED → (internal provisioning) → STOPPED
    # We poll the boot volume attachment to detect when a NEW BV is attached
    local wait_elapsed=0
    local wait_max=1200
    local old_bv="$CURRENT_BOOT_VOLUME_ID"
    while (( wait_elapsed < wait_max )); do
        local current_bv
        current_bv=$(oci_cmd compute boot-volume-attachment list \
            --compartment-id "$COMPARTMENT_OCID" \
            --availability-domain "$AVAILABILITY_DOMAIN" \
            --instance-id "$INSTANCE_OCID" 2>/dev/null \
            | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | .[0]["boot-volume-id"] // "none"')

        if [[ "$current_bv" != "none" && "$current_bv" != "$old_bv" && "$current_bv" != "null" ]]; then
            new_bv_id="$current_bv"
            break
        fi

        printf "\r    Replacing boot volume... Elapsed: %ds / %ds" "$wait_elapsed" "$wait_max"
        sleep 15
        wait_elapsed=$((wait_elapsed + 15))
    done
    echo ""

    if [[ -z "$new_bv_id" || "$new_bv_id" == "none" ]]; then
        die "Timeout waiting for boot volume replacement to complete after ${wait_max}s"
    fi

    local new_state
    new_state=$(oci_cmd compute instance get \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '.data["lifecycle-state"]')

    log "Replace boot volume complete. Instance state: $new_state, new BV: $new_bv_id"
    print_success "Boot volume replaced! New BV: $new_bv_id"
    print_detail "Instance state: $new_state"

    # --- 8.5: Start instance if not already running ---
    if [[ "$new_state" != "RUNNING" ]]; then
        print_step "8.5 Starting instance..."
        oci_cmd compute instance action \
            --instance-id "$INSTANCE_OCID" \
            --action START 2>/dev/null >/dev/null || true
        log "Start command sent"
        wait_for_state "instance" "$INSTANCE_OCID" "RUNNING"
    else
        print_step "8.5 Instance already running"
    fi

    # --- 8.6: Verify SSH connectivity ---
    print_step "8.6 Verifying SSH connectivity..."
    print_info "Waiting 60 seconds for cloud-init to start..."
    sleep 60

    # Get public IP
    local vnic_attachments
    vnic_attachments=$(oci_cmd compute vnic-attachment list \
        --compartment-id "$COMPARTMENT_OCID" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null)
    local vnic_id
    vnic_id=$(echo "$vnic_attachments" | jq -r '.data[0]["vnic-id"]')
    local public_ip
    public_ip=$(oci_cmd network vnic get --vnic-id "$vnic_id" 2>/dev/null \
        | jq -r '.data["public-ip"] // empty')

    if [[ -n "$public_ip" ]]; then
        local ssh_user="$NEW_USERNAME"
        local ssh_key_flag=""
        [[ -n "$SSH_PRIVATE_KEY_PATH" && -f "$SSH_PRIVATE_KEY_PATH" ]] && \
            ssh_key_flag="-i $SSH_PRIVATE_KEY_PATH"

        local retries=5
        local connected=false
        for (( i=1; i<=retries; i++ )); do
            print_info "SSH attempt $i/$retries to ${ssh_user}@${public_ip}..."
            if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
                $ssh_key_flag "${ssh_user}@${public_ip}" \
                "echo 'SSH connection successful'" 2>/dev/null; then
                connected=true
                break
            fi
            sleep 15
        done

        if $connected; then
            print_success "SSH connection verified! Instance is ready."
        else
            print_warning "SSH connection could not be verified after $retries attempts."
            print_info "The instance may still be running cloud-init. Try manually:"
            print_detail "ssh $ssh_key_flag ${ssh_user}@${public_ip}"
        fi
    else
        print_warning "No public IP found. SSH verification skipped."
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
# Main
# ============================================================================

main() {
    parse_args "$@"
    init
    step_verify_oci_config
    step_select_instance
    step_select_image
    step_ssh_key
    step_user_config
    step_cloud_init
    step_confirm
    step_execute
    step_summary
}

main "$@"
