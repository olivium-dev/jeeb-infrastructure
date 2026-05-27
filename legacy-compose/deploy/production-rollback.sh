#!/usr/bin/env bash
# ──────────────────────────────────────────────
# production-rollback.sh — Roll production back to a previous image tag.
#
# SLO: rollback completes within 5 minutes (acceptance criterion for T-devops-003).
# In practice this script finishes within ~60s on a warm cache because we only
# repoint the image tag and trigger a rolling update; no rebuild is performed.
#
# Usage:  ./deploy/production-rollback.sh <image-tag>
# Example: ./deploy/production-rollback.sh sha-3f9a1c2
#
# If <image-tag> is omitted the script reads the most recent tag from the
# .deploy-history file written by production-deploy.sh.
# ──────────────────────────────────────────────

set -euo pipefail

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${REGISTRY:?REGISTRY is required}"
: "${GATEWAY_DOMAIN:?GATEWAY_DOMAIN is required}"

ROLLBACK_TAG="${1:-}"
REMOTE_DIR="${REMOTE_DIR:-/opt/jeeb}"
HEALTH_URL="${HEALTH_URL:-https://${GATEWAY_DOMAIN}/health/live}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"

if [ -z "${ROLLBACK_TAG}" ]; then
  echo "==> No tag passed — resolving last known good tag from remote .deploy-history"
  # shellcheck disable=SC2029  # REMOTE_DIR intentionally expands client-side.
  ROLLBACK_TAG="$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "tail -n1 ${REMOTE_DIR}/.deploy-history 2>/dev/null | awk '{print \$2}'")"
fi

if [ -z "${ROLLBACK_TAG}" ] || [ "${ROLLBACK_TAG}" = "unknown" ]; then
  echo "ERROR: Could not determine rollback tag. Pass it explicitly: production-rollback.sh <tag>"
  exit 1
fi

echo "==> Rolling production back to ${REGISTRY}/jeeb-gateway:${ROLLBACK_TAG}"
START_EPOCH=$(date +%s)

# shellcheck disable=SC2087  # heredoc intentionally expands client-side
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<REMOTE
  set -euo pipefail
  cd "${REMOTE_DIR}"
  export REGISTRY="${REGISTRY}"
  export IMAGE_TAG="${ROLLBACK_TAG}"

  docker compose -f docker-compose.yml -f docker-compose.production.yml pull jeeb-gateway
  docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --no-build --wait --wait-timeout 120 jeeb-gateway
  docker compose -f docker-compose.yml -f docker-compose.production.yml ps
REMOTE

echo "==> Verifying ${HEALTH_URL}"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
attempt=0
while :; do
  attempt=$((attempt + 1))
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${HEALTH_URL}" || echo '000')"
  if [ "$code" = "200" ]; then
    ELAPSED=$(( $(date +%s) - START_EPOCH ))
    echo "==> Rollback to ${ROLLBACK_TAG} complete in ${ELAPSED}s (SLO: <300s)"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ERROR: Health check did not return 200 within ${HEALTH_TIMEOUT}s after rollback (last=${code})"
    exit 1
  fi
  sleep 3
done
