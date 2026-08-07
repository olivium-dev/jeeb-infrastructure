#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-lib.sh
. "${SCRIPT_DIR}/release-lib.sh"

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--runtime" ]; }; then
  echo "Usage: $0 [--runtime]" >&2
  exit 2
fi

require_command "$PYTHON_BIN"
TARGET="$(resolve_release_link "$CURRENT_LINK")"
RELEASE_ID="$(release_id_for "$TARGET")"
validate_release "$TARGET" --expected-release-id "$RELEASE_ID"

if [ "${1:-}" = "--runtime" ]; then
  test_nginx
  verify_http_release "$RELEASE_ID"
fi

echo "Current Jeeb CMS release is valid: $RELEASE_ID"
