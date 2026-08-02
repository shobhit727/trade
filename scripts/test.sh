#!/usr/bin/env bash
# Run all tests with coverage
# Usage: ./scripts/test.sh [pytest_args]

set -euo pipefail

ARGS="${@:-}"

echo "Running tests..."
python3 -m pytest -q --tb=short --cov=cryptobot --cov-report=term-missing --timeout=60 $ARGS