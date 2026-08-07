#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-lib.sh
. "${SCRIPT_DIR}/release-lib.sh"

if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [release-id]" >&2
  exit 2
fi

require_command "$PYTHON_BIN"
mkdir -p "$RELEASES_DIR"
acquire_deploy_lock

CURRENT_TARGET=""
ORIGINAL_PREVIOUS=""
LINKS_CHANGED=0
ROLLBACK_COMMITTED=0

restore_links() {
  [ "$LINKS_CHANGED" -eq 1 ] || return 0
  atomic_link "$CURRENT_TARGET" "$CURRENT_LINK"
  if [ -n "$ORIGINAL_PREVIOUS" ]; then
    atomic_link "$ORIGINAL_PREVIOUS" "$PREVIOUS_LINK"
  else
    [ ! -L "$PREVIOUS_LINK" ] || unlink "$PREVIOUS_LINK"
  fi
  local current_release_id
  current_release_id="$(release_id_for "$CURRENT_TARGET")"
  test_nginx >/dev/null 2>&1 && reload_nginx >/dev/null 2>&1 \
    && verify_http_release "$current_release_id" >/dev/null 2>&1 || true
  LINKS_CHANGED=0
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [ "$status" -ne 0 ] && [ "$ROLLBACK_COMMITTED" -eq 0 ]; then
    restore_links
  fi
  release_deploy_lock
  exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

CURRENT_TARGET="$(resolve_release_link "$CURRENT_LINK")"
if [ -L "$PREVIOUS_LINK" ]; then
  ORIGINAL_PREVIOUS="$(resolve_release_link "$PREVIOUS_LINK")"
fi

if [ "$#" -eq 1 ]; then
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || die "release-id contains unsafe characters"
  TARGET="${RELEASES_DIR}/$1"
  [ -d "$TARGET" ] && [ ! -L "$TARGET" ] || die "requested release does not exist: $1"
  assert_release_path "$TARGET" || die "requested release is outside $RELEASES_DIR"
else
  TARGET="$(resolve_release_link "$PREVIOUS_LINK")"
fi

TARGET="$(canonical_path "$TARGET")"
[ "$TARGET" != "$CURRENT_TARGET" ] || die "requested rollback target is already active"
TARGET_RELEASE_ID="$(release_id_for "$TARGET")"
validate_release "$TARGET" --expected-release-id "$TARGET_RELEASE_ID"

# A successful rollback makes the formerly-current release the roll-forward target.
LINKS_CHANGED=1
atomic_link "$CURRENT_TARGET" "$PREVIOUS_LINK"
atomic_link "$TARGET" "$CURRENT_LINK"

if activate_and_verify "$TARGET_RELEASE_ID"; then
  ROLLBACK_COMMITTED=1
  echo "Rolled back Jeeb CMS to release $TARGET_RELEASE_ID."
  exit 0
fi

echo "Rollback checks failed; restoring the original active release." >&2
exit 1
