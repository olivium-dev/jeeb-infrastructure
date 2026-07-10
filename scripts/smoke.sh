#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT="$INFRA_DIR/SMOKE-REPORT.md"
TMPDIR="${TMPDIR:-/tmp}/jeeb-smoke-$$"
mkdir -p "$TMPDIR"

GW="http://localhost:10000"
TOKEN=""
REQ_ID=""
OFFER_ID=""
DEL_ID=""
DISPUTE_ID=""

PASS=0
FAIL=0
FLAG=0
TOTAL=0
RESULTS=()

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

# ── Helpers ──

run_curl() {
  local id="$1" label="$2" method="$3" url="$4"
  shift 4
  local body_file="$TMPDIR/${id}.body"
  local meta_file="$TMPDIR/${id}.meta"

  TOTAL=$((TOTAL + 1))

  local http_code time_total
  http_code=$(curl -sS -o "$body_file" -w "%{http_code}" \
    -X "$method" "$url" "$@" 2>"$TMPDIR/${id}.err") || true

  time_total=$(curl -sS -o /dev/null -w "%{time_total}" \
    -X "$method" "$url" "$@" 2>/dev/null) || time_total="0"

  local body_preview
  body_preview=$(head -c 200 "$body_file" 2>/dev/null | tr '\n' ' ' || echo "(empty)")

  local verdict="PASS"
  if [[ "$http_code" =~ ^2 ]]; then
    verdict="PASS"
    PASS=$((PASS + 1))
    printf "${GREEN}[PASS]${NC} %-6s %-7s %-55s %s  %ss\n" "$id" "$method" "$url" "$http_code" "$time_total"
  elif [[ "$http_code" =~ ^[45] ]]; then
    verdict="FAIL"
    FAIL=$((FAIL + 1))
    printf "${RED}[FAIL]${NC} %-6s %-7s %-55s %s  %ss\n" "$id" "$method" "$url" "$http_code" "$time_total"
  else
    verdict="FLAG"
    FLAG=$((FLAG + 1))
    printf "${YELLOW}[FLAG]${NC} %-6s %-7s %-55s %s  %ss\n" "$id" "$method" "$url" "$http_code" "$time_total"
  fi

  echo "${id}|${label}|${method}|${url}|${http_code}|${time_total}|${body_preview}|${verdict}" >> "$TMPDIR/results.csv"
  RESULTS+=("$id|$label|$method|$url|$http_code|$time_total|$body_preview|$verdict")
}

capture_json_field() {
  local file="$1" field="$2"
  jq -r ".$field // empty" "$file" 2>/dev/null || echo ""
}

# ══════════════════════════════════════════
#  LAYER A — Direct per-service health
# ══════════════════════════════════════════

echo ""
echo "══════════════════════════════════════════"
echo "  Layer A — Direct per-service health"
echo "══════════════════════════════════════════"

run_curl "A-01" "postgres"       GET "http://localhost:15432" || true
run_curl "A-02" "redis"          GET "http://localhost:16379" || true
run_curl "A-03" "gateway-live"   GET "$GW/health/live"
run_curl "A-04" "gateway-ready"  GET "$GW/health/ready"
run_curl "A-05" "user-mgmt"      GET "http://localhost:10001/api/User/check"
run_curl "A-06" "auth"           POST "http://localhost:10003/api/Client/SignUpGoogle" \
  -H "Content-Type: application/json" -d '{}'
run_curl "A-07" "delivery"       GET "http://localhost:10005/health"
run_curl "A-08" "geolocation"    GET "http://localhost:10006/health"
run_curl "A-09" "offer"          GET "http://localhost:10007/health"
run_curl "A-10" "realtime"       GET "http://localhost:10008/"
run_curl "A-11" "score-take"     GET "http://localhost:10009/health"
run_curl "A-12" "voice"          GET "http://localhost:10010/health/live"
run_curl "A-13" "contract"       GET "http://localhost:10011/health"
run_curl "A-14" "wallet"         GET "http://localhost:10014/health"
run_curl "A-15" "upg"            GET "http://localhost:10016/api/v1/gateways"
run_curl "A-16" "feedback"       GET "http://localhost:10020/Review/rating"
run_curl "A-18" "notification"   GET "http://localhost:10026/health"
run_curl "A-19" "chat"           GET "http://localhost:10028/api/health/check"
run_curl "A-20" "form-builder"   GET "http://localhost:10032/templates"
run_curl "A-21" "compliment"     GET "http://localhost:10036/health"
run_curl "A-22" "push"           GET "http://localhost:10040/health"
run_curl "A-23" "ban"            GET "http://localhost:10042/health"

# ══════════════════════════════════════════
#  LAYER B — Gateway readiness aggregation
# ══════════════════════════════════════════

