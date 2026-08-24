#!/usr/bin/env python3
"""Enforce the owner block and forward-only staging edge authority."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDGE_WORKFLOW = ROOT / ".github/workflows/jeeb-staging-edge-deploy.yml"
SAFETY_WORKFLOW = ROOT / ".github/workflows/deployment-safety.yml"
CONTRACT_WORKFLOW = ROOT / ".github/workflows/staging-edge-contract.yml"
EDGE_ROLLOUT = ROOT / "deploy/staging/scripts/edge-origin-rollout.sh"
WSS_PROBE = ROOT / "deploy/staging/scripts/verify-authorized-wss.mjs"
ACTIVE_RUNBOOK = ROOT / "deploy/staging-192.168.2.20.md"
SWARM_MUTATION_COMMAND = re.compile(
    r"\b(?:service\s+(?:create|update|rollback|scale|rm)|"
    r"stack\s+(?:deploy|rm))\b",
    re.I,
)
AUTOMATIC_EDGE_RECOVERY_COMMAND = re.compile(
    r"\bwrangler(?:@[^\s\"]+)?[^\n]*\brollback\b|"
    r"\bdocker\s+service\s+rollback\b|"
    r"\b(?:restore_after_apply_error|restore_origin|rollback_origin)\b|"
    r"^\s*rollback\)\s*$|"
    r"\brollback\s+\"\$EDGE_RUN_KEY\"",
    re.I | re.M,
)
EXECUTABLE_SUFFIXES = {".sh", ".yml", ".yaml"}


def normalized_shell_source(source: str) -> str:
    return re.sub(r"\\[ \t]*\r?\n[ \t]*", " ", source)


def tracked_utf8():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    for raw in names.split(b"\0"):
        if not raw:
            continue
        path = ROOT / raw.decode("utf-8")
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        try:
            yield path.relative_to(ROOT), data.decode("utf-8")
        except UnicodeDecodeError:
            continue


def require(source: str, needles: tuple[str, ...], label: str) -> list[str]:
    return [f"{label} is missing {needle!r}" for needle in needles if needle not in source]


def executable_mutation_paths(sources: Iterable[tuple[Path, str]]) -> list[Path]:
    return [
        path
        for path, source in sources
        if path.suffix.lower() in EXECUTABLE_SUFFIXES
        and SWARM_MUTATION_COMMAND.search(normalized_shell_source(source))
    ]


def executable_recovery_paths(sources: Iterable[tuple[Path, str]]) -> list[Path]:
    return [
        path
        for path, source in sources
        if path.suffix.lower() in EXECUTABLE_SUFFIXES
        and AUTOMATIC_EDGE_RECOVERY_COMMAND.search(normalized_shell_source(source))
    ]


def main() -> int:
    workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
    safety = SAFETY_WORKFLOW.read_text(encoding="utf-8")
    contract = CONTRACT_WORKFLOW.read_text(encoding="utf-8")
    rollout = EDGE_ROLLOUT.read_text(encoding="utf-8")
    wss_probe = WSS_PROBE.read_text(encoding="utf-8")
    runbook = ACTIVE_RUNBOOK.read_text(encoding="utf-8")
    findings: list[str] = []

    findings.extend(
        require(
            workflow,
            (
                "workflow_dispatch:",
                "environment: staging",
                "node-version: '22.18.0'",
                "DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}",
                '[ "$GITHUB_REF_NAME" = "$DEFAULT_BRANCH" ]',
                "owner-forward-only-block:",
                "OWNER BLOCK — edge mutations are disabled",
                "OWNER BLOCK: automatic rollback/recovery has been removed.",
                "No Cloudflare, Worker, SSH, nginx, origin, or provider action is permitted.",
                "exit 78",
                "needs: owner-forward-only-block",
                "Capture exact incumbent Worker and domain associations",
                "versions upload",
                "WRANGLER_OUTPUT_FILE_PATH",
                '"$candidate@100%"',
                '[ "$active" = "$CANDIDATE_WORKER_VERSION" ]',
                "/workers/domains",
                'cmp "$RUNNER_TEMP/incumbent-worker-domains.json"',
                "JEEB_STAGING_WSS_PROBE_MINT_KEY",
                "https://app.jeeb.fds-1.com/health/ready",
                "https://cms.jeeb.fds-1.com/healthz",
                "verify-authorized-wss.mjs",
                "StrictHostKeyChecking yes",
                "JEEB_STAGING_SSH_KNOWN_HOSTS",
                '"$(dirname -- "$target")" = "$root"',
            ),
            "staging edge workflow",
        )
    )
    block_start = workflow.find("  owner-forward-only-block:")
    deploy_start = workflow.find("  deploy:")
    if block_start < 0 or deploy_start < 0 or block_start >= deploy_start:
        findings.append("owner block must be a separate prerequisite job before deploy")
    else:
        block_job = workflow[block_start:deploy_start]
        for forbidden in ("uses:", "secrets.", "curl ", "ssh ", "npx ", "wrangler"):
            if forbidden in block_job:
                findings.append(
                    f"owner block performs a provider or external action: {forbidden!r}"
                )
    if "if: ${{ failure()" in workflow or "if: failure()" in workflow:
        findings.append("staging edge workflow still has an automatic failure handler")
    findings.extend(
        require(
            rollout,
            (
                '[ "$(hostname -s)" = "olivium-ephemerals" ]',
                "grep -Fxq '192.168.2.20'",
                '[ "$stage_ref" = ".jeeb-edge-deploy/$run_key" ]',
                "verify_incumbent_origin()",
                "verify_candidate_origin()",
                'recording > "$capture_dir/status"',
                "write_status prepared",
                "write_status applied",
                "write_status verified",
                "cmp -s -- \"$state_dir/jeeb-direct-tls.conf\" \"$config\"",
                "The snapshot is retained for audit only.",
                "OWNER BLOCK: forward-only edge promotion is pending approval",
                "exit 78",
                "systemctl reload nginx",
                "apply)",
                "finalize)",
            ),
            "staging origin rollout",
        )
    )
    script_block = rollout.find("OWNER BLOCK: forward-only edge promotion")
    script_stop = rollout.find("exit 78", script_block)
    first_host_access = rollout.find("hostname -s")
    if not (0 <= script_block < script_stop < first_host_access):
        findings.append(
            "origin rollout must stop loudly before argument, host, tool, or mutation access"
        )
    findings.extend(
        require(
            wss_probe,
            (
                'createHmac("sha256", mintKey)',
                'descriptorPath = "/internal/ops/staging/realtime-probe-descriptor"',
                'socketUrl.protocol !== "wss:"',
                'socketUrl.hostname !== publicHost',
                '"heartbeat"',
                '"phx_join"',
                '"not_in_membership"',
                "forged_ticket=denied",
                '"authorized WSS request did not receive a 101 upgrade"',
                "remainingMs < 30_000 || remainingMs > 900_000",
            ),
            "authorized WSS probe",
        )
    )
    findings.extend(
        require(
            safety,
            (
                "pull_request:",
                "push:",
                "branches: [main]",
            ),
            "deployment safety workflow trigger",
        )
    )
    if re.search(r"(?m)^\s+paths(?:-ignore)?:", safety):
        findings.append(
            "deployment safety workflow must audit every pull request and main push"
        )
    findings.extend(
        require(
            contract,
            (
                "'.github/workflows/jeeb-staging-edge-deploy.yml'",
                "'deploy/staging/**'",
                "'scripts/check-deployment-safety-policy.py'",
            ),
            "edge contract path filters",
        )
    )
    findings.extend(
        require(
            runbook,
            (
                "Super Login Plus is retired",
                "Authorized realtime edge-probe contract",
                "Owner-blocked forward-only edge deployment",
                "No automatic Worker or origin rollback",
            ),
            "active staging runbook",
        )
    )
    if "returns exactly Nour and Karim" in runbook:
        findings.append("active staging runbook still treats Super Login as a release gate")

    for forbidden in (
        "StrictHostKeyChecking accept-new",
        "StrictHostKeyChecking no",
        "192.168.2." + "50",
        "service rm",
        ":latest",
    ):
        if forbidden in workflow or forbidden in rollout:
            findings.append(f"staging edge deploy contains forbidden text {forbidden!r}")

    mutable_action = re.compile(r"^\s*uses:\s*(?!\./)[^@\s]+@(?!(?:[0-9a-f]{40})\s*$)", re.M)
    if mutable_action.search(workflow):
        findings.append("staging edge workflow has a mutable external action reference")

    executable_mutations = executable_mutation_paths(tracked_utf8())
    if executable_mutations:
        findings.append(
            "Infrastructure duplicates application/datastore Swarm mutation authority: "
            + ", ".join(map(str, executable_mutations))
        )

    executable_recoveries = executable_recovery_paths(tracked_utf8())
    if executable_recoveries:
        findings.append(
            "Infrastructure contains prohibited automatic rollback/recovery authority: "
            + ", ".join(map(str, executable_recoveries))
        )

    if findings:
        print("Deployment safety violations:")
        print("\n".join(findings))
        return 1

    print(
        "Deployment safety verified: loud owner block, forward-only edge code, exact "
        "Worker/domain state, real authorized Phoenix WSS, strict access, and no "
        "automatic rollback/recovery or infra-owned Swarm mutation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
