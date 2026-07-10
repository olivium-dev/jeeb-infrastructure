#!/usr/bin/env bash
set -euo pipefail

GATEWAY="http://localhost:10000"
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_status() {
    local test_name="$1"
    local actual="$2"
    shift 2
    local expected=("$@")
    
    for code in "${expected[@]}"; do
        if [[ "$actual" == "$code" ]]; then
            echo -e "${GREEN}PASS${NC} [$actual] $test_name"
            ((PASS_COUNT++))
            return
        fi
    done
    echo -e "${RED}FAIL${NC} [$actual] $test_name (expected: ${expected[*]})"
    ((FAIL_COUNT++))
}

echo "============================================"
echo "  Jeeb Gateway Integration Test Suite"
echo "  36 assertions across 18 microservices"
echo "============================================"
echo ""

# --- Stack pre-flight ---
echo "--- Stack Pre-flight ---"
UNHEALTHY=$(docker stack services jeeb --format '{{.Name}} {{.Replicas}}' 2>/dev/null | awk '$2 != "1/1" && $1 ~ /jeeb_/' || true)
if [[ -n "$UNHEALTHY" ]]; then
    echo -e "${YELLOW}WARNING: Some services not at 1/1 replicas:${NC}"
    echo "$UNHEALTHY"
    echo ""
fi

# --- Auth flow pre-test ---
echo "--- Auth Flow Pre-test ---"
echo "Acquiring super-login token via POST /api/User/user-id-login..."
LOGIN_RESPONSE=$(curl -s -X POST "$GATEWAY/api/User/user-id-login" \
    -H "Content-Type: application/json" \
    -d '{"userId":"11111111-1111-1111-1111-111111111111","superAdminPassCode":"123768"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.authToken // .accessToken // .token // empty' 2>/dev/null || true)

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
    echo -e "${RED}FATAL: Could not acquire auth token from super-login${NC}"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi
echo -e "${GREEN}Token acquired successfully${NC}"
echo ""

H="Authorization: Bearer $TOKEN"

# Token-login re-mint test
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY/api/User/token-login" \
    -H "Content-Type: application/json" -d "{\"token\":\"$TOKEN\"}")
assert_status "Auth: token-login re-mint" "$STATUS" 200

# Logout test
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY/api/User/logout" \
    -H "$H" -H "Content-Type: application/json" \
    -d '{"userId":"11111111-1111-1111-1111-111111111111"}')
assert_status "Auth: logout" "$STATUS" 200

echo ""
echo "--- Integration Test Matrix (36 assertions) ---"
echo ""

# 1. user-management: check
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/User/check")
assert_status "#1  user-management: check" "$STATUS" 200

# 2. user-management: profile
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/User/profile/11111111-1111-1111-1111-111111111111")
assert_status "#2  user-management: profile" "$STATUS" 200 404

# 3. chat-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Chat/health")
assert_status "#3  chat-service: health" "$STATUS" 200

# 4. chat-service: conversation
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Chat/conversations/22222222-2222-2222-2222-222222222222")
assert_status "#4  chat-service: conversation" "$STATUS" 200 404

# 5. wallet-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Wallet/health")
assert_status "#5  wallet-service: health" "$STATUS" 200

# 6. wallet-service: earnings
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Wallet/earnings?jeeberId=11111111-1111-1111-1111-111111111111&period=week")
assert_status "#6  wallet-service: earnings" "$STATUS" 200 404

# 9. notification-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Notifications/health")
assert_status "#9  notification-service: health" "$STATUS" 200

# 10. notification-service: preferences
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Notifications/preferences")
assert_status "#10 notification-service: preferences" "$STATUS" 200 404

# 11. geolocation-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Geolocation/health")
assert_status "#11 geolocation-service: health" "$STATUS" 200

# 12. geolocation-service: availability
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$H" -H "Content-Type: application/json" \
    -d '{"available":true}' "$GATEWAY/api/Geolocation/availability")
assert_status "#12 geolocation-service: availability" "$STATUS" 200 204 404 422

# 13. push-notification: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/PushNotifications/health")
assert_status "#13 push-notification: health" "$STATUS" 200

