import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy/staging/scripts/readiness-inventory.py"
spec = importlib.util.spec_from_file_location("readiness_inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)
CANARY = "private-token-DO-NOT-OUTPUT"


def service(name="jeeb-staging-form-builder-service"):
    return {"Spec": {"Name": name, "Mode": {"Replicated": {"Replicas": 1}},
                     "TaskTemplate": {"ContainerSpec": {
                         "Image": "ghcr.io/olivium-dev/form-builder-service@sha256:" + "a" * 64,
                         "Env": ["DATABASE_URL=postgresql://user:" + CANARY + "@192.168.2.20:5432/jeeb_form_builder_staging",
                                 "SENTRY_DSN=" + CANARY,
                                 "UNRELATED_PASSWORD=" + CANARY],
                         "Mounts": []},
                         "LogDriver": {"Name": "json-file", "Options": {"max-size": "10m", "max-file": "3"}}}}}


class InventoryTests(unittest.TestCase):
    def test_secrets_are_projected_to_booleans(self):
        output = inventory.sanitize_service("jeeb-staging-form-builder-service", service())
        serialized = json.dumps(output)
        self.assertNotIn(CANARY, serialized)
        self.assertNotIn("UNRELATED_PASSWORD", serialized)
        self.assertTrue(output["telemetry_configured"]["SENTRY_DSN"])
        self.assertFalse(output["telemetry_configured"]["OTEL_SERVICE_NAME"])
        self.assertTrue(output["builder"]["database_host_matches_staging"])
        self.assertTrue(output["builder"]["database_name_matches_staging"])

    def test_individual_database_configuration_has_runtime_precedence(self):
        raw = service()
        raw["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"] += [
            "DB_HOST=production.invalid", "DB_NAME=production", "DB_USERNAME=user", "DB_PASSWORD=" + CANARY]
        result = inventory.sanitize_service("jeeb-staging-form-builder-service", raw)["builder"]
        self.assertEqual(result["database_source"], "individual")
        self.assertFalse(result["database_host_matches_staging"])
        self.assertFalse(result["database_name_matches_staging"])
        self.assertNotIn("production", json.dumps(result))

    def test_malformed_database_url_fails_closed_without_disclosure(self):
        for value in ("postgresql://[bad", "sqlite:///:memory:", "https://192.168.2.20/jeeb_form_builder_staging"):
            result = inventory.builder_contract({"DATABASE_URL": value}, {})
            self.assertFalse(result["database_host_matches_staging"])

    def test_duplicate_runtime_key_is_rejected(self):
        with self.assertRaises(inventory.DiagnosticError):
            inventory.environment(["DATABASE_URL=a", "DATABASE_URL=" + CANARY])

    def test_mount_sources_and_unknown_template_names_are_never_emitted(self):
        result = inventory.builder_contract({"TEMPLATE_JSON_FILES": "jeeb_kyc_form_builder.json," + CANARY}, {
            "Mounts": [{"Target": "/app", "Source": "/private/" + CANARY, "Type": "bind"},
                       {"Target": "/private/" + CANARY, "Source": CANARY}]})
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertTrue(result["unknown_template_present"])
        self.assertTrue(result["other_mount_present"])
        self.assertFalse(result["relevant_mounts"][0]["source_is_scoped_staging_path"])

    def test_untrusted_image_state_replica_and_flags_do_not_escape(self):
        raw = service()
        raw["Spec"]["Mode"]["Replicated"]["Replicas"] = CANARY
        raw["UpdateStatus"] = {"State": CANARY}
        raw["Spec"]["TaskTemplate"]["ContainerSpec"]["Image"] = CANARY
        raw["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"].append("PUSH_AUTH_MODE=" + CANARY)
        result = inventory.sanitize_service("jeeb-staging-form-builder-service", raw)
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertIsNone(result["image"])
        self.assertEqual(result["flags"]["PUSH_AUTH_MODE"], "invalid")

    def test_service_identity_mismatch_is_rejected(self):
        with self.assertRaises(inventory.DiagnosticError):
            inventory.sanitize_service("jeeb-staging-form-builder-service", service(CANARY))

    def test_wrong_hostname_stops_before_docker_or_http(self):
        with patch.object(inventory, "command", return_value="production\n") as cmd:
            with self.assertRaises(inventory.DiagnosticError):
                inventory.collect()
        self.assertEqual(cmd.call_args_list[0].args[0], ["hostname", "-s"])
        self.assertEqual(cmd.call_count, 1)

    def test_wrong_ip_stops_before_docker_or_http(self):
        with patch.object(inventory, "command", return_value="olivium-ephemerals\n") as cmd, \
             patch.object(inventory, "structured", return_value=[{"addr_info": [{"local": "192.168.2.50"}]}]):
            with self.assertRaises(inventory.DiagnosticError):
                inventory.collect()
        self.assertEqual(cmd.call_count, 1)

    def test_top_level_failure_never_serializes_exception(self):
        output = io.StringIO()
        with patch.object(inventory.sys, "argv", ["-"]), \
             patch.object(inventory, "collect", side_effect=ValueError(CANARY)), redirect_stdout(output):
            self.assertEqual(inventory.main(), 1)
        self.assertNotIn(CANARY, output.getvalue())

    def test_no_command_inputs(self):
        with patch.object(inventory.sys, "argv", ["-", "--command", CANARY]), \
             patch.object(inventory, "collect") as collect, redirect_stdout(io.StringIO()):
            self.assertEqual(inventory.main(), 1)
        collect.assert_not_called()

    def test_redirects_are_not_followed(self):
        self.assertIsNone(inventory.NoRedirect().redirect_request(None, None, 302, "", {}, "http://other/"))

    def test_live_metrics_emit_only_counts_not_labels(self):
        payload = {"status": "success", "data": {"result": [
            {"metric": {"secret_label": CANARY}, "value": [123, "1"]},
            {"metric": {"secret_label": CANARY}, "value": [123, "0"]}]}}
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps(payload).encode()
        with patch.object(inventory, "build_opener") as opener:
            opener.return_value.open.return_value = Response()
            result = inventory.http_probe(9090, "/api/v1/query?query=up", True)
        self.assertEqual(result, {"http_status": 200, "query_success": True, "sample_count": 2, "up_samples": 1})
        self.assertNotIn(CANARY, json.dumps(result))

    def test_workflow_has_protected_owner_scope_and_no_input_or_remote_mutation(self):
        source = (ROOT / ".github/workflows/jeeb-staging-readiness-inventory.yml").read_text()
        for expected in ("github.ref_protected", "github.actor == 'oudaykhaled'", "github.triggering_actor == 'oudaykhaled'",
                         "environment: staging", "StrictHostKeyChecking yes", "BatchMode yes",
                         "JEEB_STAGING_SSH_KNOWN_HOSTS", "python3 -", "permissions:\n  contents: read"):
            self.assertIn(expected, source)
        for forbidden in ("inputs:", "sudo ", "workflow_call:", "secrets: inherit", "docker service update", "scp "):
            self.assertNotIn(forbidden, source)

    def test_complete_inventory_uses_only_fixed_read_only_operations(self):
        calls = []
        def command(args):
            calls.append(args)
            if args == ["hostname", "-s"]:
                return "olivium-ephemerals\n"
            if args[:2] == ["ip", "-j"]:
                return json.dumps([{"addr_info": [{"local": "192.168.2.20"}]}])
            if args[:3] == ["docker", "service", "ls"]:
                return "jeeb-staging-form-builder-service\nprometheus\n" + CANARY + "\n"
            if args[:3] == ["docker", "network", "inspect"]:
                return json.dumps([{"Driver": "overlay", "Attachable": True, "Options": {"encrypted": ""}}])
            if args[:3] == ["docker", "service", "inspect"]:
                return json.dumps([service(args[-1])])
            if args[:3] == ["docker", "service", "ps"]:
                return "Running 3 minutes ago\n"
            if args[:2] == ["docker", "ps"]:
                return "grafana\n" + CANARY + "\n"
            if args[:2] == ["systemctl", "show"]:
                return "LoadState=not-found\nActiveState=inactive\n"
            raise AssertionError("Unexpected operation")
        with patch.object(inventory, "command", side_effect=command), \
             patch.object(inventory, "http_probe", return_value={"http_status": 401}):
            result = inventory.collect()
        self.assertEqual(len(result["services"]), 24)
        self.assertTrue(result["network"]["encrypted"])
        self.assertNotIn(CANARY, json.dumps(result))
        builder = next(row for row in result["services"] if row["name"] == "jeeb-staging-form-builder-service")
        self.assertEqual(builder["running_tasks"], 1)
        self.assertEqual(result["monitoring"]["grafana"]["matched_running_container_names"], ["grafana"])
        for args in calls:
            self.assertNotIn("sudo", args)
            self.assertNotIn("exec", args)
            self.assertNotIn("update", args)
            self.assertNotIn("logs", args)


if __name__ == "__main__":
    unittest.main()
