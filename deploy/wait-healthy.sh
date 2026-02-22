#!/usr/bin/env bash
# wait-healthy.sh — Wait for Nimbus services to become healthy
# Usage: ./wait-healthy.sh [--timeout 120]
set -euo pipefail

TIMEOUT=${1:-120}
INTERVAL=5
ELAPSED=0
ENGINE_URL="${NIMBUS_ENGINE_URL:-http://localhost:8000/health}"

echo "Waiting for Nimbus engine at ${ENGINE_URL} (timeout: ${TIMEOUT}s)..."

while [ $ELAPSED -lt $TIMEOUT ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$ENGINE_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✔ Engine is healthy (${ELAPSED}s)"
        # Check DB connectivity from health response
        STATUS=$(curl -s "$ENGINE_URL" | grep -o '"status":"[^"]*"' | head -1)
        echo "  Health: ${STATUS}"
        exit 0
    fi
    echo "  Waiting... (${ELAPSED}s, HTTP ${HTTP_CODE})"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo "✗ Timeout after ${TIMEOUT}s — engine not healthy"
exit 1
