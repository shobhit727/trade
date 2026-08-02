#!/usr/bin/env bash
# View logs from cryptobot service
# Usage: ./scripts/logs.sh [service] [lines]

set -euo pipefail

SERVICE="${1:-cryptobot-paper}"
LINES="${2:-100}"

echo "Showing last $LINES lines of $SERVICE logs..."
docker compose logs --tail="$LINES" -f "$SERVICE"