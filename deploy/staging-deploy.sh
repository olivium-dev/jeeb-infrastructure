#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# staging-deploy.sh — Deploy Jeeb to staging
#
# Prerequisites:
#   - SSH access to DEPLOY_HOST
#   - Docker and Docker Compose on the target
#   - REGISTRY, IMAGE_TAG, DEPLOY_HOST, DEPLOY_USER env vars set
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

: "${REGISTRY:?REGISTRY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"

echo "==> Deploying jeeb-gateway:${IMAGE_TAG} to staging (${DEPLOY_HOST})"

# Pull the latest image on the remote host
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << REMOTE
  set -euo pipefail
  cd /opt/jeeb
  export REGISTRY="${REGISTRY}"
  export IMAGE_TAG="${IMAGE_TAG}"

  docker compose -f docker-compose.yml -f docker-compose.staging.yml pull jeeb-gateway
  docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --no-build jeeb-gateway

  echo "==> Waiting for health check..."
  sleep 5
  docker compose ps
REMOTE

echo "==> Staging deploy complete"
