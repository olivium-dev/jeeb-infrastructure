#!/usr/bin/env python3
"""Fixed protected staging observations; local consistency is not isolation."""
import json
import os
import re
import select
import socket
import stat
import subprocess
import sys
import time

HOST = "olivium-ephemerals"
ADDRESS = "192.168.2.20"
UNIT = "cloudflared-jeeb-staging.service"
CONFIG = "/etc/cloudflared-jeeb-staging/config.yml"
TUNNEL = "f029ab58-b82d-4bf3-906a-508ffe4c5661"
LIMIT = 65536
FIREWALL_LIMIT = 1048576
PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState", "MainPID", "ControlGroup", "ExecStart")
COMMANDS = {
    "nftables": ("/usr/sbin/nft", "-j", "list", "ruleset"),
    "iptables": ("/usr/sbin/iptables-save",),
    "ip6tables": ("/usr/sbin/ip6tables-save",),
    "addresses": ("/usr/sbin/ip", "-j", "-4", "address", "show"),
    "unit": ("/usr/bin/systemctl", "show", "--no-pager", "--property=" + ",".join(PROPERTIES), UNIT),
}
EXPECTED_CONFIG = """tunnel: f029ab58-b82d-4bf3-906a-508ffe4c5661
credentials-file: /etc/cloudflared-jeeb-staging/f029ab58-b82d-4bf3-906a-508ffe4c5661.json
metrics: 127.0.0.1:20242

ingress:
  - hostname: jeeb-app-origin.fds-1.com
    service: https://127.0.0.1:443
    originRequest:
      originServerName: app.jeeb.fds-1.com
      httpHostHeader: app.jeeb.fds-1.com
  - hostname: jeeb-cms-origin.fds-1.com
    service: https://127.0.0.1:443
    originRequest:
      originServerName: cms.jeeb.fds-1.com
      httpHostHeader: cms.jeeb.fds-1.com
  - hostname: jeeb-staging-ssh.fds-1.com
    service: ssh://127.0.0.1:22
  - service: http_status:404
"""


def require(value):
    if not value:
        raise ValueError("unsupported observation")


