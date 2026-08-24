#!/usr/bin/env python3
"""Enforce the owner block and forward-only staging edge authority."""

from __future__ import annotations

import re
import subprocess
import textwrap
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
OWNER_BLOCK_JOB = "owner-forward-only-block"
DEFAULT_GATE_JOB = "default-branch-gate"
APPROVED_EDGE_JOBS = {DEFAULT_GATE_JOB, OWNER_BLOCK_JOB, "deploy"}
DEFAULT_GATE_STEP = "Refuse non-default-branch dispatch"
OWNER_BLOCK_STEP = "OWNER BLOCK — edge mutations are disabled"
OWNER_BLOCK_MARKER = "OWNER BLOCK: automatic rollback/recovery has been removed."
DIRECT_BLOCK_MARKER = "OWNER BLOCK: forward-only edge promotion is pending approval"
OWNER_BLOCK_COMMANDS = (
    "echo '::error::OWNER BLOCK: automatic rollback/recovery has been removed.'",
    "echo '::error::No Cloudflare, Worker, SSH, nginx, origin, or provider action is permitted.'",
    "echo '::error::Approve a forward-only failure policy before enabling this deployment.'",
    "exit 78",
)
DIRECT_BLOCK_COMMANDS = (
    "set -euo pipefail",
    "echo '::error::OWNER BLOCK: forward-only edge promotion is pending approval; "
    "no origin mutation was attempted.' >&2",
    "exit 78",
)
DEFAULT_GATE_COMMANDS = (
    "set -euo pipefail",
    '[ "$GITHUB_REF_TYPE" = branch ]',
    '[ "$GITHUB_REF_NAME" = "$DEFAULT_BRANCH" ] || {',
    "echo '::error::Staging edge deploys are allowed only from the default branch.'",
    "exit 1",
    "}",
)


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


def uncomment_yaml_scalar(value: str) -> str:
    """Remove an unquoted YAML comment from the small workflow subset we audit."""
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in ("'", '"'):
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if character == "#" and quote is None and (
            index == 0 or value[index - 1].isspace()
        ):
            return value[:index].rstrip()
    return value.rstrip()


def yaml_code(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    return uncomment_yaml_scalar(line)


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def workflow_jobs(source: str) -> dict[str, list[str]]:
    lines = source.splitlines()
    try:
        jobs_start = next(
            index for index, line in enumerate(lines) if yaml_code(line) == "jobs:"
        )
    except StopIteration:
        return {}

    jobs: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[jobs_start + 1 :]:
        code = yaml_code(line)
        if code and indentation(code) == 0:
            break
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+)\s*:", code)
        if match:
            current = match.group(1)
            jobs[current] = []
            continue
        if current is not None:
            jobs[current].append(line)
    return jobs


def direct_properties(lines: list[str], indent: int) -> dict[str, list[str]]:
    properties: dict[str, list[str]] = {}
    for line in lines:
        code = yaml_code(line)
        if not code or indentation(code) != indent:
            continue
        pattern = (
            rf"^\s{{{indent}}}(?:\"([A-Za-z0-9_-]+)\"|"
            rf"'([A-Za-z0-9_-]+)'|([A-Za-z0-9_-]+))\s*:(?:\s*(.*))?$"
        )
        match = re.match(pattern, code)
        if match:
            key = match.group(1) or match.group(2) or match.group(3)
            properties.setdefault(key, []).append((match.group(4) or "").strip())
    return properties


def workflow_steps(job_lines: list[str]) -> list[list[str]]:
    steps_start = next(
        (
            index
            for index, line in enumerate(job_lines)
            if yaml_code(line) == "    steps:"
        ),
        None,
    )
    if steps_start is None:
        return []

    steps: list[list[str]] = []
    current: list[str] | None = None
    for line in job_lines[steps_start + 1 :]:
        code = yaml_code(line)
        if code and indentation(code) <= 4:
            break
        if code and indentation(code) == 6 and code.lstrip().startswith("- "):
            current = [line]
            steps.append(current)
            continue
        if current is not None:
            current.append(line)
    return steps


def step_properties(step_lines: list[str]) -> dict[str, list[str]]:
    normalized: list[str] = []
    for index, line in enumerate(step_lines):
        code = yaml_code(line)
        if index == 0 and code and indentation(code) == 6:
            normalized.append("        " + code.lstrip()[2:])
        else:
            normalized.append(line)
    return direct_properties(normalized, 8)


def literal_run_script(step_lines: list[str]) -> str | None:
    for index, line in enumerate(step_lines):
        code = yaml_code(line)
        effective = code
        if index == 0 and code and indentation(code) == 6:
            effective = "        " + code.lstrip()[2:]
        if not re.fullmatch(r"        run:\s*\|[-+]?", effective):
            continue
        content: list[str] = []
        for candidate in step_lines[index + 1 :]:
            if candidate.strip() and indentation(candidate) <= 8:
                break
            content.append(candidate)
        return textwrap.dedent("\n".join(content)) + "\n"
    return None


