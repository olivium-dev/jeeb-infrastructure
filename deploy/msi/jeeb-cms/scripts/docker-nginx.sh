#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_BIN="${JEEB_CMS_DOCKER_BIN:-docker}"
CURL_BIN="${JEEB_CMS_CURL_BIN:-curl}"
PYTHON_BIN="${JEEB_CMS_PYTHON_BIN:-python3}"
CMS_ROOT="${JEEB_CMS_ROOT:-/home/ec2-user/jeeb-cms}"
CONTAINER="${JEEB_CMS_NGINX_CONTAINER:-jeeb-cms-nginx}"
IMAGE="${JEEB_CMS_NGINX_IMAGE:-}"
MAIN_CONFIG="${JEEB_CMS_CONTAINER_NGINX_CONFIG:-${BASE_DIR}/nginx/container-nginx.conf}"
SITE_CONFIG="${JEEB_CMS_SITE_NGINX_CONFIG:-${BASE_DIR}/nginx/backoffice.jeeb.fds-1.com.conf}"
HEALTH_URL="${JEEB_CMS_HEALTH_URL:-http://127.0.0.1:10100/healthz}"
VERIFY_CURRENT="${JEEB_CMS_VERIFY_CURRENT:-${SCRIPT_DIR}/verify-current.sh}"
CONTRACT_VALIDATOR="${JEEB_CMS_CONTAINER_CONTRACT_VALIDATOR:-${SCRIPT_DIR}/validate-nginx-container.py}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command is unavailable: $1"
}

real_directory() {
  [ -d "$1" ] && [ ! -L "$1" ] || die "must be a real directory: $1"
}

real_file() {
  [ -f "$1" ] && [ ! -L "$1" ] || die "must be a real file: $1"
}

container_exists() {
  if "$DOCKER_BIN" container inspect "$CONTAINER" >/dev/null 2>&1; then
    return 0
  fi
  local names
  if ! names="$("$DOCKER_BIN" container ls --all --format '{{.Names}}' 2>/dev/null)"; then
    die "container state could not be inspected: $CONTAINER"
  fi
  grep -Fxq "$CONTAINER" <<<"$names"
}

remove_invalid_container() {
  "$DOCKER_BIN" container rm --force "$CONTAINER" >/dev/null 2>&1 || true
  if container_exists; then
    die "invalid container could not be removed and may still be running: $CONTAINER"
  fi
}

stop_unhealthy_container() {
  "$DOCKER_BIN" container stop "$CONTAINER" >/dev/null 2>&1 || true
  if ! container_exists; then
    return
  fi
  local running
  if ! running="$("$DOCKER_BIN" container inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null)"; then
    die "unhealthy container state could not be verified: $CONTAINER"
  fi
  if [ "$running" = true ]; then
    die "unhealthy container could not be stopped: $CONTAINER"
  fi
  [ "$running" = false ] || die "unhealthy container returned an invalid running state: $CONTAINER"
}

require_image() {
  [ -n "$IMAGE" ] || die "JEEB_CMS_NGINX_IMAGE is required for every container operation"
  [[ "$IMAGE" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]] \
    || die "JEEB_CMS_NGINX_IMAGE must use an immutable sha256 digest"
}

verify_container_contract() {
  local expected_running="$1"
  [ -f "$CONTRACT_VALIDATOR" ] && [ ! -L "$CONTRACT_VALIDATOR" ] \
    || die "container contract validator is unavailable: $CONTRACT_VALIDATOR"
  "$DOCKER_BIN" container inspect "$CONTAINER" | "$PYTHON_BIN" "$CONTRACT_VALIDATOR" \
    --expected-running "$expected_running" \
    --image "$IMAGE" \
    --cms-root "$CMS_ROOT" \
    --main-config "$MAIN_CONFIG" \
    --site-config "$SITE_CONFIG"
}

validate_active_release() {
  [ -x "$VERIFY_CURRENT" ] || die "active-release verifier is unavailable: $VERIFY_CURRENT"
  JEEB_CMS_ROOT="$CMS_ROOT" "$VERIFY_CURRENT" >/dev/null \
    || die "active CMS release validation failed"
}

verify_health() {
  if ! "$CURL_BIN" -fsS --retry 10 --retry-connrefused --retry-delay 1 --max-time 10 "$HEALTH_URL" >/dev/null; then
    return 1
  fi
}

