"""Offline catalog-to-engine probe compatibility and fail-closed regressions.

The generated cases prove that the catalog can be interpreted by the actual
probe parser. They do NOT independently validate an owner's source or live
response. The separate fixed fixtures below pin selected source-reviewed wire
contracts so changing both a catalog literal and its generated fixture cannot
silently weaken the gateway, canonical Firebase identity, or RUP gates.

Every HTTP response is synthetic. Network, subprocess and host-command access
are denied; no owner is launched, contacted or modified by this module.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "msi_service_probe_contracts_under_test", ROOT / "msi_deploy.py"
)
engine = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = engine
SPEC.loader.exec_module(engine)
CATALOG = json.loads((ROOT / "service-catalog.json").read_text())
ACTIVE = {row["id"]: row for row in CATALOG["services"]}
PRIVATE = copy.deepcopy(next(
    row for row in CATALOG["auxiliary"] if row["id"] == "cdn-private-artifacts"
))
# This optional owner has no selected live listener. A synthetic port makes the
# fixture explicit without inventing a deployable catalog assignment.
PRIVATE["port"] = 18080
PROFILES = [*CATALOG["services"], PRIVATE]


def set_field(body, dotted_key, value=None, *, delete=False, only_missing=False):
    parts = dotted_key.split(".")
    node = body
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    if delete:
        del node[parts[-1]]
    elif not only_missing or parts[-1] not in node:
        node[parts[-1]] = value


def compatibility_body(profile):
    """Construct parser input from catalog constraints, not a live fixture."""
    probe = profile["probe"]
    if probe["kind"] == "text":
        return probe["text"]
    if probe["kind"] != "json" or not probe.get("equals"):
        raise ValueError("A JSON profile must have nonempty exact literals: " + profile["id"])
    body = {}
    for key, value in probe["equals"].items():
        set_field(body, key, copy.deepcopy(value))
    for key in probe.get("required_keys", []):
        set_field(body, key, {}, only_missing=True)
    for key in probe.get("required_true", []):
        set_field(body, key, True)
    for key, minimum in probe.get("numeric_min", {}).items():
        set_field(body, key, minimum)
    return body


def compatibility_cases():
    cases = []
    for profile in PROFILES:
        body = compatibility_body(profile)
        prefix = profile["id"]
        cases.append((prefix + "__accepted", profile, body, True, 200, False))
        cases.append((prefix + "__http_503", profile, body, False, 503, False))
        cases.append((prefix + "__oversized_body", profile, body, False, 200, True))
        if isinstance(body, str):
            cases.append((prefix + "__degraded_text", profile, "Degraded", False, 200, False))
            continue
        probe = profile["probe"]
        for key in probe["equals"]:
            invalid = copy.deepcopy(body)
            set_field(invalid, key, "wrong-literal")
            cases.append((prefix + "__wrong_" + key, profile, invalid, False, 200, False))
        for key in probe.get("required_true", []):
            invalid = copy.deepcopy(body)
            # Python considers 1 == True: the gate must require actual bool True.
            set_field(invalid, key, 1)
            cases.append((prefix + "__non_boolean_" + key, profile, invalid, False, 200, False))
        for key in probe.get("required_keys", []):
            invalid = copy.deepcopy(body)
            set_field(invalid, key, delete=True)
            cases.append((prefix + "__missing_" + key, profile, invalid, False, 200, False))
        for key, minimum in probe.get("numeric_min", {}).items():
            invalid = copy.deepcopy(body)
            set_field(invalid, key, minimum - 1)
            cases.append((prefix + "__below_minimum_" + key, profile, invalid, False, 200, False))
    return cases


COMPATIBILITY_CASES = compatibility_cases()


class SyntheticProbeCase(unittest.TestCase):
    def run_probe_case(self, profile, body, accepted, status=200, oversized=False):
        probe = profile["probe"]
        limit = 2 * 1024 * 1024 if probe["strength"] == "documentation" else 65536
        payload = json.dumps(body).encode() if isinstance(body, dict) else body.encode()
        if oversized:
            payload = b"x" * (limit + 1)
        calls = []
        closed = []
        test = self

        class Response:
            def __init__(self):
                self.status = status

            def read(self, amount):
                test.assertEqual(limit + 1, amount)
                return payload[:amount]

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "application/json" if probe["kind"] == "json" else "text/plain"
                return default

        class Connection:
            def __init__(self, host, port, timeout):
                test.assertEqual("127.0.0.1", host)
                test.assertEqual(profile["port"], port)
                test.assertEqual(5, timeout)

            def request(self, method, path, headers):
                test.assertEqual("GET", method)
                test.assertEqual(probe["path"], path)
                test.assertEqual({"Host": "127.0.0.1", "Connection": "close"}, headers)
                calls.append((method, path))

            def getresponse(self):
                return Response()

            def close(self):
                closed.append(True)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(engine, "command", side_effect=AssertionError("host command forbidden")))
            stack.enter_context(mock.patch.object(engine.subprocess, "Popen", side_effect=AssertionError("subprocess forbidden")))
            stack.enter_context(mock.patch.object(engine.os, "system", side_effect=AssertionError("shell forbidden")))
            stack.enter_context(mock.patch.object(engine.socket, "socket", side_effect=AssertionError("network forbidden")))
            stack.enter_context(mock.patch.object(engine.socket, "create_connection", side_effect=AssertionError("network forbidden")))
            stack.enter_context(mock.patch.object(engine.socket, "gethostname", side_effect=AssertionError("host inspection forbidden")))
            stack.enter_context(mock.patch.object(engine.http.client, "HTTPConnection", Connection))
            if accepted:
                self.assertEqual(
                    {"status": 200, "strength": probe["strength"], "contract_passed": True},
                    engine.probe(profile),
                )
            else:
                with self.assertRaises(engine.GuardError):
                    engine.probe(profile)
        self.assertEqual([("GET", probe["path"])], calls)
        self.assertEqual([True], closed, "The response connection must close on pass and rejection")


class CatalogCompatibilityTests(SyntheticProbeCase):
    def test_compatibility_inventory_is_25_positive_and_115_negative(self):
        self.assertEqual(25, len(PROFILES))
        self.assertEqual(25, sum(case[3] for case in COMPATIBILITY_CASES))
        self.assertEqual(115, sum(not case[3] for case in COMPATIBILITY_CASES))
        self.assertEqual(24, len(ACTIVE))
        self.assertFalse(PRIVATE["activate"])


# Independent literals, not derived from service-catalog.json:
# - gateway AggregateHealthResponseWriter and Program /health/ready registration;
# - chat FirestoreReadinessProbe and the canonical Jeeb project/database contract;
# - RUP Cargo.toml package metadata + locked utoipa4.2.3/utoipa-gen4.3.1 defaults.
# These deliberately remain synthetic; no RPC/source build is claimed here.
GATEWAY_HEALTHY = {
    "status": "Healthy", "failing": [], "totalDurationMs": 0,
    "checks": [{"name": "synthetic-ready-check", "status": "Healthy"}],
}
CHAT_CANONICAL = {
    "ok": True, "projectId": "jeeb-5a293", "databaseId": "(default)",
    "mode": "firestore", "latencyMs": 0,
}
RUP_CURRENT_SOURCE = {
    "openapi": "3.0.3",
    "info": {"title": "remote-user-preferences", "version": "0.1.0"},
    "paths": {},
}


def changed(body, key, value):
    result = copy.deepcopy(body)
    set_field(result, key, value)
    return result


FIXED_CASES = [
    ("gateway_healthy", "jeeb-gateway", GATEWAY_HEALTHY, True),
    # Keep failing=[] to isolate the status literal even when HTTP remains200.
    ("gateway_http200_degraded", "jeeb-gateway", changed(GATEWAY_HEALTHY, "status", "Degraded"), False),
    ("gateway_healthy_with_failing_check", "jeeb-gateway", changed(GATEWAY_HEALTHY, "failing", ["synthetic-failure"]), False),
    ("chat_canonical_identity", "chat-service", CHAT_CANONICAL, True),
    ("chat_wrong_project", "chat-service", changed(CHAT_CANONICAL, "projectId", "synthetic-wrong-project"), False),
    ("chat_wrong_database", "chat-service", changed(CHAT_CANONICAL, "databaseId", "synthetic-other-database"), False),
    ("chat_emulator_mode", "chat-service", changed(CHAT_CANONICAL, "mode", "emulator"), False),
    ("chat_ok_integer_not_bool", "chat-service", changed(CHAT_CANONICAL, "ok", 1), False),
    ("chat_ok_false", "chat-service", changed(CHAT_CANONICAL, "ok", False), False),
    ("chat_latency_bool_not_number", "chat-service", changed(CHAT_CANONICAL, "latencyMs", True), False),
    ("chat_negative_latency", "chat-service", changed(CHAT_CANONICAL, "latencyMs", -1), False),
    ("rup_current_source_identity", "remote-user-preferences", RUP_CURRENT_SOURCE, True),
    ("rup_wrong_title", "remote-user-preferences", changed(RUP_CURRENT_SOURCE, "info.title", "rust-remote-user-preferences"), False),
    ("rup_historical_version", "remote-user-preferences", changed(RUP_CURRENT_SOURCE, "info.version", "0.1.1"), False),
    ("rup_wrong_openapi_version", "remote-user-preferences", changed(RUP_CURRENT_SOURCE, "openapi", "3.1.0"), False),
    ("rup_openapi_number_not_string", "remote-user-preferences", changed(RUP_CURRENT_SOURCE, "openapi", 3.03), False),
    ("rup_title_array_not_string", "remote-user-preferences", changed(RUP_CURRENT_SOURCE, "info.title", ["remote-user-preferences"]), False),
    ("rup_version_number_not_string", "remote-user-preferences", changed(RUP_CURRENT_SOURCE, "info.version", 0.1), False),
]


class FixedWireContractTests(SyntheticProbeCase):
    pass


def install_case(target, name, profile, body, accepted, status=200, oversized=False):
    method_name = "test_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if hasattr(target, method_name):
        raise ValueError("Duplicate generated probe test: " + method_name)

    def test(self):
        self.run_probe_case(profile, copy.deepcopy(body), accepted, status, oversized)

    test.__name__ = method_name
    setattr(target, method_name, test)


for case in COMPATIBILITY_CASES:
    install_case(CatalogCompatibilityTests, *case)
for name, service, body, accepted in FIXED_CASES:
    install_case(FixedWireContractTests, name, ACTIVE[service], body, accepted)


if __name__ == "__main__":
    unittest.main()
