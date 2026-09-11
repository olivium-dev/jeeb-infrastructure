"""Credential-free contracts for the existing workflow's isolated opt-in mode."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/jeeb-staging-readiness-inventory.yml"
GUARD = ROOT / "deploy/staging/scripts/assert-protected-ingress-source.sh"
spec = importlib.util.spec_from_file_location("deployment_policy", ROOT / "scripts/check-deployment-safety-policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ProtectedWorkflowTests(unittest.TestCase):
    def test_opt_in_is_exact_and_default_has_no_secret_or_elevation(self):
        source = WORKFLOW.read_text()
        self.assertEqual(source.split("\npermissions:\n", 1)[1].split("\nconcurrency:", 1)[0].strip(),
                         "contents: read\n  actions: read")
        inputs = source.split("    inputs:\n", 1)[1].split("\npermissions:", 1)[0]
        names = [line.strip()[:-1] for line in inputs.splitlines()
                 if line.startswith("      ") and not line.startswith("       ") and line.endswith(":")]
        self.assertEqual(names, ["protected_ingress", "reviewed_sha"])
        self.assertIn("type: boolean\n        required: false\n        default: false", inputs)
        self.assertIn("type: string\n        required: false\n        default: ''", inputs)
        steps = policy.workflow_steps(policy.workflow_jobs(source)["inventory"])
        names = [policy.step_properties(step).get("name", [""])[0] for step in steps]
        protected = names.index("Collect opt-in protected ingress evidence")
        self.assertEqual(names[protected - 1], "Recheck protected current source immediately before authenticated diagnostic")
        self.assertLess(names.index("Verify protected ingress source before transport preparation"),
                        names.index("Prepare pinned user-space transport"))
        for index, step in enumerate(steps):
            text = "\n".join(step)
            properties = policy.step_properties(step)
            if "MSI_SSH_PASSWORD" in text or "STAGING_SUDO_PASSWORD" in text:
                self.assertEqual(index, protected)
                self.assertEqual(properties["if"], ["${{ inputs.protected_ingress }}"])
                self.assertEqual(text.count("secrets.MSI_SSH_PASSWORD"), 1)
                self.assertNotIn("GH_TOKEN", text)
            if names[index] == "Collect fixed read-only staging evidence":
                self.assertEqual(properties["if"], ["${{ !inputs.protected_ingress }}"])
                self.assertNotIn("sudo", text)
                self.assertIn("< deploy/staging/scripts/readiness-inventory.py", text)
        self.assertEqual(source.count("secrets.MSI_SSH_PASSWORD"), 1)
        self.assertIn('[ "$SSH_USER" = ec2-user ]', source)
        self.assertIn("StrictHostKeyChecking yes", source)
        self.assertIn("persist-credentials: false", source)
        for forbidden in ("workflow_call:", "secrets: inherit", "continue-on-error:", "sudo bash", "sudo sh", "scp "):
            self.assertNotIn(forbidden, source)

    def test_only_validated_output_is_retained(self):
        source = WORKFLOW.read_text()
        step = source.split("      - name: Collect opt-in protected ingress evidence\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("python3 -I -B deploy/staging/scripts/protected-ingress-transport.py", step)
        self.assertIn('> "$RUNNER_TEMP/protected-ingress-report.json"', step)
        self.assertNotIn("2>&1", step)
        self.assertNotIn("tee", step)
        artifact = source.split("      - name: Retain validated protected ingress evidence\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("steps.protected-ingress.outcome == 'success'", artifact)
        self.assertIn("path: ${{ runner.temp }}/protected-ingress-report.json", artifact)
        self.assertNotIn("**", artifact)

    def test_root_fixtures_only_in_credential_free_existing_ci(self):
        source = (ROOT / ".github/workflows/staging-edge-contract.yml").read_text()
        self.assertIn("sudo -n /usr/bin/python3 -B -m unittest discover -s deploy/staging/tests -p test_protected_ingress_collector.py -v", source)
        self.assertNotIn("secrets.", source)
        self.assertNotIn("test_protected_ingress_collector.py", WORKFLOW.read_text())

    def test_source_requests_are_read_only_and_bounded(self):
        source = GUARD.read_text()
        self.assertEqual(source.count("timeout 20s gh api --hostname github.com"), 2)
        self.assertNotIn("--method", source)
        self.assertNotIn("STAGING_SUDO_PASSWORD", source)
        self.assertNotIn("MSI_SSH_PASSWORD", source)


@unittest.skipUnless(shutil.which("jq") and shutil.which("timeout"), "source guard uses jq/timeout supplied by hosted Ubuntu")
class SourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="protected-source-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "source.txt").write_text("reviewed fixture\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "gh"
        fake.write_text("#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\n"
                        "name='branch.json' if sys.argv[-1].endswith('/branches/main') else 'run.json'\n"
                        "sys.stdout.write((Path(os.environ['FIXTURE_ROOT'])/name).read_text())\n")
        fake.chmod(0o700)
        self.branch = {"protected": True, "commit": {"sha": self.sha}}
        self.run = {"id": 123, "head_sha": self.sha, "head_branch": "main", "event": "workflow_dispatch",
                    "run_attempt": 1, "path": ".github/workflows/jeeb-staging-readiness-inventory.yml",
                    "repository": {"full_name": "olivium-dev/jeeb-infrastructure"},
                    "actor": {"login": "oudaykhaled"}, "triggering_actor": {"login": "oudaykhaled"}}
        self.env = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"], "FIXTURE_ROOT": str(self.root),
                    "PROTECTED_INGRESS": "true", "GITHUB_REPOSITORY": "olivium-dev/jeeb-infrastructure",
                    "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                    "SOURCE_DEFAULT_BRANCH": "main", "SOURCE_REF_PROTECTED": "true", "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_ACTOR": "oudaykhaled", "GITHUB_TRIGGERING_ACTOR": "oudaykhaled",
                    "REVIEWED_SHA": self.sha, "GITHUB_SHA": self.sha, "GITHUB_RUN_ID": "123"}

    def execute(self, changes=None, args=()):
        (self.root / "branch.json").write_text(json.dumps(self.branch))
        (self.root / "run.json").write_text(json.dumps(self.run))
        return subprocess.run(["bash", str(GUARD), *args], cwd=self.repo,
                              env={**self.env, **(changes or {})}, capture_output=True, text=True, timeout=10)

    def test_current_protected_owner_source_passes(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_metadata_and_argument_negatives(self):
        for key, value in (("PROTECTED_INGRESS", "false"), ("GITHUB_REPOSITORY", "other/repo"),
                           ("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REF", "refs/heads/other"),
                           ("SOURCE_DEFAULT_BRANCH", "other"), ("SOURCE_REF_PROTECTED", "false"),
                           ("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_ACTOR", "other"),
                           ("GITHUB_TRIGGERING_ACTOR", "other"), ("REVIEWED_SHA", "x" * 40),
                           ("GITHUB_SHA", "a" * 40), ("GITHUB_RUN_ID", "../other")):
            with self.subTest(key=key):
                self.assertNotEqual(self.execute({key: value}).returncode, 0)
        self.assertNotEqual(self.execute(args=("arbitrary",)).returncode, 0)

    def test_remote_branch_run_and_worktree_negatives(self):
        self.branch["protected"] = False
        self.assertNotEqual(self.execute().returncode, 0)
        self.branch["protected"] = True
        self.branch["commit"]["sha"] = "a" * 40
        self.assertNotEqual(self.execute().returncode, 0)
        self.branch["commit"]["sha"] = self.sha
        for key, value in (("id", 124), ("head_sha", "a" * 40), ("head_branch", "other"),
                           ("event", "push"), ("run_attempt", 2), ("path", "other.yml"),
                           ("actor", {"login": "other"}), ("triggering_actor", {"login": "other"})):
            original = self.run[key]
            self.run[key] = value
            with self.subTest(key=key):
                self.assertNotEqual(self.execute().returncode, 0)
            self.run[key] = original
        (self.repo / "source.txt").write_text("changed\n")
        self.assertNotEqual(self.execute().returncode, 0)