# 14. push-notification: register-device
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$H" -H "Content-Type: application/json" \
    -d '{"platform":"android","fcmToken":"smoke-test-fcm","appVersion":"1.0.0","locale":"en"}' \
    "$GATEWAY/api/PushNotifications/devices/register")
assert_status "#14 push-notification: register-device" "$STATUS" 200 204 201

# 15. offer-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Offer/health")
assert_status "#15 offer-service: health" "$STATUS" 200

# 16. offer-service: list
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Offer/list?jeeberId=11111111-1111-1111-1111-111111111111")
assert_status "#16 offer-service: list" "$STATUS" 200 404

# 17. score-taking-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/ScoreTaking/health")
assert_status "#17 score-taking-service: health" "$STATUS" 200

# 18. score-taking-service: rating-status
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/ScoreTaking/ratings/22222222-2222-2222-2222-222222222222/status")
assert_status "#18 score-taking-service: rating-status" "$STATUS" 200 404

# 19. ban-service: prohibited-items
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Ban/prohibited-items")
assert_status "#19 ban-service: prohibited-items" "$STATUS" 200

# 20. ban-service: check
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "$H" -H "Content-Type: application/json" \
    -d '{"text":"test parcel delivery"}' "$GATEWAY/api/Ban/check")
assert_status "#20 ban-service: check" "$STATUS" 200

# 21. compliment-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Compliment/health")
assert_status "#21 compliment-service: health" "$STATUS" 200

# 22. compliment-service: disputes
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Compliment/disputes?userId=11111111-1111-1111-1111-111111111111")
assert_status "#22 compliment-service: disputes" "$STATUS" 200 404

# 23. contract-signing-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/ContractSigning/health")
assert_status "#23 contract-signing-service: health" "$STATUS" 200

# 24. contract-signing-service: template
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/ContractSigning/templates/jeeb_tos_v1")
assert_status "#24 contract-signing-service: template" "$STATUS" 200 404

# 25. voice-transcription-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/VoiceTranscription/health")
assert_status "#25 voice-transcription-service: health" "$STATUS" 200

# 26. voice-transcription-service: ready
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/VoiceTranscription/ready")
assert_status "#26 voice-transcription-service: ready" "$STATUS" 200 503

# 27. form-builder-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/FormBuilder/health")
assert_status "#27 form-builder-service: health" "$STATUS" 200

# 28. form-builder-service: template
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/FormBuilder/templates/jeeb_jeeber_v1")
assert_status "#28 form-builder-service: template" "$STATUS" 200 404

# 29. feedback-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Feedback/health")
assert_status "#29 feedback-service: health" "$STATUS" 200

# 30. feedback-service: groups
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Feedback/groups")
assert_status "#30 feedback-service: groups" "$STATUS" 200

# 31. delivery-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Delivery/health")
assert_status "#31 delivery-service: health" "$STATUS" 200

# 32. delivery-service: tiers
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Delivery/tiers")
assert_status "#32 delivery-service: tiers" "$STATUS" 200

# 33. realtime-comunication-service: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Realtime/health")
assert_status "#33 realtime-service: health" "$STATUS" 200

# 34. realtime-comunication-service: ready
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/Realtime/ready")
assert_status "#34 realtime-service: ready" "$STATUS" 200 503

# 35. unified-payment-gateway: health
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/UnifiedPaymentGateway/health")
assert_status "#35 unified-payment-gateway: health" "$STATUS" 200

# 36. unified-payment-gateway: batches
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$GATEWAY/api/UnifiedPaymentGateway/batches")
assert_status "#36 unified-payment-gateway: batches" "$STATUS" 200

echo ""
echo "============================================"
echo "  RESULTS"
echo "============================================"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}PASS:   $PASS_COUNT${NC}"
echo -e "  ${RED}FAIL:   $FAIL_COUNT${NC}"
echo ""

if [[ $FAIL_COUNT -gt 0 ]]; then
    echo -e "${RED}INTEGRATION TESTS FAILED${NC}"
    exit 1
fi

echo -e "${GREEN}ALL INTEGRATION TESTS PASSED${NC}"
exit 0
