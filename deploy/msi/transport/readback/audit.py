#!/usr/bin/python3 -IB
"""Owner-only fixed development readback. No CLI inputs; no service mutations."""
import ast
import contextlib
import errno
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import pwd
import resource
import select
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import time
import types

BASE = "962ac6815be32174a9e8dca2119fe9f32ac808e5"
FIXED_SCRIPT = "/root/jeeb-row20-readback-v1/audit.py"
HOST = "ouday-GT70-2OC-2OD"
UNIT = "jeeb-user-management.service"
LOCK = "/run/jeeb-msi-service-deploy.lock"
POLICY = "/etc/sudoers.d/jeeb-msi-runtime-activation"
POLICY_HASH = "dd8ceed91afaf154a2e3766692b407a9d28dab35cdcbc4429cca98d851ad4189"
SOURCE = "50f9e89614a75266b86db07e0b6298777c858746"
NATIVE_ARCHIVE = "54848781c9c8a1d61292ebcd0d9f97b9e01f5f45d7500e47ea06effa83cfc4e9"
BOOTSTRAP_ARCHIVE = "eb7ab758caa553908bdb87aea05f70c7f11057e2cac697e324a767fff8cc9059"
HELPERS = {
    "chat-firebase": "af54023079743a06ddb14a4024fc693b40289566ecf37f55a4a5078bbe56315a",
    "push-firebase": "088fe0bc221314369653b610ca35bfcde9512cf48fb80bb5e7e4fea118f3c8ef",
    "user-management-firebase": "b5af4d006242589a0c4add05377146021ed172a72c22000a5f25297f163daddf",
    "user-management-smtp": "5d79348bbc589d0e2d1bb259c89f75f09249bf038dd2a81ac0120f600ce350aa",
    "otp-twilio": "0cc8003c7ced0badbf6858cc43888c116b8c09b93d8b2dc37554414a49e60735",
    "gateway-firebase-diagnostics": "8095616b956bb5c455c0b44f018612a79a6fd2570025e7c1bc7ee8d5dfe04438",
}
SIBLINGS = ("jeeb-chat.service", "jeeb-push.service", "jeeb-otp.service", "jeeb-gateway.service")
PROPERTIES = "Id,LoadState,ActiveState,SubState,MainPID,NRestarts,WorkingDirectory,User,Group,FragmentPath,DropInPaths"
CHAT_SNAPSHOT_PROPERTIES = "User,WorkingDirectory,ExecStart,Environment,EnvironmentFiles,FragmentPath,DropInPaths,ActiveState"
PHASES = ("entry", "transport", "policy", "lock", "units", "um-receipt", "um-credentials", "um-runtime", "predecessor", "chat-stage", "stable-snapshot")
CHECKS = ("transport", "policy", "lock", "units", "um-receipt", "um-credentials", "um-runtime", "predecessor", "chat-stage", "stable-snapshot")
_pending_command = None


class AuditHold(Exception):
    pass


def require(value):
    if not value:
        raise AuditHold()


def json_unique(raw):
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value)
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def protected_fd(path, *, uid=0, gid=0, mode=None, limit=1024 * 1024, parent_uids=(0,)):
    """Walk with directory FDs; no symlink component or writable parent admitted."""
    require(path.startswith("/") and ".." not in Path(path).parts)
    parts = Path(path).parts[1:]
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nxt
            info = os.fstat(directory)
            require(info.st_uid in parent_uids and info.st_gid in parent_uids and not info.st_mode & 0o022)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        require((info.st_uid, info.st_gid) == (uid, gid))
        require(mode is None or stat.S_IMODE(info.st_mode) == mode)
        require(0 <= info.st_size <= limit)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_held(fd, limit):
    before = os.fstat(fd)
    output = bytearray()
    while True:
        chunk = os.read(fd, min(65536, limit + 1 - len(output)))
        if not chunk:
            break
        output.extend(chunk)
        require(len(output) <= limit)
    after = os.fstat(fd)
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
    return bytes(output)


