"""Offline tests. Never invoke the root entrypoint or contact MSI/providers."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import types
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "audit.py"
spec = importlib.util.spec_from_file_location("row20_audit_test", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CustodyTests(unittest.TestCase):
    def setUp(self):
        # Under the isolated checkout, not a world-writable temp ancestry.
        self.folder = Path(tempfile.mkdtemp(prefix="audit-test-", dir=SCRIPT.parent))
        self.path = self.folder / "file"
        self.path.write_bytes(b"reviewed bytes")
        self.path.chmod(0o600)
        fixture_owners = {0, os.getuid(), os.getgid()}
        for ancestor in self.folder.parents:
            fixture_owners.update((ancestor.stat().st_uid, ancestor.stat().st_gid))
        self.options = dict(uid=os.getuid(), gid=os.getgid(), mode=0o600,
                            parent_uids=tuple(fixture_owners), limit=64)

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_actual_descriptor_read_and_digest(self):
        self.assertEqual(audit.read_file(str(self.path), **self.options), b"reviewed bytes")

    def test_final_symlink_rejected(self):
        link = self.folder / "link"
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            audit.read_file(str(link), **self.options)

    def test_parent_symlink_rejected(self):
        real = self.folder / "real"
        real.mkdir()
        file = real / "file"
        file.write_bytes(b"data")
        file.chmod(0o600)
        link = self.folder / "link"
        link.symlink_to(real)
        with self.assertRaises(OSError):
            audit.read_file(str(link / "file"), **self.options)

    def test_hardlink_rejected(self):
        os.link(self.path, self.folder / "link")
        with self.assertRaises(audit.AuditHold):
            audit.read_file(str(self.path), **self.options)

    def test_group_writable_parent_rejected(self):
        self.folder.chmod(0o770)
        with self.assertRaises(audit.AuditHold):
            audit.read_file(str(self.path), **self.options)

    def test_size_rejected_before_read(self):
        self.path.write_bytes(b"x" * 65)
        with mock.patch.object(audit.os, "read", side_effect=AssertionError("must not read")):
            with self.assertRaises(audit.AuditHold):
                audit.read_file(str(self.path), **self.options)

    def test_held_descriptor_cannot_follow_replacement(self):
        fd = audit.protected_fd(str(self.path), **self.options)
        try:
            self.path.rename(self.folder / "original")
            self.path.write_bytes(b"replacement")
            self.assertEqual(audit.read_held(fd, 64), b"reviewed bytes")
        finally:
            os.close(fd)

    def test_empty_stream_is_not_accepted_as_pinned_source(self):
        with self.assertRaises(audit.AuditHold):
            audit.load_pinned_module("test_empty", b"", audit.HELPERS["user-management-smtp"])


class SourceAndOutputTests(unittest.TestCase):
    def test_hash_drift_fails_before_parse(self):
        with mock.patch.object(audit.ast, "parse", side_effect=AssertionError("must not parse")):
            with self.assertRaises(audit.AuditHold):
                audit.load_pinned_module("drift", b"print('NO')", "0" * 64)

    def test_entire_main_guard_removed(self):
        raw = b'VALUE = 7\nif __name__ == "__main__":\n    raise RuntimeError("do not run")\n'
        mod = audit.load_pinned_module("audit_fixture", raw, hashlib.sha256(raw).hexdigest())
        self.assertEqual(mod.VALUE, 7)

    def test_other_top_level_control_flow_rejected(self):
        raw = b'if True:\n    raise RuntimeError("do not run")\n'
        with self.assertRaises(audit.AuditHold):
            audit.load_pinned_module("audit_fixture_bad", raw, hashlib.sha256(raw).hexdigest())

    def test_top_level_expression_call_rejected(self):
        raw = b'print("do not run")\n'
        with self.assertRaises(audit.AuditHold):
            audit.load_pinned_module("audit_fixture_bad", raw, hashlib.sha256(raw).hexdigest())

    def test_duplicate_json_rejected(self):
        with self.assertRaises(audit.AuditHold):
            audit.json_unique(b'{"status":1,"status":2}')

    def test_pipe_stdin_rejected_without_read(self):
        with mock.patch.object(audit.os, "fstat", return_value=types.SimpleNamespace(st_mode=stat.S_IFIFO, st_rdev=0)):
            with mock.patch.object(audit.os, "read", side_effect=AssertionError("must not wait")):
                with self.assertRaises(audit.AuditHold):
                    audit.require_empty_stdin()

    def test_failure_output_never_contains_exception_or_unknown_values(self):
        with mock.patch.object(audit.sys, "argv", [audit.FIXED_SCRIPT]):
            with mock.patch.object(audit.os, "geteuid", side_effect=RuntimeError("SECRET-CANARY")) as entered:
                result = audit.run_audit()
                entered.assert_called_once()
        raw = json.dumps(result)
        self.assertNotIn("SECRET-CANARY", raw)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["failurePhase"], "entry")
        self.assertFalse(result["step5PrerequisitesReady"])
        self.assertFalse(result["cutoverGo"])
        self.assertFalse(result["functionalAuthGo"])
        self.assertEqual(set(result["checks"].values()), {"not-run"})

    def test_reachable_mutator_names_absent_from_entrypoint(self):
        tree = ast.parse(SCRIPT.read_text())
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_audit")
        attrs = {n.func.attr for n in ast.walk(run) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertTrue({"activate", "stage", "restart", "daemon_reload", "main", "install_bundle", "select_bundle", "activate_staged"}.isdisjoint(attrs))
        self.assertTrue({"read_stage_receipt", "validate_installed_bundle", "verify_candidate", "snapshot", "credential", "healthy"}.issubset(attrs))


class MutationDefenses(unittest.TestCase):
    def test_write_open_rejected(self):
        with self.assertRaises(audit.AuditHold):
            audit.safety_hook("open", ("/fixed", "w", os.O_WRONLY | os.O_CREAT))

    def test_filesystem_mutation_rejected(self):
        for event in ("os.remove", "os.rename", "os.chmod", "os.chown", "os.mkdir", "os.system"):
            with self.subTest(event=event), self.assertRaises(audit.AuditHold):
                audit.safety_hook(event, ())

    def test_provider_socket_rejected(self):
        with self.assertRaises(audit.AuditHold):
            audit.safety_hook("socket.connect", (None, ("smtp.invalid", 587)))
        audit.safety_hook("socket.connect", (None, ("127.0.0.1", 10001)))

    def test_unapproved_subprocess_rejected(self):
        with self.assertRaises(audit.AuditHold):
            audit.safety_hook("subprocess.Popen", ("/bin/sh", ["/bin/sh"], None, None))

    def test_arbitrary_property_selector_rejected_without_launch(self):
        with mock.patch.object(audit.subprocess, "Popen", side_effect=AssertionError("must not launch")):
            with self.assertRaises(audit.AuditHold):
                audit.command("/usr/bin/systemctl", "show", audit.UNIT, "--property=Environment")

    def test_mutation_command_rejected_without_launch(self):
        with mock.patch.object(audit.subprocess, "Popen", side_effect=AssertionError("must not launch")):
            with self.assertRaises(audit.AuditHold):
                audit.command("/usr/bin/systemctl", "restart", audit.UNIT)


if __name__ == "__main__":
    unittest.main()

class InstalledHookBehaviorTests(unittest.TestCase):
    def test_real_audit_hook_stops_write_and_connection_before_side_effect(self):
        import subprocess
        import sys
        code = '''import importlib.util,json,sys,socket,os
spec=importlib.util.spec_from_file_location("isolated_hook",sys.argv[1])
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
sys.addaudithook(a.safety_hook)
out={}
try:
    open(sys.argv[1]+".must-not-exist","w")
except a.AuditHold:
    out["writeBlocked"]=True
s=socket.socket()
try:
    s.connect(("127.0.0.1",12345))
except a.AuditHold:
    out["connectBlocked"]=True
finally:
    s.close()
print(json.dumps(out))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SCRIPT)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'writeBlocked': True, 'connectBlocked': True})
        self.assertFalse(Path(str(SCRIPT)+'.must-not-exist').exists())
