#!/usr/bin/env bash
# Run full CI pipeline locally (lint + tests + docker)
# Usage: ./scripts/ci_local.sh

set -euo pipefail

echo "=== Running CI pipeline locally ==="
echo
echo "1/4 Linting..."
./scripts/lint.sh
echo
echo "2/4 Running tests..."
./scripts/test.sh
echo
echo "3/4 Building Docker test image..."
./scripts/docker_build.sh test cryptobot:test
echo
echo "4/4 Running pytest in container..."
docker run --rm cryptobot:test
echo
echo "✓ CI pipeline passed"