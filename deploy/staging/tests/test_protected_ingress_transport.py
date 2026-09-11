import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/protected-ingress-transport.py"
SPEC = importlib.util.spec_from_file_location("transport", SCRIPT)
T = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)
PASSWORD = "transport-test-only-password"
VALIDATOR = '''def validate_report(report):
 if set(report)!={"safe","status"} or report["safe"] is not True or report["status"] not in ("unverified","observed-local-consistency","unsupported-invocation"): raise ValueError()
 return report
'''


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fake_ssh(self, mode="ok"):
        output = self.root / "observations.json"
        child = self.root / "fake-ssh"
        child.write_text(f'''#!{sys.executable}
import json,os,select,sys,time
mode={mode!r}; observations={{"early":False,"environment":False,"arguments":False,"once":False}}
try:
 observations["environment"]=any(k in os.environ for k in ("STAGING_SUDO_PASSWORD","GH_TOKEN","UNRELATED_SECRET"))
 observations["arguments"]={PASSWORD!r} in repr(sys.argv)
 observations["early"]=bool(select.select([sys.stdin],[],[],0.1)[0])
 with open({str(output)!r},"a") as f:f.write(json.dumps(observations)+"\\n")
 if mode=="missing_preflight":sys.exit(0)
 if mode=="timeout":time.sleep(5)
 elif mode=="oversize":sys.stdout.write("PRIVATE_PROVIDER_TEXT"*20000);sys.stdout.flush()
 elif mode=="stderr_oversize":sys.stderr.write("PRIVATE_PROVIDER_TEXT"*20000);sys.stderr.flush()
 else:
  pre={T.PREFLIGHT!r}
  if mode in ("host","address","user"):pre[mode]="wrong"
  line=json.dumps(pre)
  if mode=="unknown_preflight":line=json.dumps(dict(pre,extra="PRIVATE_PROVIDER_TEXT"))
  if mode=="duplicate_preflight":line=line[:-1]+',"host":"olivium-ephemerals"}}'
  print(line,flush=True)
  if mode in ("host","address","user","unknown_preflight","duplicate_preflight"):
   observations["early"]=bool(sys.stdin.buffer.read())
  else:
   data=sys.stdin.buffer.readline();tail=sys.stdin.buffer.read()
   observations["once"]=(data=={(PASSWORD + chr(10)).encode()!r} and tail==b"")
   if mode=="bad_json":print("PRIVATE_PROVIDER_TEXT",flush=True)
   elif mode=="unknown_report":print(json.dumps({{"safe":True,"raw":"PRIVATE_PROVIDER_TEXT"}}),flush=True)
   elif mode=="failure":sys.stderr.write("PRIVATE_PROVIDER_TEXT");sys.exit(1)
   else:
    status="unverified" if mode in ("partial","wrong_exit_zero") else "unsupported-invocation" if mode=="invocation" else "observed-local-consistency"
    print(json.dumps({{"safe":True,"status":status}}),flush=True)
    if mode in ("partial","wrong_exit_one","invocation"):sys.exit(1)
finally:
 with open({str(output)!r},"a") as f:f.write(json.dumps(observations)+"\\n")
''')
        child.chmod(0o700)
        return child, output

    def invoke(self, mode):
        child, observations = self.fake_ssh(mode)
        out = io.StringIO()
        spawn = subprocess.Popen
        streams = []
        def observed_spawn(*args, **kwargs):
            process = spawn(*args, **kwargs)
            process.stdin = mock.Mock(wraps=process.stdin)
            streams.append(process.stdin)
            return process
        with mock.patch.object(T, "SSH", str(child)), mock.patch.object(T, "TIMEOUT", 0.5), \
             mock.patch.object(T.subprocess, "Popen", side_effect=observed_spawn), \
             mock.patch.object(T, "provenance", return_value=({"reviewedSourceSha": "a" * 40}, VALIDATOR)), \
             mock.patch.object(T, "configuration", return_value=self.root / "config"), \
             mock.patch.dict(os.environ, {"STAGING_SUDO_PASSWORD": PASSWORD, "GH_TOKEN": "private", "UNRELATED_SECRET": "private"}), \
             mock.patch.object(sys, "argv", [str(SCRIPT)]), contextlib.redirect_stdout(out):
            result = T.main()
            self.assertNotIn("STAGING_SUDO_PASSWORD", os.environ)
        text = out.getvalue()
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn("PRIVATE_PROVIDER_TEXT", text)
        self.assertEqual(len(streams), 1)
        if mode in ("host", "address", "user", "unknown_preflight", "duplicate_preflight", "missing_preflight", "timeout", "oversize", "stderr_oversize"):
            streams[0].write.assert_not_called()
        else:
            streams[0].write.assert_called_once_with((PASSWORD + "\n").encode())
        if observations.exists():
            observed = json.loads(observations.read_text().splitlines()[-1])
            self.assertFalse(observed["early"])
            self.assertFalse(observed["environment"])
            self.assertFalse(observed["arguments"])
        else:
            observed = None
        return result, json.loads(text), observed

    def test_real_child_receives_password_only_after_valid_target_once_and_eof(self):
        code, report, observed = self.invoke("ok")
        self.assertEqual(code, 0)
        self.assertEqual(report["report"], {"safe": True, "status": "observed-local-consistency"})
        self.assertEqual(report["collectionResult"], "complete")
        self.assertTrue(observed["once"])

    def test_validated_partial_evidence_is_retained_without_success_claim(self):
        code, report, observed = self.invoke("partial")
        self.assertEqual(code, 0)
        self.assertEqual(report["collectionResult"], "partial")
        self.assertEqual(report["report"]["status"], "unverified")
        self.assertTrue(observed["once"])

    def test_wrong_or_unknown_preflight_never_receives_password(self):
        for mode in ("host", "address", "user", "unknown_preflight", "duplicate_preflight", "missing_preflight"):
            with self.subTest(mode=mode):
                code, report, observed = self.invoke(mode)
                self.assertEqual(code, 1)
                self.assertEqual(report, {"transportStatus": "unverified", "failureStage": "preflight"})
                self.assertFalse(observed["once"])

    def test_report_errors_output_caps_timeout_and_child_failure_are_sanitized(self):
        for mode in ("bad_json", "unknown_report", "failure", "oversize", "stderr_oversize", "timeout",
                     "wrong_exit_zero", "wrong_exit_one", "invocation"):
            with self.subTest(mode=mode):
                code, report, _ = self.invoke(mode)
                self.assertEqual(code, 1)
                self.assertEqual(report["transportStatus"], "unverified")
                self.assertIn(report["failureStage"], ("preflight", "transport", "output", "remote-command"))

    def test_missing_invalid_password_and_arguments_create_no_child(self):
        for secret in (None, "", "x\n", "x\r", "x\x00", "x" * 4097):
            with self.subTest(secret=repr(secret)[:20]), mock.patch.object(T.os, "environ", {}), \
                 mock.patch.object(T, "provenance", return_value=({}, VALIDATOR)), \
                 mock.patch.object(T.subprocess, "Popen") as child, \
                 mock.patch.object(sys, "argv", [str(SCRIPT)]), contextlib.redirect_stdout(io.StringIO()) as out:
                if secret is not None:
                    os.environ["STAGING_SUDO_PASSWORD"] = secret
                self.assertEqual(T.main(), 1)
                child.assert_not_called()
                self.assertEqual(json.loads(out.getvalue()), {"transportStatus": "unverified", "failureStage": "secret"})
        with mock.patch.dict(os.environ, {"STAGING_SUDO_PASSWORD": PASSWORD}), \
             mock.patch.object(T.subprocess, "Popen") as child, \
             mock.patch.object(sys, "argv", [str(SCRIPT), "unexpected"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(T.main(), 1)
            child.assert_not_called()

    def source_fixture(self):
        for name, content in ((T.RUNNER, SCRIPT.read_bytes()), (T.COLLECTOR, VALIDATOR.encode())):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
        sha = git("rev-parse", "HEAD")
        return {"GITHUB_REPOSITORY": "olivium-dev/jeeb-infrastructure", "GITHUB_REF": "refs/heads/main",
                "SOURCE_REF_PROTECTED": "true", "SOURCE_DEFAULT_BRANCH": "main", "PROTECTED_INGRESS": "true",
                "GITHUB_ACTOR": "oudaykhaled", "GITHUB_TRIGGERING_ACTOR": "oudaykhaled",
                "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_RUN_ID": "123456", "GITHUB_SHA": sha, "REVIEWED_SHA": sha}

    def test_provenance_binds_actual_head_and_both_exact_source_files(self):
        env = self.source_fixture()
        with mock.patch.object(T, "ROOT", self.root), mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(T, "COLLECTOR_SHA256", hashlib.sha256(VALIDATOR.encode()).hexdigest()):
            metadata, source = T.provenance()
            self.assertEqual(metadata["reviewedSourceSha"], env["GITHUB_SHA"])
            self.assertEqual(source, VALIDATOR)
            for key in env:
                with self.subTest(key=key), mock.patch.dict(os.environ, {key: "wrong"}):
                    with self.assertRaises(T.TransportError):
                        T.provenance()
            for name in (T.RUNNER, T.COLLECTOR):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.assertRaises(T.TransportError):
                    T.provenance()
                path.write_bytes(original)
            with mock.patch.object(T, "COLLECTOR_SHA256", "0" * 64):
                with self.assertRaises(T.TransportError):
                    T.provenance()

    def test_source_failure_precedes_secret_use_and_never_starts_ssh(self):
        with mock.patch.dict(os.environ, {"STAGING_SUDO_PASSWORD": PASSWORD}), \
             mock.patch.object(T, "provenance", side_effect=ValueError("PRIVATE_PROVIDER_TEXT")) as source, \
             mock.patch.object(T, "session") as session, mock.patch.object(T, "configuration") as config, \
             mock.patch.object(sys, "argv", [str(SCRIPT)]), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(T.main(), 1)
            source.assert_called_once()
            config.assert_not_called()
            session.assert_not_called()
            self.assertNotIn("STAGING_SUDO_PASSWORD", os.environ)
            self.assertEqual(json.loads(out.getvalue()), {"transportStatus": "unverified", "failureStage": "source"})
    def test_configuration_is_exact_and_rejects_overrides_or_wrong_target(self):
        directory = self.root / "jeeb-readiness-transport"
        directory.mkdir(mode=0o700)
        for name in ("key", "known_hosts", "config", "cloudflared"):
            path = directory / name
            path.write_text("fixture")
            path.chmod(0o700 if name == "cloudflared" else 0o600)
        config = "\n".join(["Host jeeb-staging-readiness", "  HostName jeeb-staging-ssh.fds-1.com",
            "  User ec2-user", f"  IdentityFile {directory}/key", f"  UserKnownHostsFile {directory}/known_hosts",
            f"  ProxyCommand {directory}/cloudflared access ssh --hostname %h", "  IdentitiesOnly yes",
            "  BatchMode yes", "  StrictHostKeyChecking yes", "  ConnectTimeout 20",
            "  ServerAliveInterval 10", "  ServerAliveCountMax 2"]) + "\n"
        with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(self.root)}), \
             mock.patch.object(T, "CLOUDFLARED_SHA256", hashlib.sha256(b"fixture").hexdigest()):
            (directory / "config").write_text(config)
            self.assertEqual(T.configuration(), directory / "config")
            for invalid in (config + "Include /tmp/other\n", config.replace("ec2-user", "root"),
                            config.replace("StrictHostKeyChecking yes", "StrictHostKeyChecking no"),
                            config.replace("fds-1.com", "invalid.test")):
                (directory / "config").write_text(invalid)
                with self.assertRaises(T.TransportError):
                    T.configuration()
            (directory / "config").write_text(config)
            (directory / "key").chmod(0o644)
            with self.assertRaises(T.TransportError):
                T.configuration()


if __name__ == "__main__":
    unittest.main()
