#!/usr/bin/env python3

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROLLOUT = ROOT / "deploy" / "staging" / "scripts" / "edge-origin-rollout.sh"
FUNCTIONS = (
    "write_status",
    "read_status",
    "require_state_identity",
    "verify_nginx_runtime",
    "verify_incumbent_origin",
    "restore_origin",
    "restore_after_apply_error",
    "rollback_origin",
)


def extract_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n", source)
    if match is None:
        raise AssertionError(f"could not extract {name}")
    return match.group(0)


class EdgeOriginRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = ROLLOUT.read_text(encoding="utf-8")
        cls.functions = "\n".join(extract_function(source, name) for name in FUNCTIONS)
        cls.bash = shutil.which("bash")
        if cls.bash is None:
            raise RuntimeError("bash is required")

    def run_fault_injection(self, failure_point: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / "state"
            static_root = root / "static"
            releases = static_root / "releases"
            incumbent = releases / "incumbent"
            candidate = releases / "candidate"
            state_dir.mkdir()
            incumbent.mkdir(parents=True)
            candidate.mkdir()

            commit_sha = "a" * 40
            config = root / "jeeb-direct-tls.conf"
            config.write_text("candidate\n", encoding="utf-8")
            (state_dir / "commit-sha").write_text(
                f"{commit_sha}\n", encoding="utf-8"
            )
            (state_dir / "status").write_text("prepared\n", encoding="utf-8")
            (state_dir / "jeeb-direct-tls.conf").write_text(
                "incumbent\n", encoding="utf-8"
            )
            (state_dir / "previous-current-kind").write_text(
                "symlink\n", encoding="utf-8"
            )
            (state_dir / "previous-current-target").write_text(
                "releases/incumbent\n", encoding="utf-8"
            )
            current_link = static_root / "current"
            current_link.symlink_to("releases/candidate")

            quoted = {
                "state_dir": shlex.quote(str(state_dir)),
                "config": shlex.quote(str(config)),
                "static_root": shlex.quote(str(static_root)),
                "current_link": shlex.quote(str(current_link)),
                "failure_point": shlex.quote(failure_point),
            }
            harness = f"""
set -u -o pipefail
run_key=123_1
commit_sha={commit_sha}
state_dir={quoted["state_dir"]}
config={quoted["config"]}
static_root={quoted["static_root"]}
current_link={quoted["current_link"]}
failure_point={quoted["failure_point"]}

{self.functions}

install() {{
  local arguments=("$@") count source target
  count=${{#arguments[@]}}
  source=${{arguments[$((count - 2))]}}
  target=${{arguments[$((count - 1))]}}
  if [ "$failure_point" = install ] && [ "$target" = "$config.restore-$run_key" ]; then
    return 71
  fi
  command cp -- "$source" "$target" || return
  command chmod 0644 "$target" || return
}}

mv() {{
  local arguments=("$@") count source target
  count=${{#arguments[@]}}
  source=${{arguments[$((count - 2))]}}
  target=${{arguments[$((count - 1))]}}
  if [ "$failure_point" = mv-config ] && [ "$target" = "$config" ]; then
    return 72
  fi
  python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
    "$source" "$target" || return
}}

nginx() {{
  if [ "$failure_point" = nginx ]; then
    return 73
  fi
  return 0
}}

systemctl() {{
  return 0
}}

cmp() {{
  if [ "$failure_point" = verification ]; then
    return 74
  fi
  command cmp "$@" || return
}}

set +e
(
  set -E -e
  trap restore_after_apply_error ERR
  bash -c 'exit 79'
)
apply_exit=$?
set -e

[ "$apply_exit" -eq 79 ]
[ "$(<"$state_dir/status")" = restoring ]
[ "$(<"$config")" != incumbent ] || [ "$failure_point" != install ]

failure_point=none
rollback_origin > "$state_dir/rollback-output"
[ "$(<"$state_dir/status")" = restored ]
cmp -s -- "$state_dir/jeeb-direct-tls.conf" "$config"
[ "$(readlink -- "$current_link")" = releases/incumbent ]
grep -Fxq origin_state=restored-and-verified "$state_dir/rollback-output"
"""
            result = subprocess.run(
                [self.bash],
                input=harness,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=(
                    f"failure point {failure_point!r} did not fail closed and recover\n"
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                ),
            )

    def test_failed_restore_never_marks_restored_and_rollback_retries(self) -> None:
        for failure_point in ("install", "mv-config", "nginx", "verification"):
            with self.subTest(failure_point=failure_point):
                self.run_fault_injection(failure_point)


if __name__ == "__main__":
    unittest.main()
