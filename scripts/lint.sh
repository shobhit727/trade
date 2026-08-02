#!/usr/bin/env bash
# Run linters (ruff + pyflakes)
# Usage: ./scripts/lint.sh

set -euo pipefail

echo "Running ruff..."
python3 -m ruff check src tests
echo "Running pyflakes..."
python3 -m pyflakes src tests
echo "✓ All lints passed"