#!/usr/bin/env python3
"""Enforce staging edge restoration and keep Swarm authority out of infra."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDGE_WORKFLOW = ROOT / ".github/workflows/jeeb-staging-edge-deploy.yml"
EDGE_ROLLOUT = ROOT / "deploy/staging/scripts/edge-origin-rollout.sh"


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
    rollout = EDGE_ROLLOUT.read_text(encoding="utf-8")
    findings: list[str] = []

    findings.extend(
        require(
            workflow,
            (
                "workflow_dispatch:",
                'environment: staging',
                'DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}',
                '[ "$GITHUB_REF_NAME" = "$DEFAULT_BRANCH" ]',
                "Capture the exact incumbent Worker version",
                'wrangler@$WRANGLER_VERSION\" rollback',
                "failure() && steps.origin.outcome == 'success'",
                "StrictHostKeyChecking yes",
                "JEEB_STAGING_SSH_KNOWN_HOSTS",
                "CLOUDFLARE_API_TOKEN",
                "Verify public HTTPS, association identities, and WSS routing",
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
                "restore_origin()",
                "nginx -t",
                "systemctl reload nginx",
                "rollback)",
            ),
            "staging origin rollout",
        )
    )

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
        "Deployment safety verified: default-branch edge deploy, strict access, "
        "live gates, automatic restoration, and no infra-owned Swarm mutation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
