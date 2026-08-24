#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "scripts" / "check-deployment-safety-policy.py"
SAFETY_WORKFLOW = ROOT / ".github" / "workflows" / "deployment-safety.yml"

SPEC = importlib.util.spec_from_file_location("deployment_safety_policy", POLICY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load deployment safety policy")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class DeploymentSafetyPolicyTests(unittest.TestCase):
    def assert_policy_rejects(self, path: Path, source: str) -> None:
        output = io.StringIO()
        with patch.object(
            POLICY, "tracked_utf8", return_value=iter([(path, source)])
        ), redirect_stdout(output):
            exit_code = POLICY.main()
        self.assertEqual(exit_code, 1)
        self.assertIn(str(path), output.getvalue())

    def test_safety_gate_runs_for_every_pr_and_main_push(self) -> None:
        workflow = SAFETY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("push:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIsNone(re.search(r"(?m)^\s+paths(?:-ignore)?:", workflow))

    def test_mutation_outside_former_path_filter_is_rejected(self) -> None:
        path = Path("ops/new-release-authority.yml")
        self.assert_policy_rejects(
            path,
            "run: docker service update --image candidate jeeb_gateway\n",
        )

    def test_service_rollback_is_rejected(self) -> None:
        path = Path("tools/emergency-recovery.sh")
        self.assert_policy_rejects(
            path,
            "docker service rollback jeeb_gateway\n",
        )

    def test_read_only_swarm_inspection_is_allowed(self) -> None:
        path = Path("tools/check-service.sh")
        mutations = POLICY.executable_mutation_paths(
            [(path, "docker service ps jeeb_gateway\n")]
        )
        self.assertEqual(mutations, [])


if __name__ == "__main__":
    unittest.main()
