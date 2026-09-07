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
                            body = {"ApiVersion": maximum, "MinAPIVersion": minimum, "private": "private-sentinel"}
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
                    self.assertEqual(minimum == "1.24", report["api_1_41_supported"])
                    self.assertTrue(report["auth_shapes"]["um"]["designated_username_matches"])
                    self.assertTrue(report["auth_shapes"]["otp"]["password_present"])

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
        for path in ("/services/create", "/v1.41/services/example/update", "/containers/create", "/info?other=1"):
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
