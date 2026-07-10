#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

MAX_PARALLEL=${MAX_PARALLEL:-2}
FAIL_COUNT=0
BUILD_COUNT=0

log() { printf "${CYAN}[build]${NC} %s\n" "$*"; }
ok()  { printf "${GREEN}[  ok ]${NC} %s\n" "$*"; }
err() { printf "${RED}[fail]${NC} %s\n" "$*"; }

build_one() {
  local name="$1" context="$2" dockerfile="$3"
  local tag="jeeb/${name}:local"
  log "Building $tag"
  if docker build -t "$tag" -f "$dockerfile" "$context" 2>&1 | tail -5; then
    ok "$tag"
    return 0
  else
    err "$tag"
    return 1
  fi
}

SERVICES=(
  "jeeb-gateway|${REPO_ROOT}/jeeb-gateway|${REPO_ROOT}/jeeb-gateway/Dockerfile"
  "auth-service|${REPO_ROOT}/auth-service|${REPO_ROOT}/auth-service/Dockerfile"
  "user-management|${REPO_ROOT}/user-management|${REPO_ROOT}/user-management/Dockerfile"
  "delivery-service|${REPO_ROOT}/delivery-service|${REPO_ROOT}/delivery-service/Dockerfile"
  "chat-service|${REPO_ROOT}/chat-service|${REPO_ROOT}/chat-service/dockerfiles/Dockerfile"
  "wallet-service|${REPO_ROOT}/wallet-service|${REPO_ROOT}/wallet-service/Dockerfile"
  "score-taking-service|${REPO_ROOT}/score-taking-service|${REPO_ROOT}/score-taking-service/Dockerfile"
  "feedback-service|${REPO_ROOT}/feedback-service|${REPO_ROOT}/feedback-service/Dockerfile"
  "offer-service|${REPO_ROOT}/offer-service|${REPO_ROOT}/offer-service/Dockerfile"
  "realtime-comunication-service|${REPO_ROOT}/realtime-comunication-service|${REPO_ROOT}/realtime-comunication-service/Dockerfile"
  "voice-transcription-service|${REPO_ROOT}/voice-transcription-service|${REPO_ROOT}/voice-transcription-service/Dockerfile"
)

TOTAL=${#SERVICES[@]}

echo "══════════════════════════════════════════"
echo "  Rebuild failed services ($TOTAL images)"
echo "  Parallelism: $MAX_PARALLEL"
echo "══════════════════════════════════════════"
echo ""

PIDS=""
RUNNING=0

wait_for_slot() {
  while [ "$RUNNING" -ge "$MAX_PARALLEL" ]; do
    local new_pids=""
    for pid in $PIDS; do
      if kill -0 "$pid" 2>/dev/null; then
        new_pids="$new_pids $pid"
      else
        wait "$pid" 2>/dev/null && BUILD_COUNT=$((BUILD_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1))
        RUNNING=$((RUNNING - 1))
      fi
    done
    PIDS="$new_pids"
    if [ "$RUNNING" -ge "$MAX_PARALLEL" ]; then
      sleep 3
    fi
  done
}

for entry in "${SERVICES[@]}"; do
  IFS='|' read -r name context dockerfile <<< "$entry"
  wait_for_slot
  build_one "$name" "$context" "$dockerfile" &
  PIDS="$PIDS $!"
  RUNNING=$((RUNNING + 1))
done

for pid in $PIDS; do
  wait "$pid" 2>/dev/null && BUILD_COUNT=$((BUILD_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1))
done

echo ""
echo "══════════════════════════════════════════"
echo "  Rebuild Summary"
echo "══════════════════════════════════════════"
echo "  Total:  $TOTAL"
echo "  Built:  $BUILD_COUNT"
echo "  Failed: $FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  printf "${RED}  Some builds still failing.${NC}\n"
  exit 1
else
  printf "${GREEN}  All $TOTAL images rebuilt successfully.${NC}\n"
fi
