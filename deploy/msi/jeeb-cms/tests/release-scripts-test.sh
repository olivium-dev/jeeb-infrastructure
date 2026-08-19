#!/usr/bin/env bash

set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${TEST_DIR}/.." && pwd)"
SCRIPTS_DIR="${BASE_DIR}/scripts"
TMP_ROOT="$(mktemp -d)"

cleanup() {
  case "$TMP_ROOT" in
    /tmp/*|/private/tmp/*|/var/folders/*)
      chmod -R u+w "$TMP_ROOT" 2>/dev/null || true
      rm -rf -- "$TMP_ROOT"
      ;;
    *) echo "Refusing to clean unexpected test path: $TMP_ROOT" >&2 ;;
  esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

CMS_ROOT="${TMP_ROOT}/cms"
STUB_DIR="${TMP_ROOT}/bin"
REAL_PYTHON="$(command -v python3)"
mkdir -p "$CMS_ROOT" "$STUB_DIR"

cat >"${STUB_DIR}/nginx" <<'STUB'
#!/usr/bin/env bash
set -Eeuo pipefail
if [ "${STUB_SIGNAL_DURING_NGINX_TEST:-0}" = "1" ] \
  && [ ! -e "${STUB_SIGNAL_MARKER:?signal marker is required}" ]; then
  : >"$STUB_SIGNAL_MARKER"
  kill -TERM "$PPID"
  sleep 1
fi
exit 0
STUB

cat >"${STUB_DIR}/systemctl" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

cat >"${STUB_DIR}/python3" <<'STUB'
#!/usr/bin/env bash
set -Eeuo pipefail
"${STUB_REAL_PYTHON:?real Python is required}" "$@"
status=$?
if [ "$status" -eq 0 ] \
  && [ "${STUB_SIGNAL_AFTER_LINK:-}" != "" ] \
  && [ "${1:-}" = "-" ] \
  && [ "${3:-}" = "$STUB_SIGNAL_AFTER_LINK" ] \
  && [ ! -e "${STUB_SIGNAL_MARKER:?signal marker is required}" ]; then
  : >"$STUB_SIGNAL_MARKER"
  kill -TERM "$PPID"
  sleep 1
fi
exit "$status"
STUB

cat >"${STUB_DIR}/curl" <<'STUB'
#!/usr/bin/env bash
set -Eeuo pipefail
url="${*: -1}"
if [ "${STUB_GATEWAY_UNREADY:-0}" = "1" ] && [[ "$url" == */gateway/health/ready ]]; then
  exit 22
elif [ "${STUB_RELEASE_MISMATCH:-0}" = "1" ] && [[ "$url" == */release.json ]]; then
  echo '{"releaseId":"wrong-release"}'
elif [[ "$url" == */healthz ]]; then
  echo healthy
elif [[ "$url" == */gateway/health/ready ]]; then
  echo '{"status":"ready"}'
elif [[ "$url" == */release.json ]]; then
  cat "${JEEB_CMS_ROOT}/current/release.json"
elif [[ "$url" == */SHA256SUMS ]]; then
  if [ "${STUB_MANIFEST_MISMATCH:-0}" = "1" ]; then
    echo tampered-manifest
  else
    cat "${JEEB_CMS_ROOT}/current/SHA256SUMS"
  fi
else
  exit 22
fi
STUB

cat >"${STUB_DIR}/cp" <<'STUB'
#!/usr/bin/env bash
set -Eeuo pipefail
/bin/cp "$@"
if [ "${STUB_MUTATE_AFTER_COPY:-0}" = "1" ]; then
  destination="${*: -1}"
  printf 'transport-race-mutation\n' >>"$destination/index.html"
  python3 - "$destination" <<'PY'
