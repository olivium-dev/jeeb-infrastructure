import base64
import http.server
import importlib.util
import json
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "deploy/staging/scripts/cas-readonly-diagnostic.py"
SPEC = importlib.util.spec_from_file_location("cas_diagnostic", SOURCE)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


class CasReadonlyDiagnosticTests(unittest.TestCase):
    def test_runner_transport_is_exclusive_before_writing_credentials(self):
        workflow = (ROOT / ".github/workflows/jeeb-staging-cas-readonly-diagnostic.yml").read_text()
        setup = workflow.split('          transport="$RUNNER_TEMP/jeeb-cas-readonly-transport"', 1)[1]
        setup = 'transport="$RUNNER_TEMP/jeeb-cas-readonly-transport"\n' + setup.split("          curl ", 1)[0]
        for scenario in ("fresh", "existing", "symlink"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runner = root / "runner"
                runner.mkdir()
                transport = runner / "jeeb-cas-readonly-transport"
                if scenario == "existing":
                    transport.mkdir()
                elif scenario == "symlink":
                    transport.symlink_to(root, target_is_directory=True)
                result = subprocess.run(["bash", "-euc", setup], capture_output=True, text=True,
                                        env={"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(runner),
                                             "GITHUB_OUTPUT": str(root / "output")})
                self.assertEqual(scenario == "fresh", result.returncode == 0)
                self.assertEqual(scenario == "fresh", (root / "output").exists())
        self.assertIn("if: always() && steps.transport.outputs.created == 'true'", workflow)

    def test_real_unix_get_transport_and_safe_projection(self):
        for minimum, maximum in (("1.24", "1.47"), ("1.44", "1.47"), ("private-sentinel", "1.47")):
            with self.subTest(minimum=minimum), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                requests = []
                socket_path = str(home / "engine.sock")
                for value in diagnostic.PROFILES.values():
                    path = home / value
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"auths": {"ghcr.io": {"auth": base64.b64encode(
                        b"oudaykhaled:private-sentinel").decode()}}}))
                class Handler(http.server.BaseHTTPRequestHandler):
                    def log_message(self, *_):
                        pass
                    def do_GET(self):
                        requests.append(("GET", self.path))
                        if self.path == "/version":
                            body = {"ApiVersion": maximum, "MinAPIVersion": minimum,
                                    "Version": "29.0.0", "GitCommit": "abcdef123456",
                                    "private": "private-sentinel"}
                        else:
                            body = {"Name": "olivium-ephemerals", "Swarm": {
                                "NodeAddr": "192.168.2.20", "ControlAvailable": True, "LocalNodeState": "active"},
                                "private": "private-sentinel"}
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(json.dumps(body).encode())
                with socketserver.UnixStreamServer(socket_path, Handler) as server:
                    worker = threading.Thread(target=server.serve_forever, daemon=True)
                    worker.start()
                    try:
                        with patch.object(diagnostic, "SOCKET", socket_path), \
                             patch.object(diagnostic.socket, "gethostname", return_value="olivium-ephemerals"), \
                             patch.object(diagnostic.Path, "home", return_value=home):
                            report, status = diagnostic.collect()
                    finally:
                        server.shutdown()
                        worker.join()
                output = json.dumps(report)
                self.assertNotIn("private-sentinel", output)
                self.assertTrue(all(method == "GET" for method, _ in requests))
                if minimum == "private-sentinel":
                    self.assertEqual(1, status)
                    self.assertEqual("engine_version", report["phase"])
                else:
                    self.assertEqual(0, status)
                    self.assertEqual("29.0.0", report["engine_version"])
                    self.assertEqual("abcdef123456", report["engine_git_commit"])
                    self.assertEqual(minimum == "1.24", report["api_1_41_supported"])
                    self.assertTrue(report["auth_shapes"]["um"]["designated_username_matches"])
                    self.assertTrue(report["auth_shapes"]["otp"]["password_present"])

    def test_engine_identity_rejects_unbounded_or_private_text(self):
        for release in (None, 29, "", "private-sentinel", "29.0.0\nprivate-sentinel",
                        "29.0.0-" + "a" * 49):
            with self.subTest(release=release), self.assertRaises(ValueError):
                diagnostic.engine_source({"Version": release, "GitCommit": "abcdef1"})
        for commit in (None, 1234567, "", "private sentinel", "abcdef1\n", "a" * 101, "a/b", "a=secret"):
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                diagnostic.engine_source({"Version": "29.0.0", "GitCommit": commit})
        self.assertEqual({"engine_version": "29.0.0-rc.1", "engine_git_commit": "abcdef1"},
                         diagnostic.engine_source({"Version": "29.0.0-rc.1", "GitCommit": "abcdef1"}))

    def test_partial_identity_is_explicit_and_does_not_emit_unvalidated_field(self):
        report = {}
        with self.assertRaises(ValueError):
            diagnostic.engine_source({"Version": "29.0.0", "GitCommit": "private sentinel"}, report)
        self.assertEqual("29.0.0", report["engine_version"])
        self.assertFalse(report["engine_git_commit_valid"])
        self.assertNotIn("engine_git_commit", report)
        self.assertNotIn("private sentinel", json.dumps(report))

    def test_public_package_identity_is_distinct_from_pure_hex(self):
        for commit in ("29.1.3-0ubuntu1~24.04.1", "1:29.1.3+dfsg_1", "a" * 100):
            report = {}
            diagnostic.engine_source({"Version": "29.1.3", "GitCommit": commit}, report)
            self.assertEqual(commit, report["engine_git_commit"])
            self.assertFalse(report["engine_git_commit_valid"])
            self.assertTrue(report["engine_git_commit_package_shape_valid"])

    def test_paired_projection_is_fixed_and_does_not_emit_spec_or_secret_data(self):
        node, network, secret = "n" * 25, "k" * 25, "s" * 25
        calls = []
        def get(path):
            calls.append(path)
            if "/networks/" in path:
                value = {"Id": network, "Driver": "overlay", "Attachable": True, "Options": {"encrypted": ""}}
            elif "/secrets/" in path:
                value = {"ID": secret, "Spec": {"Name": "jeeb-staging-delivery-service-auth-v1",
                    "Data": "private-sentinel", "Labels": {"jeeb.environment": "staging",
                    "jeeb.purpose": "delivery-service-auth", "jeeb.version": "1"}}}
            elif "/images/" in path:
                value = {"Config": {"User": "appuser", "Entrypoint": ["dotnet", "JeebGateway.dll"],
                                    "Env": ["UNRELATED=private-sentinel"]}}
            else:
                gateway = path.endswith("jeeb-gateway")
                name = "jeeb-gateway" if gateway else "delivery-service"
                value = {"Spec": {"Name": "jeeb-staging-" + name, "Mode": {"Replicated": {"Replicas": 1}},
                    "UpdateConfig": {"FailureAction": "pause"}, "EndpointSpec": {"Ports": [{
                    "Protocol": "tcp", "TargetPort": 8080, "PublishedPort": 10000 if gateway else 10055,
                    "PublishMode": "ingress" if gateway else "host"}]}, "TaskTemplate": {
                    "Networks": [{"Target": network}], "Placement": {"Constraints": ["node.id == " + node]},
                    "ContainerSpec": {"Image": "ghcr.io/olivium-dev/" + name + "@sha256:" + "a" * 64,
                    "Env": ["Services__Delivery__BaseUrl=http://192.168.2.20:10055", "SKIP_DB_INIT=true",
                            "DATABASE_URL=private-sentinel"]}}}}
            return {"http_status": 200}, value
        with tempfile.TemporaryDirectory() as directory, patch.object(diagnostic, "get", side_effect=get), \
             patch.object(diagnostic.Path, "home", return_value=Path(directory)):
            result = diagnostic.paired_posture("1.52", {"Swarm": {"NodeID": node}})
        self.assertEqual(5, len(calls))
        self.assertTrue(result["expected_overlay"])
        self.assertTrue(result["services"]["gateway"]["pinned_actual_node"])
        self.assertTrue(result["services"]["gateway"]["delivery_url_matches"])
        self.assertTrue(result["services"]["gateway"]["entrypoint_matches"])
        self.assertTrue(result["services"]["delivery"]["skip_db_init_true"])
        for role in ("gateway", "delivery"):
            for field in ("no_mounts", "no_configs", "no_loader_environment_overrides"):
                self.assertTrue(result["services"][role][field])
        self.assertTrue(result["dedicated_secret"]["metadata_matches"])
        self.assertNotIn("private-sentinel", json.dumps(result))
        def overridden(path):
            transport, value = get(path)
            if "/services/" in path:
                container = value["Spec"]["TaskTemplate"]["ContainerSpec"]
                container.update(Mounts=[{"Target": "private-sentinel"}], Configs=[{"ConfigID": "private-sentinel"}])
                container["Env"].append("LD_PRELOAD=private-sentinel")
            return transport, value
        with tempfile.TemporaryDirectory() as directory, patch.object(diagnostic, "get", side_effect=overridden), \
             patch.object(diagnostic.Path, "home", return_value=Path(directory)):
            negative = diagnostic.paired_posture("1.52", {"Swarm": {"NodeID": node}})
        for role in ("gateway", "delivery"):
            for field in ("no_mounts", "no_configs", "no_loader_environment_overrides"):
                self.assertFalse(negative["services"][role][field])
        self.assertNotIn("private-sentinel", json.dumps(negative))

    def test_missing_or_malformed_profiles_disclose_only_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.assertFalse(diagnostic.auth_shape(path)["exists"])
            for body in ("not-json-private-sentinel", '[]', '{"auths":null}',
                         '{"auths":{"ghcr.io":{"auth":"private-sentinel"}}}'):
                path.write_text(body)
                report = diagnostic.auth_shape(path)
                self.assertNotIn("private-sentinel", json.dumps(report))
                self.assertTrue(all(isinstance(value, bool) for value in report.values()))

    def test_routes_are_get_only_and_workflow_is_protected(self):
        for path in ("/services/create", "/v1.41/services/example/update", "/containers/create", "/info?other=1",
                     "/v1.52/services/unrelated", "/v1.52/secrets/unrelated", "/v1.52/images/arbitrary/json"):
            with self.assertRaises(ValueError):
                diagnostic.get(path)
        text = SOURCE.read_text()
        self.assertEqual(1, text.count('connection.request("GET", path)'))
        self.assertNotIn('connection.request("POST"', text)
        self.assertNotIn("subprocess", text)
        workflow = (ROOT / ".github/workflows/jeeb-staging-cas-readonly-diagnostic.yml").read_text()
        for marker in ("github.ref_protected", "github.triggering_actor == 'oudaykhaled'",
                       "github.actor == 'oudaykhaled'", "StrictHostKeyChecking yes",
                       "cas-readonly-diagnostic.py", "python3 -I -"):
            self.assertIn(marker, workflow)
        for verb in ("docker service", "docker container", "docker secret", "docker network"):
            self.assertNotIn(verb, workflow)


if __name__ == "__main__":
    unittest.main()
