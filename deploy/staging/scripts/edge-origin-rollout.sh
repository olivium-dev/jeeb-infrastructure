#!/usr/bin/env bash
set -euo pipefail

mode=${1:?mode is required}
run_key=${2:?run key is required}
commit_sha=${3:?commit SHA is required}
stage_dir=${4:?candidate directory is required}

[[ "$run_key" =~ ^[0-9]+_[0-9]+$ ]]
[[ "$commit_sha" =~ ^[0-9a-f]{40}$ ]]
stage_dir=$(realpath -- "$stage_dir")
[ -d "$stage_dir" ]
[ ! -L "$stage_dir" ]

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

restore_origin() {
  [ -f "$state_dir/jeeb-direct-tls.conf" ]
  install -o root -g root -m 0644 \
    "$state_dir/jeeb-direct-tls.conf" "$config"

  if [ -f "$state_dir/previous-current-target" ]; then
    previous_target=$(<"$state_dir/previous-current-target")
    [ -n "$previous_target" ]
    ln -s "$previous_target" "$static_root/.current-$run_key"
    mv -Tf "$static_root/.current-$run_key" "$current_link"
  else
    rm -f -- "$current_link"
  fi

  nginx -t
  systemctl reload nginx
  systemctl is-active --quiet nginx
  printf '%s\n' restored > "$state_dir/status"
}

restore_after_apply_error() {
  exit_code=$?
  trap - ERR
  if ! restore_origin; then
    echo 'Automatic origin restoration failed; nginx requires operator review.' >&2
  fi
  exit "$exit_code"
}

case "$mode" in
  apply)
    [ -f "$config" ]
    [ ! -e "$state_dir" ]
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

    install -d -o root -g root -m 0700 "$state_dir"
    install -o root -g root -m 0600 "$config" \
      "$state_dir/jeeb-direct-tls.conf"
    if [ -L "$current_link" ]; then
      readlink "$current_link" > "$state_dir/previous-current-target"
      chmod 0600 "$state_dir/previous-current-target"
    elif [ -e "$current_link" ]; then
      echo 'The managed well-known current path is not a symlink.' >&2
      exit 31
    fi

    install -d -o root -g root -m 0755 "$static_root/releases"
    [ ! -e "$release_dir" ]
    install -d -o root -g root -m 0755 "$release_dir"
    install -o root -g root -m 0644 \
      "$stage_dir/apple-app-site-association" \
      "$release_dir/apple-app-site-association"
    install -o root -g root -m 0644 \
      "$stage_dir/assetlinks.json" "$release_dir/assetlinks.json"

    trap restore_after_apply_error ERR
    install -o root -g root -m 0644 \
      "$stage_dir/jeeb-direct-tls.conf" "$config.candidate-$run_key"
    mv -f -- "$config.candidate-$run_key" "$config"
    ln -s "releases/$release_name" "$static_root/.current-$run_key"
    mv -Tf "$static_root/.current-$run_key" "$current_link"

    if ! nginx -t; then
      trap - ERR
      restore_origin
      exit 32
    fi
    if ! systemctl reload nginx || ! systemctl is-active --quiet nginx; then
      trap - ERR
      restore_origin
      exit 33
    fi
    trap - ERR

    printf '%s\n' "$commit_sha" > "$state_dir/commit-sha"
    chmod 0600 "$state_dir/commit-sha"
    printf '%s\n' applied > "$state_dir/status"
    ;;
  rollback)
    [ "$(<"$state_dir/status")" = applied ]
    restore_origin
    ;;
  finalize)
    [ "$(<"$state_dir/status")" = applied ]
    printf '%s\n' verified > "$state_dir/status"
    ;;
  *)
    echo "Unsupported mode: $mode" >&2
    exit 64
    ;;
esac