import hashlib
import sys
from pathlib import Path
root = Path(sys.argv[1])
names = sorted(
    p.relative_to(root).as_posix()
    for p in root.rglob("*")
    if p.is_file() and p.name != "SHA256SUMS"
)
with (root / "SHA256SUMS").open("w", encoding="utf-8") as manifest:
    for name in names:
        manifest.write(f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n")
PY
fi
STUB
chmod +x "${STUB_DIR}/nginx" "${STUB_DIR}/systemctl" "${STUB_DIR}/python3" "${STUB_DIR}/curl" "${STUB_DIR}/cp"

write_manifest() {
  local destination="$1"
  python3 - "$destination" <<'PY'
import hashlib
import sys
from pathlib import Path
root = Path(sys.argv[1])
names = sorted(
    p.relative_to(root).as_posix()
    for p in root.rglob("*")
    if p.is_file() and p.name != "SHA256SUMS"
)
with (root / "SHA256SUMS").open("w", encoding="utf-8") as manifest:
    for name in names:
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        manifest.write(f"{digest}  {name}\n")
PY
}

make_release() {
  local release_id="$1" destination="${TMP_ROOT}/$1" remote
  mkdir -p "$destination/assets"
  printf '<!doctype html><title>%s</title>\n' "$release_id" >"$destination/index.html"
  for remote in cases config deliveries kyc orders settlements users wallet; do
    mkdir -p "$destination/mf/$remote"
    printf 'console.log("%s-%s")\n' "$remote" "$release_id" >"$destination/mf/$remote/remoteEntry.js"
  done
  printf 'body{}\n' >"$destination/assets/app.1234abcd.css"
  cat >"$destination/release.json" <<JSON
{"releaseId":"${release_id}","cmsCommit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","gatewayCommit":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","openapiSha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","builtAt":"2026-08-07T00:00:00Z"}
JSON
  write_manifest "$destination"
  printf '%s\n' "$destination"
}

run_deploy() {
  local artifact="$1" expected_manifest_sha
  expected_manifest_sha="${JEEB_CMS_EXPECTED_MANIFEST_SHA256:-$(python3 - "$artifact/SHA256SUMS" <<'PY'
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)}"
  PATH="${STUB_DIR}:$PATH" \
  JEEB_CMS_ROOT="$CMS_ROOT" \
  JEEB_CMS_OWNER="" \
  JEEB_CMS_NGINX_BIN="${STUB_DIR}/nginx" \
  JEEB_CMS_SYSTEMCTL_BIN="${STUB_DIR}/systemctl" \
  JEEB_CMS_CURL_BIN="${STUB_DIR}/curl" \
  STUB_REAL_PYTHON="$REAL_PYTHON" \
  JEEB_CMS_EXPECTED_MANIFEST_SHA256="$expected_manifest_sha" \
  "$SCRIPTS_DIR/deploy-release.sh" "$artifact"
}

assert_link_release() {
  local link_path="$1" expected="$2" actual
  actual="$(basename "$(python3 - "$link_path" <<'PY'
import os,sys
print(os.path.realpath(sys.argv[1]))
PY
)")"
  [ "$actual" = "$expected" ] || {
    echo "Expected $link_path to resolve to $expected; got $actual" >&2
    exit 1
  }
}

release_one="$(make_release release-001)"
release_two="$(make_release release-002)"

# Production deployment must never trust only the artifact's self-authored
# checksum manifest.
if PATH="${STUB_DIR}:$PATH" \
  JEEB_CMS_ROOT="$CMS_ROOT" \
  JEEB_CMS_OWNER="" \
  JEEB_CMS_NGINX_BIN="${STUB_DIR}/nginx" \
  JEEB_CMS_SYSTEMCTL_BIN="${STUB_DIR}/systemctl" \
  JEEB_CMS_CURL_BIN="${STUB_DIR}/curl" \
  "$SCRIPTS_DIR/deploy-release.sh" "$release_one" >/dev/null 2>&1; then
  echo "Release without an external manifest digest unexpectedly deployed" >&2
  exit 1
