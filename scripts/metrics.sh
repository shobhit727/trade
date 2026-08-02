#!/usr/bin/env bash
# View Prometheus metrics from cryptobot
# Usage: ./scripts/metrics.sh [host] [port]

set -euo pipefail

HOST="${1:-localhost}"
PORT="${2:-8080}"

URL="http://$HOST:$PORT/metrics"
echo "Fetching metrics from $URL"
curl -s "$URL"