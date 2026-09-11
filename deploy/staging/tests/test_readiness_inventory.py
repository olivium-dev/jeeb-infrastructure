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
    return {"ID": "s" * 25, "Spec": {"Name": name, "Mode": {"Replicated": {"Replicas": 1}},
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

    def test_builder_partial_components_and_absent_runtime_shape_are_not_defaults(self):
        result = inventory.builder_contract({"DB_PASSWORD": CANARY, "DB_PORT": "5432"}, {})
        self.assertEqual(result["database_components_nonempty"], {
            "DB_HOST": False, "DB_NAME": False, "DB_USERNAME": False,
            "DB_PASSWORD": True, "DB_PORT": True})
        self.assertEqual(result["database_source"], "DATABASE_URL")
        self.assertFalse(any(result["runtime_property_present"].values()))
        for key in ("command_matches_docker_cmd", "args_matches_docker_cmd", "dir_matches_docker_workdir"):
            self.assertIsNone(result[key])
        self.assertNotIn(CANARY, json.dumps(result))

    def test_builder_materialized_command_args_and_dir_defaults(self):
        default = ["python", "-m", "app.main", "--host", "0.0.0.0", "--port", "8000"]
        for property_name, match_key in (("Command", "command_matches_docker_cmd"), ("Args", "args_matches_docker_cmd")):
            result = inventory.builder_contract({}, {property_name: default, "Dir": "/app"})
            self.assertTrue(result["runtime_property_present"][property_name])
            self.assertTrue(result[match_key])
            self.assertTrue(result["dir_matches_docker_workdir"])
            self.assertNotIn("0.0.0.0", json.dumps(result))

    def test_builder_runtime_config_metadata_never_exposes_values_names_or_paths(self):
        container = {"Mounts": [{"Target": CANARY, "Source": CANARY}],
                     "Configs": [{"ConfigName": CANARY}], "Secrets": [{"SecretName": CANARY}],
                     "Command": [CANARY], "Args": [CANARY], "Dir": CANARY}
        result = inventory.builder_contract({"DB_PASSWORD": CANARY}, container)
        self.assertTrue(all(result["runtime_property_present"].values()))
        for key in ("command_matches_docker_cmd", "args_matches_docker_cmd", "dir_matches_docker_workdir"):
            self.assertFalse(result[key])
        self.assertNotIn(CANARY, json.dumps(result))

    def test_builder_component_nonempty_matches_python_environment_truthiness(self):
        # Partial whitespace components are still nonempty to the runtime's all().
        result = inventory.builder_contract({"DB_HOST": " ", "DB_PASSWORD": ""}, {})
        self.assertTrue(result["database_components_nonempty"]["DB_HOST"])
        self.assertFalse(result["database_components_nonempty"]["DB_PASSWORD"])

    def test_malformed_database_url_fails_closed_without_disclosure(self):
        for value in ("postgresql://[bad", "sqlite:///:memory:", "https://192.168.2.20/jeeb_form_builder_staging"):
            result = inventory.builder_contract({"DATABASE_URL": value}, {})
            self.assertFalse(result["database_host_matches_staging"])

    def test_postgres_query_routing_cannot_masquerade_as_staging(self):
        base = "postgresql://user:password@192.168.2.20:5432/jeeb_form_builder_staging"
        for query in ("host=other", "port=5433", "dbname=other", "database=other", "service=other",
                      "hostaddr=192.168.2.50", "host=192.168.2.20&host=other", "%68ost=other",
                      "options=other", "HOST=other", "unknown=other"):
            with self.subTest(query=query):
                result = inventory.builder_contract({"DATABASE_URL": base + "?" + query}, {})
                self.assertFalse(result["database_target_unambiguous"])
                self.assertIsNone(result["database_host_matches_staging"])
                self.assertIsNone(result["database_name_matches_staging"])

    def test_postgres_ports_fragments_and_absent_values_are_unknown(self):
        for value in ("", "postgresql://u:p@192.168.2.20:bad/jeeb_form_builder_staging",
                      "postgresql://u:p@192.168.2.20:0/jeeb_form_builder_staging",
                      "postgresql://u:p@192.168.2.20:65536/jeeb_form_builder_staging",
                      "postgresql://u:p@192.168.2.20:/jeeb_form_builder_staging",
                      "postgresql://u:p@192.168.2.20/jeeb_form_builder_staging#other"):
            result = inventory.builder_contract({"DATABASE_URL": value}, {})
            self.assertFalse(result["database_target_unambiguous"])
            self.assertIsNone(result["database_host_matches_staging"])
        different_port = inventory.builder_contract({"DATABASE_URL": "postgresql://u:p@192.168.2.20:5433/jeeb_form_builder_staging"}, {})
        self.assertTrue(different_port["database_target_unambiguous"])
        self.assertFalse(different_port["database_port_matches_staging"])

    def test_database_percent_encoding_matches_sqlalchemy_2027_literal_behavior(self):
        result = inventory.builder_contract({"DATABASE_URL": "postgresql://u:p@192.168.2.20/jeeb%5fform_builder_staging"}, {})
        self.assertTrue(result["database_target_unambiguous"])
        self.assertFalse(result["database_name_matches_staging"])

    def test_nonrouting_postgres_query_preserves_attestation(self):
        result = inventory.builder_contract({"DATABASE_URL": "postgresql://u:p@192.168.2.20/jeeb_form_builder_staging?sslmode=require&connect_timeout=5"}, {})
        self.assertTrue(result["database_target_unambiguous"])
        self.assertTrue(result["database_port_matches_staging"])

    def test_individual_bad_port_or_unescaped_credentials_are_unknown(self):
        base = {"DB_HOST": "192.168.2.20", "DB_NAME": "jeeb_form_builder_staging", "DB_USERNAME": "user", "DB_PASSWORD": "secret"}
        for update in ({"DB_PORT": "bad"}, {"DB_PORT": "0"}, {"DB_PASSWORD": "contains@host"}):
            result = inventory.builder_contract({**base, **update}, {})
            self.assertFalse(result["database_target_unambiguous"])
            self.assertIsNone(result["database_host_matches_staging"])

    def test_cdn_exact_mount_and_absent_config_are_not_inferred(self):
        result = inventory.cdn_contract({}, {"Mounts": [{"Type": "bind", "Source": "/opt/jeeb-staging-cdn/uploads", "Target": "/app/uploads"}]})
        self.assertTrue(result["exact_upload_bind_mount"])
        self.assertIsNone(result["storage_provider_is_local"])
        self.assertIsNone(result["storage_path_matches_mount"])
        self.assertFalse(result["additional_config_or_command_override"])
        for override in ({"Args": [CANARY]}, {"Command": [CANARY]}, {"Configs": [{"name": CANARY}]},
                         {"Mounts": [{"Target": CANARY}]}):
            result = inventory.cdn_contract({}, override)
            self.assertTrue(result["additional_config_or_command_override"])
            self.assertNotIn(CANARY, json.dumps(result))
        for mounts in ([], [{"Type": "bind", "Source": CANARY, "Target": "/app/uploads"}],
                       [{"Type": "bind", "Source": "/opt/jeeb-staging-cdn/uploads", "Target": "/app/uploads", "ReadOnly": True}]):
            result = inventory.cdn_contract({}, {"Mounts": mounts})
            self.assertIsNot(result["exact_upload_bind_mount"], True)
            self.assertNotIn(CANARY, json.dumps(result))

    def test_heartbeat_redis_query_overrides_and_malformed_ports_are_unknown(self):
        base = "redis://user:" + CANARY + "@192.168.2.20:6379/4"
        good = inventory.heartbeat_contract({"REDIS_URL": base})
        self.assertTrue(good["redis_database_matches_staging"])
        self.assertTrue(good["redis_host_matches_staging"])
        self.assertNotIn(CANARY, json.dumps(good))
        for value in ("", base + "?db=0", base + "?%64b=0", base + "#other", "redis://192.168.2.20:bad/4", "redis://192.168.2.20:0/4"):
            result = inventory.heartbeat_contract({"REDIS_URL": value})
            self.assertFalse(result["redis_target_unambiguous"])
            self.assertIsNone(result["redis_database_matches_staging"])

    def test_gateway_actual_otel_key_is_boolean_only(self):
        raw = service("jeeb-staging-jeeb-gateway")
        raw["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"].append("Otel__Endpoint=" + CANARY)
        result = inventory.sanitize_service("jeeb-staging-jeeb-gateway", raw)
        self.assertTrue(result["telemetry_configured"]["Otel__Endpoint"])
        self.assertNotIn(CANARY, json.dumps(result))

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

    def test_tagged_digest_is_canonicalized_without_emitting_tag(self):
        base = "ghcr.io/olivium-dev/offer-service"
        digest = "@sha256:" + "a" * 64
        self.assertEqual(inventory.safe_image(base + ":" + CANARY + digest), base + digest)
        for value in (base + ":latest", base + ":bad/tag" + digest,
                      "ghcr.io/other/offer-service" + digest,
                      "ghcr.io/olivium-dev/unknown-service" + digest):
            self.assertIsNone(inventory.safe_image(value))

    def task_contract(self, updates=None, count=1, expected=None):
        name = "jeeb-staging-form-builder-service"
        entry = inventory.sanitize_service(name, service())
        if expected is not None:
            entry.update(expected)
        task = {"Name": name + ".1", "DesiredState": "Running",
                "CurrentState": "Running 3 minutes ago", "Image": entry["image"],
                "Error": CANARY, "Node": CANARY, "ID": CANARY}
        task.update(updates or {})
        return inventory.task_image_contract(name, entry, [json.dumps(task)] * count)

    def test_running_task_digest_matches_without_raw_task_details(self):
        result = self.task_contract()
        self.assertTrue(result["running_task_images_match_service_spec"])
        self.assertEqual(result["running_tasks"], 1)
        self.assertNotIn(CANARY, json.dumps(result))

    def test_task_attestation_never_accepts_mismatch_absence_or_transition(self):
        for updates in ({"Image": "ghcr.io/olivium-dev/form-builder-service@sha256:" + "b" * 64},
                        {"Image": CANARY}, {"CurrentState": "Starting 1 second ago"}):
            self.assertFalse(self.task_contract(updates)["running_task_images_match_service_spec"])
        self.assertFalse(self.task_contract(count=0)["running_task_images_match_service_spec"])
        self.assertFalse(self.task_contract(expected={"image": None})["running_task_images_match_service_spec"])

    def test_task_identity_and_malformed_payloads_fail_closed(self):
        with self.assertRaises(inventory.DiagnosticError):
            self.task_contract(count=2, expected={"desired_replicas": 2})
        for updates in ({"Name": CANARY}, {"DesiredState": "Shutdown"}, {"CurrentState": None}):
            with self.assertRaises(inventory.DiagnosticError):
                self.task_contract(updates)
        for raw in (CANARY, "null", "[]"):
            with self.assertRaises(inventory.DiagnosticError):
                inventory.task_image_contract("jeeb-staging-form-builder-service", {}, [raw])

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

    def test_workflow_has_protected_owner_scope_and_only_reviewed_opt_in(self):
        source = (ROOT / ".github/workflows/jeeb-staging-readiness-inventory.yml").read_text()
        for expected in ("github.ref_protected", "github.actor == 'oudaykhaled'", "github.triggering_actor == 'oudaykhaled'",
                         "environment: staging", "StrictHostKeyChecking yes", "BatchMode yes",
                         "JEEB_STAGING_SSH_KNOWN_HOSTS", "python3 -", "permissions:\n  contents: read"):
            self.assertIn(expected, source)
        self.assertIn("protected_ingress:\n", source)
        self.assertIn("type: boolean\n        required: false\n        default: false", source)
        self.assertIn("reviewed_sha:\n", source)
        self.assertEqual(source.count("secrets.MSI_SSH_PASSWORD"), 1)
        secret_step = source.split("      - name: Collect opt-in protected ingress evidence\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("if: ${{ inputs.protected_ingress }}", secret_step)
        self.assertIn("STAGING_SUDO_PASSWORD: ${{ secrets.MSI_SSH_PASSWORD }}", secret_step)
        self.assertNotIn("STAGING_SUDO_PASSWORD", source.split("      - name: Collect opt-in protected ingress evidence\n", 1)[0])
        for forbidden in ("sudo ", "workflow_call:", "secrets: inherit", "docker service update", "scp "):
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
                self.assertIn("--no-trunc", args)
                self.assertEqual(args[-1], "{{json .}}")
                return json.dumps({"ID": "t" * 25, "Name": args[3] + ".1", "DesiredState": "Running",
                                   "CurrentState": "Running 3 minutes ago",
                                   "Image": service()["Spec"]["TaskTemplate"]["ContainerSpec"]["Image"],
                                   "Error": CANARY}) + "\n"
            if args[:2] == ["docker", "inspect"]:
                raise inventory.DiagnosticError("fixed read-only command unavailable")
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
        self.assertTrue(builder["running_task_images_match_service_spec"])
        self.assertEqual(result["monitoring"]["grafana"]["matched_running_container_names"], ["grafana"])
        for args in calls:
            self.assertNotIn("sudo", args)
            self.assertNotIn("exec", args)
            self.assertNotIn("update", args)
            self.assertNotIn("logs", args)


class OfferLocalImageTests(unittest.TestCase):
    def setUp(self):
        self.raw = service("jeeb-staging-offer-service")
        self.raw["Spec"]["TaskTemplate"]["ContainerSpec"]["Image"] = "offer:" + CANARY
        self.entry = inventory.sanitize_service("jeeb-staging-offer-service", self.raw)
        self.rows = [json.dumps({"ID": "t" * 25, "Name": "jeeb-staging-offer-service.1",
                                "DesiredState": "Running", "CurrentState": "Running 2 minutes ago"})]
        self.task = {"id": "t" * 25, "service": "s" * 25, "desired": "running", "state": "running",
                     "container": "c" * 64, "image": "offer:" + CANARY}
        self.container = {"id": "c" * 64, "running": True, "image": "sha256:" + "a" * 64,
                          "task": "t" * 25, "service": "s" * 25}
        self.digest = "ghcr.io/olivium-dev/offer-service@sha256:" + "b" * 64
        self.image = {"id": "sha256:" + "a" * 64, "digests": [self.digest, "other/" + CANARY]}

    def run_probe(self, values=None):
        values = values if values is not None else [self.task, self.container, self.image, self.task, self.container]
        outputs = [value if isinstance(value, Exception) else json.dumps(value) for value in values]
        with patch.object(inventory, "command", side_effect=outputs) as command:
            result = inventory.offer_local_image(self.raw, self.entry, self.rows)
        self.assertNotIn(CANARY, json.dumps(result))
        for call in command.call_args_list:
            args = call.args[0]
            self.assertEqual(args[:3], ["docker", "inspect", "--type"])
            self.assertIn(args[-1], ("t" * 25, "c" * 64, "sha256:" + "a" * 64))
            self.assertNotIn(CANARY, " ".join(args))
        return result

    def test_resolves_tag_only_task_without_disclosing_tag_or_other_digests(self):
        self.assertEqual(self.run_probe(), {"verified": True, "image": self.digest})

    def test_nonlocal_or_disappeared_container_remains_unknown(self):
        unavailable = inventory.DiagnosticError("fixed read-only command unavailable")
        self.assertEqual(self.run_probe([self.task, unavailable]), {"verified": False, "image": None})

    def test_unknown_or_ambiguous_repo_digests_remain_unknown(self):
        for digests in (None, [], [CANARY], [self.digest, self.digest[:-1] + "c"], [123]):
            self.image["digests"] = digests
            self.assertFalse(self.run_probe()["verified"])

    def test_identity_and_cardinality_fail_before_engine_derived_followups(self):
        for field, value in (("id", CANARY), ("service", CANARY), ("container", "--" + CANARY)):
            original = self.task[field]
            self.task[field] = value
            with self.assertRaises(inventory.DiagnosticError):
                self.run_probe()
            self.task[field] = original
        for field in ("id", "task", "service", "image"):
            original = self.container[field]
            self.container[field] = CANARY
            with self.assertRaises(inventory.DiagnosticError):
                self.run_probe()
            self.container[field] = original
        for rows in ([], self.rows * 2):
            with patch.object(inventory, "command") as command:
                with self.assertRaises(inventory.DiagnosticError):
                    inventory.offer_local_image(self.raw, self.entry, rows)
                command.assert_not_called()

    def test_task_id_rejected_before_inspect(self):
        row = json.loads(self.rows[0])
        for key, value in (("ID", CANARY), ("Name", "jeeb-staging-offer-service.2")):
            invalid = dict(row, **{key: value})
            with patch.object(inventory, "command") as command:
                with self.assertRaises(inventory.DiagnosticError):
                    inventory.offer_local_image(self.raw, self.entry, [json.dumps(invalid)])
                command.assert_not_called()
        self.raw["ID"] = CANARY
        with patch.object(inventory, "command") as command:
            with self.assertRaises(inventory.DiagnosticError):
                inventory.offer_local_image(self.raw, self.entry, self.rows)
            command.assert_not_called()

    def test_transition_mismatch_and_race_are_not_attested(self):
        for change in ({"state": "starting"}, {"desired": "shutdown"}, {"image": CANARY}):
            self.assertFalse(self.run_probe([dict(self.task, **change)])["verified"])
        self.assertFalse(self.run_probe([self.task, dict(self.container, running=False)])["verified"])
        self.assertFalse(self.run_probe([self.task, self.container, self.image,
                                         dict(self.task, state="shutdown")])["verified"])

    def test_malformed_inspect_and_image_identity_fail_closed(self):
        for output in ([], "not-json-object", dict(self.image, id=CANARY)):
            with self.assertRaises(inventory.DiagnosticError):
                self.run_probe([self.task, self.container, output])

    def test_existing_immutable_reference_cannot_disagree_with_local_digest(self):
        reference = "ghcr.io/olivium-dev/offer-service@sha256:" + "d" * 64
        self.raw["Spec"]["TaskTemplate"]["ContainerSpec"]["Image"] = reference
        self.task["image"] = reference
        self.assertFalse(self.run_probe()["verified"])


if __name__ == "__main__":
    unittest.main()
