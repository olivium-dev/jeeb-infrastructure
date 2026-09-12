"""Synthetic-only engine tests. No SSH, root operations, or real HTTP requests."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


ENGINE_PATH = Path(__file__).resolve().parents[1] / "msi_deploy.py"
SPEC = importlib.util.spec_from_file_location("msi_deploy_under_test", ENGINE_PATH)
engine = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = engine
SPEC.loader.exec_module(engine)
LAUNCH_SPEC = importlib.util.spec_from_file_location("native_launch_under_test", ENGINE_PATH.with_name("native_launch.py"))
launcher = importlib.util.module_from_spec(LAUNCH_SPEC)
LAUNCH_SPEC.loader.exec_module(launcher)
REAL_VERIFY_CANDIDATE = engine.verify_candidate
ORIGINAL_LISTENER = engine.listener
ORIGINAL_PROBE = engine.probe


def tar_bytes(files, extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in files:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
        if extra is not None:
            archive.addfile(extra)
    return output.getvalue()


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="msi-engine-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.catalog_path = self.root / "catalog.json"
        self.manifest_path = self.root / "manifest.json"
        self.unit_file = self.root / "incumbent.service"
        self.config_file = self.root / "incumbent.json"
        self.unit_file.write_text("[Service]\nUser=synthetic\n")
        self.config_file.write_text('{"synthetic":true}\n')
        self.archive = self.root / "payload.tar"
        self.archive.write_bytes(tar_bytes([("app.dll", b"synthetic-binary")]))
        self.service = {
            "id": "synthetic", "repository": "olivium-dev/synthetic",
            "unit": "jeeb-synthetic.service", "port": 18081,
            "listen_addresses": ["127.0.0.1"],
            "effects": ["synthetic startup effect requires acknowledgment"],
            "probe": {"path": "/health/ready", "status": 200, "kind": "json",
                      "strength": "readiness", "equals": {"status": "Healthy"},
                      "required_true": ["checks.database"]},
        }
        self.catalog = {"schema": 1, "host": {"hostname": "ouday-GT70-2OC-2OD",
                       "ipv4": "192.168.2.39"}, "services": [self.service]}
        self.unit = {key: "" for key in engine.PROPS}
        self.unit.update({"Id": self.service["unit"], "LoadState": "loaded",
                          "ActiveState": "active", "SubState": "running",
                          "MainPID": "12345", "NRestarts": "0", "User": "synthetic",
                          "Group": "synthetic", "DynamicUser": "no",
                          "FragmentPath": str(self.unit_file),
                          "WorkingDirectory": str(self.root),
                          "ExecStart": "a" * 64, "Environment": "b" * 64,
                          "ExecMainStartTimestampMonotonic": "123456"})
        self.unit["process"] = {"uid": 1001, "exe": "/usr/bin/dotnet", "cwd": str(self.root),
                                "argv_sha256": "c" * 64, "environment": {"HOME": "d" * 64}}
        self.unit["manager"] = {"scope": "system"}
        self.manifest = {
            "schema": 1, "service": self.service["id"], "run_id": "synthetic-001",
            "source": {"repository": self.service["repository"], "commit": "1" * 40,
                       "default_branch": "main", "default_commit": "1" * 40,
                       "approved_commit": True, "provenance_sha256": "2" * 64},
            "catalog_sha256": "0" * 64,
            "launcher_sha256": engine.digest(ENGINE_PATH.with_name("native_launch.py").read_bytes()),
            "baseline": {"units": {self.service["unit"]: self.unit},
                         "listener_addresses": ["127.0.0.1"],
                         "files": [{"path": str(path), "sha256": engine.digest(path.read_bytes())}
                                   for path in (self.unit_file, self.config_file)]},
            "config_files": [str(self.config_file)],
            "artifact": {"path": str(self.archive), "sha256": engine.digest(self.archive.read_bytes()),
                         "files": [{"path": "app.dll", "size": 16, "executable": True,
                                    "sha256": engine.digest(b"synthetic-binary")}]},
            "launch": {"argv": ["{release}/app.dll"], "environment_bindings": [],
                       "source_review_sha256": "2" * 64, "argv_policy": "runtime-and-paths-only",
                       "contains_no_inline_credentials": True,
                       "configuration_and_persistent_paths_reviewed": True},
            "expected_environment": {"HOME": "d" * 64},
            "runtime_files": [],
            "path_bindings": [{"path": "incumbent.json", "target": str(self.config_file),
                               "kind": "config", "sha256": engine.digest(self.config_file.read_bytes()),
                               "uid": self.config_file.stat().st_uid,
                               "mode": self.config_file.stat().st_mode & 0o777}],
        }
        self.manifest["artifact"]["files"][0]["size"] = len(b"synthetic-binary")
        self.save_inputs()
        self.commands = []
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        # Default deny: every test must explicitly opt into a synthetic command mock.
        self.stack.enter_context(mock.patch.object(engine, "command", side_effect=AssertionError("unexpected host command")))
        self.stack.enter_context(mock.patch.object(engine.http.client, "HTTPConnection", side_effect=AssertionError("unexpected HTTP")))

    def save_inputs(self):
        self.catalog_path.write_bytes(engine.canonical(self.catalog))
        self.manifest["catalog_sha256"] = engine.digest(self.catalog_path.read_bytes())
        self.manifest_path.write_bytes(engine.canonical(self.manifest))
        return engine.digest(self.manifest_path.read_bytes())

    def cli(self, *args):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", [str(ENGINE_PATH), "--service", "synthetic",
                               "--catalog", str(self.catalog_path), *args]), contextlib.redirect_stdout(output):
            engine.main()
        return json.loads(output.getvalue())

    def manifest_args(self):
        return ["--manifest", str(self.manifest_path), "--manifest-sha256", self.save_inputs()]

    def host_mocks(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(engine.os, "geteuid", return_value=0))
        stack.enter_context(mock.patch.object(engine.sys, "platform", "linux"))
        stack.enter_context(mock.patch.object(engine.socket, "gethostname", return_value=self.catalog["host"]["hostname"]))
        stack.enter_context(mock.patch.object(engine, "command", return_value='[{"addr_info":[{"family":"inet","local":"192.168.2.39"}]}]'))
        stack.enter_context(mock.patch.object(engine, "inventory_units", return_value=[self.service["unit"]]))
        stack.enter_context(mock.patch.object(engine, "inspect_unit", side_effect=lambda *_: copy.deepcopy(self.unit)))
        stack.enter_context(mock.patch.object(engine, "physical", side_effect=lambda path, **_: Path(path)))
        resolve = Path.resolve
        def mock_linux_executable(path, *args, **kwargs):
            if str(path) == "/usr/bin/bash":
                return Path("/synthetic-linux/usr/bin/bash")
            return resolve(path, *args, **kwargs)
        stack.enter_context(mock.patch.object(Path, "resolve", mock_linux_executable))
        stack.enter_context(mock.patch.object(engine, "listener"))
        stack.enter_context(mock.patch.object(engine, "probe", return_value={"contract_passed": True}))
        return stack

    def test_default_is_local_plan_without_manifest_or_host_calls(self):
        self.manifest_path.unlink()
        result = self.cli()
        self.assertEqual("plan", result["action"])
        self.assertIs(result["host_operations"], False)
        self.assertEqual(engine.digest(engine.canonical(self.service["effects"])), result["effects_ack_sha256"])

    def chat_launch_inputs(self):
        service = dict(self.service, id="chat-service", repository="olivium-dev/chat-service",
                       unit="jeeb-chat.service")
        manifest = copy.deepcopy(self.manifest)
        manifest["service"] = service["id"]
        manifest["source"]["repository"] = service["repository"]
        manifest["baseline"]["units"] = {service["unit"]: self.unit}
        manifest["launch"]["argv"] = [
            "/home/ouday/.dotnet/dotnet", "{release}/ChatService.API.dll",
            "--urls=http://127.0.0.1:5803",
            "--Firebase:Chat:IdentityEndpointEnabled=true",
            "--Firestore:DatabaseId=(default)",
        ]
        return manifest, service

    def observe_unit_fixture(self, omitted=(), manager=None, bus_result="a(sb) 0", changes=None):
        unit = "jeeb-chat.service"
        data = {key: value for key, value in self.unit.items() if key in engine.PROPS and key not in omitted}
        data.update(Id=unit, ExecStart="{ path=/usr/bin/dotnet ; argv[]=/usr/bin/dotnet ; start_time=now }")
        data.update(changes or {})
        raw = "\n".join(f"{key}={value}" for key, value in data.items())
        with mock.patch.object(engine, "systemctl", return_value=raw), \
                mock.patch.object(engine, "command", return_value=bus_result) as called, \
                mock.patch.object(engine.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=1000)), \
                mock.patch.object(Path, "read_text", return_value="Uid:\t1000\t1000\t1000\t1000\n"), \
                mock.patch.object(Path, "read_bytes", side_effect=lambda: b"HOME=/synthetic\0"), \
                mock.patch.object(engine.os, "readlink", return_value="/synthetic/path"):
            result = engine.inspect_unit(unit, manager)
            return result, called.call_args_list

    def test_missing_environment_files_requires_exact_typed_empty_system_property(self):
        result, calls = self.observe_unit_fixture(omitted=("EnvironmentFiles",))
        self.assertEqual("", result["EnvironmentFiles"])
        self.assertEqual(set(engine.PROPS) | {"manager", "process"}, set(result))
        self.assertEqual([mock.call([
            "/usr/bin/busctl", "--system", "get-property", "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1/unit/jeeb_2dchat_2eservice",
            "org.freedesktop.systemd1.Service", "EnvironmentFiles",
        ])], calls)

    def test_missing_environment_files_stays_on_selected_user_manager(self):
        manager = {"scope": "user", "user": "ouday", "uid": 1000}
        result, calls = self.observe_unit_fixture(omitted=("EnvironmentFiles",), manager=manager)
        self.assertEqual(manager, result["manager"])
        self.assertEqual([mock.call([
            "/usr/sbin/runuser", "-u", "ouday", "--", "/usr/bin/env", "-i",
            "PATH=/usr/bin:/bin", "XDG_RUNTIME_DIR=/run/user/1000",
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
            "/usr/bin/busctl", "--user", "get-property", "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1/unit/jeeb_2dchat_2eservice",
            "org.freedesktop.systemd1.Service", "EnvironmentFiles",
        ])], calls)

    def test_present_environment_files_never_uses_bus_fallback(self):
        for value in ("", "/synthetic/service.env (ignore_errors=no)"):
            result, calls = self.observe_unit_fixture(changes={"EnvironmentFiles": value})
            self.assertEqual(value, result["EnvironmentFiles"])
            self.assertEqual([], calls)

    def test_missing_environment_files_rejects_nonempty_malformed_or_unknown_type(self):
        for value in ("", 'a(sb) 1 "/synthetic/service.env" false', "as 0", "a(sb) 00",
                      "a(sb) 0 extra", "a(sb) 0\nunknown", "permission denied"):
            with self.subTest(value=value), self.assertRaisesRegex(engine.GuardError, "unproven-empty-environmentfiles"):
                self.observe_unit_fixture(omitted=("EnvironmentFiles",), bus_result=value)

    def test_other_missing_unknown_or_wrong_identity_never_queries_bus(self):
        for omitted, changes in ((("Environment",), {}), (("EnvironmentFiles", "User"), {}),
                                 (("EnvironmentFiles",), {"Unknown": ""}),
                                 (("EnvironmentFiles",), {"Id": "other.service"}),
                                 (("EnvironmentFiles",), {"LoadState": "not-found"})):
            with self.subTest(omitted=omitted, changes=changes), \
                    mock.patch.object(engine, "confirm_empty_environment_files") as confirm, \
                    self.assertRaises(engine.GuardError):
                self.observe_unit_fixture(omitted=omitted, changes=changes)
            confirm.assert_not_called()

    def test_environment_files_bus_failure_or_wrong_user_never_falls_back(self):
        for manager in ({"scope": "system"}, {"scope": "user", "user": "ouday", "uid": 1000}):
            with mock.patch.object(engine, "command", side_effect=engine.GuardError("command-failed:busctl")) as called, \
                    mock.patch.object(engine.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=1000)), \
                    self.assertRaisesRegex(engine.GuardError, "command-failed:busctl"):
                engine.confirm_empty_environment_files("jeeb-chat.service", manager)
            self.assertEqual(1, called.call_count)
        with mock.patch.object(engine, "command") as called, \
                mock.patch.object(engine.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=2000)), \
                self.assertRaisesRegex(engine.GuardError, "user-manager-uid"):
            engine.confirm_empty_environment_files("jeeb-chat.service", {"scope": "user", "user": "ouday", "uid": 1000})
        called.assert_not_called()

    def test_environment_files_bus_unit_label_uses_canonical_escaping(self):
        with mock.patch.object(engine, "command", return_value="a(sb) 0") as called:
            engine.confirm_empty_environment_files("1_a-b@c.service", {"scope": "system"})
        self.assertEqual("/org/freedesktop/systemd1/unit/_31_5fa_2db_40c_2eservice", called.call_args.args[0][4])

    def test_chat_preserves_exact_native_cli_overrides_without_rewriting(self):
        manifest, service = self.chat_launch_inputs()
        before = copy.deepcopy(manifest)
        engine.validate_manifest(manifest, service)
        self.assertEqual(before, manifest)
        launch = engine.expected_launch(manifest, Path("/synthetic/new-release"))
        self.assertEqual("/synthetic/new-release/ChatService.API.dll", launch["argv"][1])
        self.assertEqual(before["launch"]["argv"][2:], launch["argv"][2:])

    def test_chat_rejects_any_native_launch_change(self):
        manifest, service = self.chat_launch_inputs()
        approved = manifest["launch"]["argv"]
        candidates = [approved[:2], approved + [approved[2]], approved + ["--other=true"],
                      approved[:2] + list(reversed(approved[2:])),
                      ["/usr/bin/dotnet"] + approved[1:],
                      [approved[0], "{release}/Other.dll"] + approved[2:],
                      approved[:2] + ["--urls", "http://127.0.0.1:5803"] + approved[3:]]
        for index, replacements in (
            (2, ["--urls=http://0.0.0.0:5803", "--urls=http://127.0.0.1:5804",
                 "--urls=http://localhost:5803", "--urls=http://127.0.0.1:5803;http://0.0.0.0:5803"]),
            (3, ["--Firebase:Chat:IdentityEndpointEnabled=false", "--Firebase:Chat:IdentityEndpointEnabled=True",
                 "--Firebase:Chat:IdentityEndpointEnabled=true ", "--secret=synthetic"]),
            (4, ["--Firestore:DatabaseId=other", "--Firestore:DatabaseId=", "--Firestore:DatabaseId=(default)\n"]),
        ):
            for value in replacements:
                changed = list(approved)
                changed[index] = value
                candidates.append(changed)
        for argv in candidates:
            with self.subTest(argv=argv):
                manifest["launch"]["argv"] = argv
                with self.assertRaises(engine.GuardError):
                    engine.validate_manifest(manifest, service)

    def test_chat_exception_cannot_be_reused_by_other_service_or_owner(self):
        manifest, service = self.chat_launch_inputs()
        self.manifest["launch"]["argv"] = manifest["launch"]["argv"]
        with self.assertRaisesRegex(engine.GuardError, "inline-configuration-forbidden"):
            engine.validate_manifest(self.manifest, self.service)
        for field, value in (("repository", "olivium-dev/other"), ("unit", "jeeb-other.service")):
            changed = dict(service, **{field: value})
            candidate = copy.deepcopy(manifest)
            candidate["source"]["repository"] = changed["repository"]
            candidate["baseline"]["units"] = {changed["unit"]: self.unit}
            with self.assertRaisesRegex(engine.GuardError, "chat-native-launch-contract"):
                engine.validate_manifest(candidate, changed)

    def test_unknown_and_reverse_actions_are_rejected_before_host_calls(self):
        for action in ("unknown", "rollback", "restore", "retry", "deploy-all", "enable"):
            with self.subTest(action=action), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    self.cli(action)
                self.assertEqual(2, caught.exception.code)

    def test_unknown_service_rejected(self):
        self.catalog["services"] = []
        self.save_inputs()
        with self.assertRaises(engine.GuardError):
            self.cli()

    def test_duplicate_service_option_cannot_override_wrapper(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises((SystemExit, engine.GuardError)):
            self.cli("--service", "synthetic")

    def test_host_modes_require_pinned_manifest(self):
        for action in ("preflight", "deploy", "verify"):
            with self.subTest(action=action), self.assertRaises(engine.GuardError):
                self.cli(action)

    def test_wrong_manifest_hash_rejected_before_preflight(self):
        with mock.patch.object(engine, "preflight") as before, self.assertRaises(engine.GuardError):
            self.cli("preflight", "--manifest", str(self.manifest_path), "--manifest-sha256", "f" * 64)
        before.assert_not_called()

    def test_deploy_requires_exact_current_effects_ack(self):
        for ack in (None, "f" * 64):
            args = ["deploy", *self.manifest_args()]
            if ack:
                args += ["--ack-effects", ack]
            with self.subTest(ack=ack), mock.patch.object(engine, "deploy") as activate, \
                 mock.patch.object(engine, "operation_lock") as lock:
                with self.assertRaisesRegex(engine.GuardError, "startup-effects-ack-required"):
                    self.cli(*args)
                activate.assert_not_called()
                lock.assert_not_called()

    def test_exact_effects_ack_dispatches_only_selected_service(self):
        self.host_mocks()
        self.stack.enter_context(mock.patch.object(engine, "operation_lock", return_value=contextlib.nullcontext()))
        with mock.patch.object(engine, "deploy", return_value={"synthetic": True}) as activate:
            result = self.cli("deploy", *self.manifest_args(), "--ack-effects",
                              engine.digest(engine.canonical(self.service["effects"])))
        self.assertEqual("deploy", result["action"])
        activate.assert_called_once()
        self.assertEqual("synthetic", activate.call_args.args[1]["id"])

    def test_valid_manifest_passes_pure_validation(self):
        engine.validate_manifest(self.manifest, self.service)

    def test_wrong_source_or_approval_rejected(self):
        for key, value in (("repository", "another/repository"), ("commit", "main"),
                           ("approved_commit", False), ("provenance_sha256", "unknown")):
            manifest = copy.deepcopy(self.manifest)
            manifest["source"][key] = value
            with self.subTest(key=key), self.assertRaises(engine.GuardError):
                engine.validate_manifest(manifest, self.service)

    def test_artifact_traversal_and_secret_paths_rejected(self):
        for path in ("../escape", "/absolute", "a/../../escape", ".msi/launch.json", ".env",
                     "secrets/token", "credentials/token", "appsettings.Production.json", "key.pem", "a//b"):
            manifest = copy.deepcopy(self.manifest)
            manifest["artifact"]["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(engine.GuardError):
                engine.validate_manifest(manifest, self.service)

    def test_duplicate_artifact_inventory_rejected(self):
        self.manifest["artifact"]["files"] *= 2
        with self.assertRaises(engine.GuardError):
            engine.validate_manifest(self.manifest, self.service)

    def test_launch_controls_or_unbound_release_rejected(self):
        for argv in (["/bin/echo", "secret\ntext"], ["/bin/echo", "no-release"],
                     ["/bin/echo", "{release}/app", "%n"]):
            manifest = copy.deepcopy(self.manifest)
            manifest["launch"]["argv"] = argv
            with self.subTest(argv=argv), self.assertRaises(engine.GuardError):
                engine.validate_manifest(manifest, self.service)

    def test_inline_credentials_rejected(self):
        for value in ("--Password=SYNTHETIC_SECRET", "--token=SYNTHETIC_SECRET",
                      "https://synthetic:SYNTHETIC_SECRET@example.invalid"):
            manifest = copy.deepcopy(self.manifest)
            manifest["launch"]["argv"].append(value)
            with self.subTest(value=value), self.assertRaises(engine.GuardError):
                engine.validate_manifest(manifest, self.service)

    def test_archive_roundtrip_and_missing_extra_duplicate_rejected(self):
        entries = self.manifest["artifact"]["files"]
        self.assertEqual({"app.dll": b"synthetic-binary"}, engine.unpack_checked(self.archive.read_bytes(), entries))
        for members in ([], [("app.dll", b"synthetic-binary"), ("extra", b"x")],
                        [("app.dll", b"synthetic-binary"), ("app.dll", b"synthetic-binary")],
                        [("app.dll", b"wrong-bytes")]):
            with self.subTest(members=members), self.assertRaises(engine.GuardError):
                engine.unpack_checked(tar_bytes(members), entries)

    def test_tar_links_and_devices_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.DIRTYPE):
            member = tarfile.TarInfo("app.dll")
            member.type = kind
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                member.linkname = "/synthetic-outside"
            with self.subTest(kind=kind), self.assertRaises(engine.GuardError):
                engine.unpack_checked(tar_bytes([], member), self.manifest["artifact"]["files"])

    def test_hidden_pax_and_gnu_headers_are_not_accepted_as_regular_inventory(self):
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
            # Empty extended header can be hidden by Python's logical tar iterator.
            # Exact physical inventory must reject it, even if logical payload is valid.
            header = tarfile.TarInfo("hidden-metadata")
            header.type = kind
            data = header.tobuf(format=tarfile.USTAR_FORMAT) + self.archive.read_bytes()
            with self.subTest(kind=kind), self.assertRaises((engine.GuardError, tarfile.TarError)):
                engine.unpack_checked(data, self.manifest["artifact"]["files"])

    def test_environment_projection_hashes_values_and_validates_volatile_identity(self):
        data = b"HOME=/synthetic\0PRIVATE_VALUE=synthetic-not-a-credential\0INVOCATION_ID=inv\0SYSTEMD_EXEC_PID=123\0"
        result = engine.environment_projection(data, 123, "inv")
        self.assertEqual({"HOME": engine.digest(b"/synthetic"),
                          "PRIVATE_VALUE": engine.digest(b"synthetic-not-a-credential")}, result)
        self.assertNotIn("synthetic-not-a-credential", json.dumps(result))
        for value in (data.replace(b"PID=123", b"PID=124"), data.replace(b"ID=inv", b"ID=other"),
                      data + b"HOME=/duplicate\0", data + b"INVOCATION_ID=inv\0"):
            with self.subTest(value=value), self.assertRaises(engine.GuardError):
                engine.environment_projection(value, 123, "inv")

    def test_journal_stream_must_match_actual_process_descriptor(self):
        descriptor = SimpleNamespace(st_dev=7, st_ino=8)
        with mock.patch.object(engine.os, "stat", return_value=descriptor) as observed:
            self.assertEqual({}, engine.environment_projection(b"JOURNAL_STREAM=7:8\0", 123, "inv"))
            self.assertIn(mock.call("/proc/123/fd/1"), observed.call_args_list)
            with self.assertRaises(engine.GuardError):
                engine.environment_projection(b"JOURNAL_STREAM=7:9\0", 123, "inv")

    def test_operation_lock_is_exclusive_and_closes_even_on_failure(self):
        info = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)
        with mock.patch.object(engine, "physical"), mock.patch.object(engine.os, "open", return_value=321) as opened, \
             mock.patch.object(engine.os, "fstat", return_value=info), mock.patch.object(engine.os, "close") as closed, \
             mock.patch.object(engine.fcntl, "flock") as flock:
            with self.assertRaisesRegex(RuntimeError, "synthetic-failure"):
                with engine.operation_lock():
                    raise RuntimeError("synthetic-failure")
            opened.assert_called_once()
            self.assertTrue(opened.call_args.args[1] & os.O_NOFOLLOW)
            flock.assert_called_once_with(321, engine.fcntl.LOCK_EX | engine.fcntl.LOCK_NB)
            closed.assert_called_once_with(321)

    def test_busy_or_nonprivate_lock_never_enters_operation(self):
        info = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)
        for mode, uid, busy in ((0o644, 0, False), (0o600, 1001, False), (0o600, 0, True)):
            info.st_mode, info.st_uid = stat.S_IFREG | mode, uid
            with self.subTest(mode=mode, uid=uid, busy=busy), mock.patch.object(engine, "physical"), \
                 mock.patch.object(engine.os, "open", return_value=321), mock.patch.object(engine.os, "fstat", return_value=info), \
                 mock.patch.object(engine.os, "close") as closed, mock.patch.object(engine.fcntl, "flock", side_effect=BlockingIOError() if busy else None):
                with self.assertRaises((engine.GuardError, BlockingIOError)):
                    with engine.operation_lock():
                        self.fail("invalid or busy lock entered operation")
                closed.assert_called_once_with(321)

    def test_pinned_input_rejects_symlink_and_wrong_bytes(self):
        link = self.root / "link"
        link.symlink_to(self.archive)
        for path, pin in ((link, engine.digest(self.archive.read_bytes())), (self.archive, "0" * 64)):
            with self.subTest(path=path), self.assertRaises(engine.GuardError):
                engine.pinned(path, pin)

    def test_static_launch_ignores_only_systemd_runtime_suffix(self):
        old = "{ path=/usr/bin/dotnet ; argv[]=/usr/bin/dotnet app.dll ; ignore_errors=no ; start_time=old ; pid=12345 ; }"
        reset = old.replace("start_time=old ; pid=12345", "start_time=[n/a] ; pid=0")
        self.assertEqual(engine.static_exec(old), engine.static_exec(reset))
        self.assertNotEqual(engine.static_exec(old), engine.static_exec(old.replace("app.dll", "other.dll")))
        with self.assertRaises(engine.GuardError):
            engine.static_exec("unrecognized")

    def test_wrong_host_preflight_has_no_commands(self):
        with mock.patch.object(engine.os, "geteuid", return_value=0), mock.patch.object(engine.sys, "platform", "linux"), \
             mock.patch.object(engine.socket, "gethostname", return_value="not-msi"), self.assertRaises(engine.GuardError):
            engine.preflight(self.manifest, self.service, self.catalog)

    def test_stale_unit_and_config_proof_rejected(self):
        self.host_mocks()
        with mock.patch.object(engine, "inspect_unit", return_value={**self.unit, "MainPID": "99999"}), self.assertRaises(engine.GuardError):
            engine.preflight(self.manifest, self.service, self.catalog)
        self.config_file.write_text('{"synthetic":"changed"}')
        with self.assertRaisesRegex(engine.GuardError, "hash"):
            engine.preflight(self.manifest, self.service, self.catalog)

    def test_config_and_persistent_bindings_require_exact_identity(self):
        engine.check_bindings(self.manifest)
        original = self.manifest["path_bindings"][0]
        for key, value in (("sha256", "f" * 64), ("uid", original["uid"] + 1), ("mode", 0o777)):
            changed = copy.deepcopy(self.manifest)
            changed["path_bindings"][0][key] = value
            with self.subTest(key=key), self.assertRaises(engine.GuardError):
                engine.check_bindings(changed)
        directory = self.root / "persistent"
        directory.mkdir(mode=0o700)
        info = directory.stat()
        binding = {"path": "state", "target": str(directory), "kind": "persistent-directory",
                   "uid": info.st_uid, "mode": 0o700, "device": info.st_dev, "inode": info.st_ino}
        self.manifest["path_bindings"] = [binding]
        engine.check_bindings(self.manifest)
        binding["inode"] += 1
        with self.assertRaisesRegex(engine.GuardError, "persistent-directory-identity"):
            engine.check_bindings(self.manifest)

    def test_unbound_incumbent_config_and_changed_listener_stop_preflight(self):
        self.host_mocks()
        self.manifest["path_bindings"] = []
        with self.assertRaisesRegex(engine.GuardError, "unbound-existing-config"):
            engine.preflight(self.manifest, self.service, self.catalog)
        for row in ("LISTEN 0 512 0.0.0.0:18081 0.0.0.0:* users:((app,pid=12345,fd=9))",
                    "LISTEN 0 512 127.0.0.1:18081 0.0.0.0:* users:((app,pid=99999,fd=9))"):
            with mock.patch.object(engine, "command", return_value=row), self.assertRaises(engine.GuardError):
                # Bypass only the host_mocks listener patch, not the production parser.
                ORIGINAL_LISTENER(self.service, 12345, ["127.0.0.1"])

    def test_host_ip_substring_is_not_identity(self):
        self.host_mocks()
        with mock.patch.object(engine, "command", return_value='[{"addr_info":[{"family":"inet","local":"192.168.2.390"}]}]'), \
             self.assertRaisesRegex(engine.GuardError, "host-ip"):
            engine.preflight(self.manifest, self.service, self.catalog)

    def test_http_200_degraded_incumbent_blocks_before_any_deployment_write(self):
        self.host_mocks()
        paths = tuple(self.root / name for name in ("not-created-release", "not-created-drop", "not-created-report"))
        with mock.patch.object(engine, "paths_for", return_value=paths), \
             mock.patch.object(engine, "probe", side_effect=ORIGINAL_PROBE), \
             self.probe_response({"status": "Degraded", "checks": {"database": True}}), \
             self.assertRaisesRegex(engine.GuardError, "probe-value"):
            engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        self.assertFalse(any(path.exists() for path in paths))

    def test_valid_mock_host_preflight(self):
        self.host_mocks()
        self.assertTrue(engine.preflight(self.manifest, self.service, self.catalog)["contract_passed"])

    def probe_response(self, body, status=200, content_type="application/json"):
        response = mock.Mock(status=status)
        response.read.return_value = body if isinstance(body, bytes) else json.dumps(body).encode()
        response.getheader.return_value = content_type
        connection = mock.Mock()
        connection.getresponse.return_value = response
        return mock.patch.object(engine.http.client, "HTTPConnection", return_value=connection)

    def test_strict_probe_accepts_only_correct_schema_types_and_status(self):
        with self.probe_response({"status": "Healthy", "checks": {"database": True}}):
            self.assertTrue(engine.probe(self.service)["contract_passed"])
        cases = [({"status": "Degraded", "checks": {"database": True}}, 200),
                 ({"status": "Healthy", "checks": {"database": False}}, 200),
                 ({"status": "Healthy", "checks": {"database": 1}}, 200),
                 ({"status": "Healthy"}, 200), ([], 200),
                 ({"status": "Healthy", "checks": {"database": True}}, 302)]
        for body, status in cases:
            with self.subTest(body=body, status=status), self.probe_response(body, status), self.assertRaises(engine.GuardError):
                engine.probe(self.service)

    def test_probe_html_cannot_satisfy_json_readiness(self):
        with self.probe_response(b"<html>healthy</html>", content_type="text/html"), self.assertRaises((engine.GuardError, ValueError)):
            engine.probe(self.service)

    def test_probe_required_keys_numeric_min_and_body_bound(self):
        self.service["probe"].update(required_keys=["owner"], numeric_min={"latency": 0})
        valid = {"status": "Healthy", "checks": {"database": True}, "owner": "synthetic", "latency": 0}
        with self.probe_response(valid):
            self.assertTrue(engine.probe(self.service)["contract_passed"])
        for value in (-1, "0", True, None):
            with self.subTest(value=value), self.probe_response({**valid, "latency": value}), self.assertRaises(engine.GuardError):
                engine.probe(self.service)
        del valid["owner"]
        with self.probe_response(valid), self.assertRaisesRegex(engine.GuardError, "probe-missing-field"):
            engine.probe(self.service)
        with self.probe_response(b" " * 65537), self.assertRaisesRegex(engine.GuardError, "probe-http"):
            engine.probe(self.service)

    def test_security_guards_still_execute_under_optimization(self):
        code = ("import importlib.util,sys; "
                "s=importlib.util.spec_from_file_location('engine',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "m.require(False,'synthetic-guard-must-fire')")
        result = subprocess.run([sys.executable, "-I", "-O", "-c", code, str(ENGINE_PATH)],
                                capture_output=True, text=True, timeout=10,
                                env={"PATH": os.defpath})
        self.assertNotEqual(0, result.returncode)
        self.assertIn("synthetic-guard-must-fire", result.stderr)

    def deployment_mocks(self, failed=False):
        # Config-binding identity is tested against real temp files by preflight tests;
        # this mocked host publication fixture has no external path bindings.
        self.manifest["path_bindings"] = []
        root, units, reports = (self.root / name for name in ("releases", "units", "reports"))
        units.mkdir()
        reports.mkdir()
        for name, value in (("ROOT", root), ("UNIT_DIR", units), ("REPORT_ROOT", reports)):
            self.stack.enter_context(mock.patch.object(engine, name, value))
        self.stack.enter_context(mock.patch.object(engine, "preflight", return_value={"contract_passed": True}))
        # Root ownership is mocked, but every actual deployment write stays in this test's temp tree.
        original_physical = engine.physical
        def local_physical(path, **kwargs):
            path = Path(path)
            if path.is_relative_to(self.root):
                return original_physical(path)
            return original_physical(path, **kwargs)
        self.stack.enter_context(mock.patch.object(engine, "physical", side_effect=local_physical))
        def inspected(*_):
            value = copy.deepcopy(self.unit)
            if any("daemon-reload" in argv for argv in self.commands):
                release, drop, _ = engine.paths_for(self.manifest, self.service)
                value.update(engine.expected_unit_delta(self.unit, release, drop))
            return value
        self.stack.enter_context(mock.patch.object(engine, "inspect_unit", side_effect=inspected))
        self.stack.enter_context(mock.patch.object(engine, "command", side_effect=lambda argv: self.commands.append(argv) or ""))
        self.stack.enter_context(mock.patch.object(engine.time, "sleep"))
        verify = mock.Mock(side_effect=engine.GuardError("synthetic-unhealthy") if failed else None,
                           return_value={"pid": 54321, "health": {"contract_passed": True}, "release": "synthetic"})
        self.stack.enter_context(mock.patch.object(engine, "verify_candidate", verify))
        return verify

    def test_forward_deploy_publishes_complete_drop_and_restarts_exactly_once(self):
        verify = self.deployment_mocks()
        result = engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        release, drop, report = engine.paths_for(self.manifest, self.service)
        self.assertEqual(engine.dropin_text(release), drop.read_bytes())
        self.assertEqual(b"synthetic-binary", (release / "app.dll").read_bytes())
        self.assertEqual([["/usr/bin/systemctl", "restart", "jeeb-synthetic.service"]],
                         [argv for argv in self.commands if "restart" in argv])
        self.assertEqual(2, verify.call_count)
        self.assertEqual(str(report), result["report"])
        self.assertTrue(any("verified" in path.name for path in report.iterdir()))
        self.assertEqual(drop.stat().st_ino, drop.with_suffix(".pending").stat().st_ino)

    def test_failed_candidate_is_never_restored_or_restarted_again(self):
        self.deployment_mocks(failed=True)
        with self.assertRaises(engine.GuardError):
            engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        release, drop, report = engine.paths_for(self.manifest, self.service)
        self.assertTrue(release.exists())
        self.assertEqual(engine.dropin_text(release), drop.read_bytes())
        self.assertEqual(1, sum("restart" in argv for argv in self.commands))
        self.assertFalse(any(word in " ".join(argv) for argv in self.commands for word in ("rollback", "restore", "revert")))
        failure = next(json.loads(path.read_text()) for path in report.iterdir() if "failed" in path.name)
        self.assertEqual("synthetic-unhealthy", failure["error"])
        count = len(self.commands)
        with self.assertRaises(engine.GuardError):
            engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        self.assertEqual(count, len(self.commands))

    def test_last_moment_drift_stops_before_selection_or_restart(self):
        self.deployment_mocks()
        with mock.patch.object(engine, "preflight", side_effect=[{}, engine.GuardError("synthetic-drift")]), self.assertRaises(engine.GuardError):
            engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        release, drop, report = engine.paths_for(self.manifest, self.service)
        self.assertTrue(release.exists())
        self.assertFalse(drop.exists())
        self.assertEqual([], self.commands)
        self.assertTrue(any("failed" in path.name for path in report.iterdir()))

    def test_nonexecutable_candidate_stops_before_unit_publication(self):
        self.deployment_mocks()
        self.manifest["artifact"]["files"][0]["executable"] = False
        with self.assertRaisesRegex(engine.GuardError, "candidate-launch-executable"):
            engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        release, drop, report = engine.paths_for(self.manifest, self.service)
        self.assertTrue(release.exists())
        self.assertFalse(drop.exists())
        self.assertEqual([], self.commands)
        self.assertTrue(any("failed" in path.name for path in report.iterdir()))

    def test_reload_must_load_exact_new_command_before_the_single_restart(self):
        self.deployment_mocks()
        with mock.patch.object(engine, "inspect_unit", return_value=copy.deepcopy(self.unit)), \
             self.assertRaisesRegex(engine.GuardError, "post-reload-launch-drift"):
            engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        self.assertEqual(1, sum("daemon-reload" in argv for argv in self.commands))
        self.assertEqual(0, sum("restart" in argv for argv in self.commands))

    def test_real_candidate_verifier_rejects_environment_argv_pid_and_unit_drift(self):
        self.deployment_mocks()
        engine.deploy(self.manifest, self.service, self.catalog, self.save_inputs())
        release, drop, _ = engine.paths_for(self.manifest, self.service)
        current = copy.deepcopy(self.unit)
        current.update(engine.expected_unit_delta(self.unit, release, drop))
        current.update(MainPID="54321", ExecMainStartTimestampMonotonic="654321")
        expected_argv = [v.replace("{release}", str(release)) for v in self.manifest["launch"]["argv"]]
        current["process"].update(cwd=str(release), exe=str(release / "app.dll"), environment=self.manifest["expected_environment"],
                                  argv_sha256=engine.digest(b"\0".join(v.encode() for v in expected_argv) + b"\0"))
        with mock.patch.object(engine, "inspect_unit", return_value=current), \
             mock.patch.object(engine, "inventory_units", return_value=[self.service["unit"]]), \
             mock.patch.object(engine, "listener"), mock.patch.object(engine, "probe", return_value={"contract_passed": True}):
            self.assertEqual(54321, REAL_VERIFY_CANDIDATE(self.manifest, self.service)["pid"])
            cases = [("process", "environment", {}), ("process", "argv_sha256", "0" * 64),
                     ("process", "exe", "/synthetic/another-runtime"),
                     ("process", "uid", 0), (None, "MainPID", self.unit["MainPID"]),
                     (None, "NRestarts", "1"), (None, "User", "root"),
                     (None, "ExecStart", self.unit["ExecStart"])]
            for parent, key, value in cases:
                altered = copy.deepcopy(current)
                (altered[parent] if parent else altered)[key] = value
                with self.subTest(key=key), mock.patch.object(engine, "inspect_unit", return_value=altered), self.assertRaises(engine.GuardError):
                    REAL_VERIFY_CANDIDATE(self.manifest, self.service)
            # A transformed interpreter process needs both its exact argv hash and
            # an exact release argv element, not an arbitrary substring in another arg.
            self.manifest["expected_process"] = {"argv_sha256": current["process"]["argv_sha256"],
                "exe": "{release}/app.dll", "release_argument": "{release}/app.dll",
                "source_review_sha256": "7" * 64}
            original_read = Path.read_bytes
            command_bytes = str(release / "app.dll").encode() + b"\0"
            def process_bytes(path):
                return command_bytes if str(path) == "/proc/54321/cmdline" else original_read(path)
            with mock.patch.object(Path, "read_bytes", process_bytes):
                self.assertEqual(54321, REAL_VERIFY_CANDIDATE(self.manifest, self.service)["pid"])
                command_bytes = b"prefix-" + command_bytes
                with self.assertRaisesRegex(engine.GuardError, "candidate-release-argument"):
                    REAL_VERIFY_CANDIDATE(self.manifest, self.service)

    def test_native_launcher_rejects_root_and_changed_binding_before_exec(self):
        config = {"argv": ["/synthetic/app"], "environment_bindings": [{"path": str(self.config_file),
                  "sha256": "0" * 64, "export_all": False}]}
        with mock.patch.object(launcher.sys, "argv", ["launcher", "/synthetic/config"]), \
             mock.patch.object(launcher.sys, "platform", "linux"), \
             mock.patch.object(launcher, "read_regular", side_effect=[engine.canonical(config), b"synthetic"]), \
             mock.patch.object(launcher.os, "execv") as execute:
            with mock.patch.object(launcher.os, "geteuid", return_value=0), self.assertRaisesRegex(ValueError, "nonroot Linux"):
                launcher.main()
            with mock.patch.object(launcher.os, "geteuid", return_value=1001), self.assertRaisesRegex(ValueError, "binding changed"):
                launcher.main()
            execute.assert_not_called()

    def test_native_launcher_freezes_bindings_and_encodes_close_before_exec(self):
        # memfd/seals ABI is injected on macOS. This verifies generated Bash inputs,
        # not Linux kernel sealing or systemd behavior; those require Linux validation.
        source = b"MSI_UNEXPORTED=synthetic\nexport MSI_EXPORTED=synthetic\n"
        config = {"argv": ["/synthetic/app", "argument"], "environment_bindings": [
            {"path": "/synthetic/one", "sha256": engine.digest(source), "export_all": False},
            {"path": "/synthetic/two", "sha256": engine.digest(source), "export_all": True}]}
        descriptors = []
        def synthetic_memfd(*_):
            fd = os.open(self.root / ("anonymous-" + str(len(descriptors))), os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            descriptors.append(fd)
            return fd
        class ExecObserved(Exception):
            pass
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(launcher.sys, "argv", ["launcher", "/synthetic/config"]))
            stack.enter_context(mock.patch.object(launcher.sys, "platform", "linux"))
            stack.enter_context(mock.patch.object(launcher.os, "geteuid", return_value=1001))
            stack.enter_context(mock.patch.object(launcher, "read_regular", side_effect=[engine.canonical(config), source, source]))
            stack.enter_context(mock.patch.object(launcher.os, "memfd_create", side_effect=synthetic_memfd, create=True))
            for namespace, names in ((launcher.os, ["MFD_ALLOW_SEALING"]),
                                     (launcher.fcntl, ["F_ADD_SEALS", "F_SEAL_SEAL", "F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE"])):
                for index, name in enumerate(names):
                    stack.enter_context(mock.patch.object(namespace, name, 1 << index, create=True))
            sealed = stack.enter_context(mock.patch.object(launcher.fcntl, "fcntl"))
            executed = stack.enter_context(mock.patch.object(launcher.os, "execv", side_effect=ExecObserved))
            try:
                with self.assertRaises(ExecObserved):
                    launcher.main()
                argv = executed.call_args.args[1]
                self.assertEqual("/usr/bin/bash", executed.call_args.args[0])
                self.assertEqual(["2", "0", f"/proc/self/fd/{descriptors[0]}", "1", f"/proc/self/fd/{descriptors[1]}", "/synthetic/app", "argument"], argv[6:])
                script = argv[4]
                self.assertLess(script.index('exec {fd}<&-'), script.index('exec "$@"'))
                self.assertIn('if [[ "$1" == 1 ]]; then set -a; else set +a; fi', script)
                self.assertEqual(2, sealed.call_count)
                for fd in descriptors:
                    os.lseek(fd, 0, os.SEEK_SET)
                    self.assertEqual(source, os.read(fd, 1024))
                    self.assertTrue(os.get_inheritable(fd))
                self.assertNotIn(source.decode(), json.dumps(argv))
            finally:
                for fd in descriptors:
                    os.close(fd)


if __name__ == "__main__":
    unittest.main()
