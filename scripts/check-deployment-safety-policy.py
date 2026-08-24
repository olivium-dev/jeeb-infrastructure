#!/usr/bin/env python3
"""Enforce fail-closed staging edge deployment and recovery authority."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDGE_WORKFLOW = ROOT / ".github/workflows/jeeb-staging-edge-deploy.yml"
SAFETY_WORKFLOW = ROOT / ".github/workflows/deployment-safety.yml"
CONTRACT_WORKFLOW = ROOT / ".github/workflows/staging-edge-contract.yml"
EDGE_ROLLOUT = ROOT / "deploy/staging/scripts/edge-origin-rollout.sh"
WSS_PROBE = ROOT / "deploy/staging/scripts/verify-authorized-wss.mjs"
ACTIVE_RUNBOOK = ROOT / "deploy/staging-192.168.2.20.md"


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
                "failure() && steps.worker-incumbent.outcome == 'success'",
                'rollback "$EDGE_RUN_KEY" "$GITHUB_SHA"',
                "RED + RESTORATION FAILED",
                "StrictHostKeyChecking yes",
                "JEEB_STAGING_SSH_KNOWN_HOSTS",
                "realpath -m -- \"$HOME/$candidate\"",
                '"$(dirname -- "$target")" = "$root"',
            ),
            "staging edge workflow",
        )
    )
    findings.extend(
        require(
            rollout,
            (
                '[ "$(hostname -s)" = "olivium-ephemerals" ]',
                "grep -Fxq '192.168.2.20'",
                '[ "$stage_ref" = ".jeeb-edge-deploy/$run_key" ]',
                "verify_incumbent_origin()",
                "verify_candidate_origin()",
                "restore_origin()",
                'recording > "$capture_dir/status"',
                "write_status prepared",
                "write_status applied",
                "write_status verified",
                "write_status restoring",
                "write_status restored",
                "prepared|applied|verified|restoring",
                "cmp -s -- \"$state_dir/jeeb-direct-tls.conf\" \"$config\"",
                "systemctl reload nginx",
                "rollback)",
            ),
            "staging origin rollout",
        )
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
            safety + contract,
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
                "Edge rollback and recovery gate",
                "RED + RESTORATION FAILED",
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

    mutation_command = re.compile(
        r"\b(?:service\s+(?:create|update|scale|rm)|stack\s+(?:deploy|rm))\b",
        re.I,
    )
    executable_mutations = [
        path
        for path, source in tracked_utf8()
        if path.suffix.lower() in {".sh", ".yml", ".yaml"}
        and mutation_command.search(normalized_shell_source(source))
    ]
    if executable_mutations:
        findings.append(
            "Infrastructure duplicates application/datastore Swarm mutation authority: "
            + ", ".join(map(str, executable_mutations))
        )

    if findings:
        print("Deployment safety violations:")
        print("\n".join(findings))
        return 1

    print(
        "Deployment safety verified: exact Worker version/domain state, atomic origin "
        "recovery, real authorized Phoenix WSS, strict access, and no infra-owned "
        "Swarm mutation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
