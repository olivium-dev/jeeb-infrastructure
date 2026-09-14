#!/usr/bin/env python3
"""Build the deterministic, credential-free MSI root bootstrap archive."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


ROOT_NAME = "jeeb-msi-runtime-activation-bootstrap-v7"
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "reviewed-runtime-activation-manifest.json"
INSTALLER = HERE / "install-reviewed-runtime-activation.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(repository: str, revision: str, source_path: str) -> bytes:
    endpoint = f"repos/{repository}/contents/{source_path}?ref={revision}"
    return subprocess.run(
        [
            "gh", "api", "-H", "Accept: application/vnd.github.raw+json",
            endpoint,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    ).stdout


def add(archive: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = "root"
    archive.addfile(info, io.BytesIO(data))


def add_directory(archive: tarfile.TarFile, name: str) -> None:
    info = tarfile.TarInfo(name.rstrip("/") + "/")
    info.type = tarfile.DIRTYPE
    info.mode = 0o700
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = "root"
    archive.addfile(info)


def build(output: Path) -> dict[str, object]:
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schemaVersion") != 1:
        raise ValueError("manifest-schema")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 7:
        raise ValueError("manifest-files")

    payload: list[tuple[str, bytes]] = []
    for item in files:
        data = fetch(item["repository"], item["revision"], item["sourcePath"])
        if sha256(data) != item["sha256"]:
            raise ValueError("source-digest")
        payload.append((item["packageName"], data))

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with tarfile.open(temporary, mode="w", format=tarfile.PAX_FORMAT) as archive:
            add_directory(archive, ROOT_NAME)
            add_directory(archive, f"{ROOT_NAME}/payload")
            add(
                archive,
                f"{ROOT_NAME}/install-reviewed-runtime-activation.py",
                INSTALLER.read_bytes(),
                0o500,
            )
            add(
                archive,
                f"{ROOT_NAME}/reviewed-runtime-activation-manifest.json",
                manifest_bytes,
                0o400,
            )
            for name, data in payload:
                add(archive, f"{ROOT_NAME}/{name}", data, 0o400)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    archive_bytes = output.read_bytes()
    return {
        "status": "packaged",
        "archive": str(output),
        "sha256": sha256(archive_bytes),
        "size": len(archive_bytes),
        "files": len(payload),
        "containsCredentials": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
