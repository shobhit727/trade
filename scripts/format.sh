#!/usr/bin/env bash
# Format code with ruff
# Usage: ./scripts/format.sh

set -euo pipefail

echo "Formatting code..."
python3 -m ruff format src tests
python3 -m ruff check --fix src tests
echo "✓ Formatted"