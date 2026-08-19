#!/usr/bin/env bash
# ──────────────────────────────────────────────
# production-deploy.sh — Deploy Jeeb to production
#
# Strategy: rolling update with start-first ordering and post-deploy health
# verification. Failures remain visible and require a corrected forward deploy.
#
# Prerequisites:
#   - SSH access to DEPLOY_HOST (production bastion / Swarm manager)
#   - Docker + Docker Compose v2 on the target
#   - Required env: REGISTRY, IMAGE_TAG, DEPLOY_HOST, DEPLOY_USER, GATEWAY_DOMAIN
#   - Image already pushed to REGISTRY by upstream CI
# ──────────────────────────────────────────────

set -euo pipefail

: "${REGISTRY:?REGISTRY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${GATEWAY_DOMAIN:?GATEWAY_DOMAIN is required (e.g., api.jeeb.app)}"

HEALTH_URL="${HEALTH_URL:-https://${GATEWAY_DOMAIN}/health/live}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
REMOTE_DIR="${REMOTE_DIR:-/opt/jeeb}"

echo "==> Production deploy: jeeb-gateway:${IMAGE_TAG} -> ${DEPLOY_HOST}"
echo "==> Health probe: ${HEALTH_URL} (timeout ${HEALTH_TIMEOUT}s)"

# shellcheck disable=SC2087
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<REMOTE
  set -euo pipefail
  cd "${REMOTE_DIR}"
  export REGISTRY="${REGISTRY}"
  export IMAGE_TAG="${IMAGE_TAG}"

  echo "==> [remote] Pulling \${REGISTRY}/jeeb-gateway:\${IMAGE_TAG}"
  docker compose -f docker-compose.yml -f docker-compose.production.yml pull jeeb-gateway

  echo "==> [remote] Rolling update (start-first, replicas=2)"
  docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --no-build --wait --wait-timeout 120 jeeb-gateway

  echo "==> [remote] Post-deploy state"
  docker compose -f docker-compose.yml -f docker-compose.production.yml ps
REMOTE

echo "==> Verifying ${HEALTH_URL}"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
attempt=0
while :; do
  attempt=$((attempt + 1))
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${HEALTH_URL}" || echo '000')"
  if [ "$code" = "200" ]; then
    echo "==> [${attempt}] Health OK"
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ERROR: Health check did not return 200 within ${HEALTH_TIMEOUT}s (last=${code})"
    echo "Deployment is paused on ${IMAGE_TAG}; diagnose and deploy a corrected image."
    exit 1
  fi
  printf '[%d] code=%s, retrying in 3s\n' "$attempt" "$code"
  sleep 3
done

echo "==> Production deploy of ${IMAGE_TAG} complete"
