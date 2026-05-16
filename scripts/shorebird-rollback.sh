#!/usr/bin/env bash
# ──────────────────────────────────────────────
# shorebird-rollback.sh — Roll back a bad Shorebird OTA patch.
#
# Shorebird does NOT have a "delete patch" primitive — installed clients
# that already pulled the bad patch keep it until they pull the next one.
# The only safe undo is to publish a FORWARD patch built from the
# last-good git ref against the same release-version. This mirrors how
# we roll backend releases (see production-rollback.sh).
#
# Usage:
#   ./scripts/shorebird-rollback.sh <android|ios> \
#       <staging|beta|production> <release-version> <last-good-ref>
#
# Example:
#   ./scripts/shorebird-rollback.sh android production 1.4.0+12345 v1.4.0
#
# Required env:
#   SHOREBIRD_TOKEN — CI token
#
# Optional env:
#   MOBILE_DIR        — path to jeeb-mobile checkout
#   SHOREBIRD_DRY_RUN — when "true" prints the command but does not run it
#
# Exit codes:
#   0   forward patch published (rollback effective for new pulls)
#   2   last-good ref does not exist
#   3   shorebird CLI not installed
#   4   bad arguments
# ──────────────────────────────────────────────

set -euo pipefail

PLATFORM="${1:-}"
TRACK="${2:-}"
RELEASE_VERSION="${3:-}"
LAST_GOOD_REF="${4:-}"

if [[ -z "$PLATFORM" || -z "$TRACK" || -z "$RELEASE_VERSION" || -z "$LAST_GOOD_REF" ]]; then
  echo "Usage: $0 <android|ios> <staging|beta|production> <release-version> <last-good-ref>" >&2
  exit 4
fi

: "${SHOREBIRD_TOKEN:?SHOREBIRD_TOKEN must be set}"

if ! command -v shorebird >/dev/null 2>&1; then
  echo "ERROR: shorebird CLI not on PATH" >&2
  exit 3
fi

MOBILE_DIR="${MOBILE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/jeeb-mobile}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$MOBILE_DIR"

if ! git rev-parse --verify "$LAST_GOOD_REF" >/dev/null 2>&1; then
  echo "ERROR: ref '$LAST_GOOD_REF' not found in $(pwd)" >&2
  exit 2
fi

START_EPOCH=$(date +%s)

echo "==> Saving current HEAD so we can return to it"
SAVED_REF="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$SAVED_REF" == "HEAD" ]]; then
  SAVED_REF="$(git rev-parse HEAD)"
fi
trap 'git checkout --quiet "$SAVED_REF"' EXIT

echo "==> Checking out last-good ref ${LAST_GOOD_REF}"
git checkout --quiet "$LAST_GOOD_REF"

# Re-use the patch script so the native-change check still runs.
echo "==> Cutting forward patch against release ${RELEASE_VERSION}"
LAST_GOOD_REF="$LAST_GOOD_REF" \
  "$SCRIPT_DIR/shorebird-patch.sh" "$PLATFORM" "$TRACK" "$RELEASE_VERSION" "$TRACK"

ELAPSED=$(( $(date +%s) - START_EPOCH ))
echo "==> Rollback patch published in ${ELAPSED}s."
echo "==> Existing clients on the bad patch will pick this up on next launch."
echo "==> Watch Crashlytics for ${RELEASE_VERSION} crash-free trend for the next 30 min."
