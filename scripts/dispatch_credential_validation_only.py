#!/usr/bin/env python3
"""Names-only dispatcher for final organization-secret validation.

The controller requests metadata only. It requires one selected-repository
organization-secret binding, rejects same-name repository and Environment
shadows, pins a protected default ref, and then dispatches the manual workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ORG = "olivium-dev"
WORKFLOW = "credential-validation-only.yml"
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Target:
    repo: str
    branch: str
    environment: str
    secrets: tuple[str, ...]
    pins: tuple[str, ...]


TARGETS = (
    Target(
        "chat-service",
        "main",
        "staging",
        ("JEEB_STAGING_CHAT_SERVICE_JEEB_FIREBASE_JSON",),
        ("JEEB_FIREBASE_CLIENT_EMAIL_SHA256",),
    ),
    Target(
        "push-notification",
        "main",
        "staging",
        ("JEEB_STAGING_PUSH_NOTIFICATION_JEEB_FIREBASE_JSON",),
        ("JEEB_FIREBASE_CLIENT_EMAIL_SHA256",),
    ),
    Target(
        "one-time-password",
        "master",
        "staging",
        (
            "JEEB_STAGING_ONE_TIME_PASSWORD_JEEB_OTP_TWILIO_ACCOUNT_SID",
            "JEEB_STAGING_ONE_TIME_PASSWORD_JEEB_OTP_TWILIO_API_KEY",
            "JEEB_STAGING_ONE_TIME_PASSWORD_JEEB_OTP_TWILIO_API_SECRET",
            "JEEB_STAGING_ONE_TIME_PASSWORD_JEEB_OTP_TWILIO_PHONE_NUMBER",
        ),
        (
            "JEEB_TWILIO_ACCOUNT_SID_SHA256",
            "JEEB_TWILIO_API_KEY_SID_SHA256",
            "JEEB_TWILIO_SENDER_SHA256",
        ),
    ),
    Target(
        "jeeb-infrastructure",
        "main",
        "staging",
        ("JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_API_TOKEN",),
        ("JEEB_CLOUDFLARE_TOKEN_ID_SHA256",),
    ),
    Target(
        "voice-transcription-service",
        "main",
        "development",
        ("JEEB_DEVELOPMENT_VOICE_TRANSCRIPTION_SERVICE_OPENAI_API_KEY",),
        ("JEEB_OPENAI_API_KEY_SHA256",),
    ),
    Target(
        "voice-transcription-service",
        "main",
        "staging",
        ("JEEB_STAGING_VOICE_TRANSCRIPTION_SERVICE_OPENAI_API_KEY",),
        ("JEEB_OPENAI_API_KEY_SHA256",),
    ),
)


class GateError(RuntimeError):
    pass


def gh_json(path: str, category: str) -> object:
    completed = subprocess.run(
        ["gh", "api", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise GateError(f"metadata-unavailable:{category}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise GateError(f"metadata-schema:{category}") from None


def bounded_items(path: str, key: str, category: str) -> list[dict]:
    value = gh_json(f"{path}?per_page=100", category)
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise GateError(f"metadata-schema:{category}")
    items = value[key]
    total = value.get("total_count")
    if not isinstance(total, int) or total != len(items):
        raise GateError(f"metadata-pagination:{category}")
    if not all(isinstance(item, dict) for item in items):
        raise GateError(f"metadata-schema:{category}")
    return items


def names(items: list[dict], category: str) -> set[str]:
    result = {item.get("name") for item in items}
    if not all(isinstance(name, str) for name in result):
        raise GateError(f"metadata-schema:{category}")
    return result  # type: ignore[return-value]


def require_org_secret_acl(full_repo: str, secret_name: str) -> None:
    category = f"org-secret:{full_repo}:{secret_name}"
    metadata = gh_json(f"orgs/{ORG}/actions/secrets/{secret_name}", category)
    if (
        not isinstance(metadata, dict)
        or metadata.get("name") != secret_name
        or metadata.get("visibility") != "selected"
    ):
        raise GateError(f"org-secret-not-selected:{full_repo}:{secret_name}")
    repositories = bounded_items(
        f"orgs/{ORG}/actions/secrets/{secret_name}/repositories",
        "repositories",
        f"org-secret-acl:{full_repo}:{secret_name}",
    )
    full_names = {repo.get("full_name") for repo in repositories}
    if full_names != {full_repo}:
        raise GateError(f"org-secret-acl-mismatch:{full_repo}:{secret_name}")


def require_exact_scope(target: Target) -> str:
    full_repo = f"{ORG}/{target.repo}"
    branch = gh_json(
        f"repos/{full_repo}/branches/{target.branch}",
        f"branch:{full_repo}:{target.branch}",
    )
    if (
        not isinstance(branch, dict)
        or branch.get("protected") is not True
        or not isinstance(branch.get("commit"), dict)
        or not isinstance(branch["commit"].get("sha"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", branch["commit"]["sha"])
    ):
        raise GateError(f"protected-default-ref-unproven:{target.repo}")

    repository = gh_json(f"repos/{full_repo}", f"repository:{full_repo}")
    if not isinstance(repository, dict) or repository.get("default_branch") != target.branch:
        raise GateError(f"default-ref-mismatch:{target.repo}")

    environment_secret_names = names(
        bounded_items(
            f"repos/{full_repo}/environments/{target.environment}/secrets",
            "secrets",
            f"environment-secrets:{full_repo}",
        ),
        f"environment-secrets:{full_repo}",
    )
    repository_secret_names = names(
        bounded_items(
            f"repos/{full_repo}/actions/secrets",
            "secrets",
            f"repository-secrets:{full_repo}",
        ),
        f"repository-secrets:{full_repo}",
    )
    for secret_name in target.secrets:
        require_org_secret_acl(full_repo, secret_name)
        if secret_name in repository_secret_names or secret_name in environment_secret_names:
            raise GateError(f"higher-precedence-shadow:{target.repo}:{secret_name}")

    environment_vars = bounded_items(
        f"repos/{full_repo}/environments/{target.environment}/variables",
        "variables",
        f"environment-variables:{full_repo}",
    )
    repository_variable_names = names(
        bounded_items(
            f"repos/{full_repo}/actions/variables",
            "variables",
            f"repository-variables:{full_repo}",
        ),
        f"repository-variables:{full_repo}",
    )
    organization_variable_names = names(
        bounded_items(
            f"orgs/{ORG}/actions/variables",
            "variables",
            "organization-variables",
        ),
        "organization-variables",
    )
    environment_variable_by_name = {
        item.get("name"): item.get("value") for item in environment_vars
    }
    for pin_name in target.pins:
        pin_value = environment_variable_by_name.get(pin_name)
        if not isinstance(pin_value, str) or not HEX_SHA256.fullmatch(pin_value):
            raise GateError(f"environment-pin-missing:{target.repo}:{pin_name}")
        if pin_name in repository_variable_names or pin_name in organization_variable_names:
            raise GateError(f"pin-shadow-present:{target.repo}:{pin_name}")
    return branch["commit"]["sha"]


def dispatch(target: Target, commit_sha: str) -> None:
    fields = ["--field", f"expected_commit_sha={commit_sha}"]
    if target.repo == "voice-transcription-service":
        fields.extend(["--field", f"target_environment={target.environment}"])
    completed = subprocess.run(
        [
            "gh",
            "workflow",
            "run",
            WORKFLOW,
            "--repo",
            f"{ORG}/{target.repo}",
            "--ref",
            target.branch,
            *fields,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise GateError(f"dispatch-failed:{target.repo}")


def write_manifest(path: Path, wave_id: str, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": "jeeb-credential-validation-wave/v1",
        "wave_id": wave_id,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "environments": sorted({record["environment"] for record in records}),
        "production_accessed": False,
        "credential_values_observed": False,
        "records": records,
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(body, handle, sort_keys=True, indent=2)
        handle.write("\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{5,63}", args.wave_id):
        print("credential-validation-dispatch:FAIL:wave-id", file=sys.stderr)
        return 2
    try:
        checked = [(target, require_exact_scope(target)) for target in TARGETS]
        records: list[dict] = []
        for target, commit_sha in checked:
            if args.dispatch:
                dispatch(target, commit_sha)
            records.append(
                {
                    "repository": f"{ORG}/{target.repo}",
                    "environment": target.environment,
                    "protected_ref": target.branch,
                    "commit_sha": commit_sha,
                    "workflow": WORKFLOW,
                    "organization_secret_names": list(target.secrets),
                    "identity_pin_names": list(target.pins),
                    "selected_repository_acl_exact": True,
                    "repository_shadow": False,
                    "environment_shadow": False,
                    "status": "dispatch-requested" if args.dispatch else "preflight-pass",
                }
            )
        write_manifest(args.manifest, args.wave_id, records)
    except GateError as error:
        suffix = f":{error}" if args.diagnostic else ":closed"
        print(f"credential-validation-dispatch:FAIL{suffix}", file=sys.stderr)
        return 2
    except FileExistsError:
        suffix = ":manifest-exists" if args.diagnostic else ":closed"
        print(f"credential-validation-dispatch:FAIL{suffix}", file=sys.stderr)
        return 2
    except OSError:
        print("credential-validation-dispatch:FAIL:closed", file=sys.stderr)
        return 2
    print(
        "credential-validation-dispatch:PASS:requested"
        if args.dispatch
        else "credential-validation-dispatch:PASS:preflight"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
