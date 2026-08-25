#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329
set -euo pipefail

mode=${1:?mode is required}
run_key=${2:?run key is required}
commit_sha=${3:?commit SHA is required}
stage_ref=${4:-}

[[ "$run_key" =~ ^[0-9]+_[0-9]+$ ]]
[[ "$commit_sha" =~ ^[0-9a-f]{40}$ ]]

[ "$(hostname -s)" = "olivium-ephemerals" ]
ip -4 -o addr show scope global \
  | awk '{ split($4, address, "/"); print address[1] }' \
  | grep -Fxq '192.168.2.20'

state_root=/var/lib/jeeb-staging-edge-rollouts
state_dir=$state_root/$run_key
config=/etc/nginx/sites-available/jeeb-direct-tls.conf
static_root=/var/www/jeeb-staging-well-known
current_link=$static_root/current
release_name=$commit_sha-$run_key
release_dir=$static_root/releases/$release_name

install -d -o root -g root -m 0700 "$state_root"
exec 9>"$state_root/.lock"
flock -n 9

write_status() {
  local status=$1 temporary=$state_dir/.status-$run_key
  printf '%s\n' "$status" > "$temporary" || return
  chmod 0600 "$temporary" || return
  mv -f -- "$temporary" "$state_dir/status" || return
}

read_status() {
  local status
  [ -f "$state_dir/status" ] || return
  IFS= read -r status < "$state_dir/status" || return
  printf '%s\n' "$status" || return
}

require_state_identity() {
  local recorded_commit
  [ -d "$state_dir" ] || return
  [ ! -L "$state_dir" ] || return
  IFS= read -r recorded_commit < "$state_dir/commit-sha" || return
  [ "$recorded_commit" = "$commit_sha" ] || return
}

resolve_stage_dir() {
  local deploy_user deploy_home stage_root stage_dir
  [ "$stage_ref" = ".jeeb-edge-deploy/$run_key" ]
  deploy_user=${SUDO_USER:?SUDO_USER is required for an edge rollout}
  [ "$deploy_user" != root ]
  deploy_home=$(getent passwd "$deploy_user" | awk -F: 'NR == 1 { print $6 }')
  [ -n "$deploy_home" ]
  deploy_home=$(realpath -e -- "$deploy_home")
  [ ! -L "$deploy_home/.jeeb-edge-deploy" ]
  stage_root=$(realpath -e -- "$deploy_home/.jeeb-edge-deploy")
  [ "$stage_root" = "$deploy_home/.jeeb-edge-deploy" ]
  [ ! -L "$stage_root/$run_key" ]
  stage_dir=$(realpath -e -- "$stage_root/$run_key")
  [ "$stage_dir" = "$stage_root/$run_key" ]
  [ -d "$stage_dir" ]
  printf '%s\n' "$stage_dir"
}

verify_nginx_runtime() {
  nginx -t || return
  systemctl is-active --quiet nginx || return
}

verify_incumbent_origin() {
  local link_kind previous_target current_target
  [ -f "$state_dir/jeeb-direct-tls.conf" ] || return
  cmp -s -- "$state_dir/jeeb-direct-tls.conf" "$config" || return
  IFS= read -r link_kind < "$state_dir/previous-current-kind" || return

  case "$link_kind" in
    symlink)
      IFS= read -r previous_target \
        < "$state_dir/previous-current-target" || return
      [ -L "$current_link" ] || return
      current_target=$(readlink -- "$current_link") || return
      [ "$current_target" = "$previous_target" ] || return
      ;;
    absent)
      [ ! -e "$current_link" ] || return
      [ ! -L "$current_link" ] || return
      ;;
    *)
      echo 'The recorded incumbent association-link state is invalid.' >&2
      return 41
      ;;
  esac

  verify_nginx_runtime || return
}

verify_candidate_origin() {
  local stage_dir=$1 expected_target current_target
  expected_target=releases/$release_name
  cmp -s -- "$stage_dir/jeeb-direct-tls.conf" "$config"
  [ -L "$current_link" ]
  current_target=$(readlink -- "$current_link")
  [ "$current_target" = "$expected_target" ]
  [ ! -L "$release_dir" ]
  [ -d "$release_dir" ]
  cmp -s -- \
    "$stage_dir/apple-app-site-association" \
    "$release_dir/apple-app-site-association"
  cmp -s -- "$stage_dir/assetlinks.json" "$release_dir/assetlinks.json"
  cmp -s -- \
    "$stage_dir/apple-app-site-association" \
    "$current_link/apple-app-site-association"
  cmp -s -- "$stage_dir/assetlinks.json" "$current_link/assetlinks.json"
  verify_nginx_runtime
}