fi
run_deploy "$release_one"
assert_link_release "$CMS_ROOT/current" release-001
[ "$(readlink "$CMS_ROOT/current")" = "releases/release-001" ] || {
  echo "Current release pointer must be relative for container mount portability" >&2
  exit 1
}

# A trusted transport digest can be pinned at deploy time.
release_one_manifest_sha="$(python3 - "$release_one/SHA256SUMS" <<'PY'
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
JEEB_CMS_EXPECTED_MANIFEST_SHA256="$release_one_manifest_sha" run_deploy "$release_one" >/dev/null
if JEEB_CMS_EXPECTED_MANIFEST_SHA256="$(printf '0%.0s' {1..64})" run_deploy "$release_one" >/dev/null 2>&1; then
  echo "Release with a mismatched external manifest digest unexpectedly deployed" >&2
  exit 1
fi

# A mutable transport directory cannot swap in a different, internally valid
# artifact between the source digest check and the copy.
release_toc="$(make_release release-toc)"
release_toc_manifest_sha="$(python3 - "$release_toc/SHA256SUMS" <<'PY'
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
if STUB_MUTATE_AFTER_COPY=1 JEEB_CMS_EXPECTED_MANIFEST_SHA256="$release_toc_manifest_sha" run_deploy "$release_toc" >/dev/null 2>&1; then
  echo "Transport-time artifact mutation unexpectedly deployed" >&2
  exit 1
fi
assert_link_release "$CMS_ROOT/current" release-001

run_deploy "$release_two"
assert_link_release "$CMS_ROOT/current" release-002

# Reusing an identical release is idempotent.
run_deploy "$release_two"
assert_link_release "$CMS_ROOT/current" release-002

# Corruption must be detected before the current symlink changes.
release_bad="$(make_release release-bad)"
printf 'tampered\n' >>"$release_bad/index.html"
if run_deploy "$release_bad" >/dev/null 2>&1; then
  echo "Corrupt release unexpectedly deployed" >&2
  exit 1
fi
assert_link_release "$CMS_ROOT/current" release-002

# Required remotes, source-map policy, and same-origin safety are enforced even
# when an artifact has an internally consistent checksum manifest.
release_missing_remote="$(make_release release-missing-remote)"
rm "$release_missing_remote/mf/settlements/remoteEntry.js"
write_manifest "$release_missing_remote"
if run_deploy "$release_missing_remote" >/dev/null 2>&1; then
  echo "Release missing an essential remote unexpectedly deployed" >&2
  exit 1
fi

release_source_map="$(make_release release-source-map)"
printf '{}\n' >"$release_source_map/assets/app.1234abcd.js.map"
write_manifest "$release_source_map"
if run_deploy "$release_source_map" >/dev/null 2>&1; then
  echo "Release containing a public source map unexpectedly deployed" >&2
  exit 1
fi

release_private_origin="$(make_release release-private-origin)"
printf 'fetch("http://192.168.2.39:10090/private")\n' >"$release_private_origin/assets/app.1234abcd.js"
write_manifest "$release_private_origin"
if run_deploy "$release_private_origin" >/dev/null 2>&1; then
  echo "Release containing a private gateway origin unexpectedly deployed" >&2
  exit 1
fi

