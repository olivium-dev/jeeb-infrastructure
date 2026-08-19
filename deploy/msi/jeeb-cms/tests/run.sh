#!/usr/bin/env bash

set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${TEST_DIR}/.." && pwd)"

find "$BASE_DIR/scripts" "$TEST_DIR" -type f -name '*.sh' -print0 \
  | while IFS= read -r -d '' script; do bash -n "$script"; done

python3 "$TEST_DIR/test_nginx_contract.py"
python3 "$TEST_DIR/test_assemble_release.py"
"$TEST_DIR/release-scripts-test.sh"

if command -v shellcheck >/dev/null 2>&1; then
  find "$BASE_DIR/scripts" "$TEST_DIR" -type f -name '*.sh' -print0 \
    | xargs -0 shellcheck --severity=warning
else
  echo "shellcheck unavailable; bash syntax and functional tests completed"
fi

echo "all Jeeb CMS MSI hosting tests passed"
