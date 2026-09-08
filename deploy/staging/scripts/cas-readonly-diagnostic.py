#!/usr/bin/env python3
"""Fixed read-only CAS diagnostic: GET only, safe versions and shape booleans."""
import base64
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys

SOCKET = "/var/run/docker.sock"
PROFILES = {
    "um": ".jeeb-deploy/um-ghcr-34165720635-1/config.json",
    "otp": ".jeeb-deploy/otp-ghcr-34165689040-1/config.json",
}


class LocalEngine(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


def get(path):
    # Even future callers cannot turn this helper into an Engine mutation.
    if path != "/version" and re.fullmatch(r"/v[0-9]+\.[0-9]+/info", path) is None:
        raise ValueError("route")
    connection = LocalEngine("localhost", timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(raw) > 1024 * 1024:
            return {"http_status": response.status}, None
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("shape")
        return {"http_status": 200}, data
    finally:
        connection.close()


def api(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+\.[0-9]+", value) is None:
        raise ValueError("version")
    return tuple(int(part) for part in value.split("."))


def engine_source(version):
    """Bounded public build identity, never arbitrary daemon text."""
    release, commit = version.get("Version"), version.get("GitCommit")
    if not isinstance(release, str) or re.fullmatch(
        r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[-+][a-zA-Z0-9.-]{1,48})?", release
    ) is None:
        raise ValueError("engine release")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{7,40}", commit) is None:
        raise ValueError("engine commit")
    return {"engine_version": release, "engine_git_commit": commit}


def auth_shape(path):
    report = {"exists": path.exists(), "regular_nonsymlink": False}
    if not report["exists"]:
        return report
    try:
        report["parent_directories_safe"] = not path.parent.is_symlink() and not path.parent.parent.is_symlink()
        if not report["parent_directories_safe"]:
            return report
        report["regular_nonsymlink"] = not path.is_symlink() and stat.S_ISREG(path.stat().st_mode)
        if not report["regular_nonsymlink"]:
            return report
        if path.stat().st_size > 65536:
            report["bounded_size"] = False
            return report
        report["bounded_size"] = True
        with path.open() as source:
            profile = json.load(source)
        report["object_shape"] = isinstance(profile, dict)
        if not report["object_shape"]:
            return report
        report["external_helper_absent"] = not profile.get("credsStore") and not profile.get("credHelpers")
        encoded = profile.get("auths", {}).get("ghcr.io", {}).get("auth")
        report["ghcr_auth_string"] = isinstance(encoded, str)
        if not report["ghcr_auth_string"]:
            return report
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        report["base64_utf8_valid"] = True
        username, password = decoded.split(":", 1)
        report["designated_username_matches"] = username == "oudaykhaled"
        report["password_present"] = bool(password)
        report["password_visible_ascii"] = all(32 <= ord(char) <= 126 for char in password)
    except Exception:
        report["shape_rejected"] = True
    return report


def collect():
    phase = "local_socket"
    report = {"phase": phase}
    try:
        report["host_matches"] = socket.gethostname().split(".")[0] == "olivium-ephemerals"
        report["socket_is_socket"] = stat.S_ISSOCK(os.lstat(SOCKET).st_mode)
        if not report["host_matches"] or not report["socket_is_socket"]:
            raise ValueError("target")
        phase = "engine_version"
        transport, version = get("/version")
        report["version_transport"] = transport
        if version is None:
            raise ValueError("transport")
        minimum, maximum = version.get("MinAPIVersion"), version.get("ApiVersion")
        lower, upper = api(minimum), api(maximum)
        report.update(engine_source(version))
        # Numeric strings only; never report arbitrary server-supplied fields.
        report["minimum_api"] = minimum
        report["maximum_api"] = maximum
        report["api_1_41_supported"] = lower <= (1, 41) <= upper
        phase = "engine_identity"
        transport, info = get("/v" + maximum + "/info")
        report["info_transport"] = transport
        if info is None:
            raise ValueError("transport")
        swarm = info.get("Swarm", {})
        report["daemon_name_matches"] = info.get("Name") == "olivium-ephemerals"
        report["node_address_matches"] = swarm.get("NodeAddr") == "192.168.2.20"
        report["manager"] = swarm.get("ControlAvailable") is True
        report["swarm_active"] = swarm.get("LocalNodeState") == "active"
        phase = "run_auth_shapes"
        report["auth_shapes"] = {key: auth_shape(Path.home() / value) for key, value in PROFILES.items()}
        report["phase"] = "complete"
        return report, 0
    except Exception:
        report["phase"] = phase
        report["failed"] = True
        return report, 1


if __name__ == "__main__":
    evidence, status = collect()
    print(json.dumps(evidence, sort_keys=True))
    sys.exit(status)