def blocked_shell_result(
    source: str, variables: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    environment = {"PATH": ""}
    environment.update(variables or {})
    return subprocess.run(
        ["/bin/bash", "-c", source],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=3,
        check=False,
    )


def shell_command_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def edge_workflow_findings(source: str) -> list[str]:
    findings: list[str] = []
    jobs = workflow_jobs(source)
    actual_jobs = set(jobs)
    if actual_jobs != APPROVED_EDGE_JOBS:
        findings.append(
            "staging edge workflow job inventory must be exactly "
            f"{sorted(APPROVED_EDGE_JOBS)!r}; got {sorted(actual_jobs)!r}"
        )
    default_gate = jobs.get(DEFAULT_GATE_JOB)
    owner = jobs.get(OWNER_BLOCK_JOB)
    deploy = jobs.get("deploy")
    if default_gate is None:
        return [f"staging edge workflow is missing structural job {DEFAULT_GATE_JOB!r}"]
    if owner is None:
        return [f"staging edge workflow is missing structural job {OWNER_BLOCK_JOB!r}"]
    if deploy is None:
        return ["staging edge workflow is missing structural job 'deploy'"]

    default_properties = direct_properties(default_gate, 4)
    expected_default_properties = {"runs-on": ["ubuntu-22.04"], "steps": [""]}
    if default_properties != expected_default_properties:
        findings.append("default-branch-gate job properties are not canonical")
    default_steps = workflow_steps(default_gate)
    if len(default_steps) != 1:
        findings.append("default-branch-gate must contain exactly one branch-check step")
    else:
        default_step = default_steps[0]
        default_step_properties = step_properties(default_step)
        expected_step_properties = {
            "name": [DEFAULT_GATE_STEP],
            "env": [""],
            "run": ["|"],
        }
        if default_step_properties != expected_step_properties:
            findings.append("default-branch-gate step properties are not canonical")
        default_environment = direct_properties(default_step, 10)
        if default_environment != {
            "DEFAULT_BRANCH": ["${{ github.event.repository.default_branch }}"]
        }:
            findings.append("default-branch-gate environment is not canonical")
        default_script = literal_run_script(default_step)
        if default_script is None:
            findings.append("default-branch-gate must contain a literal run script")
        else:
            if tuple(shell_command_lines(default_script)) != DEFAULT_GATE_COMMANDS:
                findings.append("default-branch-gate run script is not canonical")
            result = blocked_shell_result(
                default_script,
                {
                    "GITHUB_REF_TYPE": "branch",
                    "GITHUB_REF_NAME": "main",
                    "DEFAULT_BRANCH": "main",
                },
            )
            if result.returncode != 0:
                findings.append(
                    "default-branch-gate must pass its exact branch check under empty PATH"
                )

    for job_name, job_lines in ((OWNER_BLOCK_JOB, owner), ("deploy", deploy)):
        properties = direct_properties(job_lines, 4)
        if "continue-on-error" in properties:
            findings.append(f"{job_name} must not set job-level continue-on-error")
        if "if" in properties:
            findings.append(f"{job_name} must not set any job-level if condition")

    deploy_needs = direct_properties(deploy, 4).get("needs", [])
    if deploy_needs != [OWNER_BLOCK_JOB]:
        findings.append(
            f"deploy must structurally need only {OWNER_BLOCK_JOB!r}; got {deploy_needs!r}"
        )

    owner_steps = workflow_steps(owner)
    if len(owner_steps) != 1:
        findings.append("owner block job must contain exactly one step")
        return findings
    owner_step = owner_steps[0]
    owner_properties = step_properties(owner_step)
    if owner_properties.get("name") != [OWNER_BLOCK_STEP]:
        findings.append("owner block step name is missing or structurally changed")
    if "if" in owner_properties or "continue-on-error" in owner_properties:
        findings.append("owner block step must be unconditional and fail-closed")
    block_script = literal_run_script(owner_step)
    if block_script is None:
        findings.append("owner block step must contain a literal run script")
    else:
        if tuple(shell_command_lines(block_script)) != OWNER_BLOCK_COMMANDS:
            findings.append("owner block run script contains an unexpected command")
        result = blocked_shell_result(block_script)
        output = result.stdout + result.stderr
        if result.returncode != 78 or OWNER_BLOCK_MARKER not in output:
            findings.append(
                "owner block script must emit its marker and exit exactly 78 under empty PATH"
            )

    for step in workflow_steps(deploy):
        properties = step_properties(step)
        if "continue-on-error" in properties:
            findings.append("deploy steps must not set continue-on-error")
        if "if" in properties:
            findings.append("deploy steps must not set conditional execution")
    return findings


def direct_rollout_block_findings(source: str) -> list[str]:
    findings: list[str] = []
    commands = shell_command_lines(source)
    if tuple(commands[: len(DIRECT_BLOCK_COMMANDS)]) != DIRECT_BLOCK_COMMANDS:
        findings.append("origin rollout owner block is not the first executable prefix")
    result = blocked_shell_result(source)
    output = result.stdout + result.stderr
    if result.returncode != 78 or DIRECT_BLOCK_MARKER not in output:
        findings.append(
            "origin rollout must emit its owner marker and exit exactly 78 under empty PATH"
        )
    return findings


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
    findings.extend(edge_workflow_findings(workflow))
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
                "systemctl reload nginx",
                "apply)",
                "finalize)",
            ),
            "staging origin rollout",
        )
    )
    findings.extend(direct_rollout_block_findings(rollout))
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
