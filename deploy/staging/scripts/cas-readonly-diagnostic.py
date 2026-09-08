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
    fixed = (
        r"/v[0-9]+\.[0-9]+/info",
        r"/v[0-9]+\.[0-9]+/services/jeeb-staging-(?:jeeb-gateway|delivery-service)",
        r"/v[0-9]+\.[0-9]+/networks/jeeb-staging-net",
        r"/v[0-9]+\.[0-9]+/secrets/jeeb-staging-delivery-service-auth-v1",
        r"/v[0-9]+\.[0-9]+/images/ghcr\.io/olivium-dev/(?:jeeb-gateway|delivery-service)@sha256:[0-9a-f]{64}/json",
    )
    if path != "/version" and not any(re.fullmatch(pattern, path) for pattern in fixed):
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


def engine_source(version, report=None):
    """Bounded public build identity, never arbitrary daemon text."""
    release, commit = version.get("Version"), version.get("GitCommit")
    release_valid = isinstance(release, str) and re.fullmatch(
        r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[-+][a-zA-Z0-9.-]{1,48})?", release
    ) is not None
    commit_valid = isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{7,40}", commit) is not None
    package_valid = isinstance(commit, str) and re.fullmatch(r"[A-Za-z0-9.+:~_-]{1,100}", commit) is not None
    if report is not None:
        report.update(engine_version_valid=release_valid, engine_git_commit_valid=commit_valid,
                      engine_version_present=release is not None, engine_git_commit_present=commit is not None,
                      engine_git_commit_package_shape_valid=package_valid)
        if release_valid:
            report["engine_version"] = release
        if package_valid:
            report["engine_git_commit"] = commit
    if not release_valid:
        raise ValueError("engine release")
    if not package_valid:
        raise ValueError("engine commit")
    return {"engine_version": release, "engine_git_commit": commit}


def paired_posture(maximum, info):
    """Only exact paired resources and booleans; no Specs, env values or secret data."""
    prefix = "/v" + maximum
    node = info.get("Swarm", {}).get("NodeID")
    valid_node = isinstance(node, str) and re.fullmatch(r"[a-z0-9]{25}", node) is not None
    report = {"swarm_node_id_valid": valid_node, "ssh_uid": os.getuid()}
    if valid_node:
        report["swarm_node_id"] = node
    transport, network = get(prefix + "/networks/jeeb-staging-net")
    report["network_transport"] = transport
    valid_network = network is not None and isinstance(network.get("Id"), str) and re.fullmatch(r"[a-z0-9]{25}", network["Id"]) is not None
    report["expected_overlay"] = bool(valid_network and network.get("Driver") == "overlay"
                                      and network.get("Attachable") is True and "encrypted" in network.get("Options", {}))
    services = {}
    for role, name, port, mode in (("gateway", "jeeb-gateway", 10000, "ingress"),
                                   ("delivery", "delivery-service", 10055, "host")):
        transport, service = get(prefix + "/services/jeeb-staging-" + name)
        result = {"transport": transport}
        services[role] = result
        if service is None:
            continue
        spec = service.get("Spec", {})
        task = spec.get("TaskTemplate", {})
        container = task.get("ContainerSpec", {})
        rows = container.get("Env", [])
        values = {}
        valid_env = isinstance(rows, list)
        for row in rows if valid_env else []:
            if not isinstance(row, str) or "=" not in row:
                valid_env = False
                break
            key, value = row.split("=", 1)
            if not key or key in values:
                valid_env = False
            values[key] = value
        constraints = task.get("Placement", {}).get("Constraints", [])
        valid_constraints = isinstance(constraints, list) and all(isinstance(c, str) for c in constraints)
        normalized = [c.replace(" ", "") for c in constraints] if valid_constraints else []
        result.update(
            service_name_matches=spec.get("Name") == "jeeb-staging-" + name,
            single_replica=spec.get("Mode") == {"Replicated": {"Replicas": 1}},
            no_command_overrides=not any(container.get(k) for k in ("Command", "Args", "Dir")),
            no_mounts=not container.get("Mounts"),
            no_configs=not container.get("Configs"),
            no_loader_environment_overrides=valid_env and not any(key in values for key in (
                "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "DOTNET_ROOT", "DOTNET_STARTUP_HOOKS",
                "ASPNETCORE_HOSTINGSTARTUPASSEMBLIES")),
            failure_action_pause=spec.get("UpdateConfig", {}).get("FailureAction") == "pause",
            environment_shape_valid=valid_env,
            placement_shape_valid=valid_constraints,
            placement_constraint_count=len(normalized),
            pinned_actual_node=bool(valid_node and "node.id==" + node in normalized),
            pinned_expected_hostname="node.hostname==olivium-ephemerals" in normalized,
            ports_match=spec.get("EndpointSpec", {}).get("Ports") == [{"Protocol": "tcp", "TargetPort": 8080, "PublishedPort": port, "PublishMode": mode}],
            single_expected_network=bool(valid_network and [n.get("Target") for n in task.get("Networks", [])] == [network["Id"]]),
        )
        if role == "gateway":
            result["delivery_url_matches"] = valid_env and values.get("Services__Delivery__BaseUrl") == "http://192.168.2.20:10055"
        else:
            result["skip_db_init_true"] = valid_env and values.get("SKIP_DB_INIT") == "true"
        image = container.get("Image")
        valid_image = isinstance(image, str) and re.fullmatch(r"ghcr\.io/olivium-dev/" + name + r"@sha256:[0-9a-f]{64}", image) is not None
        result["immutable_image_reference"] = valid_image
        if role == "gateway" and valid_image:
            image_transport, image_info = get(prefix + "/images/" + image + "/json")
            result["image_transport"] = image_transport
            config = image_info.get("Config", {}) if image_info else {}
            result["runtime_user_matches"] = config.get("User") == "appuser"
            result["entrypoint_matches"] = config.get("Entrypoint") == ["dotnet", "JeebGateway.dll"]
    report["services"] = services
    transport, secret = get(prefix + "/secrets/jeeb-staging-delivery-service-auth-v1")
    report["dedicated_secret"] = {"transport": transport, "present": secret is not None}
    if secret is not None:
        identity = secret.get("ID")
        valid_id = isinstance(identity, str) and re.fullmatch(r"[a-z0-9]{25}", identity) is not None
        report["dedicated_secret"].update(id_valid=valid_id,
            metadata_matches=secret.get("Spec", {}).get("Name") == "jeeb-staging-delivery-service-auth-v1"
                and secret.get("Spec", {}).get("Labels") == {"jeeb.environment": "staging", "jeeb.purpose": "delivery-service-auth", "jeeb.version": "1"})
        if valid_id:
            report["dedicated_secret"]["id"] = identity
    report["custody"] = {}
    for suffix in (".jeeb-deploy", ".jeeb-deploy/locks", ".jeeb-deploy/paired-releases"):
        path = Path.home() / suffix
        value = {"exists": path.exists(), "is_symlink": path.is_symlink()}
        if value["exists"]:
            metadata = path.lstat()
            value.update(owner_matches=metadata.st_uid == os.getuid(), directory=stat.S_ISDIR(metadata.st_mode),
                         mode=format(stat.S_IMODE(metadata.st_mode), "03o"))
        report["custody"][suffix] = value
    return report


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
        try:
            report.update(engine_source(version, report))
        except ValueError:
            # Preserve only independently validated identity fields; missing or
            # malformed build identity remains explicit, never deployment proof.
            report["engine_source_incomplete"] = True
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
        phase = "paired_posture"
        report["paired_posture"] = paired_posture(maximum, info)
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
