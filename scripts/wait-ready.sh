#!/usr/bin/env bash
set -euo pipefail

TIMEOUT=${TIMEOUT:-120}
INTERVAL=5
ELAPSED=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

# Each line: name|port|check (tcp or http path)
ENDPOINTS=(
  "postgres|15432|tcp"
  "redis|16379|tcp"
  "jeeb-gateway|10000|/health/live"
  "user-management|10001|tcp"
  "auth-service|10003|tcp"
  "delivery-service|10005|/health"
  "geolocation-service|10006|/health"
  "offer-service|10007|/health"
  "realtime-comm|10008|tcp"
  "score-taking|10009|/health"
  "voice-transcription|10010|/health/live"
  "contract-signing|10011|/health"
  "wallet-service|10014|/health"
  "upg|10016|tcp"
  "feedback-service|10020|tcp"
  "notification|10026|/health"
  "chat-service|10028|/api/health/check"
  "form-builder|10032|tcp"
  "compliment|10036|/health"
  "push-notification|10040|/health"
  "ban-service|10042|/health"
)

TOTAL=${#ENDPOINTS[@]}
READY_FILE=$(mktemp)
echo "" > "$READY_FILE"

check_tcp() {
  local port="$1"
  (echo > /dev/tcp/localhost/"$port") 2>/dev/null
}

check_http() {
  local port="$1" path="$2"
  curl -sf -o /dev/null --max-time 3 "http://localhost:${port}${path}" 2>/dev/null
}

is_ready() {
  local name="$1"
  grep -q "^${name}$" "$READY_FILE" 2>/dev/null
}

mark_ready() {
  local name="$1"
  echo "$name" >> "$READY_FILE"
}

echo "══════════════════════════════════════════"
echo "  Jeeb Swarm — Waiting for services"
echo "  Timeout: ${TIMEOUT}s"
echo "══════════════════════════════════════════"

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  READY_COUNT=0
  NOT_READY=""

  for entry in "${ENDPOINTS[@]}"; do
    IFS='|' read -r name port check <<< "$entry"

    if is_ready "$name"; then
      READY_COUNT=$((READY_COUNT + 1))
      continue
    fi

    OK=0
    if [ "$check" = "tcp" ]; then
      check_tcp "$port" && OK=1
    else
      check_http "$port" "$check" && OK=1
    fi

    if [ "$OK" -eq 1 ]; then
      mark_ready "$name"
      READY_COUNT=$((READY_COUNT + 1))
      printf "${GREEN}[✓]${NC} %-25s (port %s, %s)\n" "$name" "$port" "$check"
    else
      NOT_READY="$NOT_READY $name:$port"
    fi
  done

  if [ "$READY_COUNT" -eq "$TOTAL" ]; then
    echo ""
    printf "${GREEN}All %d services are ready (%ds elapsed).${NC}\n" "$TOTAL" "$ELAPSED"
    rm -f "$READY_FILE"
    exit 0
  fi

  printf "${YELLOW}[%3ds/%ds]${NC} %d/%d ready — waiting:%s\n" \
    "$ELAPSED" "$TIMEOUT" "$READY_COUNT" "$TOTAL" "$NOT_READY"

  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
READY_COUNT=$(wc -l < "$READY_FILE" | tr -d ' ')
READY_COUNT=$((READY_COUNT - 1))
printf "${RED}TIMEOUT after %ds — %d/%d services not ready.${NC}\n" "$TIMEOUT" "$((TOTAL - READY_COUNT))" "$TOTAL"

echo "Not ready:"
for entry in "${ENDPOINTS[@]}"; do
  IFS='|' read -r name port check <<< "$entry"
  if ! is_ready "$name"; then
    printf "  ${RED}✗${NC} %s (port %s)\n" "$name" "$port"
  fi
done

rm -f "$READY_FILE"
exit 1
