#!/usr/bin/env python3
"""Assemble one immutable Jeeb CMS artifact from four production dist trees."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


RELEASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def regular_tree(source: Path, label: str) -> None:
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"{label} dist must be a real directory: {source}")
    for candidate in source.rglob("*"):
        if candidate.is_symlink():
            raise ValueError(f"{label} dist contains a symbolic link: {candidate}")
        if not candidate.is_dir() and not candidate.is_file():
            raise ValueError(f"{label} dist contains a non-regular entry: {candidate}")


def is_within(candidate: Path, parent: Path) -> bool:
    return os.path.commonpath((candidate, parent)) == str(parent)


def validate_layout(sources: dict[str, Path], output: Path) -> None:
    labels = tuple(sources)
    for index, label in enumerate(labels):
        source = sources[label]
        if is_within(output, source):
            raise ValueError(f"output must not be inside the {label} dist")
        for other_label in labels[index + 1 :]:
            other = sources[other_label]
            if is_within(source, other) or is_within(other, source):
                raise ValueError(f"dist trees must not overlap: {label} and {other_label}")

    reserved = ("mf", "release.json", "SHA256SUMS")
    for name in reserved:
        if (sources["shell"] / name).exists() or (sources["shell"] / name).is_symlink():
            raise ValueError(f"shell dist contains assembler-reserved path: {name}")


def copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for candidate in source.iterdir():
        target = destination / candidate.name
        if candidate.is_dir():
            shutil.copytree(candidate, target)
        elif candidate.is_file():
            shutil.copy2(candidate, target)
        else:
            raise ValueError(f"dist contains a non-regular entry: {candidate}")


def write_manifest(root: Path) -> None:
    names = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    with (root / "SHA256SUMS").open("w", encoding="utf-8") as manifest:
        for name in names:
            digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
            manifest.write(f"{digest}  {name}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--deliveries", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--cms-commit", required=True)
    parser.add_argument("--gateway-commit", required=True)
    parser.add_argument("--openapi-sha256", required=True)
    args = parser.parse_args()

    if not RELEASE_ID_RE.fullmatch(args.release_id):
        parser.error("--release-id contains unsafe characters or is too long")
    if not GIT_SHA_RE.fullmatch(args.cms_commit):
        parser.error("--cms-commit must be a lowercase 40-character Git SHA")
    if not GIT_SHA_RE.fullmatch(args.gateway_commit):
        parser.error("--gateway-commit must be a lowercase 40-character Git SHA")
    if not SHA256_RE.fullmatch(args.openapi_sha256):
        parser.error("--openapi-sha256 must be a lowercase SHA-256 digest")
    if args.output.exists() or args.output.is_symlink():
        parser.error("--output must not already exist")

    sources = {
        "shell": args.shell.resolve(),
        "cases": args.cases.resolve(),
        "deliveries": args.deliveries.resolve(),
        "settlements": args.settlements.resolve(),
    }
    for label, source in sources.items():
        regular_tree(source, label)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    try:
        validate_layout(sources, output)
    except ValueError as exc:
        parser.error(str(exc))

    temporary = Path(tempfile.mkdtemp(prefix=f".{args.release_id}.assembling.", dir=output.parent))
    try:
        copy_tree_contents(sources["shell"], temporary)
        for remote in ("cases", "deliveries", "settlements"):
            copy_tree_contents(sources[remote], temporary / "mf" / remote)
        metadata = {
            "releaseId": args.release_id,
            "cmsCommit": args.cms_commit,
            "gatewayCommit": args.gateway_commit,
            "openapiSha256": args.openapi_sha256,
            "builtAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        (temporary / "release.json").write_text(
            json.dumps(metadata, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        write_manifest(temporary)
        validator = Path(__file__).with_name("validate-release.py")
        subprocess.run(
            [sys.executable, str(validator), str(temporary), "--expected-release-id", args.release_id],
            check=True,
        )
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
