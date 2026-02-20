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

# --- Constants & Defaults ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_OCI_CONFIG="$REPO_ROOT/oci/local/config/oci-config"
DEFAULT_INSTANCE_CONFIG="$REPO_ROOT/oci/local/config/instance-config"
DEFAULT_SSH_DIR="$REPO_ROOT/oci/local/ssh"
DEFAULT_LOG_DIR="$REPO_ROOT/oci/local/logs"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
LOG_FILE=""

# --- Script State ---
DRY_RUN=false
NON_INTERACTIVE=false
OCI_CONFIG=""
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
BOOT_VOLUME_SIZE_GB=""
AVAILABILITY_DOMAIN=""

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
    read -r -p "$(echo -e "${BOLD}  ? ${prompt} [y/N]: ${NC}")" response
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
        read -r -p "$(echo -e "${BOLD}  ? ${prompt} [${default}]: ${NC}")" result
        echo "${result:-$default}"
    else
        read -r -p "$(echo -e "${BOLD}  ? ${prompt}: ${NC}")" result
        echo "$result"
    fi
}

prompt_password() {
    local prompt="$1"
    local result
    read -r -s -p "$(echo -e "${BOLD}  ? ${prompt}: ${NC}")" result
    echo ""
    echo "$result"
}

prompt_selection() {
    local prompt="$1"
    shift
    local options=("$@")
    echo ""
    echo -e "${BOLD}  ${prompt}${NC}"
    echo ""
    for i in "${!options[@]}"; do
        printf "    ${CYAN}%3d)${NC} %s\n" "$((i + 1))" "${options[$i]}"
    done
    echo ""
    local selection
    while true; do
        read -r -p "$(echo -e "${BOLD}  Enter number (1-${#options[@]}): ${NC}")" selection
        if [[ "$selection" =~ ^[0-9]+$ ]] && (( selection >= 1 && selection <= ${#options[@]} )); then
            echo "$((selection - 1))"
            return
        fi
        print_warning "Invalid selection. Please enter a number between 1 and ${#options[@]}."
    done
}

oci_cmd() {
    oci --config-file "$OCI_CONFIG" "$@"
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
    --config <path>           OCI config file (default: oci/local/config/oci-config)
    --instance-config <path>  Instance config file (default: oci/local/config/instance-config)
    --instance-id <ocid>      Instance OCID (skip selection)
    --image-id <ocid>         Ubuntu image OCID (skip selection)
    --ssh-key <path>          SSH public key file path
    --cloud-init <path>       Cloud-init YAML file path
    --arch <x86|arm>          Force architecture (auto-detected if not set)
    --dry-run                 Preview operations without executing
    --non-interactive         Skip prompts (requires all IDs via flags/config)
    --help                    Show this help message

INTERACTIVE MODE (default):
    Run without flags for a guided, step-by-step experience.
    The script explains each step and lets you make choices.

EXAMPLES:
    # Interactive (recommended for first use)
    ./reprovision-vm.sh

    # Dry run
    ./reprovision-vm.sh --dry-run

    # Fully parameterized
    ./reprovision-vm.sh \
      --instance-id ocid1.instance.oc1... \
      --image-id ocid1.image.oc1... \
      --ssh-key oci/local/ssh/my_key.pub \
      --cloud-init oci/templates/cloud-init/cloudpanel-ubuntu.yaml

PREREQUISITES:
    - OCI CLI installed:  oci --version
    - jq installed:       jq --version
    - OCI config file:    oci/local/config/oci-config
      (see: oci/docs/setup-api-key.md)

FILES:
    oci/local/config/oci-config          OCI API configuration
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
            --config) OCI_CONFIG="$2"; shift 2 ;;
            --instance-config) INSTANCE_CONFIG_FILE="$2"; shift 2 ;;
            --instance-id) INSTANCE_OCID="$2"; shift 2 ;;
            --image-id) IMAGE_OCID="$2"; shift 2 ;;
            --ssh-key) SSH_PUBLIC_KEY_PATH="$2"; shift 2 ;;
            --cloud-init) CLOUD_INIT_PATH="$2"; shift 2 ;;
            --arch) ARCH="$2"; shift 2 ;;
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
    [[ -z "$OCI_CONFIG" ]] && OCI_CONFIG="$DEFAULT_OCI_CONFIG"
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
                COMPARTMENT_OCID)     [[ -z "$COMPARTMENT_OCID" ]] && COMPARTMENT_OCID="$value" ;;
                INSTANCE_OCID)        [[ -z "$INSTANCE_OCID" ]] && INSTANCE_OCID="$value" ;;
                SSH_PUBLIC_KEY_PATH)   [[ -z "$SSH_PUBLIC_KEY_PATH" ]] && SSH_PUBLIC_KEY_PATH="$value" ;;
                SSH_PRIVATE_KEY_PATH)  [[ -z "$SSH_PRIVATE_KEY_PATH" ]] && SSH_PRIVATE_KEY_PATH="$value" ;;
                NEW_USERNAME)          [[ -z "$NEW_USERNAME" ]] && NEW_USERNAME="$value" ;;
                NEW_PASSWORD)          [[ -z "$NEW_PASSWORD" ]] && NEW_PASSWORD="$value" ;;
                INSTALL_CLOUDPANEL)    INSTALL_CLOUDPANEL="$value" ;;
                CLOUDPANEL_ADMIN_EMAIL) CLOUDPANEL_ADMIN_EMAIL="$value" ;;
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
# Step 1: Verify OCI API Configuration
# ============================================================================

