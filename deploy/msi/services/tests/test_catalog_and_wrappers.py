"""Pure local catalog/CLI checks. No host connections or application startup."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "jeeb-gateway", "jeeb-state-service", "user-management", "one-time-password", "wallet-service",
    "feedback-service", "remote-user-preferences", "ban-service", "kyc-service", "notification-service",
    "push-notification", "chat-service", "cdn-service", "geolocation-service", "delivery-service", "offer-service",
    "heart-beat", "settlement-service", "bundler-service", "realtime-comunication-service",
    "voice-transcription-service", "contract-signing-service", "form-builder-service", "compliment-service",
}
spec = importlib.util.spec_from_file_location("fleet_plan", ROOT / "plan_all.py")
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


class CatalogAndWrapperTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "service-catalog.json").read_text())

    def test_exact_active_fleet(self):
        entries = self.catalog["services"]
        self.assertEqual(24, len(entries))
        self.assertEqual(EXPECTED, {row["id"] for row in entries})
        self.assertEqual("ouday-GT70-2OC-2OD", self.catalog["host"]["hostname"])
        self.assertEqual("192.168.2.39", self.catalog["host"]["ipv4"])

    def test_dependency_order_is_complete_and_gateway_last(self):
        ordered = planner.ordered_services(self.catalog)
        seen = set()
        for entry in ordered:
            self.assertTrue(set(entry.get("depends_on", [])) <= seen)
            seen.add(entry["id"])
        self.assertEqual(EXPECTED, seen)
        self.assertEqual("jeeb-gateway", ordered[-1]["id"])

    def test_unknown_dependencies_and_cycles_fail(self):
        for entries in ([{"id": "a", "depends_on": ["missing"]}],
                        [{"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": ["a"]}],
                        [{"id": "a"}, {"id": "a"}]):
            with self.assertRaises(ValueError):
                planner.ordered_services({"services": entries})

    def test_every_service_has_only_its_own_explicit_wrapper(self):
        for service in sorted(EXPECTED):
            script = ROOT / "scripts" / (service + ".sh")
            source = script.read_text()
            self.assertIn('--service "' + service + '" "$@"', source)
            self.assertEqual(0, subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode)

    def test_every_wrapper_defaults_to_its_own_offline_plan(self):
        for service in sorted(EXPECTED):
            with self.subTest(service=service):
                result = subprocess.run([str(ROOT / "scripts" / (service + ".sh"))],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)
                plan = json.loads(result.stdout)
                self.assertEqual("plan", plan["action"])
                self.assertEqual(service, plan["service"]["id"])
                self.assertFalse(plan["host_operations"])

    def test_documented_service_table_matches_catalog(self):
        documentation = (ROOT / "README.md").read_text()
        for row in self.catalog["services"]:
            with self.subTest(service=row["id"]):
                lines = [line for line in documentation.splitlines()
                         if line.startswith("| `" + row["id"] + ".sh` |")]
                self.assertEqual(1, len(lines))
                self.assertIn("`" + row["unit"] + "`", lines[0])
                self.assertIn("| " + str(row["port"]) + " |", lines[0])
                self.assertTrue(lines[0].endswith("| " + row["probe"]["strength"].title() + " |"))

    def test_fleet_plan_is_local_in_normal_and_optimized_python(self):
        for flags in ([], ["-O"]):
            result = subprocess.run([sys.executable, *flags, "-I", str(ROOT / "plan_all.py")],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(24, report["serviceCount"])
            self.assertFalse(report["hostAccessed"])
            self.assertFalse(report["deploymentPerformed"])

    def test_user_managers_and_voice_route_are_not_guessed(self):
        services = {row["id"]: row for row in self.catalog["services"]}
        for service, user, uid, unit in (("remote-user-preferences", "ec2-user", 1001, "jeeb-rup.service"),
                                         ("settlement-service", "ouday", 1000, "settlement-service.service")):
            row = services[service]
            self.assertEqual(unit, row["unit"])
            self.assertEqual({"scope": "user", "user": user, "uid": uid}, row["manager"])
        self.assertEqual("jeeb-voice-candidate.service", services["voice-transcription-service"]["unit"])
        self.assertEqual(10063, services["voice-transcription-service"]["port"])
        self.assertEqual(11058, services["bundler-service"]["port"])

    def test_weak_health_contracts_stay_weak(self):
        services = {row["id"]: row for row in self.catalog["services"]}
        for service in ("feedback-service", "remote-user-preferences", "form-builder-service"):
            self.assertEqual("documentation", services[service]["probe"]["strength"])
        self.assertEqual("liveness", services["cdn-service"]["probe"]["strength"])
        self.assertEqual("/health/live", services["cdn-service"]["probe"]["path"])


if __name__ == "__main__":
    unittest.main()
