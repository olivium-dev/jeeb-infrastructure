"""Inert Linux subprocess integration: synthetic env only, no service/network calls.

Exercises the real memfd, seals, Bash source and exec path as the current nonroot
user. This is not MSI/systemd integration. Unsupported hosts explicitly skip.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / "native_launch.py"
SUPPORTED = (
    sys.platform == "linux"
    and os.geteuid() != 0
    and hasattr(os, "memfd_create")
    and hasattr(os, "MFD_ALLOW_SEALING")
    and all(hasattr(fcntl, name) for name in (
        "F_ADD_SEALS", "F_GET_SEALS", "F_SEAL_SEAL", "F_SEAL_SHRINK",
        "F_SEAL_GROW", "F_SEAL_WRITE"))
    and Path("/usr/bin/bash").is_file()
    and Path("/proc/self/fd").is_dir()
)
SKIP_REASON = "requires nonroot Linux, memfd/seals, /usr/bin/bash and procfs; no emulation"

# Both modes inspect only this synthetic process and its inherited synthetic fd.
PROBE = r'''
import errno, fcntl, json, os, sys
if len(sys.argv) == 3 and sys.argv[1] == "--source-fd":
    fd = int(sys.argv[2].rsplit("/", 1)[1])
    target = os.readlink("/proc/self/fd/" + str(fd))
    if "memfd:msi-env" not in target:
        raise RuntimeError("not the synthetic source memfd")
    required = (fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK |
                fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & required != required:
        raise RuntimeError("incomplete source seals")
    try:
        os.write(fd, b"synthetic-write-must-fail")
    except OSError as exc:
        if exc.errno != errno.EPERM:
            raise
    else:
        raise RuntimeError("sealed source allowed write")
    print("sealed-write-rejected")
else:
    descriptors = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            descriptors[name] = os.readlink("/proc/self/fd/" + name)
        except FileNotFoundError:
            pass  # os.listdir's own directory fd has already closed.
    keys = ("MSI_PLAIN_ONE", "MSI_EXPLICIT_ONE", "MSI_PLAIN_TWO",
            "MSI_EXPLICIT_TWO", "MSI_SEAL_PROOF", "MSI_INHERITED", "fd", "i", "count")
    print(json.dumps({"uid": os.geteuid(), "environment":
                      {key: os.environ.get(key) for key in keys},
                      "descriptors": descriptors}))
'''


@unittest.skipUnless(SUPPORTED, SKIP_REASON)
class NativeLaunchLinuxTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="msi-launch-inert-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.probe = self.root / "synthetic_probe.py"
        self.probe.write_text(PROBE)
        self.python = str(Path(sys.executable).resolve())
        self.config = self.root / "launch.json"

    def binding(self, suffix, export_all, attest=False):
        lines = [f"MSI_PLAIN_{suffix}=synthetic-plain-{suffix}",
                 f"export MSI_EXPLICIT_{suffix}=synthetic-explicit-{suffix}"]
        if attest:
            # "$1" is the currently sourced memfd path in the unmodified launcher.
            # The child inherits it and proves real kernel seals before Bash closes it.
            command = f'{shlex.quote(self.python)} -I {shlex.quote(str(self.probe))} --source-fd "$1"'
            lines.append(f'export MSI_SEAL_PROOF="$({command})"')
        path = self.root / (suffix.lower() + ".synthetic-env")
        data = ("\n".join(lines) + "\n").encode()
        path.write_bytes(data)
        path.chmod(0o600)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "export_all": export_all}

    def launch(self, bindings):
        self.config.write_text(json.dumps({"argv": [self.python, "-I", str(self.probe)],
                                           "environment_bindings": bindings}))
        self.config.chmod(0o600)
        # No inherited user credentials, BASH_ENV, tracing options, or Python hooks.
        return subprocess.run([self.python, "-I", str(LAUNCHER), str(self.config)],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=15, close_fds=True, cwd=self.root,
                              env={"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                                   "LANG": "C", "MSI_INHERITED": "synthetic-inherited"})

    def successful_result(self, bindings):
        completed = self.launch(bindings)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(os.geteuid(), result["uid"])
        self.assertEqual("synthetic-inherited", result["environment"]["MSI_INHERITED"])
        self.assertEqual("sealed-write-rejected", result["environment"]["MSI_SEAL_PROOF"])
        for internal in ("fd", "i", "count"):
            self.assertIsNone(result["environment"][internal], "launcher internal leaked: " + internal)
        self.assertFalse(any("memfd:msi-env" in target for target in result["descriptors"].values()))
        self.assertEqual({"0", "1", "2"}, set(result["descriptors"]))
        return result["environment"]

    def test_export_all_false_keeps_plain_assignment_private_and_closes_memfd(self):
        environment = self.successful_result([self.binding("ONE", False, attest=True)])
        self.assertIsNone(environment["MSI_PLAIN_ONE"])
        self.assertEqual("synthetic-explicit-ONE", environment["MSI_EXPLICIT_ONE"])

    def test_export_all_true_exports_plain_assignment_and_closes_memfd(self):
        environment = self.successful_result([self.binding("ONE", True, attest=True)])
        self.assertEqual("synthetic-plain-ONE", environment["MSI_PLAIN_ONE"])
        self.assertEqual("synthetic-explicit-ONE", environment["MSI_EXPLICIT_ONE"])

    def test_each_binding_resets_export_policy_and_closes_all_memfds(self):
        environment = self.successful_result([self.binding("ONE", True, attest=True),
                                              self.binding("TWO", False)])
        self.assertEqual("synthetic-plain-ONE", environment["MSI_PLAIN_ONE"])
        self.assertEqual("synthetic-explicit-ONE", environment["MSI_EXPLICIT_ONE"])
        self.assertIsNone(environment["MSI_PLAIN_TWO"])
        self.assertEqual("synthetic-explicit-TWO", environment["MSI_EXPLICIT_TWO"])

    def test_multiple_export_all_sources_preserve_exports_without_internal_variables(self):
        environment = self.successful_result([self.binding("ONE", True, attest=True),
                                              self.binding("TWO", True)])
        for suffix in ("ONE", "TWO"):
            self.assertEqual("synthetic-plain-" + suffix, environment["MSI_PLAIN_" + suffix])
            self.assertEqual("synthetic-explicit-" + suffix, environment["MSI_EXPLICIT_" + suffix])

    def test_changed_binding_fails_before_source_or_exec_with_sanitized_output(self):
        binding = self.binding("ONE", True, attest=True)
        marker = self.root / "must-not-be-created"
        # Retain the old pin while substituting a harmless but observable shell action.
        Path(binding["path"]).write_text(f'printf synthetic > {shlex.quote(str(marker))}\n')
        completed = self.launch([binding])
        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertEqual("Native launch validation failed\n", completed.stderr)
        self.assertFalse(marker.exists())
        self.assertNotIn(str(self.root), completed.stderr)


if __name__ == "__main__":
    unittest.main()
