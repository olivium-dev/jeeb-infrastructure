#!/usr/bin/env bash

set -Eeuo pipefail

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${JEEB_CMS_PYTHON_BIN:-python3}"
VALIDATOR="${JEEB_CMS_VALIDATOR:-${TOOLS_DIR}/validate-release.py}"
CMS_ROOT="${JEEB_CMS_ROOT:-/opt/jeeb-cms}"
RELEASES_DIR="${CMS_ROOT}/releases"
CURRENT_LINK="${CMS_ROOT}/current"
PREVIOUS_LINK="${CMS_ROOT}/previous"
NGINX_BIN="${JEEB_CMS_NGINX_BIN:-nginx}"
SYSTEMCTL_BIN="${JEEB_CMS_SYSTEMCTL_BIN:-systemctl}"
CURL_BIN="${JEEB_CMS_CURL_BIN:-curl}"
HEALTH_URL="${JEEB_CMS_HEALTH_URL:-http://127.0.0.1:10100/healthz}"
GATEWAY_READY_URL="${JEEB_CMS_GATEWAY_READY_URL:-http://127.0.0.1:10100/gateway/health/ready}"
RELEASE_URL="${JEEB_CMS_RELEASE_URL:-http://127.0.0.1:10100/release.json}"
MANIFEST_URL="${JEEB_CMS_MANIFEST_URL:-http://127.0.0.1:10100/SHA256SUMS}"
NGINX_SERVICE="${JEEB_CMS_NGINX_SERVICE:-nginx.service}"
ACTIVATOR="${JEEB_CMS_ACTIVATOR:-native}"
DOCKER_HELPER="${JEEB_CMS_DOCKER_HELPER:-${TOOLS_DIR}/docker-nginx.sh}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command is unavailable: $1"
}

canonical_path() {
  "$PYTHON_BIN" - "$1" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
}

assert_release_path() {
  local candidate releases
  candidate="$(canonical_path "$1")"
  releases="$(canonical_path "$RELEASES_DIR")"
  "$PYTHON_BIN" - "$candidate" "$releases" <<'PY'
import os
import sys
candidate, releases = sys.argv[1:]
if os.path.commonpath([candidate, releases]) != releases or candidate == releases:
    raise SystemExit(1)
PY
}

resolve_release_link() {
  local link_path="$1"
  [ -L "$link_path" ] || die "$link_path is not a symbolic link"
  local resolved
  resolved="$(canonical_path "$link_path")"
  [ -d "$resolved" ] || die "$link_path points to a missing release"
  assert_release_path "$resolved" || die "$link_path points outside $RELEASES_DIR"
  printf '%s\n' "$resolved"
}

atomic_link() {
  local target="$1" link_path="$2" next_link="${2}.next.$$"
  if [ -e "$link_path" ] && [ ! -L "$link_path" ]; then
    die "refusing to replace non-symlink path: $link_path"
  fi
  [ ! -e "$next_link" ] && [ ! -L "$next_link" ] || die "temporary link already exists: $next_link"
  "$PYTHON_BIN" - "$target" "$link_path" "$next_link" <<'PY'
import os
import sys

target, link_path, next_link = sys.argv[1:]
try:
    # Relative pointers remain valid when a user-owned CMS root is mounted at
    # /opt/jeeb-cms inside the no-sudo nginx container.
    link_directory = os.path.realpath(os.path.dirname(link_path))
    os.symlink(os.path.relpath(target, link_directory), next_link)
    os.replace(next_link, link_path)
finally:
    try:
        os.unlink(next_link)
    except FileNotFoundError:
        pass
PY
}

validate_release() {
  local release_dir="$1"
  shift
  "$PYTHON_BIN" "$VALIDATOR" "$release_dir" "$@"
}

release_id_for() {
  "$PYTHON_BIN" "$VALIDATOR" "$1" --print-release-id
}

sha256_file() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib
import sys

with open(sys.argv[1], "rb") as source:
    print(hashlib.sha256(source.read()).hexdigest())
PY
}