# Reject every non-public address class that a browser could otherwise use to
# bypass the same-origin gateway boundary, including IPv6 and cloud metadata.
unsafe_origins=(
  'http://localhost'
  'http://0.0.0.0:10090/'
  'http://169.254.169.254/latest/meta-data/'
  'http://100.64.0.1/internal'
  'http://2130706433/internal'
  'http://0x7f000001/internal'
  'http://0177.0.0.1/internal'
  'http://127.1/internal'
  'http://224.0.0.1/internal'
  'http://[::1]:10090/'
  'http://[fc00::1]/internal'
  'http://[fe80::1]/internal'
  'http://[fec0::1]/internal'
  'http://[ff02::1]/internal'
  'ws://127.0.0.1/socket'
  'https://gateway.internal/private'
  'https://delivery.default.svc/private'
  'https://localhost.localdomain/private'
)
unsafe_index=0
for unsafe_origin in "${unsafe_origins[@]}"; do
  unsafe_index=$((unsafe_index + 1))
  release_unsafe_origin="$(make_release "release-unsafe-${unsafe_index}")"
  printf 'fetch("%s")\n' "$unsafe_origin" >"$release_unsafe_origin/assets/app.1234abcd.js"
  write_manifest "$release_unsafe_origin"
  if run_deploy "$release_unsafe_origin" >/dev/null 2>&1; then
    echo "Release containing unsafe origin unexpectedly deployed: $unsafe_origin" >&2
    exit 1
  fi
done

release_backslash_origin="$(make_release release-backslash-origin)"
printf '%s\n' 'fetch("http:\\127.0.0.1\\private")' >"$release_backslash_origin/assets/app.1234abcd.js"
write_manifest "$release_backslash_origin"
if run_deploy "$release_backslash_origin" >/dev/null 2>&1; then
  echo "Release containing a browser-normalized backslash URL unexpectedly deployed" >&2
  exit 1
fi

# Axios's production bundle contains this inert base-origin fallback. It is not
# a configured service endpoint and must not make real production dist invalid.
release_axios_fallback="$(make_release release-axios-fallback)"
printf 'const escaped="https:\\/\\/example.com";const browser=typeof window!=="undefined";const origin=browser&&window.location.href||"http://localhost"\n' >"$release_axios_fallback/assets/app.1234abcd.js"
write_manifest "$release_axios_fallback"
python3 "$SCRIPTS_DIR/validate-release.py" "$release_axios_fallback" >/dev/null

safe_router_fragments=(
  'const history={createURL:e=>new URL(d(e),"http://localhost")}'
  'function D(e,t,r=!1){let n="http://localhost";e&&(n="null"!==e.location.origin?e.location.origin:e.location.href)}'
  'let t="string"==typeof e?e:x(e);t=t.replace(/ $/,"%20");let r=c.test(t)?new URL(t):new URL(t,"http://localhost");return{pathname:r.pathname,search:r.search,hash:r.hash}'
)
router_index=0
for safe_router_fragment in "${safe_router_fragments[@]}"; do
  router_index=$((router_index + 1))
  release_router_fallback="$(make_release "release-router-fallback-${router_index}")"
  printf '%s\n' "$safe_router_fragment" >"$release_router_fallback/assets/app.1234abcd.js"
  write_manifest "$release_router_fallback"
  python3 "$SCRIPTS_DIR/validate-release.py" "$release_router_fallback" >/dev/null
done

active_localhost_fragments=(
  'fetch(new URL("/admin","http://localhost"))'
  'let a="http://localhost";b&&(fetch(a))'
)
active_localhost_index=0
for active_localhost_fragment in "${active_localhost_fragments[@]}"; do
  active_localhost_index=$((active_localhost_index + 1))
  release_active_localhost="$(make_release "release-active-localhost-${active_localhost_index}")"
  printf '%s\n' "$active_localhost_fragment" >"$release_active_localhost/assets/app.1234abcd.js"
  write_manifest "$release_active_localhost"
  if run_deploy "$release_active_localhost" >/dev/null 2>&1; then
    echo "Active localhost pattern unexpectedly deployed: $active_localhost_fragment" >&2
    exit 1
  fi
done

release_signed_url="$(make_release release-signed-url)"
printf 'const proof="https://cdn.example.com/evidence?X-Amz-Signature=secret"\n' >"$release_signed_url/assets/app.1234abcd.js"
write_manifest "$release_signed_url"
if run_deploy "$release_signed_url" >/dev/null 2>&1; then
  echo "Release containing a signed evidence URL unexpectedly deployed" >&2
  exit 1
