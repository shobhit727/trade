#!/usr/bin/env bash
# Start HTTP health/metrics server
# Usage: ./scripts/serve.sh [port]

set -euo pipefail

PORT="${1:-8080}"

echo "Starting health server on port $PORT..."
python3 -m cryptobot.cli.main serve --port "$PORT"