#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

MAX_PARALLEL=${MAX_PARALLEL:-4}
FAIL_COUNT=0
BUILD_COUNT=0

log() { printf "${CYAN}[build]${NC} %s\n" "$*"; }
ok()  { printf "${GREEN}[  ok ]${NC} %s\n" "$*"; }
err() { printf "${RED}[fail]${NC} %s\n" "$*"; }

build_one() {
  local name="$1" context="$2" dockerfile="$3"
  local tag="jeeb/${name}:local"
  log "Building $tag"
  if docker build -t "$tag" -f "$dockerfile" "$context" --quiet > /dev/null 2>&1; then
    ok "$tag"
    return 0
  else
    err "$tag — retrying with output..."
    docker build -t "$tag" -f "$dockerfile" "$context" 2>&1 | tail -20
    return 1
  fi
}

# Each line: name|context|dockerfile
SERVICES=(
  "jeeb-gateway|${REPO_ROOT}/jeeb-gateway|${REPO_ROOT}/jeeb-gateway/Dockerfile"
  "auth-service|${REPO_ROOT}/auth-service|${REPO_ROOT}/auth-service/Dockerfile"
  "user-management|${REPO_ROOT}/user-management|${REPO_ROOT}/user-management/Dockerfile"
  "delivery-service|${REPO_ROOT}/delivery-service|${REPO_ROOT}/delivery-service/Dockerfile"
  "geolocation-service|${REPO_ROOT}/geolocation-service|${REPO_ROOT}/geolocation-service/Dockerfile"
  "chat-service|${REPO_ROOT}/chat-service|${REPO_ROOT}/chat-service/dockerfiles/Dockerfile"
  "wallet-service|${REPO_ROOT}/wallet-service|${REPO_ROOT}/wallet-service/Dockerfile"
  "notification-service|${REPO_ROOT}/notification-service|${REPO_ROOT}/notification-service/Dockerfile"
  "push-notification|${REPO_ROOT}/push-notification|${REPO_ROOT}/push-notification/Dockerfile"
  "score-taking-service|${REPO_ROOT}/score-taking-service|${REPO_ROOT}/score-taking-service/Dockerfile"
  "offer-service|${REPO_ROOT}/offer-service|${REPO_ROOT}/offer-service/Dockerfile"
  "realtime-comunication-service|${REPO_ROOT}/realtime-comunication-service|${REPO_ROOT}/realtime-comunication-service/Dockerfile"
  "unified-payment-gateway|${REPO_ROOT}/unified_payment_gateway/unified_payment_gateway|${REPO_ROOT}/unified_payment_gateway/unified_payment_gateway/Dockerfile"
  "compliment-service|${REPO_ROOT}/compliment-service|${REPO_ROOT}/compliment-service/Dockerfile"
  "contract-signing-service|${REPO_ROOT}/contract-signing-service|${REPO_ROOT}/contract-signing-service/Dockerfile"
  "feedback-service|${REPO_ROOT}/feedback-service|${REPO_ROOT}/feedback-service/Dockerfile"
  "form-builder-service|${REPO_ROOT}/form-builder-service|${REPO_ROOT}/form-builder-service/Dockerfile"
  "voice-transcription-service|${REPO_ROOT}/voice-transcription-service|${REPO_ROOT}/voice-transcription-service/Dockerfile"
  "ban-service|${REPO_ROOT}/ban-service|${REPO_ROOT}/ban-service/Dockerfile"
)

TOTAL=${#SERVICES[@]}

echo "══════════════════════════════════════════"
echo "  Jeeb Swarm — Build All ($TOTAL images)"
echo "  Parallelism: $MAX_PARALLEL"
echo "══════════════════════════════════════════"
echo ""

PIDS=""
NAMES=""
RUNNING=0

wait_for_slot() {
  while [ "$RUNNING" -ge "$MAX_PARALLEL" ]; do
    local new_pids="" new_names=""
    local old_pids="$PIDS"
    local old_names="$NAMES"
    local i=0
    for pid in $old_pids; do
      local name
      name=$(echo "$old_names" | cut -d' ' -f$((i+1)))
      if kill -0 "$pid" 2>/dev/null; then
        new_pids="$new_pids $pid"
        new_names="$new_names $name"
      else
        wait "$pid" 2>/dev/null && BUILD_COUNT=$((BUILD_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1))
        RUNNING=$((RUNNING - 1))
      fi
      i=$((i + 1))
    done
    PIDS="$new_pids"
    NAMES="$new_names"
    if [ "$RUNNING" -ge "$MAX_PARALLEL" ]; then
      sleep 2
    fi
  done
}

for entry in "${SERVICES[@]}"; do
  IFS='|' read -r name context dockerfile <<< "$entry"

  wait_for_slot

  build_one "$name" "$context" "$dockerfile" &
  PIDS="$PIDS $!"
  NAMES="$NAMES $name"
  RUNNING=$((RUNNING + 1))
done

for pid in $PIDS; do
  wait "$pid" 2>/dev/null && BUILD_COUNT=$((BUILD_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1))
done

echo ""
echo "══════════════════════════════════════════"
echo "  Build Summary"
echo "══════════════════════════════════════════"
echo "  Total:  $TOTAL"
echo "  Built:  $BUILD_COUNT"
echo "  Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  printf "${RED}  Some builds failed — check output above.${NC}\n"
  exit 1
else
  printf "${GREEN}  All $TOTAL images built successfully.${NC}\n"
fi
