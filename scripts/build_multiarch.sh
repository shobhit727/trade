#!/usr/bin/env bash
# Build cryptobot multi-arch images (linux/amd64, linux/arm64) using buildx.
#
# Usage:
#   REQUIREMENTS=requirements/prod.txt REGISTRY=ghcr.io/<you>/trade \
#     TARGET=production PLATFORMS="linux/amd64,linux/arm64" \
#     ./scripts/build_multiarch.sh
#
# Outputs:
#   <REGISTRY>:latest-multiarch               (manifest list)
#   <REGISTRY>:<git-sha>-multiarch           (manifest list)
#
# Requirements:
#   docker, buildx, qemu-user-static registered for cross-arch builds.

set -euo pipefail

REGISTRY=${REGISTRY:-ghcr.io/shobhit727/trade}
TAG=${TAG:-multiarch}
TARGET=${TARGET:-production}
REQUIREMENTS=${REQUIREMENTS:-requirements/prod.txt}
PLATFORMS=${PLATFORMS:-"linux/amd64,linux/arm64"}
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "dev")
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "==> building cryptobot image"
echo "    registry = ${REGISTRY}"
echo "    tag      = ${TAG}"
echo "    target   = ${TARGET}"
echo "    platforms= ${PLATFORMS}"

# Ensure buildx + qemu are usable
docker buildx version >/dev/null
docker run --rm --privileged multiarch/qemu-user-static --reset 2>/dev/null || true

docker buildx build \
  --platform "${PLATFORMS}" \
  --target "${TARGET}" \
  --tag "${REGISTRY}:${TAG}" \
  --tag "${REGISTRY}:${GIT_SHA}-${TAG}" \
  --build-arg REQUIREMENTS="${REQUIREMENTS}" \
  --build-arg GIT_SHA="${GIT_SHA}" \
  --build-arg BUILD_DATE="${BUILD_DATE}" \
  --push \
  .

echo "==> done"
echo "    ${REGISTRY}:${TAG}"
echo "    ${REGISTRY}:${GIT_SHA}-${TAG}"
