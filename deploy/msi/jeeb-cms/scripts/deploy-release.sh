#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-lib.sh
. "${SCRIPT_DIR}/release-lib.sh"

usage() {
  echo "Usage: $0 --expected-manifest-sha256 <sha256> <release-artifact-directory>" >&2
}

EXPECTED_MANIFEST_SHA256="${JEEB_CMS_EXPECTED_MANIFEST_SHA256:-}"
if [ "$#" -eq 3 ] && [ "$1" = "--expected-manifest-sha256" ]; then
  if [ -n "$EXPECTED_MANIFEST_SHA256" ] && [ "$EXPECTED_MANIFEST_SHA256" != "$2" ]; then
    die "CLI and environment expected manifest digests disagree"
  fi
  EXPECTED_MANIFEST_SHA256="$2"
  shift 2
fi
[ "$#" -eq 1 ] || { usage; exit 2; }
[ -n "$EXPECTED_MANIFEST_SHA256" ] || die "an externally trusted manifest SHA-256 is required"
require_command "$PYTHON_BIN"

ARTIFACT_DIR="$(canonical_path "$1")"
[ -d "$ARTIFACT_DIR" ] || die "artifact directory does not exist: $1"
verify_expected_manifest() {
  local release_dir="$1"
  [[ "$EXPECTED_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] \
    || die "expected manifest digest must be a lowercase SHA-256"
  [ "$(sha256_file "$release_dir/SHA256SUMS")" = "$EXPECTED_MANIFEST_SHA256" ] \
    || die "release SHA256SUMS does not match the externally supplied digest: $release_dir"
}

verify_expected_manifest "$ARTIFACT_DIR"
validate_release "$ARTIFACT_DIR"
RELEASE_ID="$(release_id_for "$ARTIFACT_DIR")"

if [ "$CMS_ROOT" = "/opt/jeeb-cms" ] && [ "$(id -u)" -ne 0 ]; then
  die "production deployment to /opt/jeeb-cms must run as root"
fi

umask 022
mkdir -p "$RELEASES_DIR"
acquire_deploy_lock

STAGING_DIR=""

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [ -n "$STAGING_DIR" ] && [ -d "$STAGING_DIR" ]; then
    case "$STAGING_DIR" in
      "$RELEASES_DIR"/.*.incoming.*)
        chmod -R u+w "$STAGING_DIR" 2>/dev/null || true
        rm -rf -- "$STAGING_DIR"
        ;;
      *) echo "WARNING: refusing to clean unexpected staging path: $STAGING_DIR" >&2 ;;
    esac
  fi
  release_deploy_lock
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

FINAL_DIR="${RELEASES_DIR}/${RELEASE_ID}"
if [ -e "$FINAL_DIR" ]; then
  [ -d "$FINAL_DIR" ] && [ ! -L "$FINAL_DIR" ] || die "release target is not a real directory: $FINAL_DIR"
  validate_release "$FINAL_DIR" --expected-release-id "$RELEASE_ID"
  verify_expected_manifest "$FINAL_DIR"
  cmp -s "$ARTIFACT_DIR/SHA256SUMS" "$FINAL_DIR/SHA256SUMS" || die "releaseId already exists with different checksums"
  echo "Release $RELEASE_ID already staged; reusing verified immutable directory."
else
  STAGING_DIR="$(mktemp -d "${RELEASES_DIR}/.${RELEASE_ID}.incoming.XXXXXX")"
  cp -a "$ARTIFACT_DIR/." "$STAGING_DIR/"
  validate_release "$STAGING_DIR" --expected-release-id "$RELEASE_ID"
  # Close the source-check/copy TOCTOU window: the copied bytes, not merely the
  # mutable transport directory, must still match the trusted build digest.
  verify_expected_manifest "$STAGING_DIR"
  RELEASE_OWNER="${JEEB_CMS_OWNER-root:root}"
  if [ -n "$RELEASE_OWNER" ]; then
    chown -R "$RELEASE_OWNER" "$STAGING_DIR"
  fi
  chmod u+rwx "$STAGING_DIR"
  mv "$STAGING_DIR" "$FINAL_DIR"
  STAGING_DIR=""
  chmod -R a-w,u+rX,go+rX "$FINAL_DIR"
  echo "Staged immutable release $RELEASE_ID."
fi
FINAL_DIR="$(canonical_path "$FINAL_DIR")"

test_nginx || die "nginx configuration preflight failed"
verify_dependencies || die "runtime dependency preflight failed"
LEGACY_RELEASE_LINK="${CMS_ROOT}/previous"
if [ -L "$LEGACY_RELEASE_LINK" ]; then
  unlink "$LEGACY_RELEASE_LINK"
elif [ -e "$LEGACY_RELEASE_LINK" ]; then
  die "refusing to remove non-symlink legacy release pointer: $LEGACY_RELEASE_LINK"
fi
atomic_link "$FINAL_DIR" "$CURRENT_LINK"

if activate_and_verify "$RELEASE_ID"; then
  echo "Activated Jeeb CMS release $RELEASE_ID."
  exit 0
fi

echo "Activation checks failed; the candidate remains active for diagnosis and a corrected forward deployment." >&2
exit 1
