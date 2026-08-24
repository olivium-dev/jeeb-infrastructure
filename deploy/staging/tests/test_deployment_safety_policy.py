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
EDGE_WORKFLOW = ROOT / ".github" / "workflows" / "jeeb-staging-edge-deploy.yml"
EDGE_ROLLOUT = ROOT / "deploy" / "staging" / "scripts" / "edge-origin-rollout.sh"

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

    def test_owner_block_is_structural_and_required_by_deploy(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(POLICY.edge_workflow_findings(workflow), [])

    def test_edge_workflow_has_no_failure_mutation_handler(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        jobs = POLICY.workflow_jobs(workflow)
        deploy = jobs["deploy"]
        for step in POLICY.workflow_steps(deploy):
            properties = POLICY.step_properties(step)
            self.assertNotIn("continue-on-error", properties)
            self.assertNotIn("if", properties)

    def test_deploy_job_always_condition_cannot_bypass_owner_block(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        mutated = workflow.replace(
            "  deploy:\n    needs: owner-forward-only-block\n",
            "  deploy:\n    if: ${{ always() }}\n    needs: owner-forward-only-block\n",
            1,
        )
        self.assertNotEqual(mutated, workflow)
        self.assertTrue(POLICY.edge_workflow_findings(mutated))

    def test_all_job_level_status_and_continue_bypasses_are_rejected(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        for property_line in (
            "if: ${{ always() }}",
            "if: ${{ failure() }}",
            "if: ${{ cancelled() }}",
            "continue-on-error: true",
        ):
            with self.subTest(property_line=property_line):
                mutated = workflow.replace(
                    "  deploy:\n    needs: owner-forward-only-block\n",
                    f"  deploy:\n    {property_line}\n"
                    "    needs: owner-forward-only-block\n",
                    1,
                )
                self.assertNotEqual(mutated, workflow)
                self.assertTrue(POLICY.edge_workflow_findings(mutated))

    def test_commented_owner_need_cannot_hide_real_deploy_dependency(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        mutated = workflow.replace(
            "  deploy:\n    needs: owner-forward-only-block\n",
            "  deploy:\n    # needs: owner-forward-only-block\n"
            "    needs: default-branch-gate\n",
            1,
        )
        self.assertNotEqual(mutated, workflow)
        findings = POLICY.edge_workflow_findings(mutated)
        self.assertTrue(any("structurally need" in finding for finding in findings))

    def test_direct_rollout_if_false_wrapper_cannot_hide_owner_block(self) -> None:
        rollout = EDGE_ROLLOUT.read_text(encoding="utf-8")
        block = (
            "echo '::error::OWNER BLOCK: forward-only edge promotion is pending "
            "approval; no origin mutation was attempted.' >&2\n"
            "exit 78"
        )
        wrapped = "if false; then\n  " + block.replace("\n", "\n  ") + "\nfi"
        mutated = rollout.replace(block, wrapped, 1)
        self.assertNotEqual(mutated, rollout)
        self.assertTrue(POLICY.direct_rollout_block_findings(mutated))

    def test_direct_rollout_exits_78_without_path_or_arguments(self) -> None:
        rollout = EDGE_ROLLOUT.read_text(encoding="utf-8")
        self.assertEqual(POLICY.direct_rollout_block_findings(rollout), [])

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

    def test_worker_rollback_is_rejected(self) -> None:
        path = Path("ops/edge-recovery.yml")
        recoveries = POLICY.executable_recovery_paths(
            [(path, "run: npx wrangler@4.120.0 rollback deadbeef --yes\n")]
        )
        self.assertEqual(recoveries, [path])

    def test_origin_restore_function_is_rejected(self) -> None:
        path = Path("ops/edge-recovery.sh")
        recoveries = POLICY.executable_recovery_paths(
            [(path, "restore_origin() { nginx -t; }\n")]
        )
        self.assertEqual(recoveries, [path])

    def test_read_only_swarm_inspection_is_allowed(self) -> None:
        path = Path("tools/check-service.sh")
        mutations = POLICY.executable_mutation_paths(
            [(path, "docker service ps jeeb_gateway\n")]
        )
        self.assertEqual(mutations, [])

    def test_read_only_worker_inspection_is_allowed(self) -> None:
        path = Path("ops/check-worker.sh")
        recoveries = POLICY.executable_recovery_paths(
            [(path, "npx wrangler@4.120.0 deployments status --json\n")]
        )
        self.assertEqual(recoveries, [])


if __name__ == "__main__":
    unittest.main()
