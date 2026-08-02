#!/usr/bin/env bash
# Build Docker image
# Usage: ./scripts/docker_build.sh [target] [tag]

set -euo pipefail

TARGET="${1:-production}"
TAG="${2:-cryptobot:latest}"

echo "Building Docker image:"
echo "  Target: $TARGET"
echo "  Tag: $TAG"

if [ "$TARGET" = "test" ]; then
    docker build --target test --build-arg REQUIREMENTS=requirements/test.txt -t "$TAG" .
else
    docker build --target production --build-arg REQUIREMENTS=requirements/prod.txt -t "$TAG" .
fi
echo "✓ Built: $TAG"