#!/usr/bin/env python3

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROLLOUT = ROOT / "deploy" / "staging" / "scripts" / "edge-origin-rollout.sh"


class EdgeOriginForwardOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ROLLOUT.read_text(encoding="utf-8")

    def test_only_forward_modes_are_executable(self) -> None:
        modes = re.findall(r"(?m)^  ([a-z][a-z-]*)\)$", self.source)
        self.assertEqual(modes, ["apply", "finalize"])

    def test_argument_validation_precedes_any_tool_or_host_access(self) -> None:
        validation = self.source.index("stage_ref=${4:-}")
        for marker in (
            'hostname -s',
            "ip -4 -o addr",
            'install -d -o root',
            'flock -n 9',
            'systemctl reload nginx',
        ):
            with self.subTest(marker=marker):
                self.assertGreater(self.source.index(marker), validation)

    def test_automatic_recovery_authority_is_absent(self) -> None:
        for forbidden in (
            "restore_origin()",
            "restore_after_apply_error()",
            "rollback_origin()",
            "rollback)",
            "trap ",
            "write_status restoring",
            "write_status restored",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_lock_and_audit_snapshot_remain_before_mutation(self) -> None:
        self.assertIn('exec 9>"$state_root/.lock"', self.source)
        self.assertIn("flock -n 9", self.source)
        self.assertIn(
            'install -o root -g root -m 0600 "$config" \\\n'
            '      "$capture_dir/jeeb-direct-tls.conf"',
            self.source,
        )
        snapshot = self.source.index('mv -- "$capture_dir" "$state_dir"')
        audit = self.source.index("verify_incumbent_origin", snapshot)
        mutation = self.source.index('"$config.candidate-$run_key"', audit)
        self.assertLess(snapshot, audit)
        self.assertLess(audit, mutation)
        self.assertIn("The snapshot is retained for audit only.", self.source)

    def test_forward_state_is_explicit_and_finalized(self) -> None:
        self.assertIn('recording > "$capture_dir/status"', self.source)
        self.assertIn("write_status prepared", self.source)
        self.assertIn("write_status applied", self.source)
        self.assertIn("write_status verified", self.source)
        self.assertIn('[ "$(read_status)" = applied ]', self.source)

    def test_rendered_candidate_is_captured_before_test_and_reload(self) -> None:
        rendered = self.source.index(
            'nginx -T | sha256sum > "$state_dir/nginx-rendered-candidate.sha256"'
        )
        tested = self.source.index("nginx -t", rendered)
        reloaded = self.source.index("systemctl reload nginx", tested)
        self.assertLess(rendered, tested)
        self.assertLess(tested, reloaded)
        self.assertIn(
            'chmod 0600 "$state_dir/nginx-rendered-candidate.sha256"',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
