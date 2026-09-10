#!/usr/bin/python3
"""Run one reviewed native payload as the unit's NON-root user. Never print env."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import stat
import sys


def read_regular(path, limit):
    p = Path(path)
    if not p.is_absolute() or p.resolve(strict=True) != p:
        raise ValueError("nonphysical binding")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("invalid binding")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("oversize binding")
        return data
    finally:
        os.close(fd)


def main():
    if os.geteuid() == 0 or len(sys.argv) != 2 or sys.platform != "linux":
        raise ValueError("nonroot Linux launch required")
    config = json.loads(read_regular(sys.argv[1], 65536))
    argv = config["argv"]
    if not argv or not all(isinstance(x, str) and "\x00" not in x for x in argv):
        raise ValueError("invalid argv")
    bindings = config["environment_bindings"]
    if not bindings:
        os.execv(argv[0], argv)
    descriptors = []
    for binding in bindings:
        data = read_regular(binding["path"], 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != binding["sha256"]:
            raise ValueError("binding changed")
        # The reviewed shell source executes only under the existing service UID.
        # Freeze bytes in anonymous RAM; never write credentials into the release.
        fd = os.memfd_create("msi-env", os.MFD_ALLOW_SEALING)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK |
                    fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)
        os.set_inheritable(fd, True)
        descriptors.append((fd, "1" if binding["export_all"] else "0"))
    script = 'set -e; count="$1"; shift; '
    script += 'for ((i=0;i<count;i++)); do if [[ "$1" == 1 ]]; then set -a; else set +a; fi; shift; '
    script += 'source "$1"; fd=${1##*/}; exec {fd}<&-; shift; done; set +a; exec "$@"'
    os.execv("/usr/bin/bash", ["/usr/bin/bash", "--noprofile", "--norc", "-c",
             script, "msi-reviewed-env", str(len(descriptors)),
             *[part for fd, export in descriptors for part in (export, f"/proc/self/fd/{fd}")], *argv])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No exceptions/paths/source lines: shell sources can contain credentials.
        print("Native launch validation failed", file=sys.stderr)
        sys.exit(1)
