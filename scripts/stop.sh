#!/usr/bin/env bash
# Stop all cryptobot services
# Usage: ./scripts/stop.sh

set -euo pipefail

echo "Stopping cryptobot services..."
docker compose down