usage() {
  echo "Usage: $0 <start|boot|status|test|reload>" >&2
  exit 2
}

[ "$#" -eq 1 ] || usage
require_command "$DOCKER_BIN"
require_command "$PYTHON_BIN"
require_image

case "$1" in
  start)
    require_command "$CURL_BIN"
    real_directory "$CMS_ROOT"
    real_file "$MAIN_CONFIG"
    real_file "$SITE_CONFIG"
    validate_active_release
    container_exists && die "container already exists; refusing to replace it (use status/test/reload)"

    # Validate the exact image and read-only mounts before creating the
    # service-managed process. Host networking is unnecessary for this pass.
    "$DOCKER_BIN" run --rm \
      --read-only \
      --runtime runc \
      --cap-drop ALL \
      --security-opt no-new-privileges \
      --user 101:101 \
      --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=0700,uid=101,gid=101 \
      --mount "type=bind,src=${CMS_ROOT},dst=/opt/jeeb-cms,readonly" \
      --mount "type=bind,src=${MAIN_CONFIG},dst=/etc/nginx/nginx.conf,readonly" \
      --mount "type=bind,src=${SITE_CONFIG},dst=/etc/nginx/conf.d/jeeb-cms.conf,readonly" \
      --entrypoint nginx \
      "$IMAGE" -t

    "$DOCKER_BIN" run --detach \
      --name "$CONTAINER" \
      --network host \
      --restart no \
      --read-only \
      --runtime runc \
      --cap-drop ALL \
      --security-opt no-new-privileges \
      --user 101:101 \
      --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=0700,uid=101,gid=101 \
      --mount "type=bind,src=${CMS_ROOT},dst=/opt/jeeb-cms,readonly" \
      --mount "type=bind,src=${MAIN_CONFIG},dst=/etc/nginx/nginx.conf,readonly" \
      --mount "type=bind,src=${SITE_CONFIG},dst=/etc/nginx/conf.d/jeeb-cms.conf,readonly" \
      --log-driver local \
      --log-opt max-size=10m \
      --log-opt max-file=3 \
      --stop-signal SIGQUIT \
      --entrypoint nginx \
      "$IMAGE" -g 'daemon off;'
    if ! verify_container_contract true; then
      remove_invalid_container
      die "new container violated the runtime contract and was removed"
    fi
    if ! verify_health; then
      remove_invalid_container
      die "loopback health verification failed; the newly created container was removed"
    fi
    echo "Started $CONTAINER on the host-network loopback listener."
    ;;
  boot)
    require_command "$CURL_BIN"
    real_directory "$CMS_ROOT"
    real_file "$MAIN_CONFIG"
    real_file "$SITE_CONFIG"
    validate_active_release
    container_exists || die "container does not exist; create it once with the start action"
    if "$DOCKER_BIN" container inspect --format '{{.State.Running}}' "$CONTAINER" | grep -qx true; then
      if ! verify_container_contract true; then
        remove_invalid_container
        die "running container violated the runtime contract and was removed"
      fi
    else
      if ! verify_container_contract false; then
        remove_invalid_container
        die "stopped container violated the runtime contract and was removed"
      fi
      "$DOCKER_BIN" container start "$CONTAINER" >/dev/null
      if ! verify_container_contract true; then
        remove_invalid_container
        die "started container violated the runtime contract and was removed"
      fi
    fi
    verify_health || {
      stop_unhealthy_container
      die "loopback health verification failed; the container was stopped"
    }
    echo "Validated the active release and started $CONTAINER."
    ;;
  status)
    container_exists || die "container does not exist: $CONTAINER"
    verify_container_contract true
    echo "$CONTAINER satisfies the host-network/read-only runtime contract."
    ;;
  test)
    container_exists || die "container does not exist: $CONTAINER"
    verify_container_contract true
    "$DOCKER_BIN" exec "$CONTAINER" nginx -t
    ;;
  reload)
    require_command "$CURL_BIN"
    container_exists || die "container does not exist: $CONTAINER"
    verify_container_contract true
    "$DOCKER_BIN" exec "$CONTAINER" nginx -t
    "$DOCKER_BIN" kill --signal HUP "$CONTAINER" >/dev/null
    "$CURL_BIN" -fsS --retry 5 --retry-connrefused --retry-delay 1 --max-time 10 "$HEALTH_URL" >/dev/null
    ;;
  *) usage ;;
esac