echo ""
echo "══════════════════════════════════════════"
echo "  Layer B — Gateway readiness"
echo "══════════════════════════════════════════"

LAYER_B_BODY=$(curl -sS "$GW/health/ready" 2>/dev/null || echo '{"status":"unreachable"}')
LAYER_B_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$GW/health/ready" 2>/dev/null || echo "000")

if [ "$LAYER_B_CODE" = "200" ]; then
  printf "${GREEN}[PASS]${NC} B-01   GET     %-55s %s\n" "$GW/health/ready" "$LAYER_B_CODE"
  PASS=$((PASS + 1))
else
  printf "${YELLOW}[FLAG]${NC} B-01   GET     %-55s %s (upstream degraded — Layer C failures expected)\n" "$GW/health/ready" "$LAYER_B_CODE"
  FLAG=$((FLAG + 1))
fi
TOTAL=$((TOTAL + 1))

# ══════════════════════════════════════════
#  LAYER C — Gateway-through end-to-end
# ══════════════════════════════════════════

echo ""
echo "══════════════════════════════════════════"
echo "  Layer C — Gateway-through E2E"
echo "══════════════════════════════════════════"

# C-1: OTP request
run_curl "C-01" "otp-request" POST "$GW/v1/auth/otp/request" \
  -H "Content-Type: application/json" -d '{"phone":"+96170123456"}'

# C-2: OTP verify → capture token
run_curl "C-02" "otp-verify" POST "$GW/v1/auth/otp/verify" \
  -H "Content-Type: application/json" -d '{"phone":"+96170123456","code":"000000"}'
TOKEN=$(capture_json_field "$TMPDIR/C-02.body" "accessToken")
if [ -z "$TOKEN" ]; then
  TOKEN=$(capture_json_field "$TMPDIR/C-02.body" "access_token")
fi
if [ -z "$TOKEN" ]; then
  TOKEN="smoke-fallback-token"
  printf "${YELLOW}[!]${NC} Could not extract token — using fallback for remaining tests\n"
fi

# C-3: Legacy token issue
run_curl "C-03" "legacy-token" POST "$GW/auth/tokens" \
  -H "Content-Type: application/json" -d '{"userId":"smoke-user","roles":["client"]}'

# C-4: Role switch
run_curl "C-04" "role-switch" POST "$GW/v1/users/me/role/switch" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"role":"jeeber"}'

# C-5: List tiers
run_curl "C-05" "list-tiers" GET "$GW/tiers"

# C-6: Create delivery request
run_curl "C-06" "create-request" POST "$GW/requests" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"description":"smoke","tierId":"standard","pickup":{"lat":33.88,"lng":35.49},"dropoff":{"lat":33.90,"lng":35.51}}'
REQ_ID=$(capture_json_field "$TMPDIR/C-06.body" "id")
if [ -z "$REQ_ID" ]; then
  REQ_ID="smoke-req-id"
fi

# C-8: Submit offer
run_curl "C-08" "submit-offer" POST "$GW/requests/$REQ_ID/offers" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"fee":12.5,"etaMinutes":15}'
OFFER_ID=$(capture_json_field "$TMPDIR/C-08.body" "id")
if [ -z "$OFFER_ID" ]; then
  OFFER_ID="smoke-offer-id"
fi

# C-9: Accept offer
run_curl "C-09" "accept-offer" POST "$GW/offers/$OFFER_ID/accept" \
  -H "Authorization: Bearer $TOKEN"

# C-10: GPS update
run_curl "C-10" "gps-update" POST "$GW/location/update" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"points":[{"lat":33.89,"lng":35.50,"timestamp":"2026-05-19T13:00:00Z"}]}'

# C-11: Advance delivery status
DEL_ID="$REQ_ID"
run_curl "C-11" "status-picked" PATCH "$GW/deliveries/$DEL_ID/status" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"picked"}'

# C-12: Cash settlement
run_curl "C-12" "cash-settle" POST "$GW/deliveries/$DEL_ID/settle" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"goodsCost":10.0,"paymentMethod":"cash"}'

# C-13: Wallet balance
run_curl "C-13" "wallet-balance" GET "$GW/api/wallet/balance" \
  -H "Authorization: Bearer $TOKEN"

# C-14: Earnings summary
run_curl "C-14" "earnings-summary" GET "$GW/api/earnings/summary" \
  -H "Authorization: Bearer $TOKEN"

# C-15: Earnings statement PDF
run_curl "C-15" "earnings-pdf" GET "$GW/api/earnings/statement?period=2026-W20" \
  -H "Authorization: Bearer $TOKEN"

# C-16: Mutual blind rating
run_curl "C-16" "blind-rate" POST "$GW/api/deliveries/$DEL_ID/rate" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"stars":5,"comment":"smoke"}'

