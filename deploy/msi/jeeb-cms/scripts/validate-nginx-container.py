#!/usr/bin/env python3
"""Validate the complete security contract of one Docker nginx container."""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-running", choices=("true", "false"), required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--cms-root", required=True)
    parser.add_argument("--main-config", required=True)
    parser.add_argument("--site-config", required=True)
    args = parser.parse_args()

    try:
        records = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"invalid Docker inspect output: {exc}")
    if not isinstance(records, list) or len(records) != 1:
        raise SystemExit("Docker inspect must return exactly one container")

    record = records[0]
    config = record.get("Config") or {}
    host = record.get("HostConfig") or {}
    state = record.get("State") or {}
    checks = {
        "pinned image": config.get("Image") == args.image,
        "host network": host.get("NetworkMode") == "host",
        "read-only root": host.get("ReadonlyRootfs") is True,
        "unprivileged user": config.get("User") == "101:101",
        "non-restarting container": (host.get("RestartPolicy") or {}).get("Name") == "no",
        "not privileged": host.get("Privileged") is False,
        "running state": state.get("Running") is (args.expected_running == "true"),
        "all capabilities dropped": {
            str(value).upper() for value in (host.get("CapDrop") or [])
        }
        == {"ALL"},
        "no capabilities added": not (host.get("CapAdd") or []),
        "exact security options": set(host.get("SecurityOpt") or [])
        == {"no-new-privileges"},
        "no host devices": not (host.get("Devices") or [])
        and not (host.get("DeviceRequests") or [])
        and not (host.get("DeviceCgroupRules") or []),
        "no published ports": not (host.get("PortBindings") or {})
        and host.get("PublishAllPorts") is False,
        "private process namespaces": host.get("PidMode") in (None, "", "private")
        and host.get("IpcMode") in (None, "", "private")
        and host.get("UTSMode") in (None, "", "private")
        and host.get("CgroupnsMode") in (None, "", "private")
        and host.get("UsernsMode") in (None, ""),
        "no supplementary groups": not (host.get("GroupAdd") or []),
        "pinned OCI runtime": host.get("Runtime") == "runc",
        "nginx entrypoint": config.get("Entrypoint") == ["nginx"],
        "nginx foreground command": config.get("Cmd") == ["-g", "daemon off;"],
        "graceful stop signal": config.get("StopSignal") == "SIGQUIT",
    }

    tmpfs_mounts = host.get("Tmpfs") or {}
    tmpfs = tmpfs_mounts.get("/tmp", "")
    checks["restricted tmpfs"] = set(tmpfs_mounts) == {"/tmp"} and set(tmpfs.split(",")) == {
        "rw",
        "noexec",
        "nosuid",
        "nodev",
        "size=32m",
        "mode=0700",
        "uid=101",
        "gid=101",
    }
    log_config = host.get("LogConfig") or {}
    checks["bounded local logging"] = (
        log_config.get("Type") == "local"
        and (log_config.get("Config") or {}).get("max-size") == "10m"
        and (log_config.get("Config") or {}).get("max-file") == "3"
    )

    expected_mounts = {
        "/opt/jeeb-cms": os.path.realpath(args.cms_root),
        "/etc/nginx/nginx.conf": os.path.realpath(args.main_config),
        "/etc/nginx/conf.d/jeeb-cms.conf": os.path.realpath(args.site_config),
    }
    actual_mounts: dict[str, str] = {}
    unexpected_binds: list[object] = []
    for mount in record.get("Mounts") or []:
        destination = mount.get("Destination")
        if mount.get("Type") == "tmpfs" and destination == "/tmp":
            continue
        if mount.get("Type") != "bind":
            unexpected_binds.append(destination)
            continue
        if destination not in expected_mounts:
            unexpected_binds.append(destination)
            continue
        if mount.get("RW") is not False:
            raise SystemExit(f"bind mount is writable: {destination}")
        actual_mounts[destination] = os.path.realpath(str(mount.get("Source", "")))
    checks["exact read-only bind mounts"] = (
        actual_mounts == expected_mounts and not unexpected_binds
    )

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise SystemExit("container runtime contract failed: " + ", ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
