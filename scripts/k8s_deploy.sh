#!/usr/bin/env bash
# Deploy to Kubernetes
# Usage: ./scripts/k8s_deploy.sh [namespace]

set -euo pipefail

NAMESPACE="${1:-cryptobot}"

echo "Deploying to Kubernetes namespace: $NAMESPACE"
kubectl apply -k deploy/k8s/ -n "$NAMESPACE"
kubectl rollout status deployment/cryptobot -n "$NAMESPACE" --timeout=300s
echo "✓ Deployed"