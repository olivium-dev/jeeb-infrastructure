#!/usr/bin/env bash
# ──────────────────────────────────────────────
# shorebird-patch.sh — Cut a Shorebird OTA patch for jeeb-mobile.
#
# Usage:
#   ./scripts/shorebird-patch.sh <android|ios> <staging|beta|production> \
#       <release-version> [flavor]
#
# Example:
#   ./scripts/shorebird-patch.sh android staging 1.4.0+12345 staging
#
# Required env:
#   SHOREBIRD_TOKEN   — CI token from `shorebird login:ci` (90-day rotation)
#
# Optional env:
#   MOBILE_DIR        — path to jeeb-mobile checkout (default: ../jeeb-mobile)
#   SHOREBIRD_DRY_RUN — when "true" prints the command but does not run it
#   LAST_GOOD_REF     — git ref used to detect native changes (default: the
#                       tag matching the release-version, e.g. v1.4.0)
#
# Exit codes:
#   0   patch published (or dry-run completed)
#   2   native code changed since LAST_GOOD_REF — patch refused
#   3   shorebird CLI not installed
#   4   bad arguments
#
# Why path-change check:
#   Shorebird can only patch Dart. If anyone touched android/, ios/, plugin
#   native bindings, or a pubspec dependency version, the patched runtime
#   will diverge from the installed AAB/IPA. Failing fast here is cheaper
#   than discovering the crash via Crashlytics 30 min later.
# ──────────────────────────────────────────────

set -euo pipefail

PLATFORM="${1:-}"
TRACK="${2:-}"
RELEASE_VERSION="${3:-}"
FLAVOR="${4:-${TRACK}}"

if [[ -z "$PLATFORM" || -z "$TRACK" || -z "$RELEASE_VERSION" ]]; then
  echo "Usage: $0 <android|ios> <staging|beta|production> <release-version> [flavor]" >&2
  exit 4
fi

case "$PLATFORM" in
  android|ios) ;;
  *) echo "ERROR: platform must be 'android' or 'ios' (got '$PLATFORM')" >&2; exit 4 ;;
esac

case "$TRACK" in
  staging|beta|production) ;;
  *) echo "ERROR: track must be staging|beta|production (got '$TRACK')" >&2; exit 4 ;;
esac

: "${SHOREBIRD_TOKEN:?SHOREBIRD_TOKEN must be set (mint via 'shorebird login:ci')}"

if ! command -v shorebird >/dev/null 2>&1; then
  echo "ERROR: shorebird CLI not on PATH. Install with:" >&2
  echo "  curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/shorebirdtech/install/main/install.sh | bash" >&2
  exit 3
fi

MOBILE_DIR="${MOBILE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/jeeb-mobile}"
if [[ ! -d "$MOBILE_DIR" ]]; then
  echo "ERROR: MOBILE_DIR '$MOBILE_DIR' does not exist" >&2
  exit 4
fi

# Reject patches that touched native code since the release ref. Default
# ref is the git tag matching the marketing version (everything before '+').
MARKETING_VERSION="${RELEASE_VERSION%%+*}"
LAST_GOOD_REF="${LAST_GOOD_REF:-v${MARKETING_VERSION}}"

cd "$MOBILE_DIR"

if git rev-parse --verify "$LAST_GOOD_REF" >/dev/null 2>&1; then
  echo "==> Checking for native / dependency changes since ${LAST_GOOD_REF}"
  # If any of these paths changed, refuse to cut a patch.
  if git diff --name-only "${LAST_GOOD_REF}"...HEAD \
       | grep -E '^(android/|ios/|pubspec\.yaml|pubspec\.lock)' >/dev/null; then
    echo "ERROR: native or pubspec changes detected since ${LAST_GOOD_REF}." >&2
    echo "       Shorebird can only patch Dart. Ship a full store build instead." >&2
    echo "       Offending files:" >&2
    git diff --name-only "${LAST_GOOD_REF}"...HEAD \
      | grep -E '^(android/|ios/|pubspec\.yaml|pubspec\.lock)' | sed 's/^/         /' >&2
    exit 2
  fi
else
  echo "WARNING: ref '${LAST_GOOD_REF}' not found — skipping native-change check." >&2
  echo "         Pass LAST_GOOD_REF=<commit-sha> to enforce." >&2
fi

CMD=(shorebird patch "$PLATFORM"
     --release-version "$RELEASE_VERSION"
     --track "$TRACK"
     --flavor "$FLAVOR"
     --no-confirm)

echo "==> ${CMD[*]}"
if [[ "${SHOREBIRD_DRY_RUN:-false}" == "true" ]]; then
  echo "DRY RUN — not executing"
  exit 0
fi

"${CMD[@]}"

echo "==> Patch published. Verify on https://console.shorebird.dev/"
echo "==> Channel:  ${TRACK}"
echo "==> Release:  ${RELEASE_VERSION}"
echo "==> Platform: ${PLATFORM}"