# C-17: Send chat message
run_curl "C-17" "chat-msg" POST "$GW/chat/messages" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"recipientId":"other-user","type":"text","text":"hello from smoke"}'

# C-18: Register push device
run_curl "C-18" "push-device" POST "$GW/push/devices" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"platform":"fcm","token":"smoke-token-abc"}'

# C-19: Cancel delivery
run_curl "C-19" "cancel-delivery" POST "$GW/deliveries/$DEL_ID/cancel" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"reason":"smoke"}'

# C-20: File dispute + admin resolve
run_curl "C-20a" "file-dispute" POST "$GW/deliveries/$DEL_ID/dispute" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"category":"damaged","description":"smoke","photoUrls":[]}'
DISPUTE_ID=$(capture_json_field "$TMPDIR/C-20a.body" "id")
if [ -z "$DISPUTE_ID" ]; then
  DISPUTE_ID="smoke-dispute-id"
fi
run_curl "C-20b" "resolve-dispute" PUT "$GW/admin/disputes/$DISPUTE_ID/resolve" \
  -H "Authorization: Bearer admin-token" -H "Content-Type: application/json" \
  -d '{"action":"resolve","resolution":"refund"}'

# C-21: Prohibited items scan
run_curl "C-21" "prohibited-scan" POST "$GW/prohibited-items/scan" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"description":"deliver smoke package"}'

# C-22: KYC submit
run_curl "C-22" "kyc-submit" POST "$GW/kyc/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -F "vehicleType=motorcycle" -F "vehicleRegistration=ABC-123" \
  -F "idFront=@/dev/null;filename=id.jpg;type=image/jpeg" \
  -F "idBack=@/dev/null;filename=id.jpg;type=image/jpeg" \
  -F "selfie=@/dev/null;filename=selfie.jpg;type=image/jpeg"

# C-23: Jeeber availability toggle
run_curl "C-23" "availability" PATCH "$GW/jeebers/me/availability" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"online":true,"vehicleType":"motorcycle","latitude":33.89,"longitude":35.50}'

# C-24: Voice transcription
run_curl "C-24" "transcribe" POST "$GW/transcribe" \
  -H "Content-Type: application/json" \
  -d '{"audioBase64":"UklGRiQAAABXQVZF","fileName":"smoke.wav","contentType":"audio/wav"}'

# C-25: Admin online jeebers per zone
run_curl "C-25" "admin-zones" GET "$GW/admin/zones/online-jeebers" \
  -H "Authorization: Bearer admin-token"

# ══════════════════════════════════════════
#  LAYER D — Direct curls (not behind gateway)
# ══════════════════════════════════════════

echo ""
echo "══════════════════════════════════════════"
echo "  Layer D — Direct service curls"
echo "══════════════════════════════════════════"

run_curl "D-01" "compliment-create" POST "http://localhost:10036/api/v1/compliments/" \
  -H "Content-Type: application/json" -d '{"fromUserId":"u1","toUserId":"u2","kind":"polite"}'

run_curl "D-02" "contract-create" POST "http://localhost:10011/v1/contracts" \
  -H "Content-Type: application/json" -d '{"templateId":"jeeber-tos-v1","userId":"u1"}'

run_curl "D-03" "feedback-rating" GET "http://localhost:10020/Review/rating?userId=u1"

run_curl "D-04" "form-components" GET "http://localhost:10032/components"

run_curl "D-05" "upg-gateways" GET "http://localhost:10016/api/v1/gateways"

run_curl "D-06" "upg-payment" POST "http://localhost:10016/api/v1/payments" \
  -H "Content-Type: application/json" -d '{"gateway":"cod_jeeb","amount":12.5,"currency":"USD"}'

run_curl "D-07" "ban-status" GET "http://localhost:10042/api/v1/ban/smoke-user/status"

run_curl "D-08" "offer-ready" GET "http://localhost:10007/health/ready"

# ══════════════════════════════════════════
#  Generate SMOKE-REPORT.md
# ══════════════════════════════════════════

echo ""
echo "══════════════════════════════════════════"
echo "  Generating SMOKE-REPORT.md"
echo "══════════════════════════════════════════"