case "$mode" in
  apply)
    stage_dir=$(resolve_stage_dir)
    [ -f "$config" ]
    [ ! -e "$state_dir" ]
    capture_dir=$state_root/.capture-$run_key
    [ ! -e "$capture_dir" ]
    [ ! -L "$capture_dir" ]
    for candidate in \
      jeeb-direct-tls.conf \
      apple-app-site-association \
      assetlinks.json; do
      [ -f "$stage_dir/$candidate" ]
      [ ! -L "$stage_dir/$candidate" ]
    done

    python3 -m json.tool \
      "$stage_dir/apple-app-site-association" >/dev/null
    python3 -m json.tool "$stage_dir/assetlinks.json" >/dev/null

    install -d -o root -g root -m 0700 "$capture_dir"
    printf '%s\n' "$commit_sha" > "$capture_dir/commit-sha"
    printf '%s\n' recording > "$capture_dir/status"
    install -o root -g root -m 0600 "$config" \
      "$capture_dir/jeeb-direct-tls.conf"

    if [ -L "$current_link" ]; then
      previous_target=$(readlink -- "$current_link")
      case "$previous_target" in
        /*|*..*)
          echo 'The incumbent association link escapes its managed release root.' >&2
          exit 31
          ;;
      esac
      resolved_previous=$(realpath -e -- "$static_root/$previous_target")
      case "$resolved_previous" in
        "$static_root"/releases/*) ;;
        *)
          echo 'The incumbent association link escapes its managed release root.' >&2
          exit 31
          ;;
      esac
      [ -d "$resolved_previous" ]
      printf '%s\n' symlink > "$capture_dir/previous-current-kind"
      printf '%s\n' "$previous_target" > "$capture_dir/previous-current-target"
      chmod 0600 \
        "$capture_dir/previous-current-kind" \
        "$capture_dir/previous-current-target"
    elif [ -e "$current_link" ]; then
      echo 'The managed well-known current path is not a symlink.' >&2
      exit 31
    else
      printf '%s\n' absent > "$capture_dir/previous-current-kind"
      chmod 0600 "$capture_dir/previous-current-kind"
    fi
    chmod 0600 "$capture_dir/commit-sha" "$capture_dir/status"
    mv -- "$capture_dir" "$state_dir"
    # The snapshot is retained for audit only. No automatic command can apply it.
    verify_incumbent_origin

    install -d -o root -g root -m 0755 "$static_root/releases"
    [ ! -e "$release_dir" ]
    [ ! -L "$release_dir" ]
    install -d -o root -g root -m 0755 "$release_dir"
    install -o root -g root -m 0644 \
      "$stage_dir/apple-app-site-association" \
      "$release_dir/apple-app-site-association"
    install -o root -g root -m 0644 \
      "$stage_dir/assetlinks.json" "$release_dir/assetlinks.json"
    cmp -s -- \
      "$stage_dir/apple-app-site-association" \
      "$release_dir/apple-app-site-association"
    cmp -s -- "$stage_dir/assetlinks.json" "$release_dir/assetlinks.json"

    write_status prepared
    install -o root -g root -m 0644 \
      "$stage_dir/jeeb-direct-tls.conf" "$config.candidate-$run_key"
    mv -f -- "$config.candidate-$run_key" "$config"
    ln -s -- "releases/$release_name" "$static_root/.current-$run_key"
    mv -Tf -- "$static_root/.current-$run_key" "$current_link"
    nginx -T | sha256sum > "$state_dir/nginx-rendered-candidate.sha256"
    chmod 0600 "$state_dir/nginx-rendered-candidate.sha256"
    nginx -t
    systemctl reload nginx
    systemctl is-active --quiet nginx
    verify_candidate_origin "$stage_dir"
    write_status applied
    ;;
  finalize)
    stage_dir=$(resolve_stage_dir)
    require_state_identity
    [ "$(read_status)" = applied ]
    verify_candidate_origin "$stage_dir"
    write_status verified
    ;;
  *)
    echo "Unsupported mode: $mode" >&2
    exit 64
    ;;
esac
