#!/usr/bin/python3 -I
"""Install the reviewed MSI activation helpers through one root-only action."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
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
PACKAGE_ROOT = Path("/root/jeeb-msi-runtime-activation-bootstrap-v4")
INSTALLER = PACKAGE_ROOT / "install-reviewed-runtime-activation.py"
VISUDO = Path("/usr/sbin/visudo")
DEPLOYMENT_LOCK = Path("/run/jeeb-msi-service-deploy.lock")
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
    predecessor_sha256: tuple[str, ...] = ()


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
        "088fe0bc221314369653b610ca35bfcde9512cf48fb80bb5e7e4fea118f3c8ef",
        0o755,
        predecessor_sha256=(
            "32fb31dcc17616475640ab37cc91fa3a08754939d1cc001edfdf7ebd69d3e205",
        ),
    ),
    FileSpec(
        "payload/jeeb-msi-user-management-firebase-admin",
        Path("/usr/local/sbin/jeeb-msi-user-management-firebase-admin"),
        "bdd2e7248bc78b753270d10ea5fc573ddb6294d9046f1c6fc7e733162db4970f",
        0o755,
        predecessor_sha256=(
            "e69b02523ffc391755429c1f46bda988c7bf0a303e374c1deeaabe3eb796d63f",
            "8468cc9a87aad83df51edc701b1d577f502e7f0a1197b94eff9a72b81c466357",
            "fdb36357f5561affc8f963a3bb78cf071131a50931d69a94c6697f164ef61497",
        ),
    ),
    FileSpec(
        "payload/jeeb-msi-user-management-smtp-admin",
        Path("/usr/local/sbin/jeeb-msi-user-management-smtp-admin"),
        "4e062041680facb2d5c0d6c478e2db0cfe50b6502650f3659316e8be2320fef2",
        0o755,
        predecessor_sha256=(
            "763e1f369f015027939cfa3bc16332b57895f8c6bcf720b25a57e2ae18f3e088",
        ),
    ),
    FileSpec(
        "payload/jeeb-msi-otp-twilio-admin",
        Path("/usr/local/sbin/jeeb-msi-otp-twilio-admin"),
        "0cc8003c7ced0badbf6858cc43888c116b8c09b93d8b2dc37554414a49e60735",
        0o755,
    ),
    FileSpec(
        "payload/jeeb-msi-gateway-firebase-diagnostics-admin",
        Path("/usr/local/sbin/jeeb-msi-gateway-firebase-diagnostics-admin"),
        "8095616b956bb5c455c0b44f018612a79a6fd2570025e7c1bc7ee8d5dfe04438",
        0o755,
    ),
    FileSpec(
        "payload/jeeb-msi-runtime-activation.sudoers",
        Path("/etc/sudoers.d/jeeb-msi-runtime-activation"),
        "dd8ceed91afaf154a2e3766692b407a9d28dab35cdcbc4429cca98d851ad4189",
        0o440,
        validate_sudoers=True,
        predecessor_sha256=(
            "73561496839190b0d4ceb54ef5b0e6ffe64949a380c927d66d3ccc044a338b7d",
        ),
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
    digest = hashlib.sha256(data).hexdigest()
    if digest == spec.sha256:
        return "exact"
    if digest in spec.predecessor_sha256:
        return "predecessor"
    raise InstallError("target-drift")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepared_temporary(spec: FileSpec, data: bytes) -> Path:
    parent = spec.destination.parent
    prefix = f".{spec.destination.name}.bootstrap-"
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, dir=parent)
    temporary = Path(temporary_name)
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
        return temporary
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise


def _install_absent(spec: FileSpec, data: bytes) -> None:
    parent = spec.destination.parent
    temporary = _prepared_temporary(spec, data)
    linked = False
    try:
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
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()


def _restore_predecessor(spec: FileSpec, previous: bytes) -> None:
    require(_target_state(spec) == "exact", "rollback-upgrade-target-drift")
    require(hashlib.sha256(previous).hexdigest() in spec.predecessor_sha256,
            "rollback-predecessor-digest")
    temporary = _prepared_temporary(spec, previous)
    try:
        os.replace(temporary, spec.destination)
        _fsync_directory(spec.destination.parent)
        require(_target_state(spec) == "predecessor", "rollback-upgrade-verification")
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()


def _replace_predecessor(spec: FileSpec, data: bytes) -> bytes:
    previous = _read_exact(spec.destination, uid=0, gid=0, mode=spec.mode)
    require(hashlib.sha256(previous).hexdigest() in spec.predecessor_sha256,
            "upgrade-predecessor-digest")
    require(_target_state(spec) == "predecessor", "upgrade-predecessor-drift")
    temporary = _prepared_temporary(spec, data)
    replaced = False
    try:
        require(_target_state(spec) == "predecessor", "upgrade-predecessor-drift")
        os.replace(temporary, spec.destination)
        replaced = True
        _fsync_directory(spec.destination.parent)
        require(_target_state(spec) == "exact", "upgrade-verification")
        return previous
    except BaseException:
        if replaced:
            try:
                _restore_predecessor(spec, previous)
            except BaseException as rollback_error:
                raise InstallError("single-file-upgrade-rollback-incomplete") from rollback_error
        raise
    finally:
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


@contextmanager
def operation_lock():
    _directory(DEPLOYMENT_LOCK.parent)
    descriptor = os.open(
        DEPLOYMENT_LOCK,
        os.O_RDWR
        | os.O_CREAT
        | os.O_NONBLOCK
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_nlink == 1
            and (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode))
            == (0, 0, 0o600),
            "deployment-lock-metadata",
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstallError("deployment-lock-busy") from error
        yield
    finally:
        os.close(descriptor)


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

    mutations: list[tuple[str, FileSpec, bytes | None]] = []
    try:
        # The sudoers file is declared last and therefore cannot expose a helper
        # command until every reviewed helper has been installed and verified.
        for spec in specs:
            if states[spec] == "exact":
                continue
            if states[spec] == "predecessor":
                previous = _replace_predecessor(spec, payload[spec])
                mutations.append(("upgraded", spec, previous))
            else:
                _install_absent(spec, payload[spec])
                mutations.append(("created", spec, None))
        for spec in specs:
            require(_target_state(spec) == "exact", "final-verification")
            if spec.validate_sudoers:
                _visudo(spec.destination)
    except BaseException as install_error:
        rollback_errors: list[str] = []
        for action, spec, previous in reversed(mutations):
            try:
                if action == "created":
                    _remove_created(spec)
                else:
                    require(previous is not None, "rollback-predecessor-missing")
                    _restore_predecessor(spec, previous)
            except BaseException:
                rollback_errors.append(spec.destination.name)
        if rollback_errors:
            raise InstallError("rollback-incomplete") from install_error
        raise InstallError("install-failed-rolled-back") from install_error

    return {
        "status": "installed",
        "host": EXPECTED_HOSTNAME,
        "created": sum(action == "created" for action, _, _ in mutations),
        "upgraded": sum(action == "upgraded" for action, _, _ in mutations),
        "alreadyExact": len(specs) - len(mutations),
        "helperCount": len(specs) - 1,
        "sudoCommandCount": 14,
        "serviceRestarts": 0,
        "containsCredentials": False,
    }


def main() -> int:
    if len(sys.argv) != 1:
        print("msi-runtime-bootstrap:unexpected-arguments", file=sys.stderr)
        return 2
    try:
        with operation_lock():
            result = install()
    except (InstallError, OSError, KeyError, subprocess.SubprocessError):
        print("msi-runtime-bootstrap:failed-safe", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