def read_file(path, **kwargs):
    limit = kwargs.get("limit", 1024 * 1024)
    fd = protected_fd(path, **kwargs)
    try:
        return read_held(fd, limit)
    finally:
        os.close(fd)


def protected_directory(path, mode=None, owner=(0, 0)):
    for parent in reversed((Path(path), *Path(path).parents)):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and info.st_gid == 0 and not info.st_mode & 0o022)
    info = Path(path).lstat()
    require((info.st_uid, info.st_gid) == owner)
    require(mode is None or stat.S_IMODE(info.st_mode) == mode)


def bounded_tree(root):
    """Pre-bound reviewed helper's later traversal; shared lock excludes deployers."""
    protected_directory(root, 0o755)
    pending = [Path(root)]
    entries = 0
    total = 0
    while pending:
        directory = pending.pop()
        require(len(directory.relative_to(root).parts) <= 8)
        for path in directory.iterdir():
            entries += 1
            require(entries <= 256)
            info = path.lstat()
            require((info.st_uid, info.st_gid) == (0, 0) and not info.st_mode & 0o022)
            if stat.S_ISDIR(info.st_mode):
                require(stat.S_IMODE(info.st_mode) == 0o755)
                pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
                total += info.st_size
                require(info.st_size <= 16777216 and total <= 33554432)


def archive_manifest_exact(raw, files):
    """Tie the root receipt to the known native archive without extracting files."""
    require(hashlib.sha256(raw).hexdigest() == NATIVE_ARCHIVE)
    observed = []
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for count, member in enumerate(archive, 1):
            require(count <= 256)
            name = Path(member.name)
            require(not name.is_absolute() and ".." not in name.parts)
            if str(name) == ".":
                require(member.isdir())
                continue
            require(str(name) not in seen and (member.isdir() or member.isfile()))
            seen.add(str(name))
            if member.isdir():
                continue
            require(0 <= member.size <= 16777216)
            total += member.size
            require(total <= 33554432)
            handle = archive.extractfile(member)
            require(handle is not None)
            with handle:
                content = handle.read(16777217)
            require(len(content) == member.size)
            observed.append({"path": str(name), "size": member.size,
                             "mode": "0755" if member.mode & 0o111 else "0644",
                             "sha256": hashlib.sha256(content).hexdigest()})
    require(sorted(observed, key=lambda x: x["path"]) == files)


def smtp_shadows_absent(environment):
    require(not any(k.startswith("PasswordResetSmtp__") for k in environment))


def command(*args):
    """Only exact caller-reviewed read-only argv; bounded output and duration."""
    global _pending_command
    require(args[0] in ("/usr/bin/hostname", "/usr/bin/systemctl", "/usr/sbin/visudo"))
    if args[0] == "/usr/bin/hostname":
        require(args == ("/usr/bin/hostname", "-I"))
    elif args[0] == "/usr/sbin/visudo":
        require(args == ("/usr/sbin/visudo", "-cf", POLICY))
    else:
        allowed = {(args[0], "show", unit, "--no-pager", "--property=" + PROPERTIES) for unit in (UNIT, *SIBLINGS)}
        allowed.add((args[0], "show", "jeeb-chat.service", "--property=" + CHAT_SNAPSHOT_PROPERTIES))
        allowed.add((args[0], "cat", "jeeb-chat.service"))
        require(args in allowed)
    _pending_command = args
    process = None
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        _pending_command = None
        output = bytearray()
        deadline = time.monotonic() + 8
        while True:
            require(time.monotonic() < deadline)
            ready, _, _ = select.select([process.stdout], [], [], 0.1)
            if not ready:
                continue
            data = os.read(process.stdout.fileno(), 65536)
            if not data:
                break
            output.extend(data)
            require(len(output) <= 262144)
        require(process.wait(timeout=1) == 0)
        return bytes(output)
    finally:
        _pending_command = None
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            process.stdout.close()


