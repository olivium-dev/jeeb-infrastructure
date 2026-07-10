#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
FAIL=0

info()  { printf "${GREEN}[✓]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[!]${NC} %s\n" "$*"; }
fail()  { printf "${RED}[✗]${NC} %s\n" "$*"; FAIL=1; }

echo "══════════════════════════════════════════"
echo "  Jeeb Swarm — Preflight Checks"
echo "══════════════════════════════════════════"

# 1. Docker installed & running
if ! command -v docker &>/dev/null; then
  fail "docker CLI not found — install Docker Desktop or Docker Engine"
else
  info "docker CLI found: $(docker --version)"
  if ! docker info &>/dev/null; then
    fail "Docker daemon is not running"
  else
    info "Docker daemon is reachable"
  fi
fi

# 2. docker compose / docker-compose
if docker compose version &>/dev/null; then
  info "docker compose v2 plugin available"
elif command -v docker-compose &>/dev/null; then
  warn "docker-compose v1 found — v2 plugin preferred"
else
  warn "docker compose not found (not required for Swarm, but nice to have)"
fi

# 3. jq
if ! command -v jq &>/dev/null; then
  fail "jq not found — install with: brew install jq (macOS) / apt install jq (Linux)"
else
  info "jq found: $(jq --version)"
fi

# 4. Swarm init (idempotent)
if docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -q "active"; then
  info "Docker Swarm already active"
else
  warn "Swarm not active — initializing..."
  if docker swarm init --advertise-addr 127.0.0.1 2>/dev/null; then
    info "Docker Swarm initialized"
  else
    fail "Failed to initialize Docker Swarm"
  fi
fi

# 5. Port collision check
PORTS=(
  15432 16379
  10000 10001 10003 10005 10006 10007 10008 10009
  10010 10011 10014 10016 10020 10025 10026 10028
  10032 10036 10040 10042
)

BUSY_PORTS=()
for p in "${PORTS[@]}"; do
  if lsof -iTCP:"$p" -sTCP:LISTEN -t &>/dev/null 2>&1; then
    BUSY_PORTS+=("$p")
  fi
done

if [ ${#BUSY_PORTS[@]} -eq 0 ]; then
  info "All ${#PORTS[@]} required ports are free"
else
  fail "Ports already in use: ${BUSY_PORTS[*]}"
  echo "     Kill the processes or change the host-port mapping in jeeb-stack.yml"
fi

# 6. Disk space (warn below 10 GB)
AVAIL_KB=$(df -k . | tail -1 | awk '{print $4}')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [ "$AVAIL_GB" -lt 10 ]; then
  warn "Only ${AVAIL_GB} GB free disk space — Docker images may need ~8-12 GB"
else
  info "${AVAIL_GB} GB free disk space"
fi

echo ""
if [ "$FAIL" -ne 0 ]; then
  printf "${RED}Preflight FAILED — fix the above issues before deploying.${NC}\n"
  exit 1
else
  printf "${GREEN}All preflight checks passed.${NC}\n"
fi