fi

release_storage_url="$(make_release release-storage-url)"
printf 'const proof="s3://private-bucket/evidence"\n' >"$release_storage_url/assets/app.1234abcd.js"
write_manifest "$release_storage_url"
if run_deploy "$release_storage_url" >/dev/null 2>&1; then
  echo "Release containing a raw storage URL unexpectedly deployed" >&2
  exit 1
fi

release_https_object_storage="$(make_release release-https-object-storage)"
printf 'const proof="https://private-bucket.s3.eu-west-1.amazonaws.com/evidence.pdf"\n' >"$release_https_object_storage/assets/app.1234abcd.js"
write_manifest "$release_https_object_storage"
if run_deploy "$release_https_object_storage" >/dev/null 2>&1; then
  echo "Release containing an HTTPS object-storage endpoint unexpectedly deployed" >&2
  exit 1
fi

storage_urls=(
  '//bucket.s3.amazonaws.com/evidence?X-Amz-Signature=secret'
  'https:\/\/bucket.s3.amazonaws.com\/evidence'
  'https://storage.cloud.google.com/private-bucket/evidence'
  'https://bucket.blob.core.chinacloudapi.cn/evidence'
  'https://bucket.dfs.core.chinacloudapi.cn/evidence'
  'https://bucket.dfs.core.usgovcloudapi.net/evidence'
  'https://bucket.s3.cn-north-1.amazonaws.com.cn/evidence'
  'https://cdn.example.com/evidence?sig=secret'
  'https://cdn.example.com/evidence?Signature=secret'
  'https://cdn.example.com/evidence?%73%69%67=secret'
  'https://cdn.example.com/evidence?mode=view&amp;sig=secret'
  'https://cdn.example.com/evidence?mode=view\u0026sig=secret'
  'https://cdn.example.com/evidence?mode=view\x26sig=secret'
)
storage_index=0
for storage_url in "${storage_urls[@]}"; do
  storage_index=$((storage_index + 1))
  release_storage_variant="$(make_release "release-storage-variant-${storage_index}")"
  printf 'const proof="%s"\n' "$storage_url" >"$release_storage_variant/assets/app.1234abcd.js"
  write_manifest "$release_storage_variant"
  if run_deploy "$release_storage_variant" >/dev/null 2>&1; then
    echo "Release containing a storage/signed URL variant unexpectedly deployed: $storage_url" >&2
    exit 1
  fi
done

printf -v bare_cr_continuation 'const u="http:\\\r//127.0.0.1/private"'
printf -v line_separator_continuation 'const u="http:\\\342\200\250//127.0.0.1/private"'
printf -v paragraph_separator_continuation 'const u="http:\\\342\200\251//127.0.0.1/private"'
browser_normalized_payloads=(
  '<img src = //10.0.0.8/private>'
  $'<img src=\n//10.0.0.8/private>'
  'const u="\/\/10.0.0.8/private"'
  'const u="http:\u002f\u002f127.0.0.1/private"'
  'const u="https://cdn.example.com/evidence?mode=view\u{26}sig=secret"'
  'const u="\u0068ttp://127.0.0.1/private"'
  'const u="http://\u0031\u0032\u0037.0.0.1/private"'
  'const u="https://cdn.example.com/evidence?\u0073ig=secret"'
  $'const u="http:\\\n//127.0.0.1/private"'
  "$bare_cr_continuation"
  "$line_separator_continuation"
  "$paragraph_separator_continuation"
  'const u=" \/\/10.0.0.8/private"'
  $'const u="\t\/\/10.0.0.8/private"'
  'decodeURIComponent("https%3A%5C/%5C/bucket.s3.amazonaws.com/evidence")'
  'const u="https://bucket.\u00733.amazonaws.com/evidence"'
)
browser_payload_index=0
for browser_payload in "${browser_normalized_payloads[@]}"; do
  browser_payload_index=$((browser_payload_index + 1))
  release_browser_payload="$(make_release "release-browser-payload-${browser_payload_index}")"
  printf '%s\n' "$browser_payload" >"$release_browser_payload/assets/app.1234abcd.js"
  write_manifest "$release_browser_payload"
  if run_deploy "$release_browser_payload" >/dev/null 2>&1; then
    echo "Browser-normalized unsafe URL unexpectedly deployed: $browser_payload" >&2
    exit 1
  fi
