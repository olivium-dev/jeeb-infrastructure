#!/usr/bin/env bash
# Bring up the local Docker Compose stack and verify the gateway
# /health/live endpoint returns 200 within the timeout budget.
#
# Usage:  ./scripts/smoke-test.sh  [timeout-seconds]
#
# Required env (defaults provided for CI; .env loaded if present):
#   POSTGRES_USER, POSTGRES_PASSWORD, JWT_KEY, JWT_ISSUER

set -euo pipefail

TIMEOUT="${1:-180}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
GATEWAY_HOST_PORT="${GATEWAY_HOST_PORT:-5000}"
HEALTH_PATH="${HEALTH_PATH:-/health/live}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [ -f .env ]; then
  echo "Loading .env"
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
: "${JWT_KEY:?JWT_KEY must be set}"
: "${JWT_ISSUER:?JWT_ISSUER must be set}"

cleanup() {
  echo "--- Tearing down ---"
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "--- Validating compose file ---"
docker compose -f "$COMPOSE_FILE" config -q

echo "--- Starting stack ---"
docker compose -f "$COMPOSE_FILE" up -d --build

url="http://localhost:${GATEWAY_HOST_PORT}${HEALTH_PATH}"
echo "--- Waiting for ${url} (timeout ${TIMEOUT}s) ---"
deadline=$(( $(date +%s) + TIMEOUT ))
attempt=0
while :; do
  attempt=$((attempt + 1))
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" || echo '000')"
  if [ "$code" = "200" ]; then
    echo "[$attempt] ${url} returned 200"
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ERROR: ${url} did not return 200 within ${TIMEOUT}s (last code=${code})"
    docker compose -f "$COMPOSE_FILE" ps
    docker compose -f "$COMPOSE_FILE" logs --no-color --tail=200
    exit 1
  fi
  printf '[%d] code=%s, retrying in 3s\n' "$attempt" "$code"
  sleep 3
done

echo "SMOKE OK"
