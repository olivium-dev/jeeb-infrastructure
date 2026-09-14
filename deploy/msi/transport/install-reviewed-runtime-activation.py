#!/usr/bin/python3 -I
"""Install the reviewed MSI activation helpers through one root-only action."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tempfile


EXPECTED_HOSTNAME = "ouday-GT70-2OC-2OD"
EXPECTED_TRANSPORT_ACCOUNT = ("msi-access", 1002, 1002)
PACKAGE_ROOT = Path("/root/jeeb-msi-runtime-activation-bootstrap")
INSTALLER = PACKAGE_ROOT / "install-reviewed-runtime-activation.py"
VISUDO = Path("/usr/sbin/visudo")
MAX_SOURCE_BYTES = 1024 * 1024


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileSpec:
    package_name: str
    destination: Path
    sha256: str
    mode: int
    validate_sudoers: bool = False


FILES = (
    FileSpec(
        "payload/jeeb-msi-chat-firebase-admin",
        Path("/usr/local/sbin/jeeb-msi-chat-firebase-admin"),
        "af54023079743a06ddb14a4024fc693b40289566ecf37f55a4a5078bbe56315a",
        0o755,
    ),
    FileSpec(
        "payload/jeeb-msi-push-firebase-admin",
        Path("/usr/local/sbin/jeeb-msi-push-firebase-admin"),
        "32fb31dcc17616475640ab37cc91fa3a08754939d1cc001edfdf7ebd69d3e205",
        0o755,
    ),
    FileSpec(
        "payload/jeeb-msi-user-management-firebase-admin",
        Path("/usr/local/sbin/jeeb-msi-user-management-firebase-admin"),
        "fdb36357f5561affc8f963a3bb78cf071131a50931d69a94c6697f164ef61497",
        0o755,
    ),
    FileSpec(
        "payload/jeeb-msi-user-management-smtp-admin",
        Path("/usr/local/sbin/jeeb-msi-user-management-smtp-admin"),
        "763e1f369f015027939cfa3bc16332b57895f8c6bcf720b25a57e2ae18f3e088",
        0o755,
    ),
    FileSpec(
        "payload/jeeb-msi-runtime-activation.sudoers",
        Path("/etc/sudoers.d/jeeb-msi-runtime-activation"),
        "73561496839190b0d4ceb54ef5b0e6ffe64949a380c927d66d3ccc044a338b7d",
        0o440,
        validate_sudoers=True,
    ),
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise InstallError(reason)


def _directory(path: Path, *, mode: int | None = None) -> None:
    metadata = path.lstat()
    require(stat.S_ISDIR(metadata.st_mode) and not path.is_symlink(), "unsafe-directory")
    require((metadata.st_uid, metadata.st_gid) == (0, 0), "unsafe-directory-owner")
    require(not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH), "writable-directory")
    if mode is not None:
        require(stat.S_IMODE(metadata.st_mode) == mode, "unsafe-directory-mode")


def _read_exact(path: Path, *, uid: int, gid: int, mode: int) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        require(
            stat.S_ISREG(metadata.st_mode)
            and (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode))
            == (uid, gid, mode)
            and metadata.st_nlink == 1
            and 0 < metadata.st_size <= MAX_SOURCE_BYTES,
            "unsafe-file-metadata",
        )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            require(total <= MAX_SOURCE_BYTES, "source-too-large")
            chunks.append(chunk)
        require(total == metadata.st_size, "source-size-changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _source_bytes(package_root: Path, spec: FileSpec) -> bytes:
    source = package_root / spec.package_name
    require(source.parent.resolve().is_relative_to(package_root.resolve()), "source-path")
    data = _read_exact(source, uid=0, gid=0, mode=0o400)
    require(hashlib.sha256(data).hexdigest() == spec.sha256, "source-digest")
    return data


def _target_state(spec: FileSpec) -> str:
    try:
        data = _read_exact(spec.destination, uid=0, gid=0, mode=spec.mode)
    except FileNotFoundError:
        return "absent"
    require(hashlib.sha256(data).hexdigest() == spec.sha256, "target-drift")
    return "exact"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install_absent(spec: FileSpec, data: bytes) -> None:
    parent = spec.destination.parent
    prefix = f".{spec.destination.name}.bootstrap-"
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, dir=parent)
    temporary = Path(temporary_name)
    linked = False
    try:
        os.fchmod(descriptor, spec.mode)
        os.fchown(descriptor, 0, 0)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            require(written > 0, "install-write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        # Hard-link creation is the portable no-replace operation used here.
        os.link(temporary, spec.destination, follow_symlinks=False)
        linked = True
        temporary.unlink()
        _fsync_directory(parent)
        require(_target_state(spec) == "exact", "install-verification")
    except BaseException:
        if linked:
            try:
                _remove_created(spec)
            except BaseException as rollback_error:
                raise InstallError("single-file-rollback-incomplete") from rollback_error
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()


def _remove_created(spec: FileSpec) -> None:
    require(_target_state(spec) == "exact", "rollback-target-drift")
    spec.destination.unlink()
    _fsync_directory(spec.destination.parent)


def _visudo(path: Path) -> None:
    result = subprocess.run(
        [str(VISUDO), "-cf", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    require(result.returncode == 0, "sudoers-invalid")


def install(
    *,
    package_root: Path = PACKAGE_ROOT,
    specs: tuple[FileSpec, ...] = FILES,
    validate_host: bool = True,
) -> dict[str, object]:
    require(os.geteuid() == 0, "must-run-as-root")
    if validate_host:
        require(socket.gethostname() == EXPECTED_HOSTNAME, "wrong-host")
        name, expected_uid, expected_gid = EXPECTED_TRANSPORT_ACCOUNT
        account = pwd.getpwnam(name)
        require((account.pw_uid, account.pw_gid) == (expected_uid, expected_gid),
                "wrong-transport-account")
        require(package_root == PACKAGE_ROOT, "wrong-package-root")
        require(Path(__file__).resolve() == INSTALLER, "wrong-installer-path")
    _directory(package_root, mode=0o700)
    _directory(package_root / "payload", mode=0o700)
    if validate_host:
        _read_exact(INSTALLER, uid=0, gid=0, mode=0o500)
    for parent in sorted({spec.destination.parent for spec in specs}):
        _directory(parent)

    payload = {spec: _source_bytes(package_root, spec) for spec in specs}
    states = {spec: _target_state(spec) for spec in specs}
    for spec in specs:
        if spec.validate_sudoers:
            _visudo(package_root / spec.package_name)

    created: list[FileSpec] = []
    try:
        # The sudoers file is declared last and therefore cannot expose a helper
        # command until every reviewed helper has been installed and verified.
        for spec in specs:
            if states[spec] == "exact":
                continue
            _install_absent(spec, payload[spec])
            created.append(spec)
        for spec in specs:
            require(_target_state(spec) == "exact", "final-verification")
            if spec.validate_sudoers:
                _visudo(spec.destination)
    except BaseException as install_error:
        rollback_errors: list[str] = []
        for spec in reversed(created):
            try:
                _remove_created(spec)
            except BaseException:
                rollback_errors.append(spec.destination.name)
        if rollback_errors:
            raise InstallError("rollback-incomplete") from install_error
        raise InstallError("install-failed-rolled-back") from install_error

    return {
        "status": "installed",
        "host": EXPECTED_HOSTNAME,
        "created": len(created),
        "alreadyExact": len(specs) - len(created),
        "helperCount": len(specs) - 1,
        "sudoCommandCount": 9,
        "serviceRestarts": 0,
        "containsCredentials": False,
    }


def main() -> int:
    if len(sys.argv) != 1:
        print("msi-runtime-bootstrap:unexpected-arguments", file=sys.stderr)
        return 2
    try:
        result = install()
    except (InstallError, OSError, KeyError, subprocess.SubprocessError):
        print("msi-runtime-bootstrap:failed-safe", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
