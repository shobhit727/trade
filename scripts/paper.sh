#!/usr/bin/env bash
# Start paper trading (live simulation)
# Usage: ./scripts/paper.sh [config_file]

set -euo pipefail

CONFIG="${1:-configs/base.yaml}"

echo "Starting paper trading with config: $CONFIG"
docker compose up -d cryptobot-paper