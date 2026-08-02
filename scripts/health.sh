#!/usr/bin/env bash
# Check health of cryptobot service
# Usage: ./scripts/health.sh [host] [port]

set -euo pipefail

HOST="${1:-localhost}"
PORT="${2:-8080}"

URL="http://$HOST:$PORT/health"
echo "Checking health: $URL"
if curl -sf "$URL" > /dev/null; then
    echo "✓ Healthy"
    curl -s "$URL"
else
    echo "✗ Unhealthy"
    exit 1
fi