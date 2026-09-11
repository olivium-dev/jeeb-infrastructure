import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/protected-ingress-collector.py"
spec = importlib.util.spec_from_file_location("tunnel_readonly", SOURCE)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
SECRET = "private-sentinel-never-print"


def unit(**changes):
    argv = "/usr/bin/cloudflared --no-autoupdate --config " + d.CONFIG + " tunnel run"
    values = dict(Id=d.UNIT, LoadState="loaded", ActiveState="active", SubState="running",
                  MainPID="123", ControlGroup="/system.slice/" + d.UNIT,
                  ExecStart="{ path=/usr/bin/cloudflared ; argv[]=" + argv + " ; ignore_errors=no ; pid=123 ; }")
    values.update(changes)
    return ("\n".join(key + "=" + value for key, value in values.items()) + "\n").encode()


class ProtectedIngressCollectorTests(unittest.TestCase):
    def test_reviewed_template_exact(self):
        path = SOURCE.parent.parent / "cloudflare/cloudflared-ingress.yml.template"
        self.assertTrue(d.config_matches(path.read_bytes()))
        for raw in (path.read_bytes() + b"token: " + SECRET.encode(),
                    path.read_bytes().replace(b"127.0.0.1:443", b"192.168.2.20:10028"),
                    b"!!python/object/apply:os.system []", path.read_bytes() + b"ingress: []"):
            self.assertFalse(d.config_matches(raw))

    def test_identity_exact_not_msi_or_address_substring(self):
        valid = b'[{"addr_info":[{"family":"inet","local":"192.168.2.20"}]}]'
        d.identity_check(d.HOST, valid)
        for host, addresses in (("ouday-GT70-2OC-2OD", valid), (d.HOST + ".local", valid), (d.HOST, valid.replace(b"2.20", b"2.200")),
                                (d.HOST, valid.replace(b"2.20", b"2.39"))):
            with self.assertRaises(ValueError):
                d.identity_check(host, addresses)

    def test_unit_and_known_local_command_shapes(self):
        value = d.unit_projection(unit())
        self.assertEqual(value["pid"], "123")
        for binary in ("/usr/bin/cloudflared", "/usr/local/bin/cloudflared"):
            for suffix in ([], [d.TUNNEL]):
                d.known_argv([binary, "--config", d.CONFIG, "tunnel", "run"] + suffix)
        for argv in (["/bin/sh", "-c", SECRET],
                     ["/usr/bin/cloudflared", "tunnel", "run", "--token", SECRET],
                     ["/usr/bin/cloudflared", "--config", d.CONFIG, "tunnel", "run", "another-tunnel"],
                     ["/usr/bin/cloudflared", "--config", "/private/config", "tunnel", "run"],
                     ["/usr/bin/cloudflared", "--config", d.CONFIG, "tunnel", "run", "--token-file", SECRET]):
            with self.assertRaises(ValueError):
                d.known_argv(argv)

    def test_inactive_unknown_duplicate_unit_and_pid_fail(self):
        for changes in (dict(ActiveState="inactive"), dict(SubState="exited"), dict(MainPID="0"),
                        dict(MainPID="../private"), dict(ControlGroup="/other.service"),
                        dict(Id="other.service"), dict(ExecStart=SECRET)):
            with self.assertRaises(ValueError):
                d.unit_projection(unit(**changes))
        with self.assertRaises(ValueError):
            d.unit_projection(unit() + b"MainPID=123\n")

    def mocked_collect(self, *, commands=None, files=None, processes=None):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(d.sys, "platform", "linux"))
        stack.enter_context(patch.object(d.os, "geteuid", return_value=0))
        stack.enter_context(patch.object(d.socket, "gethostname", return_value=d.HOST))
        address = b'[{"addr_info":[{"family":"inet","local":"192.168.2.20"}]}]'
        cmd = stack.enter_context(patch.object(d, "command", side_effect=commands or
            (lambda kind: address if kind == "addresses" else unit() if kind == "unit" else
             b'{"nftables":[]}' if kind == "nftables" else b"*filter\n:INPUT DROP [0:0]\nCOMMIT\n")) )
        file = stack.enter_context(patch.object(d, "secure_file", side_effect=files or
            (lambda path: (d.EXPECTED_CONFIG.encode(), (2,)))))
        proc = stack.enter_context(patch.object(d, "process_projection", side_effect=processes,
                                                return_value=("stable-process",)))
        return cmd, file, proc

    def test_complete_observation_keeps_all_authority_unknowns(self):
        cmd, file, _ = self.mocked_collect()
        report, status = d.collect()
        self.assertEqual(status, 0)
        self.assertTrue(report["tunnel"]["activeUnitProcessConfigPathBound"])
        for key in ("activationAuthorized", "effectiveIngressProven", "loadedConfigBytesProven",
                    "environmentOverridesExcluded", "externalConnectorsExcluded", "credentialFilesRead", "environmentRead"):
            self.assertIs(report[key], False)
        self.assertEqual([call.args[0] for call in cmd.call_args_list], ["addresses", "unit", "unit", "nftables", "iptables", "ip6tables", "addresses"])
        self.assertEqual([call.args[0] for call in file.call_args_list], [d.CONFIG, d.CONFIG])

    def test_wrong_host_stops_before_commands_or_protected_reads(self):
        cmd, file, proc = self.mocked_collect()
        with patch.object(d.socket, "gethostname", return_value="ouday-GT70-2OC-2OD"):
            self.assertEqual(d.collect()[1], 1)
        cmd.assert_not_called()
        file.assert_not_called()
        proc.assert_not_called()

    def test_wrong_address_stops_before_protected_reads(self):
        _, file, proc = self.mocked_collect(commands=lambda _: b"[]")
        self.assertEqual(d.collect()[1], 1)
        file.assert_not_called()
        proc.assert_not_called()

    def test_unprivileged_stops_before_any_command(self):
        cmd, file, _ = self.mocked_collect()
        with patch.object(d.os, "geteuid", return_value=1000):
            self.assertEqual(d.collect()[1], 1)
        cmd.assert_not_called()
        file.assert_not_called()

    def test_changed_process_or_config_fail_without_raw_output(self):
        self.mocked_collect(processes=[("first",), ("replacement",)])
        self.assertEqual(d.collect()[1], 1)
        with patch.object(d, "process_projection", return_value=("same",)), patch.object(d, "secure_file",
            side_effect=[(d.EXPECTED_CONFIG.encode(), (2,)), (SECRET.encode(), (3,))]):
            report, code = d.collect()
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, json.dumps(report))

    def test_changed_unit_or_pid_fails(self):
        address = b'[{"addr_info":[{"family":"inet","local":"192.168.2.20"}]}]'
        self.mocked_collect(commands=[address, unit(), unit(MainPID="124")])
        self.assertEqual(d.collect()[1], 1)

    def test_errors_and_arguments_never_leak(self):
        self.mocked_collect(commands=ValueError(SECRET))
        report, code = d.collect()
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, json.dumps(report))
        out = io.StringIO()
        with patch.object(d.sys, "argv", ["script", SECRET]), patch.object(d.os, "close"), contextlib.redirect_stdout(out):
            self.assertEqual(d.main(), 1)
        self.assertNotIn(SECRET, out.getvalue())

    def test_proc_reader_rejects_environment_and_other_files(self):
        for name in ("environ", "../123/cmdline", "root/private", "fd/1"):
            with self.assertRaises(ValueError):
                d.proc_read(-1, name)
        with self.assertRaises(ValueError):
            d.secure_file("/etc/shadow")

    def process_fixture(self, *, executable="/usr/bin/cloudflared", cgroup=None, starttimes=None, argv=None, inode=2, stat_pid="123"):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        value = d.unit_projection(unit())
        stack.enter_context(patch.object(d.os, "open", side_effect=[10, 11]))
        stack.enter_context(patch.object(d.os, "close"))
        stack.enter_context(patch.object(d.os, "fstat", return_value=SimpleNamespace(st_dev=1, st_ino=2)))
        stack.enter_context(patch.object(d.os, "readlink", return_value=executable))
        stack.enter_context(patch.object(d.os, "stat", side_effect=lambda name, **_: SimpleNamespace(
            st_mode=0o100755, st_uid=0, st_dev=1, st_ino=3 if name == "exe" else inode)))
        ticks = iter(starttimes or ["100", "100"])
        def read(_, name):
            if name == "cmdline": return b"\0".join(part.encode() for part in (argv or value["argv"])) + b"\0"
            if name == "cgroup": return (cgroup or "0::/system.slice/" + d.UNIT).encode()
            return (stat_pid + " (cloudflared) " + " ".join(["S"] + ["0"] * 18 + [next(ticks)] + ["0"] * 4)).encode()
        stack.enter_context(patch.object(d, "proc_read", side_effect=read))
        return value

    def test_process_binds_unit_executable_start_ticks_and_cgroup(self):
        value = self.process_fixture()
        result = d.process_projection(value)
        self.assertEqual(result[:2], (1, 2))
        self.assertEqual(result[2][4], "100")

    def test_process_rejects_deleted_executable_or_other_unit(self):
        for changes in (dict(executable="/usr/bin/cloudflared (deleted)"),
                        dict(cgroup="0::/system.slice/another.service"),
                        dict(argv=["/usr/bin/cloudflared", "tunnel", "run", "--token", SECRET]),
                        dict(starttimes=["100", "101"]), dict(inode=4), dict(stat_pid="124")):
            with self.subTest(changes=changes):
                value = self.process_fixture(**changes)
                with self.assertRaises(ValueError): d.process_projection(value)

    @unittest.skipUnless(os.geteuid() == 0 and os.sys.platform == "linux", "root-owned fixture runs in disposable Linux test container")
    def test_real_secure_file_refuses_links_modes_and_extra_links(self):
        with tempfile.TemporaryDirectory(dir="/root") as directory:
            path = Path(directory) / "config"
            path.write_bytes(b"fixture")
            path.chmod(0o600)
            with patch.object(d, "CONFIG", str(path)):
                self.assertEqual(d.secure_file(str(path))[0], b"fixture")
                path.chmod(0o644)
                with self.assertRaises(ValueError): d.secure_file(str(path))
                path.chmod(0o700)
                with self.assertRaises(ValueError): d.secure_file(str(path))
                path.chmod(0o600)
                duplicate = Path(directory) / "duplicate"
                os.link(path, duplicate)
                with self.assertRaises(ValueError): d.secure_file(str(path))
                duplicate.unlink()
                path.unlink()
                path.symlink_to("/etc/passwd")
                with self.assertRaises(OSError): d.secure_file(str(path))
            nested = Path(directory) / "nested"
            nested.symlink_to("/etc", target_is_directory=True)
            with patch.object(d, "CONFIG", str(nested / "passwd")):
                with self.assertRaises(OSError): d.secure_file(d.CONFIG)

    def test_only_fixed_subprocesses_and_readonly_opens(self):
        tree = ast.parse(SOURCE.read_text())
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {"json", "os", "re", "select", "socket", "stat", "subprocess", "sys", "time"})
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertEqual(sum(node.func.attr == "Popen" for node in calls), 1)
        self.assertFalse(any(node.func.attr in ("system", "execv", "unlink", "mkdir", "chmod", "chown", "connect", "write") for node in calls))
        self.assertEqual(set(d.COMMANDS), {"addresses", "unit", "nftables", "iptables", "ip6tables"})
        for node in calls:
            if node.func.attr == "open":
                text = ast.get_source_segment(SOURCE.read_text(), node)
                self.assertIn("os.O_RDONLY", text)


    def test_partial_firewall_errors_are_independent_and_sanitized(self):
        cmd, _, _ = self.mocked_collect()
        original = cmd.side_effect
        def read(name):
            if name == "iptables": raise OSError(SECRET)
            return original(name)
        cmd.side_effect = read
        report, status = d.collect()
        self.assertEqual(status, 1)
        self.assertEqual(report["tunnel"]["status"], "observed-local-consistency")
        self.assertEqual(report["firewalls"]["nftables"]["status"], "collected")
        self.assertEqual(report["firewalls"]["iptables"], {"status": "unverified", "failureStage": "command", "facts": None})
        self.assertEqual(report["firewalls"]["ip6tables"]["status"], "collected")
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertIs(d.validate_report(report), report)

    def test_tunnel_error_still_allows_scoped_firewall_collection(self):
        self.mocked_collect(files=PermissionError(SECRET))
        report, status = d.collect()
        self.assertEqual(status, 1)
        self.assertEqual(report["tunnel"]["status"], "unverified")
        self.assertEqual(report["tunnel"]["failureStage"], "config")
        self.assertTrue(all(row["status"] == "collected" for row in report["firewalls"].values()))

    def test_firewall_counts_never_emit_rules_names_comments_or_targets(self):
        raw = json.dumps({"nftables": [
            {"metainfo": {"version": SECRET}},
            {"table": {"name": SECRET}},
            {"chain": {"name": SECRET, "hook": "input", "policy": "drop"}},
            {"chain": {"hook": "forward", "policy": "drop"}},
            {"rule": {"expr": [{"comment": SECRET}]}},
            {"set": {"name": SECRET}}, "malformed", {}
        ]}).encode()
        facts = d.firewall_projection("nftables", raw)
        self.assertEqual((facts["tableCount"], facts["chainCount"], facts["ruleCount"]), (1, 2, 1))
        self.assertEqual(facts["unsupportedObjectCount"], 3)
        self.assertTrue(facts["inputDropPolicyPresent"] and facts["forwardDropPolicyPresent"])
        self.assertFalse(facts["completeReachabilityProven"])
        self.assertNotIn(SECRET, json.dumps(facts))
        raw = ("# " + SECRET + "\n*filter\n:INPUT DROP [1:2]\n:FORWARD DROP [3:4]\n"
               ":DOCKER-USER - [0:0]\n-A INPUT -m comment --comment " + SECRET + " -j ACCEPT\nCOMMIT\n").encode()
        for name in ("iptables", "ip6tables"):
            facts = d.firewall_projection(name, raw)
            self.assertEqual(facts["ruleCount"], 1)
            self.assertEqual(facts["unsupportedLineCount"], 0)
            self.assertTrue(facts["dockerUserChainPresent"])
            self.assertNotIn(SECRET, json.dumps(facts))
            for malformed in (raw.replace(b"COMMIT", b"UNKNOWN"), b"", b"-A INPUT -j ACCEPT\n", b"*filter\n"):
                self.assertGreater(d.firewall_projection(name, malformed)["unsupportedLineCount"], 0)

    def test_unknown_firewall_objects_never_report_collected(self):
        cmd, _, _ = self.mocked_collect()
        original = cmd.side_effect
        cmd.side_effect = lambda name: b'{"nftables":[{"set":{}}]}' if name == "nftables" else original(name)
        report, status = d.collect()
        self.assertEqual(status, 1)
        self.assertEqual(report["firewalls"]["nftables"]["status"], "unsupported")
        self.assertFalse(report["effectiveIngressProven"])

    def test_fixed_failure_stages_preserve_independent_components(self):
        cmd, file, process = self.mocked_collect()
        original = cmd.side_effect
        for kind, commands, files, processes, stage in (
            ("unit", lambda name: b"bad" if name == "unit" else original(name), None, None, "unit"),
            ("process", original, None, ValueError(SECRET), "unit-process"),
            ("config", original, ValueError(SECRET), None, "config"),
            ("stability", original, [(d.EXPECTED_CONFIG.encode(), (1,)), (d.EXPECTED_CONFIG.encode(), (2,))], None, "stability"),
        ):
            with self.subTest(kind=kind):
                cmd.side_effect = commands
                file.side_effect = files or (lambda _: (d.EXPECTED_CONFIG.encode(), (2,)))
                process.side_effect = processes
                report, code = d.collect()
                self.assertEqual(code, 1)
                self.assertEqual(report["tunnel"]["failureStage"], stage)
                self.assertTrue(all(row["status"] == "collected" for row in report["firewalls"].values()))
                self.assertNotIn(SECRET, json.dumps(report))
        cmd.side_effect = lambda name: b"invalid" if name == "nftables" else original(name)
        file.side_effect = lambda _: (d.EXPECTED_CONFIG.encode(), (2,))
        report, _ = d.collect()
        self.assertEqual(report["firewalls"]["nftables"]["failureStage"], "projection")

    def test_target_drift_discards_all_component_observations(self):
        self.mocked_collect()
        with patch.object(d.socket, "gethostname", side_effect=[d.HOST, "other-host"]):
            report, code = d.collect()
        self.assertEqual(code, 1)
        self.assertFalse(report["targetVerified"])
        self.assertEqual(report["failureStage"], "target")
        self.assertTrue(all(row["status"] == "unverified" for row in report["firewalls"].values()))

    def test_schema_rejects_extra_fields_types_authority_and_arbitrary_strings(self):
        self.mocked_collect()
        valid, _ = d.collect()
        def mutate(path, value):
            candidate = json.loads(json.dumps(valid))
            node = candidate
            for key in path[:-1]: node = node[key]
            node[path[-1]] = value
            with self.assertRaises((ValueError, TypeError)):
                d.validate_report(candidate)
        for path, value in [
            (["raw"], SECRET), (["target"], SECRET), (["schemaVersion"], True),
            (["status"], SECRET), (["targetVerified"], 1),
            (["status"], "unverified"),
            (["failureStage"], SECRET), (["tunnel", "failureStage"], SECRET),
            (["firewalls", "nftables", "failureStage"], SECRET),
            (["tunnel", "raw"], SECRET), (["tunnel", "stableRepeatedObservation"], 1),
            (["firewalls", "nftables", "raw"], SECRET),
            (["firewalls", "nftables", "facts", "ruleCount"], SECRET),
            (["firewalls", "nftables", "facts", "ruleCount"], True),
            (["firewalls", "nftables", "facts", "ruleCount"], -1),
            (["firewalls", "nftables", "facts", "ruleCount"], d.FIREWALL_LIMIT + 1),
            (["firewalls", "nftables", "facts", "raw"], SECRET),
            (["firewalls", "nftables", "facts", "completeReachabilityProven"], True),
            (["firewalls", "nftables", "status"], "unverified"),
            (["targetVerified"], False),
        ]:
            mutate(path, value)
        for key in d.FALSE_FIELDS: mutate([key], True)

    def test_main_closes_inherited_password_stdin_before_collection(self):
        events = []
        report = d.empty_report()
        out = io.StringIO()
        with patch.object(d.sys, "argv", ["-c"]), patch.object(d.os, "close", side_effect=lambda fd: events.append(("close", fd))), \
             patch.object(d, "collect", side_effect=lambda: (events.append(("collect",)), (report, 1))[1]), \
             contextlib.redirect_stdout(out):
            self.assertEqual(d.main(), 1)
        self.assertEqual(events, [("close", 0), ("collect",)])
        self.assertEqual(json.loads(out.getvalue()), report)

    def test_only_absolute_fixed_commands_and_no_self_read(self):
        self.assertEqual(d.COMMANDS["nftables"], ("/usr/sbin/nft", "-j", "list", "ruleset"))
        self.assertEqual(d.COMMANDS["iptables"], ("/usr/sbin/iptables-save",))
        self.assertEqual(d.COMMANDS["ip6tables"], ("/usr/sbin/ip6tables-save",))
        self.assertTrue(all(argv[0].startswith("/") for argv in d.COMMANDS.values()))
        with self.assertRaises(ValueError): d.secure_file(str(SOURCE))
        source = SOURCE.read_text()
        self.assertNotIn("__file__", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("stdin.read", source)

    def test_command_output_bound_and_disconnected_child_stdin(self):
        # Local, credential-free Python processes only; no daemons or containers.
        import sys
        with patch.dict(d.COMMANDS, {"unit": (sys.executable, "-I", "-c", "import sys; print(len(sys.stdin.buffer.read()))")}):
            self.assertEqual(d.command("unit"), b"0\n")
        with patch.dict(d.COMMANDS, {"unit": (sys.executable, "-I", "-c", "print('x' * 70000)")}):
            with self.assertRaises(ValueError): d.command("unit")
        with patch.dict(d.COMMANDS, {"nftables": (sys.executable, "-I", "-c", "print('x' * 70000)")}):
            self.assertEqual(len(d.command("nftables")), 70001)
        for name in ("nftables", "iptables", "ip6tables"):
            with patch.dict(d.COMMANDS, {name: (sys.executable, "-I", "-c", "print('x' * 1048576)")}):
                with self.assertRaises(ValueError): d.command(name)
        with patch.dict(d.COMMANDS, {"unit": (sys.executable, "-I", "-c", "raise SystemExit(7)")}):
            with self.assertRaises(ValueError): d.command("unit")
        with patch.dict(d.COMMANDS, {"unit": (sys.executable, "-I", "-c", "pass")}), \
             patch.object(d.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaises(ValueError): d.command("unit")

    def test_secure_file_metadata_race_rejected(self):
        from types import SimpleNamespace
        fields = dict(st_dev=1, st_ino=1, st_uid=0, st_gid=0, st_mode=0o100600,
                      st_nlink=1, st_size=7, st_mtime_ns=1, st_ctime_ns=1)
        directory = SimpleNamespace(st_uid=0, st_mode=0o40755)
        before, after = SimpleNamespace(**fields), SimpleNamespace(**{**fields, "st_ino": 2})
        with patch.object(d, "CONFIG", "/fixture"), patch.object(d.os, "open", side_effect=[10, 11]), \
             patch.object(d.os, "close"), patch.object(d.os, "fstat", side_effect=[directory, before, after]), \
             patch.object(d.os, "read", return_value=b"fixture"):
            with self.assertRaises(ValueError): d.secure_file("/fixture")

    @unittest.skipUnless(os.geteuid() == 0 and os.sys.platform == "linux", "credential-free hosted Linux root fixture only")
    def test_real_secure_file_rejects_owner_fifo_and_writable_ancestor(self):
        with tempfile.TemporaryDirectory(dir="/root") as directory:
            path = Path(directory) / "config"
            path.write_bytes(b"fixture")
            path.chmod(0o600)
            with patch.object(d, "CONFIG", str(path)):
                os.chown(path, 1, 0)
                with self.assertRaises(ValueError): d.secure_file(str(path))
                os.chown(path, 0, 1)
                with self.assertRaises(ValueError): d.secure_file(str(path))
                os.chown(path, 0, 0)
                Path(directory).chmod(0o777)
                with self.assertRaises(ValueError): d.secure_file(str(path))
                Path(directory).chmod(0o700)
                path.unlink()
                os.mkfifo(path, 0o600)
                with self.assertRaises(ValueError): d.secure_file(str(path))


if __name__ == "__main__":
    unittest.main()