# --- Auth Method A: Browser-based bootstrap (easiest) ---
setup_oci_bootstrap() {
    print_step "Browser-Based Setup (oci setup bootstrap)"
    echo ""
    print_info "This will open a browser window for you to log into OCI."
    print_info "The CLI will automatically:"
    print_detail "• Generate an API signing key pair"
    print_detail "• Upload the public key to your OCI account"
    print_detail "• Create the config file"
    echo ""
    print_info "Requirements:"
    print_detail "• A web browser accessible from this machine"
    print_detail "• Port 8181 must be available (used for the auth callback)"
    echo ""

    if ! confirm "Ready to open the browser login?"; then
        return 1
    fi

    mkdir -p "$REPO_ROOT/oci/local/config"

    # Run oci setup bootstrap with our config location
    if oci setup bootstrap --config-location "$OCI_CONFIG"; then
        print_success "OCI bootstrap complete! Config saved to: $OCI_CONFIG"
        log_quiet "OCI config created via bootstrap at $OCI_CONFIG"
        return 0
    else
        print_error "Bootstrap failed. You can try another method."
        return 1
    fi
}

# --- Auth Method B: Interactive CLI setup (oci setup config) ---
setup_oci_interactive_cli() {
    print_step "Interactive CLI Setup (oci setup config)"
    echo ""
    print_info "This walks you through creating a config file step by step."
    print_info "You'll need to provide your OCIDs — here's where to find them:"
    echo ""
    echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}  │  HOW TO FIND YOUR OCI IDENTIFIERS                              │${NC}"
    echo -e "${BOLD}  ├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${BOLD}  │                                                                 │${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}User OCID:${NC}                                                    ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    1. Log in to ${YELLOW}https://cloud.oracle.com${NC}                        ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    2. Click your ${CYAN}Profile icon${NC} (top-right corner)                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    3. Click ${CYAN}\"My Profile\"${NC} (or \"User Settings\")                    ${BOLD}│${NC}"
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

    mkdir -p "$REPO_ROOT/oci/local/config"
    mkdir -p "$REPO_ROOT/oci/local/api-keys"

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
    print_detail "Find it: Profile icon → My Profile → Copy OCID"
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
    print_detail "                eu-frankfurt-1, ap-tokyo-1, uk-london-1"
    local region
    region=$(prompt_input "Enter your region" "us-ashburn-1")
    print_success "Region: $region"
    echo ""

    # API Key
    print_info "${CYAN}Step 4 of 4: API Signing Key${NC}"
    print_detail "OCI uses RSA key pairs for API authentication."
    print_detail "We need a private key on this machine and the matching"
    print_detail "public key uploaded to your OCI user profile."
    echo ""

    local key_path="$REPO_ROOT/oci/local/api-keys/oci_api_key.pem"
    local pub_path="$REPO_ROOT/oci/local/api-keys/oci_api_key_public.pem"

    local key_action
    if [[ -f "$key_path" ]]; then
        print_info "An API key already exists at: $key_path"
        key_action=$(prompt_selection "What would you like to do?" \
            "Use the existing key" \
            "Generate a new key (overwrites existing)" \
            "Use OCI CLI to generate (oci setup keys)")
    else
        key_action=$(prompt_selection "How would you like to set up the API key?" \
            "Generate a new key pair automatically (Recommended)" \
            "Use OCI CLI to generate (oci setup keys)" \
            "I already have a key — let me provide the path")
    fi

    local fingerprint=""

    case "$key_action" in
        0)
            # Use existing or generate new
            if [[ ! -f "$key_path" ]] || confirm "Generate a new key pair?"; then
                print_step "Generating 2048-bit RSA key pair..."
                openssl genrsa -out "$key_path" 2048 2>/dev/null
                chmod 600 "$key_path"
                openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                print_success "Key pair generated:"
                print_detail "Private: $key_path"
                print_detail "Public:  $pub_path"
            fi
            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            ;;
        1)
            # Use oci setup keys
            print_step "Running: oci setup keys"
            oci setup keys \
                --output-dir "$REPO_ROOT/oci/local/api-keys" \
                --key-name oci_api_key \
                --overwrite
            # oci setup keys produces oci_api_key.pem and oci_api_key_public.pem
            key_path="$REPO_ROOT/oci/local/api-keys/oci_api_key.pem"
            pub_path="$REPO_ROOT/oci/local/api-keys/oci_api_key_public.pem"
            if [[ ! -f "$key_path" ]]; then
                # oci setup keys uses _public suffix on the public key
                pub_path="$REPO_ROOT/oci/local/api-keys/oci_api_key_public.pem"
            fi
            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            print_success "Keys generated via OCI CLI"
            ;;
        2)
            # User provides path
            key_path=$(prompt_input "Path to your private key (.pem)")
            while [[ ! -f "$key_path" ]]; do
                print_warning "File not found: $key_path"
                key_path=$(prompt_input "Path to your private key (.pem)")
            done
            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            pub_path="${key_path%.pem}_public.pem"
            if [[ ! -f "$pub_path" ]]; then
                openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
            fi
            print_success "Using existing key: $key_path"
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
    echo -e "${BOLD}  │${NC}  2. Click ${CYAN}Profile icon${NC} (top-right) → ${CYAN}\"My Profile\"${NC}               ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  3. Scroll to ${CYAN}\"API Keys\"${NC} section (left sidebar or scroll)       ${BOLD}│${NC}"
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
        read -r -p "$(echo -e "${BOLD}  Press Enter after you've uploaded the key to OCI Console...${NC}")"
    fi

    # Write config file
    cat > "$OCI_CONFIG" <<EOF
