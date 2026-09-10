#!/usr/bin/env python3
"""MSI-only, pinned-prebuilt, forward-only native systemd deployment.

Plan is local/read-only. Host actions require an externally approved manifest SHA.
There is deliberately no rollback, restore, retry, build, migration or enable verb.
Failure retains the selected candidate and private phase evidence for an operator.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import gzip
import hashlib
import http.client
import io
import json
import os
import pwd
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import sys
import tarfile
import time

ROOT = Path("/opt/jeeb-msi-service-releases")
UNIT_DIR = Path("/etc/systemd/system")
REPORT_ROOT = Path("/var/tmp")
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_EXPANDED = 1536 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
SAFE = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
PROPS = ("Id", "LoadState", "ActiveState", "SubState", "MainPID", "NRestarts",
         "User", "Group", "DynamicUser", "WorkingDirectory", "ExecStart",
         "ExecMainStartTimestampMonotonic", "FragmentPath", "DropInPaths",
         "EnvironmentFiles", "Environment", "Restart", "ProtectSystem",
         "ProtectHome", "NoNewPrivileges", "RootDirectory", "RootImage", "InvocationID")


class GuardError(Exception):
    pass


def require(ok, code):
    if not ok:
        raise GuardError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def command(argv, input_bytes=b""):
    # Never echo stdout/stderr: unit environment and application failures are private.
    result = subprocess.run(argv, input=input_bytes, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=45, check=False)
    require(result.returncode == 0, "command-failed:" + Path(argv[0]).name)
    return result.stdout.decode("utf-8", "strict").strip()


def physical(path, root_owned=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, "nonphysical-path")
    if root_owned:
        for ancestor in [path, *path.parents]:
            info = ancestor.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022, "writable-owner-boundary")
    return path


def read_once(path, limit=MAX_ARCHIVE):
    path = physical(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "invalid-input-file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        require(len(data) == info.st_size and len(data) <= limit, "input-size-drift")
        require(os.fstat(fd).st_mtime_ns == info.st_mtime_ns, "input-time-drift")
        return data
    finally:
        os.close(fd)


def pinned(path, sha, limit=MAX_ARCHIVE):
    require(isinstance(sha, str) and HEX.fullmatch(sha), "invalid-sha")
    data = read_once(path, limit)
    require(digest(data) == sha, "input-hash-mismatch")
    return data


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, data, mode=0o444):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    sync_dir(Path(path).parent)


def mkdir_new(path, mode):
    os.mkdir(path, mode)
    os.chmod(path, mode)
    sync_dir(Path(path).parent)


@contextmanager
def operation_lock():
    physical("/run", root_owned=True)
    fd = os.open("/run/jeeb-msi-service-deploy.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600, "deployment-lock-boundary")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def static_exec(value):
    require(value.startswith("{ path=") and "; start_time=" in value, "unknown-execstart-shape")
    return value.split("; start_time=", 1)[0].rstrip()


def environment_projection(data, pid, invocation):
    result = {}
    seen = set()
    for entry in data.split(b"\0"):
        if not entry:
            continue
        name, value = entry.split(b"=", 1)
        key = name.decode("ascii")
        require(key not in seen, "duplicate-process-environment")
        seen.add(key)
        if key == "INVOCATION_ID":
            require(value.decode() == invocation, "process-invocation")
        elif key == "SYSTEMD_EXEC_PID":
            require(value == str(pid).encode(), "process-systemd-pid")
        elif key == "JOURNAL_STREAM":
            require(re.fullmatch(rb"[0-9]+:[0-9]+", value), "process-journal-stream")
            # Only the journal descriptor identity changes across a service invocation.
            pair = tuple(int(x) for x in value.split(b":"))
            require(any((os.stat(f"/proc/{pid}/fd/{fd}").st_dev,
                         os.stat(f"/proc/{pid}/fd/{fd}").st_ino) == pair for fd in (1, 2)), "journal-fd-identity")
        else:
            result[key] = digest(value)
    return result


def manager_prefix(manager):
    if manager.get("scope", "system") == "system":
        return []
    require(manager["scope"] == "user" and (manager["user"], manager["uid"]) in
            (("ec2-user", 1001), ("ouday", 1000)), "unsupported-user-manager")
    account = pwd.getpwnam(manager["user"])
    require(account.pw_uid == manager["uid"], "user-manager-uid")
    return ["/usr/sbin/runuser", "-u", manager["user"], "--", "/usr/bin/env", "-i",
            "PATH=/usr/bin:/bin", f"XDG_RUNTIME_DIR=/run/user/{manager['uid']}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{manager['uid']}/bus"]


def systemctl(manager, *args):
    return command(manager_prefix(manager) + ["/usr/bin/systemctl"] +
                   (["--user"] if manager.get("scope") == "user" else []) + list(args))


def inspect_unit(unit, manager=None):
    manager = manager or {"scope": "system"}
    raw = systemctl(manager, "show", unit, "--no-pager", "--property=" + ",".join(PROPS))
    data = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    require(set(data) == set(PROPS), "unit-property-inventory")
    require(data["LoadState"] == "loaded" and data["Id"] == unit, "unit-identity")
    data["Environment"] = digest(data["Environment"].encode())
    data["ExecStart"] = digest(static_exec(data["ExecStart"]).encode())
    pid = int(data["MainPID"])
    require(pid > 1 and data["ActiveState"] == "active" and data["SubState"] == "running", "unit-not-running")
    proc = Path(f"/proc/{pid}")
    status = (proc / "status").read_text()
    uid = re.search(r"^Uid:\s+(\d+)\s+(\d+)", status, re.M)
    require(uid and uid[1] == uid[2], "setuid-service")
    data["process"] = {"uid": int(uid[1]), "exe": os.readlink(proc / "exe"),
                       "cwd": os.readlink(proc / "cwd"),
                       "argv_sha256": digest((proc / "cmdline").read_bytes()),
                       "environment": environment_projection((proc / "environ").read_bytes(), pid, data["InvocationID"])}
    data["manager"] = manager
    return data


def unit_files(unit):
    result = [unit["FragmentPath"]]
    result += unit["DropInPaths"].split()
    envs = unit["EnvironmentFiles"]
    if envs:
        matches = re.findall(r"(/[^\s;()]+) \(ignore_errors=(?:yes|no)\)", envs)
        remainder = re.sub(r"/[^\s;()]+ \(ignore_errors=(?:yes|no)\)", "", envs).strip()
        require(matches and not remainder, "unknown-environmentfiles-shape")
        result += matches
    require(all(p.startswith("/") for p in result), "unit-files-path")
    return result


def inventory_units(managers=None):
    managers = managers or [{"scope": "system"}]
    found = []
    for manager in {canonical(m): m for m in managers}.values():
        raw = systemctl(manager, "list-units", "--type=service", "--state=running",
                        "--no-legend", "--plain", "--no-pager")
        found += [line.split()[0] for line in raw.splitlines()
                  if line.split() and (line.split()[0].startswith("jeeb-") or line.split()[0] in
                                      ("nginx.service", "cloudflared-msi.service", "settlement-service.service"))]
    require(len(found) == len(set(found)), "duplicate-cross-manager-unit")
    return sorted(found)


def value_at(body, key):
    for part in key.split("."):
        require(isinstance(body, dict) and part in body, "probe-missing-field")
        body = body[part]
    return body


def probe(service):
    spec = service["probe"]
    path = spec["path"]
    require(path.startswith("/") and not path.startswith("//") and "?" not in path, "probe-path")
    conn = http.client.HTTPConnection("127.0.0.1", service["port"], timeout=5)
    limit = 2 * 1024 * 1024 if spec["strength"] == "documentation" else 65536
    try:
        conn.request("GET", path, headers={"Host": "127.0.0.1", "Connection": "close"})
        response = conn.getresponse()
        body = response.read(limit + 1)
        require(response.status == spec.get("status", 200) and len(body) <= limit, "probe-http")
        text = body.decode("utf-8", "strict")
        if spec["kind"] == "json":
            obj = json.loads(text)
            require(isinstance(obj, dict) and spec.get("equals"), "probe-json-contract")
            for key, expected in spec["equals"].items():
                require(value_at(obj, key) == expected and type(value_at(obj, key)) is type(expected), "probe-value")
            for key in spec.get("required_true", []):
                require(value_at(obj, key) is True, "probe-false")
            for key in spec.get("required_keys", []):
                value_at(obj, key)
            for key, minimum in spec.get("numeric_min", {}).items():
                actual = value_at(obj, key)
                require(type(actual) in (int, float) and actual >= minimum, "probe-number")
        elif spec["kind"] == "text":
            require(text.strip() == spec["text"], "probe-text")
        elif spec["kind"] == "html":
            require(spec.get("strength") == "documentation" and spec.get("contains") and
                    spec["contains"] in text and "text/html" in response.getheader("Content-Type", ""), "probe-html")
        else:
            raise GuardError("unsupported-probe")
        return {"status": response.status, "strength": spec["strength"], "contract_passed": True}
    finally:
        conn.close()


def listener(service, pid, expected=None):
    text = command(["/usr/bin/ss", "-H", "-ltnp", "sport = :" + str(service["port"])])
    rows = text.splitlines()
    require(rows and all(f"pid={pid}," in row for row in rows), "listener-owner")
    # Never introduce a broader listener. Manifest/catalog must state existing bind.
    hosts = {row.split()[3].rsplit(":", 1)[0] for row in rows}
    if expected is not None:
        require(hosts == set(expected), "listener-boundary")
    if "listen_addresses" in service:
        require(hosts == set(service["listen_addresses"]), "catalog-listener-boundary")
    return sorted(hosts)


def validate_manifest(manifest, service):
    require(manifest["schema"] == 1 and manifest["service"] == service["id"], "manifest-service")
    require(SAFE.fullmatch(manifest["run_id"]), "run-id")
    source = manifest["source"]
    require(source["repository"] == service["repository"] and re.fullmatch(r"[0-9a-f]{40}", source["commit"]), "source-identity")
    require(source["default_branch"] and re.fullmatch(r"[0-9a-f]{40}", source["default_commit"]) and
            source["approved_commit"] is True and HEX.fullmatch(source["provenance_sha256"]), "source-approval")
    require(service.get("default_branch") in (None, source["default_branch"]), "default-branch-mismatch")
    require(HEX.fullmatch(manifest["catalog_sha256"]) and HEX.fullmatch(manifest["launcher_sha256"]), "input-provenance")
    require(manifest["baseline"]["units"] and service["unit"] in manifest["baseline"]["units"], "missing-unit-baseline")
    files = manifest["artifact"]["files"]
    require(0 < len(files) <= 10000, "artifact-file-count")
    seen = set()
    total = 0
    for entry in files:
        name = entry["path"]
        path = PurePosixPath(name)
        require(name == str(path) and not path.is_absolute() and ".." not in path.parts and
                name not in seen and not name.startswith(".msi") and
                re.fullmatch(r"[A-Za-z0-9_./+-]+", name), "artifact-path")
        require(HEX.fullmatch(entry["sha256"]) and type(entry["size"]) is int and
                0 <= entry["size"] <= MAX_ARCHIVE and type(entry["executable"]) is bool, "artifact-entry")
        # Runtime configuration must come from reviewed incumbent bindings, not packages.
        lower = name.lower()
        require(not any(part in (".git", ".env", "secrets", "credentials", "fixtures") for part in path.parts)
                and not any(part.lower().startswith(".env") for part in path.parts)
                and not lower.endswith((".pfx", ".p12", ".pem", ".key", ".pdb", ".bak"))
                and not path.name.lower().startswith("appsettings"), "excluded-payload")
        seen.add(name)
        total += entry["size"]
    require(total <= MAX_EXPANDED, "artifact-expanded-size")
    argv = manifest["launch"]["argv"]
    require(argv and all(isinstance(v, str) and v and not re.search(r"[\x00-\x1f%]", v) for v in argv), "launch-argv")
    require(argv[0].startswith(("/", "{release}/")) and
            any("{release}/" in v for v in argv), "launch-release-binding")
    require(not any(re.search(r"(?i)(password|passwd|secret|bearer|token|connectionstring|api.?key)", v)
                    or "=" in v or re.search(r"[\r\n]", v) for v in argv), "inline-configuration-forbidden")
    require(HEX.fullmatch(manifest["launch"]["source_review_sha256"]), "launch-source-review")
    require(manifest["launch"]["argv_policy"] == "runtime-and-paths-only", "argv-policy")
    require(manifest["launch"]["contains_no_inline_credentials"] is True and
            manifest["launch"]["configuration_and_persistent_paths_reviewed"] is True, "launch-contract-review")
    require(all(v.startswith(("/", "{release}/", "--")) or re.fullmatch(r"[A-Za-z0-9_.:+-]{1,128}", v) for v in argv), "argv-shape")
    for item in manifest["launch"]["environment_bindings"]:
        require(item["path"].startswith("/") and HEX.fullmatch(item["sha256"]) and
                type(item["export_all"]) is bool, "environment-binding")
    for binding in manifest["path_bindings"]:
        path = PurePosixPath(binding["path"])
        require(str(path) == binding["path"] and not path.is_absolute() and ".." not in path.parts and
                not binding["path"].startswith(".msi") and re.fullmatch(r"[A-Za-z0-9_./+-]+", str(path)) and
                str(path) not in seen and binding["target"].startswith("/"), "path-binding-shape")
        require(binding["kind"] in ("config", "persistent-directory"), "path-binding-kind")
        if binding["kind"] == "config":
            require(HEX.fullmatch(binding["sha256"]), "path-binding-sha")
        seen.add(str(path))
    names = [PurePosixPath(p) for p in seen]
    require(not any(a in b.parents for a in names for b in names if a != b), "overlapping-payload-path")
    require(all(HEX.fullmatch(v) for v in manifest["expected_environment"].values()), "expected-environment-hashes")
    if "expected_process" in manifest:
        process = manifest["expected_process"]
        require(HEX.fullmatch(process["argv_sha256"]) and process["exe"].startswith(("/", "{release}/")) and
                process["release_argument"].startswith("{release}/") and HEX.fullmatch(process["source_review_sha256"]),
                "expected-process-contract")


def check_bindings(manifest):
    for binding in manifest["path_bindings"]:
        path = physical(binding["target"])
        info = path.stat()
        require(info.st_uid == binding["uid"] and stat.S_IMODE(info.st_mode) == binding["mode"], "binding-owner-mode")
        if binding["kind"] == "config":
            pinned(path, binding["sha256"], 16 * 1024 * 1024)
        else:
            require(stat.S_ISDIR(info.st_mode) and info.st_dev == binding["device"] and
                    info.st_ino == binding["inode"], "persistent-directory-identity")


def unpack_checked(data, entries):
    expected = {x["path"]: x for x in entries}
    payload = {}
    limit = MAX_EXPANDED + 20 * 1024 * 1024
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as zipped:
            raw = zipped.read(limit + 1)
    else:
        raw = data
    require(len(raw) <= limit and len(raw) % 512 == 0, "tar-encoding-size")
    offset = 0
    while offset + 512 <= len(raw):
        header = raw[offset:offset + 512]
        if header == bytes(512):
            require(len(raw) - offset >= 1024 and not any(raw[offset:]), "tar-trailer")
            break
        # tarfile otherwise transparently hides GNU longname/PAX/global headers.
        require(header[156:157] in (b"0", b"\0") and header[257:263] == b"ustar\0" and
                header[263:265] == b"00", "tar-nonregular-header")
        size_field = header[124:136].strip(b" \0")
        require(re.fullmatch(rb"[0-7]+", size_field), "tar-nonoctal-size")
        size = int(size_field, 8)
        require(size <= MAX_ARCHIVE and offset + 512 + size <= len(raw), "tar-member-bound")
        offset += 512 + ((size + 511) // 512) * 512
    else:
        raise GuardError("tar-missing-trailer")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            require(member.isreg() and not member.pax_headers and member.name in expected
                    and member.name not in payload and not member.linkname,
                    "unsafe-tar-member")
            spec = expected[member.name]
            require(member.size == spec["size"], "tar-size")
            stream = archive.extractfile(member)
            require(stream is not None, "tar-file")
            content = stream.read(spec["size"] + 1)
            require(len(content) == spec["size"] and digest(content) == spec["sha256"], "tar-hash")
            payload[member.name] = content
    require(set(payload) == set(expected), "tar-inventory")
    return payload


def preflight(manifest, service, catalog):
    require(os.geteuid() == 0 and sys.platform == "linux" and
            socket.gethostname() == catalog["host"]["hostname"], "host-root-identity")
    require(catalog["host"] == {"hostname": "ouday-GT70-2OC-2OD", "ipv4": "192.168.2.39"}, "catalog-host")
    addresses = json.loads(command(["/usr/sbin/ip", "-j", "address", "show"]))
    require(any(item.get("local") == catalog["host"]["ipv4"] and item.get("family") == "inet"
                for interface in addresses for item in interface.get("addr_info", [])), "host-ip")
    pinned(Path(__file__).with_name("native_launch.py"), manifest["launcher_sha256"], 65536)
    baseline = manifest["baseline"]
    require(inventory_units([u["manager"] for u in baseline["units"].values()]) == sorted(baseline["units"]), "fleet-inventory-drift")
    for name, expected in baseline["units"].items():
        require(inspect_unit(name, expected["manager"]) == expected, "unit-baseline-drift:" + name)
    selected = baseline["units"][service["unit"]]
    user_manager = service.get("manager", {"scope": "system"})
    require(selected["manager"] == user_manager and selected["process"]["uid"] > 0, "service-manager-identity")
    require((selected["User"] not in ("", "root", "0") or user_manager["scope"] == "user") and selected["DynamicUser"] == "no" and
            selected["RootDirectory"] == "" and selected["RootImage"] == "", "unsupported-service-identity")
    if user_manager["scope"] == "user":
        require(selected["process"]["uid"] == user_manager["uid"], "user-manager-process-uid")
    files = {x["path"]: x["sha256"] for x in baseline["files"]}
    required = set()
    for unit in baseline["units"].values():
        required.update(unit_files(unit))
    required.update(x["path"] for x in manifest["launch"]["environment_bindings"])
    require(required <= set(files) and manifest["config_files"] and set(manifest["config_files"]) <= set(files), "baseline-file-coverage")
    for path, sha in files.items():
        pinned(path, sha, 16 * 1024 * 1024)
    for item in manifest["launch"]["environment_bindings"]:
        require(files[item["path"]] == item["sha256"], "binding-baseline-mismatch")
    require(set(manifest["config_files"]) <= {b["target"] for b in manifest["path_bindings"] if b["kind"] == "config"}, "unbound-existing-config")
    check_bindings(manifest)
    for executable in ("/usr/bin/python3", "/usr/bin/bash"):
        physical(Path(executable).resolve(strict=True), root_owned=True)
    pins = {x["path"]: x for x in manifest["runtime_files"]}
    require(len(pins) == len(manifest["runtime_files"]), "duplicate-runtime-pin")
    for path, pin in pins.items():
        physical(path)
        info = Path(path).stat()
        require(info.st_uid == pin["uid"] and stat.S_IMODE(info.st_mode) == pin["mode"] and
                info.st_uid in (0, selected["process"]["uid"]) and not info.st_mode & 0o002, "runtime-owner-mode")
        pinned(path, pin["sha256"])
    if not manifest["launch"]["argv"][0].startswith("{release}/"):
        executable = Path(manifest["launch"]["argv"][0]).resolve(strict=True)
        require(str(executable) in pins, "unpinned-runtime")
    if "expected_process" in manifest and not manifest["expected_process"]["exe"].startswith("{release}/"):
        require(manifest["expected_process"]["exe"] in pins, "unpinned-final-runtime")
    physical("/opt", root_owned=True)
    physical(UNIT_DIR, root_owned=True)
    if ROOT.exists():
        physical(ROOT, root_owned=True)
    listener(service, int(selected["MainPID"]), baseline["listener_addresses"])
    return probe(service)


def capture_baseline(manifest, service, catalog, output):
    require(os.geteuid() == 0 and sys.platform == "linux" and
            socket.gethostname() == catalog["host"]["hostname"] and
            catalog["host"] == {"hostname": "ouday-GT70-2OC-2OD", "ipv4": "192.168.2.39"}, "host-root-identity")
    managers = [{"scope": "system"}] + [s.get("manager", {"scope": "system"}) for s in catalog["services"]]
    units = {}
    for manager in {canonical(m): m for m in managers}.values():
        for name in inventory_units([manager]):
            require(name not in units, "duplicate-cross-manager-unit")
            units[name] = inspect_unit(name, manager)
    require(service["unit"] in units, "selected-unit-missing")
    paths = set(manifest["config_files"])
    paths.update(item["path"] for item in manifest["launch"]["environment_bindings"])
    paths.update(item["target"] for item in manifest["path_bindings"] if item["kind"] == "config")
    for unit in units.values():
        paths.update(unit_files(unit))
    files = [{"path": path, "sha256": digest(read_once(path, 16 * 1024 * 1024))} for path in sorted(paths)]
    # Validate capture consistency after reading the complete inventory. No health,
    # provider, environment source execution, reload or startup in this operation.
    for name, observed in units.items():
        require(inspect_unit(name, observed["manager"]) == observed, "capture-unit-drift")
    for item in files:
        pinned(item["path"], item["sha256"], 16 * 1024 * 1024)
    out = Path(output)
    parent = physical(out.parent, root_owned=True)
    require(parent.stat().st_uid == 0 and stat.S_IMODE(parent.stat().st_mode) == 0o700,
            "capture-output-needs-private-root-directory")
    addresses = listener(service, int(units[service["unit"]]["MainPID"]))
    data = canonical({"schema": 1, "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                      "service": service["id"], "baseline": {"units": units, "files": files, "listener_addresses": addresses},
                      "incumbent_environment": units[service["unit"]]["process"]["environment"],
                      "note": "Hashes only. This is observation, not source/candidate approval."})
    write_new(out, data, 0o600)
    return {"path": str(out), "sha256": digest(data), "units": len(units)}


class Journal:
    def __init__(self, path):
        self.path = path
        mkdir_new(path, 0o700)
        self.index = 0

    def record(self, phase, **data):
        self.index += 1
        write_new(self.path / f"{self.index:03d}-{phase}.json", canonical({"phase": phase,
                  "at": dt.datetime.now(dt.timezone.utc).isoformat(), **data}), 0o600)


def dropin_text(release):
    # Paths contain only the validated service/run identifiers, no specifiers/quotes.
    return ("[Service]\nWorkingDirectory=" + str(release) + "\nExecStart=\nExecStart=/usr/bin/python3 " +
            str(release / ".msi/native_launch.py") + " " + str(release / ".msi/launch.json") + "\n").encode()


def expected_launch(manifest, release):
    return {"argv": [x.replace("{release}", str(release)) for x in manifest["launch"]["argv"]],
            "environment_bindings": manifest["launch"]["environment_bindings"]}


def expected_unit_delta(old, release, drop):
    argv = "/usr/bin/python3 " + str(release / ".msi/native_launch.py") + " " + str(release / ".msi/launch.json")
    return {"WorkingDirectory": str(release),
            "ExecStart": digest(("{ path=/usr/bin/python3 ; argv[]=" + argv + " ; ignore_errors=no").encode()),
            "DropInPaths": " ".join(sorted(old["DropInPaths"].split() + [str(drop)], key=lambda p: Path(p).name))}


def paths_for(manifest, service):
    release = ROOT / service["id"] / manifest["run_id"]
    manager = service.get("manager", {"scope": "system"})
    units = UNIT_DIR if manager["scope"] == "system" else Path(pwd.getpwnam(manager["user"]).pw_dir) / ".config/systemd/user"
    drop = units / (service["unit"] + ".d") / ("zzzzzz-msi-release-" + manifest["run_id"] + ".conf")
    report = REPORT_ROOT / ("jeeb-msi-deploy-" + service["id"] + "-" + manifest["run_id"])
    return release, drop, report


def validate_payload_on_disk(manifest, release):
    declared = {item["path"] for item in manifest["artifact"]["files"]}
    declared.update(binding["path"] for binding in manifest["path_bindings"])
    declared.update((".msi/native_launch.py", ".msi/launch.json"))
    observed = set()
    for directory, dirs, files in os.walk(release, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if path.is_symlink():
                observed.add(path.relative_to(release).as_posix())
                dirs.remove(name)
            else:
                physical(path, root_owned=True)
        observed.update((Path(directory) / name).relative_to(release).as_posix() for name in files)
    require(observed == declared, "release-inventory-drift")
    for item in manifest["artifact"]["files"]:
        path = release / item["path"]
        physical(path, root_owned=True)
        require(stat.S_IMODE(path.stat().st_mode) == (0o555 if item["executable"] else 0o444), "release-mode-drift")
        pinned(path, item["sha256"])
    physical(release, root_owned=True)
    for path, sha in ((release / ".msi/native_launch.py", manifest["launcher_sha256"]),
                      (release / ".msi/launch.json", digest(canonical(expected_launch(manifest, release))))):
        physical(path, root_owned=True)
        require(stat.S_IMODE(path.stat().st_mode) == 0o444, "launcher-mode-drift")
        pinned(path, sha, 65536)
    for binding in manifest["path_bindings"]:
        link = release / binding["path"]
        require(link.is_symlink() and os.readlink(link) == binding["target"] and link.lstat().st_uid == 0, "binding-link-drift")
    check_bindings(manifest)
    argv = expected_launch(manifest, release)["argv"]
    executable = Path(argv[0])
    require(executable.is_file() and executable.stat().st_mode & 0o111, "candidate-launch-executable")
    for argument in manifest["launch"]["argv"]:
        if argument.startswith("{release}/"):
            require(Path(argument.replace("{release}", str(release))).exists(), "missing-release-argument")


USER_INSTALL = r'''
import os,pathlib,stat,sys
p=pathlib.Path(sys.argv[1]); data=sys.stdin.buffer.read(65537)
if os.geteuid()==0 or len(data)>65536: raise RuntimeError("invalid installer")
base=p.parent.parent
if base.resolve(strict=True)!=base or not base.is_dir(): raise RuntimeError("nonphysical user unit root")
if not p.parent.exists(): os.mkdir(p.parent,0o755)
if p.parent.resolve(strict=True)!=p.parent or p.parent.stat().st_uid!=os.geteuid(): raise RuntimeError("user dropin boundary")
if any(x.name>=p.name for x in p.parent.glob("*.conf")): raise RuntimeError("dropin ordering")
pending=p.with_suffix(".pending")
fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
with os.fdopen(fd,"wb") as f: f.write(data); f.flush(); os.fchmod(f.fileno(),0o444); os.fsync(f.fileno())
os.link(pending,p,follow_symlinks=False)
fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); os.fsync(fd); os.close(fd)
'''


def install_dropin(service, drop, content):
    manager = service.get("manager", {"scope": "system"})
    if manager["scope"] == "user":
        # All creation in mutable user-owned ancestors executes as that user, not root.
        command(manager_prefix(manager) + ["/usr/bin/python3", "-c", USER_INSTALL, str(drop)], content)
        return
    if not drop.parent.exists():
        mkdir_new(drop.parent, 0o755)
    physical(drop.parent, root_owned=True)
    require(all(p.name < drop.name for p in drop.parent.glob("*.conf")), "dropin-not-last")
    pending = drop.with_suffix(".pending")
    write_new(pending, content)
    os.link(pending, drop, follow_symlinks=False)
    sync_dir(drop.parent)


def verify_candidate(manifest, service, restart_required=True):
    release, drop, _ = paths_for(manifest, service)
    require(read_once(drop) == dropin_text(release), "dropin-drift")
    validate_payload_on_disk(manifest, release)
    require(inventory_units([u["manager"] for u in manifest["baseline"]["units"].values()]) == sorted(manifest["baseline"]["units"]), "fleet-inventory-drift")
    current = inspect_unit(service["unit"], service.get("manager"))
    old = manifest["baseline"]["units"][service["unit"]]
    for key, value in expected_unit_delta(old, release, drop).items():
        require(current[key] == value, "candidate-unit-delta:" + key)
    for unit, expected in manifest["baseline"]["units"].items():
        if unit != service["unit"]:
            require(inspect_unit(unit, expected["manager"]) == expected, "peer-drift:" + unit)
    for key in PROPS:
        if key not in ("MainPID", "ExecMainStartTimestampMonotonic", "WorkingDirectory", "ExecStart", "DropInPaths", "InvocationID"):
            require(current[key] == old[key], "preserved-unit-drift:" + key)
    require(current["WorkingDirectory"] == str(release) and current["process"]["cwd"] == str(release), "candidate-cwd")
    require(current["process"]["uid"] == old["process"]["uid"] and
            current["NRestarts"] == old["NRestarts"], "candidate-identity-restart")
    if restart_required:
        require(current["MainPID"] != old["MainPID"] and
                current["ExecMainStartTimestampMonotonic"] != old["ExecMainStartTimestampMonotonic"], "candidate-not-restarted")
    expected_argv = [v.replace("{release}", str(release)) for v in manifest["launch"]["argv"]]
    if "expected_process" in manifest:
        contract = manifest["expected_process"]
        expected_exe = contract["exe"].replace("{release}", str(release))
        require(current["process"]["argv_sha256"] == contract["argv_sha256"], "candidate-argv")
        actual_argv = Path(f"/proc/{current['MainPID']}/cmdline").read_bytes().split(b"\0")
        argument = contract["release_argument"].replace("{release}", str(release)).encode()
        require(argument in actual_argv, "candidate-release-argument")
    else:
        expected_exe = str(Path(expected_argv[0]).resolve(strict=True))
        require(current["process"]["argv_sha256"] == digest(b"\0".join(x.encode() for x in expected_argv) + b"\0"), "candidate-argv")
    require(current["process"]["exe"] == expected_exe, "candidate-executable")
    for runtime in manifest["runtime_files"]:
        pinned(runtime["path"], runtime["sha256"])
    # An explicit new process environment hash is mandatory; never assume all runtimes
    # preserve their launch environment byte ordering or systemd invocation fields.
    require(current["process"]["environment"] == manifest["expected_environment"], "candidate-environment")
    expected_drops = sorted(old["DropInPaths"].split() + [str(drop)], key=lambda p: Path(p).name)
    require(current["DropInPaths"].split() == expected_drops, "candidate-dropin-inventory")
    for item in manifest["baseline"]["files"]:
        pinned(item["path"], item["sha256"], 16 * 1024 * 1024)
    listener(service, int(current["MainPID"]), manifest["baseline"]["listener_addresses"])
    health = probe(service)
    return {"pid": int(current["MainPID"]), "health": health, "release": str(release)}


def await_candidate(manifest, service):
    # This is bounded observation of one start, not another restart/deploy attempt.
    # Peer/config/unit/credential drift errors are never treated as startup latency.
    deadline = time.monotonic() + 45
    observed_pid = None
    transient = {"candidate-argv", "listener-owner", "probe-http", "probe-value", "probe-false",
                 "probe-text", "probe-missing-field"}
    while True:
        current = inspect_unit(service["unit"], service.get("manager"))
        if observed_pid is None:
            observed_pid = current["MainPID"]
        require(current["MainPID"] == observed_pid, "candidate-pid-changed-during-start")
        try:
            return verify_candidate(manifest, service)
        except (ConnectionError, TimeoutError, http.client.HTTPException):
            require(time.monotonic() < deadline, "candidate-readiness-timeout")
        except GuardError as exc:
            require(exc.args[0] in transient and time.monotonic() < deadline, exc.args[0])
        time.sleep(1)


def deploy(manifest, service, catalog, manifest_sha):
    release, drop, report = paths_for(manifest, service)
    require(not any(p.exists() or p.is_symlink() for p in (release, drop, report)), "run-already-exists")
    payload = unpack_checked(pinned(manifest["artifact"]["path"], manifest["artifact"]["sha256"]), manifest["artifact"]["files"])
    launcher = pinned(Path(__file__).with_name("native_launch.py"), manifest["launcher_sha256"], 65536)
    preflight(manifest, service, catalog)
    journal = Journal(report)
    journal.record("intent", manifest_sha256=manifest_sha, service=service["id"], source=manifest["source"],
                   release=str(release), dropin=str(drop), policy="forward-only-no-restore")
    try:
        for parent in (ROOT, ROOT / service["id"]):
            if not parent.exists():
                mkdir_new(parent, 0o755)
            physical(parent, root_owned=True)
        mkdir_new(release, 0o755)
        for item in manifest["artifact"]["files"]:
            path = release / item["path"]
            for parent in reversed(path.parent.relative_to(release).parents):
                if str(parent) != "." and not (release / parent).exists():
                    mkdir_new(release / parent, 0o755)
            if not path.parent.exists():
                mkdir_new(path.parent, 0o755)
            write_new(path, payload[item["path"]], 0o555 if item["executable"] else 0o444)
        for binding in manifest["path_bindings"]:
            link = release / binding["path"]
            for parent in reversed([link.parent, *link.parent.parents]):
                if parent != release and release in parent.parents and not parent.exists():
                    mkdir_new(parent, 0o755)
            os.symlink(binding["target"], link)
            sync_dir(link.parent)
        mkdir_new(release / ".msi", 0o755)
        launch = expected_launch(manifest, release)
        write_new(release / ".msi/native_launch.py", launcher)
        write_new(release / ".msi/launch.json", canonical(launch))
        validate_payload_on_disk(manifest, release)
        journal.record("release-staged")
        preflight(manifest, service, catalog)  # last-moment peer/PID/config drift gate
        require(all(Path(p).name < drop.name for p in manifest["baseline"]["units"][service["unit"]]["DropInPaths"].split()), "dropin-not-last")
        journal.record("install-dropin-intent")
        install_dropin(service, drop, dropin_text(release))
        journal.record("dropin-installed")
        manager = service.get("manager", {"scope": "system"})
        command(manager_prefix(manager) + ["/usr/bin/systemd-analyze"] +
                (["--user"] if manager["scope"] == "user" else []) + ["verify", service["unit"]])
        journal.record("daemon-reload-intent")
        systemctl(manager, "daemon-reload")
        # No restart if any preserved setting or incumbent process has drifted.
        for unit, expected in manifest["baseline"]["units"].items():
            actual = inspect_unit(unit, expected["manager"])
            if unit == service["unit"]:
                for key, value in expected_unit_delta(expected, release, drop).items():
                    require(actual[key] == value, "post-reload-launch-drift:" + key)
                    actual[key] = expected[key]
            require(actual == expected, "post-reload-drift:" + unit)
        require(read_once(drop) == dropin_text(release), "post-reload-dropin-drift")
        validate_payload_on_disk(manifest, release)
        for item in manifest["baseline"]["files"]:
            pinned(item["path"], item["sha256"], 16 * 1024 * 1024)
        journal.record("restart-intent")
        systemctl(manager, "restart", service["unit"])
        journal.record("restart-returned")
        result = await_candidate(manifest, service)
        time.sleep(5)
        require(verify_candidate(manifest, service) == result, "candidate-unstable")
        journal.record("verified", **result)
        return {"report": str(report), **result}
    except BaseException as exc:
        try:
            journal.record("failed", error=exc.args[0] if isinstance(exc, GuardError) else type(exc).__name__,
                           selected_candidate_may_remain=True, automatic_restore=False)
        finally:
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--service", required=True)
    parser.add_argument("action", nargs="?", choices=("plan", "inspect", "preflight", "deploy", "verify"), default="plan")
    parser.add_argument("--catalog", default=str(Path(__file__).with_name("service-catalog.json")))
    parser.add_argument("--manifest")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--ack-effects")
    parser.add_argument("--capture-baseline")
    for option in ("--service", "--catalog", "--manifest", "--manifest-sha256", "--ack-effects", "--capture-baseline"):
        require(sum(v == option or v.startswith(option + "=") for v in sys.argv[1:]) <= 1, "duplicate-option")
    args = parser.parse_args()
    catalog_bytes = read_once(args.catalog, 1024 * 1024)
    catalog = json.loads(catalog_bytes)
    require(catalog["schema"] == 1, "catalog-schema")
    matches = [s for s in catalog["services"] if s["id"] == args.service]
    require(len(matches) == 1 and SAFE.fullmatch(args.service), "unknown-service")
    service = matches[0]
    require(re.fullmatch(r"(?:jeeb-[a-z0-9-]+|settlement-service)\.service", service["unit"]), "unit-name")
    require(type(service["port"]) is int and 1024 < service["port"] < 65536, "port")
    effects_hash = digest(canonical(service["effects"]))
    if args.action == "plan":
        print(json.dumps({"action": "plan", "host_operations": False, "service": service,
                          "effects_ack_sha256": effects_hash, "catalog_sha256": digest(catalog_bytes),
                          "policy": "forward-only; no build/migrate/enable/rollback/restore"}, indent=2))
        return
    require(args.manifest and args.manifest_sha256, "pinned-manifest-required")
    manifest = json.loads(pinned(args.manifest, args.manifest_sha256, 4 * 1024 * 1024))
    if args.action == "inspect":
        require(args.capture_baseline and manifest["schema"] == 1 and manifest["service"] == args.service,
                "inspect-output-and-service-required")
        result = capture_baseline(manifest, service, catalog, args.capture_baseline)
        print(json.dumps({"action": "inspect", "result": result}, indent=2))
        return
    require(not args.capture_baseline, "capture-only-with-inspect")
    validate_manifest(manifest, service)
    require(manifest["catalog_sha256"] == digest(catalog_bytes), "catalog-hash-mismatch")
    if args.action == "deploy":
        require(args.ack_effects == effects_hash, "startup-effects-ack-required")
    require(os.geteuid() == 0 and sys.platform == "linux" and socket.gethostname() == catalog["host"]["hostname"], "host-root-identity")
    # One host-wide advisory lock coordinates different service/run IDs. External
    # operators must honor the same lock; configuration is still drift-checked.
    with operation_lock():
        if args.action == "preflight":
            unpack_checked(pinned(manifest["artifact"]["path"], manifest["artifact"]["sha256"]), manifest["artifact"]["files"])
            result = preflight(manifest, service, catalog)
        elif args.action == "deploy":
            result = deploy(manifest, service, catalog, args.manifest_sha256)
        else:
            result = verify_candidate(manifest, service)
    print(json.dumps({"action": args.action, "service": args.service, "result": result}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "stopped", "error": exc.args[0] if isinstance(exc, GuardError) else type(exc).__name__,
                          "automatic_restore": False}), file=sys.stderr)
        sys.exit(1)