def safety_hook(event, args):
    """Defense against accidentally reaching a mutation/provider function."""
    if event == "open":
        _path, mode, flags = args
        require(not (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        require(not isinstance(mode, str) or not any(x in mode for x in "wax+"))
        # Bound direct stdlib/Path reads inside the pinned helper as well.
        if isinstance(_path, (str, bytes)) and os.path.isabs(_path):
            try:
                info = os.stat(_path)
                require(info.st_size <= 33554432)
            except FileNotFoundError:
                pass  # Opening a missing path still fails normally.
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.link", "os.symlink",
                   "os.chmod", "os.chown", "os.truncate", "os.utime", "os.system", "os.exec", "os.posix_spawn"}:
        raise AuditHold()
    elif event == "subprocess.Popen":
        require(_pending_command is not None and tuple(args[1]) == _pending_command)
    elif event == "socket.connect":
        require(args[1] in (("127.0.0.1", 10001), ("127.0.0.1", 5803)))


def load_pinned_module(name, raw, expected):
    """Load exact approved definitions; remove entrypoint, never run helper CLI."""
    require(hashlib.sha256(raw).hexdigest() == expected)
    tree = ast.parse(raw, filename="<pinned-helper>")
    body = []
    for node in tree.body:
        if isinstance(node, ast.If):
            require(ast.dump(node.test) == ast.dump(ast.parse('__name__ == "__main__"', mode="eval").body))
            continue
        require(isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef)) or
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
        body.append(node)
    tree.body = body
    module = types.ModuleType(name)
    module.__file__ = "<pinned-helper>"
    sys.modules[name] = module
    exec(compile(tree, "<pinned-helper>", "exec"), module.__dict__)
    return module


def show(unit):
    raw = command("/usr/bin/systemctl", "show", unit, "--no-pager", "--property=" + PROPERTIES)
    result = dict(x.split("=", 1) for x in raw.decode().splitlines() if "=" in x)
    require(set(result) == set(PROPERTIES.split(",")))
    require(result["Id"] == unit and result["LoadState"] == "loaded")
    require(result["ActiveState"] == "active" and result["SubState"] == "running")
    require(int(result["MainPID"]) > 1)
    return result


