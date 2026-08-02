#!/usr/bin/env bash
# Tag a new release and push to trigger release workflow
# Usage: ./scripts/release.sh <version>

set -euo pipefail

VERSION="${1:-}"

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version> (e.g., v0.2.0)"
    exit 1
fi

if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format vX.Y.Z (got '$VERSION')"
    exit 1
fi

echo "Tagging release: $VERSION"
git tag "$VERSION"
git push origin "$VERSION"
echo "✓ Release tagged: $VERSION"