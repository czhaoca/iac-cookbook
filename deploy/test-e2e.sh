#!/usr/bin/env bash
# deploy/test-e2e.sh — Build and test the full Docker stack end-to-end.
# Usage: ./deploy/test-e2e.sh
#
# Builds both containers, starts the stack, verifies health,
# tests key API endpoints, and tears down.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
PROJECT="nimbus-e2e"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass=0
fail=0

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

assert_status() {
    local desc="$1" url="$2" expected="${3:-200}"
    local status
    status=$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")
    if [ "$status" = "$expected" ]; then
        log "$desc — HTTP $status"
        ((pass++))
    else
        err "$desc — expected $expected, got $status"
        ((fail++))
    fi
}

assert_json_field() {
    local desc="$1" url="$2" field="$3"
    local body
    body=$(curl -sf "$url" 2>/dev/null || echo "{}")
    if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$field' in d" 2>/dev/null; then
        log "$desc — field '$field' present"
        ((pass++))
    else
        err "$desc — field '$field' missing in response"
        ((fail++))
    fi
}

cleanup() {
    warn "Tearing down E2E stack..."
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down --volumes --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# ── Build ─────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Nimbus E2E Docker Test"
echo "══════════════════════════════════════════════════════════════"
echo ""

warn "Building containers..."
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" build --quiet 2>&1

warn "Starting stack..."
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d 2>&1

# ── Wait for health ──────────────────────────────────────────────────
warn "Waiting for engine health (up to 60s)..."
HEALTHY=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 2
done

if [ "$HEALTHY" = "true" ]; then
    log "Engine healthy after ~$((i*2))s"
    ((pass++))
else
    err "Engine failed to become healthy"
    ((fail++))
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs engine 2>&1 | tail -30
fi

# ── API Tests ─────────────────────────────────────────────────────────
echo ""
warn "Running API tests..."

# Health endpoint
assert_json_field "Health endpoint" "http://localhost:8000/health" "status"

# Providers list (empty but 200)
assert_status "GET /api/providers" "http://localhost:8000/api/providers"

# Resources list
assert_status "GET /api/resources" "http://localhost:8000/api/resources"

# Budget rules
assert_status "GET /api/budget/rules" "http://localhost:8000/api/budget/rules"

# Budget status
assert_status "GET /api/budget/status" "http://localhost:8000/api/budget/status"

# Budget spending
assert_status "GET /api/budget/spending" "http://localhost:8000/api/budget/spending"

# Settings
assert_status "GET /api/settings" "http://localhost:8000/api/settings"

# Audit log
assert_status "GET /api/audit" "http://localhost:8000/api/audit"

# OpenAPI docs
assert_status "GET /docs" "http://localhost:8000/docs"

# Non-existent endpoint
assert_status "404 on unknown path" "http://localhost:8000/api/nonexistent" "404"

# ── UI Tests ──────────────────────────────────────────────────────────
echo ""
warn "Testing UI (nginx)..."

# Wait for UI
UI_UP=false
for i in $(seq 1 15); do
    if curl -sf http://localhost:3000/ >/dev/null 2>&1; then
        UI_UP=true
        break
    fi
    sleep 2
done

if [ "$UI_UP" = "true" ]; then
    assert_status "UI index.html" "http://localhost:3000/"
    # API proxy through nginx
    assert_status "UI → API proxy /health" "http://localhost:3000/health"
    assert_status "UI → API proxy /api/providers" "http://localhost:3000/api/providers"
    # SPA fallback — unknown routes should serve index.html
    assert_status "SPA fallback /settings" "http://localhost:3000/settings"
else
    err "UI failed to start"
    ((fail++))
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs ui 2>&1 | tail -15
fi

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo -e "  Results: ${GREEN}$pass passed${NC}, ${RED}$fail failed${NC}"
echo "══════════════════════════════════════════════════════════════"
echo ""

if [ "$fail" -gt 0 ]; then
    exit 1
fi