def runtime_environment(pid):
    # Kernel procfs PID is obtained only from the fixed systemd unit; no caller input.
    require(isinstance(pid, int) and pid > 1)
    fd = os.open(f"/proc/{pid}/environ", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        raw = read_held(fd, 262144)
    finally:
        os.close(fd)
    result = {}
    for entry in raw.split(b"\0"):
        if entry:
            key, value = entry.split(b"=", 1)
            require(key.decode() not in result)
            result[key.decode()] = value.decode()
    return result


def require_empty_stdin():
    info = os.fstat(0)
    expected = os.stat("/dev/null")
    require(stat.S_ISCHR(info.st_mode) and info.st_rdev == expected.st_rdev)
    require(os.read(0, 1) == b"")


def run_audit():
    phase = "entry"
    checks = {name: "not-run" for name in CHECKS}
    output = {"status": "HOLD", "protectedSource": BASE, "checks": checks,
              "functionalAuthGo": False, "production": "untouched",
              "step5PrerequisitesReady": False, "cutoverGo": False,
              "predecessorLegacyEnvironment": "metadata-only-per-reviewed-helper",
              "externalProofs": {"row03AuthProbeReadiness": "owner-lane-required", "row03Acceptance": "pending",
                                 "pushProtectedPreflight": "separate-run-required", "currentProtectedHeads": "separate-refresh-required"}}
    lock_fd = None
    try:
        require(len(sys.argv) == 1 and os.geteuid() == 0)
        require(sys.flags.isolated == 1 and sys.flags.dont_write_bytecode == 1)
        require(socket.gethostname().split(".")[0] == HOST)
        require_empty_stdin()
        require(os.path.abspath(__file__) == FIXED_SCRIPT)
        protected_directory(str(Path(FIXED_SCRIPT).parent), 0o700)
        read_file(FIXED_SCRIPT, mode=0o500)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
        def deadline(_signal, _frame):
            raise AuditHold()
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(60)
        require(b"192.168.2.39" in command("/usr/bin/hostname", "-I").split())
        sys.addaudithook(safety_hook)
        phase = "lock"
        lock_fd = protected_fd(LOCK, mode=0o600, limit=0)
        fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        checks[phase] = "passed"
        phase = "transport"
        sources = {}
        for name, digest in HELPERS.items():
            raw = read_file("/usr/local/sbin/jeeb-msi-" + name + "-admin", mode=0o755)
            require(hashlib.sha256(raw).hexdigest() == digest)
            if name in ("user-management-smtp", "chat-firebase"):
                sources[name] = raw
        archive = read_file("/root/jeeb-msi-runtime-activation-bootstrap-v9-eb7ab758.tar", mode=0o400, limit=4194304)
        require(hashlib.sha256(archive).hexdigest() == BOOTSTRAP_ARCHIVE)
        checks[phase] = "passed"
        phase = "policy"
        policy = read_file(POLICY, mode=0o440)
        require(hashlib.sha256(policy).hexdigest() == POLICY_HASH)
        require(sum(x.startswith(b"msi-access ") for x in policy.splitlines()) == 14)
        command("/usr/sbin/visudo", "-cf", POLICY)
        checks[phase] = "passed"
        phase = "units"
        before = {unit: show(unit) for unit in (UNIT, *SIBLINGS)}
        checks[phase] = "passed"
        um = load_pinned_module("row20_pinned_um", sources["user-management-smtp"], HELPERS["user-management-smtp"])
        layout = um.PRODUCTION  # The pinned helper's historical name; identity is development MSI.
        require(layout.hostname == HOST and layout.ipv4 == "192.168.2.39" and layout.unit == UNIT)
        class ReadOnlySystem:
            def show(self):
                return show(UNIT)
            process_environment = staticmethod(runtime_environment)
            process_cwd = staticmethod(um.ProductionSystem.process_cwd)
            ready = staticmethod(um.ProductionSystem.ready)
            @staticmethod
            def runtime_credentials(directory):
                require(str(directory) == "/run/credentials/" + UNIT)
                info = directory.lstat()
                require(stat.S_ISDIR(info.st_mode) and not directory.is_symlink())
                require({p.name for p in directory.iterdir()} == set(um.FIELDS))
                files = {}
                for name in um.FIELDS:
                    path = directory / name
                    member = path.lstat()
                    fd = protected_fd(str(path), uid=member.st_uid, gid=member.st_gid,
                                      mode=stat.S_IMODE(member.st_mode), limit=4096,
                                      parent_uids=(0, 1001))
                    try:
                        files[name] = (os.fstat(fd), read_held(fd, 4096), um.read_access_acl(path))
                    finally:
                        os.close(fd)
                return um.RuntimeCredentials(info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
                    um.read_access_acl(directory), bool(os.statvfs(directory).f_flag & os.ST_RDONLY), files)
        phase = "um-receipt"
        protected_directory(layout.bundle_root, 0o700)
        read_file(str(layout.bundle_root / um.RECEIPT_NAME), mode=0o400, limit=65536)
        bounded_tree(um.current_stage(layout).release)
        release, manifest = um.read_stage_receipt(layout)
        require(um.SOURCE_COMMIT == SOURCE and um.NATIVE_ARCHIVE_SHA256 == NATIVE_ARCHIVE)
        require(len(manifest["files"]) == 38)
        archive_manifest_exact(read_file(str(layout.bundle_root / "staged-artifact" / um.ARCHIVE_NAME),
                                        mode=0o400, limit=16777216), manifest["files"])
        superseded = um.superseded_stage(layout).release
        require(not superseded.exists() and not superseded.is_symlink())
        require({p.name for p in layout.bundle_root.iterdir()} == {um.RECEIPT_NAME, "staged-artifact", "versions", "current"})
        checks[phase] = "passed"
        phase = "um-credentials"
        candidate_version = layout.bundle_root / "versions" / um.VERSION
        protected_directory(candidate_version, 0o700)
        read_file(str(candidate_version / "manifest.json"), mode=0o400, limit=16384)
        for name in um.FIELDS:
            fd = protected_fd(str(candidate_version / name), mode=0o400, limit=4096)
            os.close(fd)
        version = um.validate_installed_bundle(layout)
        current = layout.bundle_root / "current"
        require(current.is_symlink() and os.readlink(current) == "versions/" + um.VERSION)
        values = {name: read_file(str(version / name), mode=0o400, limit=4096).decode() for name in um.FIELDS}
        checks[phase] = "passed"
        phase = "um-runtime"
        state = before[UNIT]
        require(state["FragmentPath"] == str(layout.fragment))
        require(state["NRestarts"] == "0")
        um.verify_candidate(layout, ReadOnlySystem(), release, values, str(um.FIREBASE_TARGET))
        environment = runtime_environment(int(state["MainPID"]))
        smtp_shadows_absent(environment)
        require(os.readlink(f"/proc/{state['MainPID']}/exe") == str(release / "UserManagement"))
        firebase = json_unique(read_file(str(um.FIREBASE_TARGET), uid=0, gid=1001, mode=0o640, limit=65536))
        require(firebase.get("type") == "service_account" and firebase.get("project_id") == "jeeb-development-msi")
        require(read_file(str(layout.activation_dropin), mode=0o644) == um.render_dropin(layout, release))
        require(read_file(str(um.FIREBASE_DROPIN), mode=0o644) == um.FIREBASE_DROPIN_BYTES)
        checks[phase] = "passed"
        phase = "predecessor"
        for path, digest, uid, gid, mode in ((str(layout.fragment), layout.fragment_sha256, 0, 0, 0o644),
                (str(layout.base_dropin), layout.base_dropin_sha256, 0, 0, 0o644),
                (str(layout.base_binary), layout.base_binary_sha256, 1001, 1001, 0o755)):
            require(hashlib.sha256(read_file(path, uid=uid, gid=gid, mode=mode, limit=1048576,
                                            parent_uids=(0, 1001))).hexdigest() == digest)
        env_fd = protected_fd(str(layout.environment_file), uid=1001, gid=1001, mode=0o600, parent_uids=(0, 1001))
        os.close(env_fd)  # Metadata only; never source or execute legacy environment.
        checks[phase] = "passed"
        phase = "chat-stage"
        chat = load_pinned_module("row20_pinned_chat", sources["chat-firebase"], HELPERS["chat-firebase"])
        chat.command = command  # Existing snapshot's exact readonly argv, bounded implementation.
        chat.safe_directory(chat.ROOT)
        receipt = json_unique(read_file(str(chat.RECEIPT), mode=0o600, limit=65536))
        require(set(receipt) == {"baseline", "credential"})
        account = pwd.getpwnam("ouday")
        key = read_file(str(chat.KEY), uid=account.pw_uid, gid=0, mode=0o400, limit=65536)
        require(chat.digest(key) == receipt["credential"] and chat.credential(key) == key)
        baseline = chat.snapshot()
        require(baseline == receipt["baseline"] and baseline["binding"] == chat.binding(chat.OLD_PROJECT, chat.OLD_KEY))
        chat.healthy(chat.OLD_PROJECT, attempts=1)
        require(not chat.DROP.exists() and not chat.DROP.is_symlink())
        checks[phase] = "passed"
        phase = "stable-snapshot"
        require(before == {unit: show(unit) for unit in (UNIT, *SIBLINGS)})
        current_lock = os.stat(LOCK, follow_symlinks=False)
        held_lock = os.fstat(lock_fd)
        require((current_lock.st_dev, current_lock.st_ino) == (held_lock.st_dev, held_lock.st_ino))
        checks[phase] = "passed"
        output["status"] = "READBACK-PASS"
        output["runtimeProject"] = "jeeb-development-msi"
    except BaseException:
        if phase in checks:
            checks[phase] = "failed"
        output["failurePhase"] = phase if phase in PHASES else "entry"
    finally:
        signal.alarm(0)
        if lock_fd is not None:
            os.close(lock_fd)
    return output


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if result["status"] == "READBACK-PASS" else 2)