[DEFAULT]
user=${user_ocid}
fingerprint=${fingerprint}
tenancy=${tenancy_ocid}
region=${region}
key_file=${key_path}
EOF
    chmod 600 "$OCI_CONFIG"
    print_success "OCI config saved to: $OCI_CONFIG"
    log_quiet "OCI config created at $OCI_CONFIG (interactive CLI method)"
}

# --- Auth Method C: Use existing config ---
setup_oci_existing_config() {
    print_step "Use Existing OCI Configuration"
    echo ""

    # Check common locations
    local found_configs=()
    local found_labels=()

    if [[ -f "$HOME/.oci/config" ]]; then
        found_configs+=("$HOME/.oci/config")
        found_labels+=("~/.oci/config (standard OCI CLI location)")
    fi

    # Check for any profile configs
    if [[ -d "$HOME/.oci" ]]; then
        while IFS= read -r f; do
            if [[ "$f" != "$HOME/.oci/config" && -f "$f" ]]; then
                found_configs+=("$f")
                found_labels+=("$f")
            fi
        done < <(find "$HOME/.oci" -name "config*" -type f 2>/dev/null)
    fi

    found_labels+=("Enter a custom path")

    if [[ ${#found_configs[@]} -gt 0 ]]; then
        print_info "Found existing OCI configurations:"
        local idx
        idx=$(prompt_selection "Choose a config to use:" "${found_labels[@]}")

        if [[ $idx -lt ${#found_configs[@]} ]]; then
            local src="${found_configs[$idx]}"
            mkdir -p "$(dirname "$OCI_CONFIG")"
            cp "$src" "$OCI_CONFIG"
            chmod 600 "$OCI_CONFIG"
            print_success "Copied $src → $OCI_CONFIG"
            # Verify key_file path is accessible
            local key_file
            key_file=$(grep '^key_file=' "$OCI_CONFIG" | cut -d= -f2 | xargs)
            if [[ -n "$key_file" && ! -f "$key_file" ]]; then
                # Try expanding ~ or relative paths
                local expanded="${key_file/#\~/$HOME}"
                if [[ -f "$expanded" ]]; then
                    sed -i "s|^key_file=.*|key_file=${expanded}|" "$OCI_CONFIG"
                    print_info "Updated key_file path to: $expanded"
                else
                    print_warning "API key not found at: $key_file"
                    print_info "You may need to update the key_file path in: $OCI_CONFIG"
                fi
            fi
            return 0
        fi
    fi

    # Custom path
    local custom_path
    custom_path=$(prompt_input "Enter path to your OCI config file")
    while [[ ! -f "$custom_path" ]]; do
        print_warning "File not found: $custom_path"
        custom_path=$(prompt_input "Enter path to your OCI config file")
    done
    mkdir -p "$(dirname "$OCI_CONFIG")"
    cp "$custom_path" "$OCI_CONFIG"
    chmod 600 "$OCI_CONFIG"
    print_success "Copied $custom_path → $OCI_CONFIG"
}

# --- Main auth step ---
step_verify_oci_config() {
    print_header "Step 1: OCI API Configuration"

    print_info "To manage OCI resources, the CLI needs API credentials."
    print_info "This script stores the config in: ${CYAN}${OCI_CONFIG}${NC}"
    print_info "(This file is gitignored — your credentials stay local.)"
    echo ""

    if [[ -f "$OCI_CONFIG" ]]; then
        print_success "OCI config found at: $OCI_CONFIG"
        print_info "Testing connectivity..."
        echo ""
        if oci_cmd iam region list --output table 2>/dev/null | head -5; then
            print_success "OCI API connection successful!"
            log_quiet "OCI API connection verified (existing config)"
        else
            print_warning "Connection failed with existing config."
            if confirm "Re-configure OCI API access?"; then
                rm -f "$OCI_CONFIG"
                # Fall through to setup below
            else
                die "Cannot continue without working OCI API access."
            fi
        fi
    fi

    if [[ ! -f "$OCI_CONFIG" ]]; then
        print_info "No OCI config found. Let's set one up."
        print_info "Choose how you'd like to authenticate with OCI:"
        echo ""

        local method
        method=$(prompt_selection "Choose an authentication method:" \
            "Browser login (easiest — opens browser, auto-configures everything)" \
            "Interactive CLI setup (step-by-step — paste OCIDs, generate/provide key)" \
            "Use existing OCI config (copy from ~/.oci/config or custom path)")

        echo ""
        local setup_ok=false
        case "$method" in
            0) setup_oci_bootstrap && setup_ok=true ;;
            1) setup_oci_interactive_cli && setup_ok=true ;;
            2) setup_oci_existing_config && setup_ok=true ;;
        esac

        if ! $setup_ok; then
            die "OCI configuration was not completed."
        fi

        # Test connectivity
        echo ""
        print_step "Testing OCI API connectivity..."
        if oci_cmd iam region list --output table 2>/dev/null | head -5; then
            print_success "OCI API connection successful!"
            log_quiet "OCI API connection verified"
        else
            print_error "Connection failed. Common issues:"
            print_detail "• API key not uploaded to OCI Console yet"
            print_detail "• Fingerprint mismatch (re-generate and re-upload key)"
            print_detail "• User/Tenancy OCID typo (verify in OCI Console)"
            print_detail "• Region incorrect (check OCI Console top bar)"
            echo ""
            print_info "Your config file: $OCI_CONFIG"
            print_info "Edit it with: nano $OCI_CONFIG"
            die "OCI API connection failed. Fix the config and re-run."
        fi
    fi

    # Get tenancy for later use
    local tenancy_ocid
    tenancy_ocid=$(grep '^tenancy=' "$OCI_CONFIG" | cut -d= -f2 | xargs)

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

    CURRENT_BOOT_VOLUME_ID=$(echo "$boot_volumes" | jq -r '.data[0]["boot-volume-id"]')
    CURRENT_BOOT_ATTACH_ID=$(echo "$boot_volumes" | jq -r '.data[0].id')
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

        if [[ ${#pub_keys[@]} -eq 0 && ${#home_keys[@]} -eq 0 ]]; then
            print_warning "No SSH keys found in $DEFAULT_SSH_DIR or ~/.ssh/"
            echo ""
            print_info "Let's generate a new SSH key pair for your OCI instances."
            print_info "The key will be stored in $DEFAULT_SSH_DIR (gitignored)."
            echo ""

            local key_name
            key_name=$(prompt_input "SSH key name" "oci_instance_key")
            local key_path="$DEFAULT_SSH_DIR/${key_name}"

            ssh-keygen -t ed25519 -f "$key_path" -N "" -C "oci-instance-$(date +%Y%m%d)"
            print_success "SSH key generated:"
            print_detail "Private: $key_path"
            print_detail "Public:  ${key_path}.pub"
            SSH_PUBLIC_KEY_PATH="${key_path}.pub"
            SSH_PRIVATE_KEY_PATH="$key_path"
        else
            # Combine and let user choose
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

            local idx
            idx=$(prompt_selection "Choose an SSH public key:" "${all_labels[@]}")

            if [[ $idx -eq ${#all_keys[@]} ]]; then
                # Generate new key
                local key_name
                key_name=$(prompt_input "SSH key name" "oci_instance_key")
                local key_path="$DEFAULT_SSH_DIR/${key_name}"
                ssh-keygen -t ed25519 -f "$key_path" -N "" -C "oci-instance-$(date +%Y%m%d)"
                print_success "SSH key generated: ${key_path}.pub"
                SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                SSH_PRIVATE_KEY_PATH="$key_path"
            else
                SSH_PUBLIC_KEY_PATH="${all_keys[$idx]}"
                SSH_PRIVATE_KEY_PATH="${SSH_PUBLIC_KEY_PATH%.pub}"

                # If key is from ~/.ssh, offer to copy to repo local
                if [[ "$SSH_PUBLIC_KEY_PATH" == "$HOME/.ssh/"* ]]; then
                    if confirm "Copy this key to $DEFAULT_SSH_DIR for this project?"; then
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
        sed \
            -e "s|__NEW_USERNAME__|${NEW_USERNAME}|g" \
            -e "s|__NEW_PASSWORD_HASH__|${password_hash}|g" \
            -e "s|__SSH_PUBLIC_KEY__|${ssh_pub_key}|g" \
            -e "s|__CLOUDPANEL_DB_PASS__|$(openssl rand -base64 24)|g" \
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
    print_detail "│ 1. Stop instance                                      │"
    print_detail "│ 2. Snapshot current boot volume (safety net)           │"
    print_detail "│ 3. Detach current boot volume                         │"
    print_detail "│ 4. Create new boot volume from Ubuntu image           │"
    print_detail "│ 5. Attach new boot volume to instance                 │"
    print_detail "│ 6. Start instance with cloud-init                     │"
    print_detail "│ 7. Verify SSH connectivity                            │"
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

    # --- 8.1: Stop the instance ---
    print_step "8.1 Stopping instance..."
    local instance_state
    instance_state=$(oci_cmd compute instance get \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '.data["lifecycle-state"]')

    if [[ "$instance_state" == "RUNNING" ]]; then
        oci_cmd compute instance action \
            --instance-id "$INSTANCE_OCID" \
            --action SOFTSTOP 2>/dev/null
        log "Stop command sent"
        wait_for_state "instance" "$INSTANCE_OCID" "STOPPED"
    elif [[ "$instance_state" == "STOPPED" ]]; then
        print_info "Instance is already stopped"
    else
        die "Instance is in unexpected state: $instance_state"
    fi

    # --- 8.2: Snapshot current boot volume ---
    print_step "8.2 Creating snapshot of current boot volume (safety net)..."
    local backup_name="reprovision-backup-${TIMESTAMP}"
    local backup_result
    backup_result=$(oci_cmd bv boot-volume-backup create \
        --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" \
        --display-name "$backup_name" \
        --type INCREMENTAL 2>/dev/null)

    local backup_id
    backup_id=$(echo "$backup_result" | jq -r '.data.id')
    log "Boot volume backup created: $backup_id ($backup_name)"
    print_success "Backup: $backup_id"
    print_info "This backup is your rollback safety net. Do NOT delete it until you verify the new OS."

    # Wait for backup to complete (can take a while, but we don't need to wait fully)
    print_info "Backup is processing in background. Continuing with detach..."

    # --- 8.3: Detach current boot volume ---
    print_step "8.3 Detaching current boot volume..."
    oci_cmd compute boot-volume-attachment detach \
        --boot-volume-attachment-id "$CURRENT_BOOT_ATTACH_ID" \
        --force 2>/dev/null
    log "Detach command sent for attachment: $CURRENT_BOOT_ATTACH_ID"
    wait_for_state "boot-volume-attachment" "$CURRENT_BOOT_ATTACH_ID" "DETACHED"

    # --- 8.4: Create new boot volume from Ubuntu image ---
    print_step "8.4 Creating new boot volume from selected Ubuntu image..."
    local new_bv_name="bv-reprovision-${TIMESTAMP}"

    local ssh_pub_key
    ssh_pub_key=$(cat "$SSH_PUBLIC_KEY_PATH")

    local create_cmd="oci_cmd bv boot-volume create \
        --availability-domain \"$AVAILABILITY_DOMAIN\" \
        --compartment-id \"$COMPARTMENT_OCID\" \
        --image-id \"$IMAGE_OCID\" \
        --display-name \"$new_bv_name\" \
        --size-in-gbs $BOOT_VOLUME_SIZE_GB"

    local new_bv_result
    new_bv_result=$(oci_cmd bv boot-volume create \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --compartment-id "$COMPARTMENT_OCID" \
        --image-id "$IMAGE_OCID" \
        --display-name "$new_bv_name" \
        --size-in-gbs "$BOOT_VOLUME_SIZE_GB" 2>/dev/null)

    local new_bv_id
    new_bv_id=$(echo "$new_bv_result" | jq -r '.data.id')
    log "New boot volume created: $new_bv_id ($new_bv_name)"
    print_success "New boot volume: $new_bv_id"

    wait_for_state "boot-volume" "$new_bv_id" "AVAILABLE" 900

    # --- 8.5: Attach new boot volume ---
    print_step "8.5 Attaching new boot volume to instance..."
    local attach_result
    attach_result=$(oci_cmd compute boot-volume-attachment attach \
        --boot-volume-id "$new_bv_id" \
        --instance-id "$INSTANCE_OCID" \
        --display-name "bv-attach-${TIMESTAMP}" 2>/dev/null)

    local new_attach_id
    new_attach_id=$(echo "$attach_result" | jq -r '.data.id')
    log "Boot volume attachment: $new_attach_id"
    wait_for_state "boot-volume-attachment" "$new_attach_id" "ATTACHED"

    # --- 8.6: Update instance metadata (SSH key + cloud-init) ---
    print_step "8.6 Updating instance metadata..."
    local metadata_args="--metadata '{\"ssh_authorized_keys\": \"$ssh_pub_key\"}'"

    if [[ -n "${CLOUD_INIT_PREPARED:-}" && -f "${CLOUD_INIT_PREPARED}" ]]; then
        # Base64 encode the cloud-init for user_data
        local user_data_b64
        user_data_b64=$(base64 -w 0 "$CLOUD_INIT_PREPARED")

        oci_cmd compute instance update \
            --instance-id "$INSTANCE_OCID" \
            --metadata "{\"ssh_authorized_keys\": \"$ssh_pub_key\", \"user_data\": \"$user_data_b64\"}" \
            --force 2>/dev/null
    else
        oci_cmd compute instance update \
            --instance-id "$INSTANCE_OCID" \
            --metadata "{\"ssh_authorized_keys\": \"$ssh_pub_key\"}" \
            --force 2>/dev/null
    fi
    print_success "Instance metadata updated with SSH key and cloud-init"

    # --- 8.7: Start instance ---
    print_step "8.7 Starting instance..."
    oci_cmd compute instance action \
        --instance-id "$INSTANCE_OCID" \
        --action START 2>/dev/null
    log "Start command sent"
    wait_for_state "instance" "$INSTANCE_OCID" "RUNNING"

    # --- 8.8: Verify SSH connectivity ---
    print_step "8.8 Verifying SSH connectivity..."
    print_info "Waiting 60 seconds for cloud-init to complete..."
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
    print_detail "Old Boot Volume:   $CURRENT_BOOT_VOLUME_ID"
    print_detail "Backup:            ${backup_id:-N/A}"
    print_detail "Admin User:        $NEW_USERNAME"
    print_detail "CloudPanel:        $INSTALL_CLOUDPANEL"
    print_detail "Log File:          $LOG_FILE"
    echo ""

    print_info "ROLLBACK: To revert, stop the instance, detach the new boot volume,"
    print_info "          and re-attach the old boot volume: $CURRENT_BOOT_VOLUME_ID"
    echo ""

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