{
  echo "# Jeeb Backend — Smoke Test Report"
  echo ""
  echo "**Date:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "**Summary:** ${PASS}/${TOTAL} passed, ${FAIL} failed, ${FLAG} flagged"
  echo ""

  # Section 1: Stack summary
  echo "## 1. Stack Summary"
  echo ""
  echo '```'
  docker stack services jeeb 2>/dev/null || echo "(stack not available — images may not be deployed)"
  echo '```'
  echo ""

  # Section 2: Layer A
  echo "## 2. Layer A — Per-Service Health"
  echo ""
  echo "| ID | Service | Port | Health Path | HTTP | Latency | Verdict |"
  echo "|---|---------|------|-------------|------|---------|---------|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r id label method url code latency body verdict <<< "$r"
    if [[ "$id" == A-* ]]; then
      port=$(echo "$url" | grep -oE ':[0-9]+' | tail -1 | tr -d ':')
      path=$(echo "$url" | sed 's|http://[^/]*||')
      echo "| $id | $label | $port | ${path:-/} | $code | ${latency}s | $verdict |"
    fi
  done
  echo ""

  # Section 3: Layer B
  echo "## 3. Layer B — Gateway Readiness"
  echo ""
  echo "**HTTP $LAYER_B_CODE**"
  echo ""
  echo '```json'
  echo "$LAYER_B_BODY" | jq . 2>/dev/null || echo "$LAYER_B_BODY"
  echo '```'
  echo ""

  # Section 4: Layer C
  echo "## 4. Layer C — Gateway-Through E2E"
  echo ""
  echo "| ID | Label | Method | Path | HTTP | Latency | Body (first 200 chars) | Verdict |"
  echo "|---|-------|--------|------|------|---------|------------------------|---------|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r id label method url code latency body verdict <<< "$r"
    if [[ "$id" == C-* ]]; then
      path=$(echo "$url" | sed 's|http://[^/]*||')
      safe_body=$(echo "$body" | sed 's/|/∣/g' | head -c 120)
      echo "| $id | $label | $method | $path | $code | ${latency}s | \`${safe_body}\` | $verdict |"
    fi
  done
  echo ""

  # Section 5: Layer D
  echo "## 5. Layer D — Direct Service Curls"
  echo ""
  echo "| ID | Label | Method | URL | HTTP | Latency | Verdict |"
  echo "|---|-------|--------|-----|------|---------|---------|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r id label method url code latency body verdict <<< "$r"
    if [[ "$id" == D-* ]]; then
      echo "| $id | $label | $method | $url | $code | ${latency}s | $verdict |"
    fi
  done
  echo ""

  # Section 6: Failure summary
  echo "## 6. Failure Summary"
  echo ""
  HAS_FAILURES=0
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r id label method url code latency body verdict <<< "$r"
    if [ "$verdict" = "FAIL" ]; then
      HAS_FAILURES=1
      echo "- **$id ($label):** \`$method $url\` → HTTP $code"
      if [ -f "$TMPDIR/${id}.body" ]; then
        echo '  ```'
        head -c 500 "$TMPDIR/${id}.body" 2>/dev/null || true
        echo '  ```'
      fi
    fi
  done
  if [ "$HAS_FAILURES" -eq 0 ]; then
    echo "No failures."
  fi
  echo ""

  # Section 7: Next actions
  echo "## 7. Next Actions"
  echo ""
  if [ "$FAIL" -gt 0 ]; then
    echo "- [ ] Investigate failed services (see failure summary above)"
    echo "- [ ] Check \`docker service logs jeeb_<service>\` for crash loops"
    echo "- [ ] Verify environment variables are correctly injected"
  fi
  if [ "$FLAG" -gt 0 ]; then
    echo "- [ ] Review flagged results — may be expected (e.g. Whisper without API key, Postgres/Redis TCP probes)"
  fi
  echo "- [ ] Run Pact/Schemathesis contract tests as follow-up"
  echo "- [ ] Run load tests with oha/vegeta for perf baselines"
  echo ""

  # Section 8: Appendix
  echo "## 8. Appendix — Stack State"
  echo ""
  echo '```'
  docker stack ps jeeb --no-trunc 2>/dev/null || echo "(stack not available)"
  echo '```'
  echo ""

  if [ "$FAIL" -gt 0 ]; then
    echo "### Service Logs (failed services, last 200 lines)"
    echo ""
    for r in "${RESULTS[@]}"; do
      IFS='|' read -r id label method url code latency body verdict <<< "$r"
      if [ "$verdict" = "FAIL" ]; then
        svc_name=$(echo "$label" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')
        echo "#### jeeb_${svc_name}"
        echo '```'
        docker service logs --tail 200 "jeeb_${svc_name}" 2>/dev/null || echo "(no logs available for jeeb_${svc_name})"
        echo '```'
        echo ""
      fi
    done
  fi

} > "$REPORT"

echo ""
echo "══════════════════════════════════════════"
echo "  SMOKE TEST COMPLETE"
echo "══════════════════════════════════════════"
printf "  Passed:  ${GREEN}%d${NC}\n" "$PASS"
printf "  Failed:  ${RED}%d${NC}\n" "$FAIL"
printf "  Flagged: ${YELLOW}%d${NC}\n" "$FLAG"
printf "  Total:   %d\n" "$TOTAL"
echo ""
echo "  Report: $REPORT"
echo "══════════════════════════════════════════"

rm -rf "$TMPDIR"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
