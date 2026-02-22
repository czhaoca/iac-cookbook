#!/usr/bin/env bash
# deploy-nimbus.sh — Deploy Nimbus on a Proxmox VM via Docker Compose
# Usage: ./deploy-nimbus.sh [--host <IP>] [--user <USER>] [--key <SSH_KEY>]
#
# Prerequisites:
#   - SSH access to the target VM
#   - Docker + Docker Compose installed on the VM
#   - Git installed on the VM
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Defaults
HOST=""
USER="root"
SSH_KEY=""
REPO_URL="https://github.com/czhaoca/nimbus.git"
DEPLOY_DIR="/opt/nimbus"

usage() {
    echo "Usage: $0 --host <IP> [--user <USER>] [--key <SSH_KEY>]"
    echo ""
    echo "Options:"
    echo "  --host    Target VM IP address (required)"
    echo "  --user    SSH user (default: root)"
    echo "  --key     Path to SSH private key"
    echo "  --help    Show this help"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --user) USER="$2"; shift 2 ;;
        --key)  SSH_KEY="$2"; shift 2 ;;
        --help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$HOST" ]]; then
    echo "Error: --host is required"
    usage
fi

SSH_OPTS="-o StrictHostKeyChecking=accept-new"
[[ -n "$SSH_KEY" ]] && SSH_OPTS="$SSH_OPTS -i $SSH_KEY"

run_remote() {
    ssh $SSH_OPTS "${USER}@${HOST}" "$@"
}

echo "=== Nimbus Deployment to ${USER}@${HOST} ==="

# 1. Install Docker if not present
echo "[1/5] Checking Docker..."
run_remote 'command -v docker >/dev/null 2>&1 || {
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
}'

# 2. Install Docker Compose plugin if not present
echo "[2/5] Checking Docker Compose..."
run_remote 'docker compose version >/dev/null 2>&1 || {
    echo "Installing Docker Compose plugin..."
    apt-get update && apt-get install -y docker-compose-plugin
}'

# 3. Clone or update repo
echo "[3/5] Syncing repository..."
run_remote "
    if [ -d ${DEPLOY_DIR}/.git ]; then
        cd ${DEPLOY_DIR} && git pull --ff-only
    else
        git clone ${REPO_URL} ${DEPLOY_DIR}
    fi
"

# 4. Ensure local directories exist
echo "[4/5] Setting up local directories..."
run_remote "
    mkdir -p ${DEPLOY_DIR}/local/data
    mkdir -p ${DEPLOY_DIR}/local/config
    mkdir -p ${DEPLOY_DIR}/local/backups
"

# 5. Build and deploy
echo "[5/5] Building and starting containers..."
run_remote "
    cd ${DEPLOY_DIR}
    docker compose build --no-cache
    docker compose up -d
    docker compose ps
"

echo ""
echo "=== Deployment complete ==="
echo "  Engine: http://${HOST}:8000/health"
echo "  UI:     http://${HOST}:3000"
echo ""
echo "To view logs:  ssh ${USER}@${HOST} 'cd ${DEPLOY_DIR} && docker compose logs -f'"
echo "To stop:       ssh ${USER}@${HOST} 'cd ${DEPLOY_DIR} && docker compose down'"