def command(kind):
    require(kind in COMMANDS)
    limit = FIREWALL_LIMIT if kind in ("nftables", "iptables", "ip6tables") else LIMIT
    child = subprocess.Popen(COMMANDS[kind], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd="/", env={
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C",
            "SYSTEMD_PAGER": "", "SYSTEMD_PAGERSECURE": "1", "SYSTEMD_COLORS": "0"})
    output = bytearray()
    deadline = time.monotonic() + 10
    try:
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0)
            require(select.select([child.stdout], [], [], remaining)[0])
            chunk = os.read(child.stdout.fileno(), min(4096, limit + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            require(len(output) <= limit)
        require(child.wait(timeout=max(0.01, deadline - time.monotonic())) == 0)
        return bytes(output)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        child.stdout.close()


def identity_check(host, addresses):
    require(host == HOST)
    rows = json.loads(addresses)
    require(isinstance(rows, list))
    require(any(row.get("family") == "inet" and row.get("local") == ADDRESS
                for device in rows for row in device.get("addr_info", [])))


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def secure_file(path):
    """Fixed callers only. Pin every ancestor; refuse links and writable roots."""
    require(path == CONFIG)
    descriptors = []
    try:
        current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(current)
        for part in path.split("/")[1:-1]:
            info = os.fstat(current)
            require(info.st_uid == 0 and not info.st_mode & 0o022)
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(current)
        info = os.fstat(current)
        require(info.st_uid == 0 and not info.st_mode & 0o022)
        leaf = os.open(path.rsplit("/", 1)[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        descriptors.append(leaf)
        before = os.fstat(leaf)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
                and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
                and 0 < before.st_size <= LIMIT)
        raw = os.read(leaf, LIMIT + 1)
        require(len(raw) == before.st_size and fingerprint(before) == fingerprint(os.fstat(leaf)))
        return raw, fingerprint(before)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def known_argv(argv):
    require(isinstance(argv, list) and argv and argv[0] in ("/usr/bin/cloudflared", "/usr/local/bin/cloudflared"))
    prefixes = (["--config", CONFIG], ["--no-autoupdate", "--config", CONFIG],
                ["--config", CONFIG, "--no-autoupdate"])
    require(any(argv[1:] == prefix + ["tunnel", "run"] + suffix
                for prefix in prefixes for suffix in ([], [TUNNEL])))


def unit_projection(raw):
    values = {}
    for line in raw.decode().splitlines():
        key, separator, value = line.partition("=")
        require(separator and key in PROPERTIES and key not in values)
        values[key] = value
    require(set(values) == set(PROPERTIES))
    require(values["Id"] == UNIT and values["LoadState"] == "loaded"
            and values["ActiveState"] == "active" and values["SubState"] == "running")
    require(re.fullmatch(r"[1-9][0-9]{0,9}", values["MainPID"]))
    require(values["ControlGroup"] == "/system.slice/" + UNIT)
    # No general shell/unescape parser: only literal known arguments qualify.
    start = values["ExecStart"]
    require(start.startswith("{ path=") and start.endswith(" }") and start.count("{ path=") == 1)
    match = re.search(r"^\{ path=([^ ;]+) ; argv\[\]=([^;]+) ; ", start)
    require(match is not None)
    argv = match[2].split()
    known_argv(argv)
    require(argv[0] == match[1])
    return {"pid": values["MainPID"], "cgroup": values["ControlGroup"], "argv": argv, "raw": raw}


def proc_read(directory, name):
    require(name in ("cmdline", "stat", "cgroup"))
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode))
        raw = os.read(descriptor, LIMIT + 1)
        require(0 < len(raw) <= LIMIT)
        return raw
    finally:
        os.close(descriptor)


def process_projection(unit):
    pid = unit["pid"]
    require(re.fullmatch(r"[1-9][0-9]{0,9}", pid))
    parent = os.open("/proc", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory = None
    try:
        directory = os.open(pid, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        identity = os.fstat(directory)
        def capture():
            raw = proc_read(directory, "cmdline")
            require(raw.endswith(b"\0"))
            argv = [part.decode() for part in raw[:-1].split(b"\0")]
            known_argv(argv)
            require(argv == unit["argv"])
            executable = os.readlink("exe", dir_fd=directory)
            require(executable == argv[0])  # Also rejects the kernel's ' (deleted)' suffix.
            info = os.stat("exe", dir_fd=directory)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
            process_stat = proc_read(directory, "stat").decode()
            match = re.fullmatch(r"([0-9]+) \(cloudflared\) (.+)\n?", process_stat)
            require(match is not None and match[1] == pid)
            fields = match[2].split()
            require(len(fields) >= 20 and fields[0] not in ("Z", "X") and fields[19].isdigit())
            cgroups = [row.split(":", 2) for row in proc_read(directory, "cgroup").decode().splitlines()]
            binding = [row for row in cgroups if len(row) == 3 and (row[:2] == ["0", ""] or "name=systemd" in row[1].split(","))]
            require(len(binding) == 1 and binding[0][2] == unit["cgroup"])
            return (argv, executable, info.st_dev, info.st_ino, fields[19], binding)
        first = capture()
        require(capture() == first)
        require(os.stat(pid, dir_fd=parent, follow_symlinks=False).st_ino == identity.st_ino)
        return (identity.st_dev, identity.st_ino, first)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def config_matches(raw):
    # Exact reviewed text, ignoring only blank lines; no YAML constructors,
    # interpolation, includes, referenced paths, or credential file access.
    return [line for line in raw.decode().splitlines() if line.strip()] == [
        line for line in EXPECTED_CONFIG.splitlines() if line.strip()]


def firewall_projection(kind, raw):
    """Counts and literal policy facts only; no rule interpretation or targets."""
    require(kind in ("nftables", "iptables", "ip6tables"))
    if kind == "nftables":
        data = json.loads(raw)
        require(isinstance(data, dict) and set(data) == {"nftables"})
        items = data["nftables"]
        require(isinstance(items, list) and len(items) <= LIMIT)
        facts = dict(tableCount=0, chainCount=0, ruleCount=0, unsupportedObjectCount=0,
                     inputDropPolicyPresent=False, forwardDropPolicyPresent=False,
                     completeReachabilityProven=False)
        for item in items:
            if not isinstance(item, dict) or len(item) != 1:
                facts["unsupportedObjectCount"] += 1
                continue
            name = next(iter(item))
            value = item[name]
            if name not in ("metainfo", "table", "chain", "rule") or not isinstance(value, dict):
                facts["unsupportedObjectCount"] += 1
                continue
            if name != "metainfo":
                facts[name + "Count"] += 1
            if name == "chain":
                for hook in ("input", "forward"):
                    if value.get("hook") == hook and value.get("policy") == "drop":
                        facts[hook + "DropPolicyPresent"] = True
        return facts
    facts = dict(tableCount=0, chainCount=0, ruleCount=0, unsupportedLineCount=0,
                 dockerUserChainPresent=False, inputDropPolicyPresent=False,
                 forwardDropPolicyPresent=False, completeReachabilityProven=False)
    active = False
    for line in raw.decode().splitlines():
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"\*[A-Za-z0-9_-]{1,64}", line) and not active:
            active = True
            facts["tableCount"] += 1
        elif line == "COMMIT" and active:
            active = False
        elif active and re.fullmatch(r":[A-Za-z0-9_-]{1,64} (?:ACCEPT|DROP|-) \[[0-9]+:[0-9]+\]", line):
            facts["chainCount"] += 1
            facts["dockerUserChainPresent"] |= line.startswith(":DOCKER-USER ")
            facts["inputDropPolicyPresent"] |= line.startswith(":INPUT DROP ")
            facts["forwardDropPolicyPresent"] |= line.startswith(":FORWARD DROP ")
        elif active and re.match(r"^-A [A-Za-z0-9_-]{1,64} ", line):
            facts["ruleCount"] += 1
        else:
            facts["unsupportedLineCount"] += 1
    if active or not facts["tableCount"]:
        facts["unsupportedLineCount"] += 1
    return facts


FALSE_FIELDS = ("activationAuthorized", "effectiveIngressProven", "externalConnectorsExcluded",
                "environmentOverridesExcluded", "loadedConfigBytesProven", "credentialFilesRead",
                "environmentRead", "rawSensitiveOutput")
TUNNEL_FIELDS = ("exactReviewedConfigMatches", "activeUnitProcessConfigPathBound", "stableRepeatedObservation")


def empty_report():
    return dict(schemaVersion=1, target=HOST, targetAddress=ADDRESS, status="unverified",
                targetVerified=False, failureStage=None, **dict.fromkeys(FALSE_FIELDS, False),
                tunnel=dict(status="unverified", failureStage=None, **dict.fromkeys(TUNNEL_FIELDS, False)),
                firewalls={name: {"status": "unverified", "failureStage": None, "facts": None}
                           for name in ("nftables", "iptables", "ip6tables")})


def validate_report(report):
    """Strict runner-local output boundary. Never return unreviewed strings."""
    shape = empty_report()
    require(type(report) is dict and set(report) == set(shape))
    require(type(report["schemaVersion"]) is int and report["schemaVersion"] == 1)
    require(type(report["target"]) is str and report["target"] == HOST)
    require(type(report["targetAddress"]) is str and report["targetAddress"] == ADDRESS)
    require(type(report["status"]) is str and report["status"] in ("unverified", "observed-local-consistency", "unsupported-invocation"))
    require(report["failureStage"] is None or type(report["failureStage"]) is str and report["failureStage"] in ("target", "invocation"))
    require(type(report["targetVerified"]) is bool)
    require(all(report[key] is False for key in FALSE_FIELDS))
    tunnel = report["tunnel"]
    require(type(tunnel) is dict and set(tunnel) == set(shape["tunnel"]))
    require(type(tunnel["status"]) is str and tunnel["status"] in ("unverified", "observed-local-consistency"))
    require(tunnel["failureStage"] is None or type(tunnel["failureStage"]) is str and tunnel["failureStage"] in ("unit", "unit-process", "config", "stability"))
    require(tunnel["status"] != "observed-local-consistency" or tunnel["failureStage"] is None)
    require(all(type(tunnel[key]) is bool for key in TUNNEL_FIELDS))
    require(all(tunnel[key] == (tunnel["status"] == "observed-local-consistency") for key in TUNNEL_FIELDS))
    firewalls = report["firewalls"]
    require(type(firewalls) is dict and set(firewalls) == set(shape["firewalls"]))
    for name, row in firewalls.items():
        require(type(row) is dict and set(row) == {"status", "failureStage", "facts"})
        require(type(row["status"]) is str and row["status"] in ("unverified", "collected", "unsupported"))
        require(row["failureStage"] is None or type(row["failureStage"]) is str and row["failureStage"] in ("command", "projection"))
        if row["status"] == "unverified":
            require(row["facts"] is None)
            continue
        template = firewall_projection(name, b'{"nftables":[]}' if name == "nftables" else b"*filter\nCOMMIT\n")
        facts = row["facts"]
        require(type(facts) is dict and set(facts) == set(template))
        for key, value in facts.items():
            require(type(value) is type(template[key]))
            if type(value) is int:
                require(0 <= value <= FIREWALL_LIMIT)
        require(facts["completeReachabilityProven"] is False)
        unsupported = facts["unsupportedObjectCount" if name == "nftables" else "unsupportedLineCount"]
        require((row["status"] == "unsupported") == (unsupported > 0))
        require(row["failureStage"] == ("projection" if unsupported else None))
    complete = tunnel["status"] == "observed-local-consistency" and all(
        row["status"] == "collected" for row in firewalls.values())
    require((report["status"] == "observed-local-consistency") == (report["targetVerified"] and complete))
    if report["targetVerified"]:
        require(report["failureStage"] is None and report["status"] != "unsupported-invocation")
    else:
        require({**report, "status": "unverified", "failureStage": None} == shape)
        require(report["failureStage"] == "invocation" if report["status"] == "unsupported-invocation"
                else report["failureStage"] in (None, "target"))
    return report


def collect():
    report = empty_report()
    try:
        require(sys.platform == "linux" and os.geteuid() == 0)
        require(socket.gethostname() == HOST)
        identity_check(HOST, command("addresses"))
        report["targetVerified"] = True
    except Exception:
        report["failureStage"] = "target"
        return validate_report(report), 1
    stage = "unit"
    try:
        first = unit_projection(command("unit"))
        stage = "unit-process"
        process = process_projection(first)
        stage = "config"
        raw, metadata = secure_file(CONFIG)
        require(config_matches(raw))
        stage = "stability"
        require(secure_file(CONFIG) == (raw, metadata))
        require(process_projection(first) == process)
        require(unit_projection(command("unit")) == first)
        report["tunnel"] = dict(status="observed-local-consistency", failureStage=None, **dict.fromkeys(TUNNEL_FIELDS, True))
    except Exception:
        report["tunnel"]["failureStage"] = stage
    for name in ("nftables", "iptables", "ip6tables"):
        stage = "command"
        try:
            raw_firewall = command(name)
            stage = "projection"
            facts = firewall_projection(name, raw_firewall)
            unsupported = facts["unsupportedObjectCount" if name == "nftables" else "unsupportedLineCount"]
            report["firewalls"][name] = {"status": "unsupported" if unsupported else "collected",
                "failureStage": "projection" if unsupported else None, "facts": facts}
        except Exception:
            report["firewalls"][name]["failureStage"] = stage
    try:
        identity_check(socket.gethostname(), command("addresses"))
    except Exception:
        report = empty_report()
        report["failureStage"] = "target"
        return validate_report(report), 1
    complete = report["tunnel"]["status"] == "observed-local-consistency" and all(
        row["status"] == "collected" for row in report["firewalls"].values())
    if complete:
        report["status"] = "observed-local-consistency"
    return validate_report(report), 0 if complete else 1


def main():
    # sudo may consume no password bytes (cached/NOPASSWD); discard the inherited
    # pipe without reading it before any collection or child process can run.
    try:
        os.close(0)
    except OSError:
        pass
    if len(sys.argv) != 1:
        report = empty_report()
        report["status"] = "unsupported-invocation"
        report["failureStage"] = "invocation"
        status = 1
    else:
        report, status = collect()
    print(json.dumps(validate_report(report), sort_keys=True))
    return status


if __name__ == "__main__":
    sys.exit(main())
