#!/usr/bin/env bash
# Install production dependencies
# Usage: ./scripts/install.sh [dev|test|prod]

set -euo pipefail

ENV="${1:-prod}"

case "$ENV" in
    dev|test)
        echo "Installing test dependencies..."
        pip install -e . -r requirements/test.txt
        pip install numpy pandas
        ;;
    prod|"")
        echo "Installing production dependencies..."
        pip install -r requirements/prod.txt
        ;;
    *)
        echo "Unknown env: $ENV (use dev|test|prod)"
        exit 1
        ;;
esac
echo "✓ Installed"