done

# Fail closed when an asset exceeds the canonicalization bound. Seven nested
# HTML entity layers previously needed one more decode than the validator ran,
# allowing the browser to reconstruct a loopback URL after validation.
release_nonconvergent_payload="$(make_release release-nonconvergent-payload)"
printf '%s\n' \
  'const u="http:&amp;amp;amp;amp;amp;amp;#47;&amp;amp;amp;amp;amp;amp;#47;127.0.0.1/private"' \
  >"$release_nonconvergent_payload/assets/app.1234abcd.js"
write_manifest "$release_nonconvergent_payload"
if run_deploy "$release_nonconvergent_payload" >/dev/null 2>&1; then
  echo "Non-convergent encoded URL unexpectedly deployed" >&2
  exit 1
fi

special_use_dns_names=(
  'https://printer.home.arpa/private'
  'https://service.consul/private'
)
special_dns_index=0
for special_dns_url in "${special_use_dns_names[@]}"; do
  special_dns_index=$((special_dns_index + 1))
  release_special_dns="$(make_release "release-special-dns-${special_dns_index}")"
  printf 'const u="%s"\n' "$special_dns_url" >"$release_special_dns/assets/app.1234abcd.js"
  write_manifest "$release_special_dns"
  if run_deploy "$release_special_dns" >/dev/null 2>&1; then
    echo "Special-use DNS URL unexpectedly deployed: $special_dns_url" >&2
    exit 1
  fi
done

unquoted_urls=(
  '//10.0.0.8/private'
  '//bucket.s3.amazonaws.com/evidence'
)
unquoted_index=0
for unquoted_url in "${unquoted_urls[@]}"; do
  unquoted_index=$((unquoted_index + 1))
  release_unquoted="$(make_release "release-unquoted-${unquoted_index}")"
  printf '<img src=%s>\n' "$unquoted_url" >"$release_unquoted/index.html"
  write_manifest "$release_unquoted"
  if run_deploy "$release_unquoted" >/dev/null 2>&1; then
    echo "Release containing unquoted unsafe URL unexpectedly deployed: $unquoted_url" >&2
    exit 1
  fi
done

release_hidden_remote="$(make_release release-hidden-remote)"
printf 'DATABASE_URL=secret\n' >"$release_hidden_remote/mf/cases/.env"
write_manifest "$release_hidden_remote"
if run_deploy "$release_hidden_remote" >/dev/null 2>&1; then
  echo "Release containing a hidden remote file unexpectedly deployed" >&2
  exit 1
fi

release_upper_map="$(make_release release-upper-map)"
printf '{}\n' >"$release_upper_map/assets/debug.MAP"
write_manifest "$release_upper_map"
if run_deploy "$release_upper_map" >/dev/null 2>&1; then
  echo "Release containing an uppercase source map unexpectedly deployed" >&2
  exit 1
fi

release_disguised_map="$(make_release release-disguised-map)"
printf '%s\n' '{"version":3,"sources":["app.ts"],"mappings":"AAAA"}' >"$release_disguised_map/assets/debug.json"
write_manifest "$release_disguised_map"
if run_deploy "$release_disguised_map" >/dev/null 2>&1; then
  echo "Release containing a disguised source map unexpectedly deployed" >&2
  exit 1
fi

