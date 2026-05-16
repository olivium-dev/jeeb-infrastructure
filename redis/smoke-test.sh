#!/usr/bin/env bash
# Redis smoke test — exercises every workload class served by the instance.
# Run after `docker compose up -d` from the jeeb-infrastructure root.
#
# Usage: ./redis/smoke-test.sh
# Env:   REDIS_CONTAINER (default: jeeb-infrastructure-redis-1)

set -euo pipefail

CONTAINER="${REDIS_CONTAINER:-$(docker compose ps -q redis)}"
if [[ -z "${CONTAINER}" ]]; then
    echo "FAIL: cannot find redis container — is docker compose up?" >&2
    exit 1
fi

cli() { docker exec -i "${CONTAINER}" redis-cli "$@"; }

pass() { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1" >&2; exit 1; }

echo "Redis smoke test against container ${CONTAINER}"

# 1. PING
[[ "$(cli PING)" == "PONG" ]] || fail "PING"
pass "PING"

# 2. maxmemory + eviction policy are loaded from redis.conf
policy="$(cli CONFIG GET maxmemory-policy | tail -n1)"
[[ "${policy}" == "volatile-lru" ]] || fail "maxmemory-policy=${policy} (expected volatile-lru)"
pass "maxmemory-policy=${policy}"

maxmem="$(cli CONFIG GET maxmemory | tail -n1)"
[[ "${maxmem}" != "0" ]] || fail "maxmemory is 0 (unlimited)"
pass "maxmemory=${maxmem}"

# 3. Persistence: AOF + RDB enabled
aof="$(cli CONFIG GET appendonly | tail -n1)"
[[ "${aof}" == "yes" ]] || fail "appendonly=${aof}"
pass "appendonly=yes"

save="$(cli CONFIG GET save | tail -n1)"
[[ -n "${save}" ]] || fail "RDB save policy empty"
pass "save policy: ${save}"

# 4. GEO commands — Jeeber location flow
cli DEL geo:smoke >/dev/null
cli GEOADD geo:smoke 35.5018 33.8938 "jeeber-a" >/dev/null
cli GEOADD geo:smoke 35.5100 33.9000 "jeeber-b" >/dev/null
hits="$(cli GEOSEARCH geo:smoke FROMLONLAT 35.5018 33.8938 BYRADIUS 5 km ASC | wc -l | tr -d ' ')"
[[ "${hits}" == "2" ]] || fail "GEOSEARCH returned ${hits} (expected 2)"
pass "GEOSEARCH found ${hits} jeebers within 5km"
cli DEL geo:smoke >/dev/null

# 5. Pub/Sub — chat channel round-trip
out="$(mktemp)"
docker exec -i "${CONTAINER}" timeout 3 redis-cli SUBSCRIBE chat:smoke >"${out}" 2>&1 &
sub_pid=$!
sleep 1
delivered="$(cli PUBLISH chat:smoke "hello")"
[[ "${delivered}" -ge 1 ]] || fail "PUBLISH delivered to ${delivered} subscribers"
pass "PUBLISH delivered to ${delivered} subscriber(s)"
wait "${sub_pid}" 2>/dev/null || true
grep -q "hello" "${out}" || fail "subscriber did not receive message"
pass "subscriber received message"
rm -f "${out}"

# 6. Key expiration — proves TTL plumbing works for the cache/rate-limit class
cli SET smoke:ttl "x" EX 1 >/dev/null
[[ "$(cli GET smoke:ttl)" == "x" ]] || fail "SET smoke:ttl"
sleep 2
[[ "$(cli EXISTS smoke:ttl)" == "0" ]] || fail "smoke:ttl did not expire"
pass "TTL expiration works"

echo "OK — Redis is configured correctly for jeeb workloads"
