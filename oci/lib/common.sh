#!/usr/bin/env bash
# ============================================================================
# oci/lib/common.sh — Shared utilities for OCI IaC scripts
# ============================================================================
# Provides: colors, logging, prompts, JSON transaction log, error handling
# Requires: jq
# Sets: REPO_ROOT, TIMESTAMP, LOG_FILE, JSON_LOG_FILE
# ============================================================================

[[ -n "${_LIB_COMMON_LOADED:-}" ]] && return 0
_LIB_COMMON_LOADED=1

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Constants ---
# CALLER_DIR can be set by the sourcing script before sourcing common.sh
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TIMESTAMP="${TIMESTAMP:-$(date +%Y-%m-%d-%H%M%S)}"
DEFAULT_LOG_DIR="${DEFAULT_LOG_DIR:-$REPO_ROOT/oci/local/logs}"
LOG_FILE="${LOG_FILE:-}"
JSON_LOG_FILE="${JSON_LOG_FILE:-}"

# --- Shared Script State ---
DRY_RUN="${DRY_RUN:-false}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"

# ============================================================================
# Display Functions
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

# ============================================================================
# Logging
# ============================================================================

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
    json_step_update "failed" "$1"
    json_finalize "failed" "$1"
    exit 1
}

# ============================================================================
# JSON Transaction Log
# ============================================================================

json_log_init() {
    local script_name="${1:-unknown}"
    [[ -z "${JSON_LOG_FILE:-}" ]] && return 0
    jq -n \
      --arg ts "$TIMESTAMP" \
      --argjson dry_run "$DRY_RUN" \
      --arg script "$script_name" \
      '{
        session: {
          timestamp: $ts,
          started_at: (now | todate),
          dry_run: $dry_run,
          script: $script
        },
        steps: [],
        result: {status: "in_progress"}
      }' > "$JSON_LOG_FILE"
}

json_step() {
    local step="$1"
    local description="$2"
    local status="${3:-started}"
    [[ -z "${JSON_LOG_FILE:-}" || ! -f "$JSON_LOG_FILE" ]] && return 0
    local tmp
    tmp=$(mktemp)
    jq --arg step "$step" \
       --arg desc "$description" \
       --arg status "$status" \
       --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       '.steps += [{step: $step, description: $desc, status: $status, timestamp: $ts}]' \
       "$JSON_LOG_FILE" > "$tmp" && mv "$tmp" "$JSON_LOG_FILE"
}

json_step_update() {
    local status="$1"
    local message="${2:-}"
    [[ -z "${JSON_LOG_FILE:-}" || ! -f "$JSON_LOG_FILE" ]] && return 0
    local tmp
    tmp=$(mktemp)
    jq --arg status "$status" \
       --arg msg "$message" \
       --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       'if (.steps | length) > 0 then
          .steps[-1].status = $status |
          .steps[-1].completed_at = $ts |
          if ($msg != "") then .steps[-1].message = $msg else . end
        else . end' \
       "$JSON_LOG_FILE" > "$tmp" && mv "$tmp" "$JSON_LOG_FILE"
}

json_finalize() {
    local status="$1"
    local message="${2:-}"
    [[ -z "${JSON_LOG_FILE:-}" || ! -f "$JSON_LOG_FILE" ]] && return 0
    local tmp
    tmp=$(mktemp)
    # Use global vars if available — modules set these
    jq --arg status "$status" \
       --arg msg "$message" \
       --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg instance "${INSTANCE_OCID:-}" \
       --arg image "${IMAGE_OCID:-}" \
       --arg new_bv "${new_bv_id:-}" \
       --arg old_bv "${CURRENT_BOOT_VOLUME_ID:-}" \
       --arg user "${NEW_USERNAME:-}" \
       --argjson delete_old "${DELETE_OLD_BV:-false}" \
       --argjson dry_run "${DRY_RUN:-false}" \
       '.result = {
          status: $status,
          message: $msg,
          completed_at: $ts,
          instance_ocid: $instance,
          image_ocid: $image,
          new_boot_volume_ocid: $new_bv,
          old_boot_volume_ocid: $old_bv,
          admin_user: $user,
          old_bv_deleted: $delete_old,
          dry_run: $dry_run
        }' \
       "$JSON_LOG_FILE" > "$tmp" && mv "$tmp" "$JSON_LOG_FILE"
}

# ============================================================================
# Interactive Prompts
# ============================================================================

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

# ============================================================================
# Dependency Checking
# ============================================================================

check_dependencies() {
    local deps=("$@")
    for cmd in "${deps[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            print_success "$cmd found: $(command -v "$cmd")"
        else
            die "$cmd is required but not installed. Please install it and try again."
        fi
    done
}

# ============================================================================
# Logging Initialization
# ============================================================================

init_logging() {
    local prefix="${1:-operation}"
    mkdir -p "$DEFAULT_LOG_DIR"
    LOG_FILE="${LOG_FILE:-$DEFAULT_LOG_DIR/${prefix}-${TIMESTAMP}.log}"
    JSON_LOG_FILE="${JSON_LOG_FILE:-$DEFAULT_LOG_DIR/${prefix}-${TIMESTAMP}.json}"
    log_quiet "=== Session started at $(date) ==="
    log_quiet "Dry-run: $DRY_RUN"
}