release_spaced_inline_map="$(make_release release-spaced-inline-map)"
printf '%s\n' '//# sourceMappingURL = data:application/json;base64,e30=' >"$release_spaced_inline_map/assets/app.1234abcd.js"
write_manifest "$release_spaced_inline_map"
if run_deploy "$release_spaced_inline_map" >/dev/null 2>&1; then
  echo "Release containing a spaced inline source map unexpectedly deployed" >&2
  exit 1
fi

# Non-script public assets are scanned too; nginx serves these paths directly.
release_svg_secret="$(make_release release-svg-secret)"
printf '<svg><text>http://10.0.0.9/private</text></svg>\n' >"$release_svg_secret/assets/logo.svg"
write_manifest "$release_svg_secret"
if run_deploy "$release_svg_secret" >/dev/null 2>&1; then
  echo "Release containing a private origin in SVG unexpectedly deployed" >&2
  exit 1
fi

release_txt_secret="$(make_release release-txt-secret)"
printf '%s\n' '-----BEGIN PRIVATE KEY-----' >"$release_txt_secret/assets/notice.txt"
write_manifest "$release_txt_secret"
if run_deploy "$release_txt_secret" >/dev/null 2>&1; then
  echo "Release containing private key material in TXT unexpectedly deployed" >&2
  exit 1
fi

release_pgp_secret="$(make_release release-pgp-secret)"
printf '%s\n' '-----BEGIN PGP PRIVATE KEY BLOCK-----' >"$release_pgp_secret/assets/notice.txt"
write_manifest "$release_pgp_secret"
if run_deploy "$release_pgp_secret" >/dev/null 2>&1; then
  echo "Release containing PGP private key material unexpectedly deployed" >&2
  exit 1
fi
assert_link_release "$CMS_ROOT/current" release-002

# A failed post-activation check must remain on the candidate for diagnosis.
release_three="$(make_release release-003)"
if STUB_RELEASE_MISMATCH=1 run_deploy "$release_three" >/dev/null 2>&1; then
  echo "Activation with a mismatched served release unexpectedly succeeded" >&2
  exit 1
fi
assert_link_release "$CMS_ROOT/current" release-003

# Activating static assets is insufficient when their only API dependency is
# not ready. The dependency preflight must fail before the release pointer moves.
release_four="$(make_release release-004)"
if STUB_GATEWAY_UNREADY=1 run_deploy "$release_four" >/dev/null 2>&1; then
  echo "Activation with an unready gateway unexpectedly succeeded" >&2
  exit 1
fi
assert_link_release "$CMS_ROOT/current" release-003

# TERM/INT are failure paths too. If the operator or service manager interrupts
# preflight, the release pointer must remain unchanged.
release_signal="$(make_release release-signal)"
deploy_signal_marker="${TMP_ROOT}/deploy-signal-fired"
if STUB_SIGNAL_DURING_NGINX_TEST=1 \
  STUB_SIGNAL_MARKER="$deploy_signal_marker" \
  run_deploy "$release_signal" >/dev/null 2>&1; then
  echo "Signal-interrupted deployment unexpectedly succeeded" >&2
  exit 1
fi
[ -f "$deploy_signal_marker" ] || {
  echo "Deployment signal test did not reach nginx activation" >&2
  exit 1
}
assert_link_release "$CMS_ROOT/current" release-003

# Runtime verification compares served manifest bytes, not only releaseId.
if STUB_MANIFEST_MISMATCH=1 \
  JEEB_CMS_ROOT="$CMS_ROOT" \
  JEEB_CMS_NGINX_BIN="${STUB_DIR}/nginx" \
  JEEB_CMS_CURL_BIN="${STUB_DIR}/curl" \
  "$SCRIPTS_DIR/verify-current.sh" --runtime >/dev/null 2>&1; then
  echo "Runtime verification accepted a mismatched served manifest" >&2
  exit 1
fi

JEEB_CMS_ROOT="$CMS_ROOT" "$SCRIPTS_DIR/verify-current.sh" >/dev/null
echo "release script tests passed"
