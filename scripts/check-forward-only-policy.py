#!/usr/bin/env python3
"""Reject prior-state deployment authority in every tracked text file."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    ("Swarm service deletion/reversion", re.compile(r"\bservice\s+(?:r" + r"m|roll" + r"back)\b", re.I)),
    ("Swarm automatic reversion", re.compile(r"update-failure-action[ =:]roll" + r"back\b", re.I)),
    ("Swarm reversion option", re.compile(r"--roll" + r"back(?:-|\b)", re.I)),
    ("container rename swap", re.compile(r"\bdocker\s+rename\b", re.I)),
    ("Kubernetes rollout undo", re.compile(r"\bkubectl\s+rollout\s+undo\b", re.I)),
    ("Helm reversion", re.compile(r"\bhelm\s+roll" + r"back\b", re.I)),
    (
        "Git prior-state selection",
        re.compile(
            r"\bgit\s+(?:re" + r"vert\b|reset\s+--hard\b|(?:checkout|switch)\s+"
            r"(?:(?:HEAD(?:[~^]\d*)+)|[\"']?\$\{?(?:PREVIOUS|PRIOR|OLD|BASE)"
            r"[A-Z0-9_]*\}?[\"']?|[0-9a-f]{7,})(?=\s|$))",
            re.I,
        ),
    ),
    ("database prior-state artifact", re.compile(r"\bpg_" + r"(?:restore|dump)\b", re.I)),
    (
        "schema downgrade",
        re.compile(
            r"\b(?:alembic\s+down" + r"grade|mix\s+ecto\.roll" + r"back|goose\s+down|flyway\s+undo)\b",
            re.I,
        ),
    ),
    ("Entity Framework Down migration", re.compile(r"\boverride\s+void\s+D" + r"own\s*\(", re.I)),
    ("mutable image alias", re.compile(r":lat" + r"est\b", re.I)),
    ("mutable GHCR tag", re.compile(r"ghcr\.io/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+", re.I)),
    ("backup overwrite", re.compile(r"\b(?:c" + r"p|m" + r"v)\b[^\n]*(?:\.bak\b|backup)[^\n]*(?:current|active|production)", re.I)),
    ("predecessor symlink selection", re.compile(r"\bl" + r"n\s+-sfn\b[^\n]*(?:previous|predecessor|backup)", re.I)),
    (
        "prior deployment restoration",
        re.compile(
            r"\b(?:restore|repoint)\b.{0,80}\b(?:previous|prior|superseded)\s+"
            r"(?:release|image|ruleset|deployment)\b",
            re.I,
        ),
    ),
)

FORBIDDEN_CONTROLS = (
    "docker service " + "r" + "m service",
    "docker service " + "roll" + "back service",
    'sudo "$DOCKER_BIN" service ' + "r" + "m service",
    'sudo "$DOCKER_BIN" service ' + "roll" + "back service",
    "--update-failure-action " + "roll" + "back",
    "docker " + "rename service-old service",
    "kubectl rollout " + "undo deployment/service",
    "helm " + "roll" + "back service 2",
    "git " + "re" + "vert deadbeef",
    "git reset " + "--hard",
    "git checkout " + "deadbeef",
    "git checkout HEAD" + "~1",
    "git switch HEAD" + "^",
    'git checkout "$' + 'PREVIOUS_SHA"',
    "pg_" + "restore service.dump",
    "pg_" + "dump service > service.dump",
    "alembic down" + "grade -1",
    "override void D" + "own(MigrationBuilder builder)",
    "ghcr.io/olivium-dev/service:" + "latest",
    "c" + "p service.backup /srv/service/current",
    "l" + "n -sfn /srv/service/previous /srv/service/current",
    "docker service " + "\\\n" + "roll" + "back service",
    'ENGINE=docker; "$ENGINE" service ' + "\\\n" + "r" + "m service",
)

BENIGN_CONTROLS = (
    "transaction." + "rollback()",
    "docker compose down",
    "git checkout -- package.json",
)

MUTATION_CONTROLS = (
    'ENGINE=docker; "$ENGINE" service update --image "$IMAGE" app',
    "docker service create --name app image@sha256:" + "a" * 64,
    "docker service scale app=0",
    "docker stack deploy -c compose.yml app",
    "docker stack " + "r" + "m app",
    'ENGINE=docker; "$ENGINE" service ' + "\\\n" + 'update --image "$IMAGE" app',
)


def normalized_shell_source(source: str) -> str:
    """Collapse shell line continuations before policy and inventory scans."""
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


def main() -> int:
    for control in FORBIDDEN_CONTROLS:
        normalized_control = normalized_shell_source(control)
        if not any(pattern.search(normalized_control) for _, pattern in PATTERNS):
            print(f"policy negative control was not rejected: {control}")
            return 2
    for control in BENIGN_CONTROLS:
        if any(pattern.search(control) for _, pattern in PATTERNS):
            print(f"benign control was rejected: {control}")
            return 2

    files = list(tracked_utf8())
    findings = []
    for path, source in files:
        normalized_source = normalized_shell_source(source)
        for line_number, line in enumerate(normalized_source.splitlines(), 1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path}:{line_number}:{label}:{line.strip()}")
    if findings:
        print("Forward-only policy violations:")
        print("\n".join(findings))
        return 1

    mutation_command = re.compile(
        r"\b(?:service\s+(?:create|update|scale)|stack\s+(?:deploy|r" + r"m))\b",
        re.I,
    )
    for control in MUTATION_CONTROLS:
        if not mutation_command.search(normalized_shell_source(control)):
            print(f"mutation inventory negative control was not rejected: {control}")
            return 2
    executable_mutations = [
        path
        for path, source in files
        if path.suffix.lower() in {".sh", ".yml", ".yaml"}
        and mutation_command.search(normalized_shell_source(source))
    ]
    if executable_mutations:
        print(
            "Infrastructure must not duplicate application or datastore Swarm mutation authority: "
            + ", ".join(map(str, executable_mutations))
        )
        return 2

    print(
        f"Forward-only policy verified across {len(files)} tracked UTF-8 files; "
        "no Swarm mutation authority is retained."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
