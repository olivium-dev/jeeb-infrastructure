#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# rollback.sh — Rollback Jeeb to a previous image tag
#
# Usage: ./deploy/rollback.sh <image-tag>
# Example: ./deploy/rollback.sh v1.2.3
# ──────────────────────────────────────────────

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${REGISTRY:?REGISTRY is required}"

ROLLBACK_TAG="${1:?Usage: rollback.sh <image-tag>}"

echo "==> Rolling back jeeb-gateway to tag: ${ROLLBACK_TAG}"

# shellcheck disable=SC2087  # heredoc intentionally expands client-side so ROLLBACK_TAG lands in the remote env
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << REMOTE
  set -euo pipefail
  cd /opt/jeeb
  export REGISTRY="${REGISTRY}"
  export IMAGE_TAG="${ROLLBACK_TAG}"

  docker compose -f docker-compose.yml -f docker-compose.staging.yml pull jeeb-gateway
  docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --no-build jeeb-gateway

  echo "==> Waiting for health check..."
  sleep 5
  docker compose ps
REMOTE

echo "==> Rollback to ${ROLLBACK_TAG} complete"