test_nginx() {
  if [ "$ACTIVATOR" = "docker" ]; then
    [ -x "$DOCKER_HELPER" ] || {
      echo "ERROR: Docker nginx helper is unavailable: $DOCKER_HELPER" >&2
      return 1
    }
    "$DOCKER_HELPER" test || return 1
    return 0
  fi
  [ "$ACTIVATOR" = "native" ] || {
    echo "ERROR: unsupported JEEB_CMS_ACTIVATOR: $ACTIVATOR" >&2
    return 1
  }
  if ! command -v "$NGINX_BIN" >/dev/null 2>&1; then
    echo "ERROR: required command is unavailable: $NGINX_BIN" >&2
    return 1
  fi
  "$NGINX_BIN" -t || return 1
}

reload_nginx() {
  if [ "$ACTIVATOR" = "docker" ]; then
    [ -x "$DOCKER_HELPER" ] || {
      echo "ERROR: Docker nginx helper is unavailable: $DOCKER_HELPER" >&2
      return 1
    }
    "$DOCKER_HELPER" reload || return 1
    return 0
  fi
  [ "$ACTIVATOR" = "native" ] || {
    echo "ERROR: unsupported JEEB_CMS_ACTIVATOR: $ACTIVATOR" >&2
    return 1
  }
  if ! command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
    echo "ERROR: required command is unavailable: $SYSTEMCTL_BIN" >&2
    return 1
  fi
  "$SYSTEMCTL_BIN" reload "$NGINX_SERVICE" || return 1
}

verify_http_release() {
  local expected_release_id="$1" health current_target served_release_id served_manifest_sha local_manifest_sha
  if ! command -v "$CURL_BIN" >/dev/null 2>&1; then
    echo "ERROR: required command is unavailable: $CURL_BIN" >&2
    return 1
  fi
  if ! health="$("$CURL_BIN" -fsS --max-time 10 "$HEALTH_URL")"; then
    echo "ERROR: CMS health endpoint is unavailable" >&2
    return 1
  fi
  if [ "$health" != "healthy" ]; then
    echo "ERROR: unexpected CMS health response" >&2
    return 1
  fi
  if ! "$CURL_BIN" -fsS --max-time 10 "$GATEWAY_READY_URL" >/dev/null; then
    echo "ERROR: gateway readiness endpoint is unavailable" >&2
    return 1
  fi
  current_target="$(resolve_release_link "$CURRENT_LINK")" || return 1
  if ! served_release_id="$("$CURL_BIN" -fsS --max-time 10 "$RELEASE_URL" | "$PYTHON_BIN" -c '
import json
import sys
served = json.load(sys.stdin)
with open(sys.argv[1], encoding="utf-8") as expected_file:
    expected = json.load(expected_file)
if served != expected:
    raise SystemExit("served release metadata does not match the active release")
print(served.get("releaseId", ""))
' "$current_target/release.json")"; then
    echo "ERROR: CMS release endpoint is unavailable or invalid" >&2
    return 1
  fi
  if [ "$served_release_id" != "$expected_release_id" ]; then
    echo "ERROR: served releaseId does not match activated release" >&2
    return 1
  fi
  if ! served_manifest_sha="$("$CURL_BIN" -fsS --max-time 10 "$MANIFEST_URL" | "$PYTHON_BIN" -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"; then
    echo "ERROR: CMS manifest endpoint is unavailable" >&2
    return 1
  fi
  local_manifest_sha="$(sha256_file "$current_target/SHA256SUMS")" || return 1
  if [ "$served_manifest_sha" != "$local_manifest_sha" ]; then
    echo "ERROR: served SHA256SUMS does not match the active release" >&2
    return 1
  fi
}

activate_and_verify() {
  local release_id="$1"
  test_nginx || return 1
  reload_nginx || return 1
  verify_http_release "$release_id" || return 1
}

acquire_deploy_lock() {
  DEPLOY_LOCK_DIR="${CMS_ROOT}/.deploy-lock"
  if ! mkdir "$DEPLOY_LOCK_DIR" 2>/dev/null; then
    die "another CMS release operation is active (or the lock is stale): $DEPLOY_LOCK_DIR"
  fi
}

release_deploy_lock() {
  if [ -n "${DEPLOY_LOCK_DIR:-}" ] && [ -d "$DEPLOY_LOCK_DIR" ]; then
    rmdir "$DEPLOY_LOCK_DIR" 2>/dev/null || true
  fi
}
