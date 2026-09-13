from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("cloudflare_org_auth", ROOT / "scripts/verify_cloudflare_org_auth.py")
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
TOKEN = "SYNTHETIC-CLOUDFLARE-CANARY-NEVER-EMIT"
TOKEN_ID = "synthetic-staging-token-id"
PIN = hashlib.sha256(TOKEN_ID.encode()).hexdigest()
ACTIVE = {"success": True, "result": {"id": TOKEN_ID, "status": "active"}}
DOMAINS = {"success": True, "result": [
    {"hostname": host, "zone_id": subject.ZONE_ID, "zone_name": "fds-1.com",
     "service": subject.WORKER_NAME, "environment": "production"}
    for host in sorted(subject.HOSTNAMES)
]}


class CloudflareOrgAuthTests(unittest.TestCase):
    def test_exact_token_and_domains_use_only_two_fixed_reads(self):
        with mock.patch.object(subject, "get_json", side_effect=[ACTIVE, DOMAINS]) as get:
            subject.validate(TOKEN, PIN)
        self.assertEqual(get.call_args_list, [
            mock.call(subject.VERIFY_PATH, TOKEN), mock.call(subject.DOMAINS_PATH, TOKEN),
        ])

    def test_missing_or_invalid_pin_fails_before_network(self):
        for pin in ("", "z" * 64, "0" * 63):
            with self.subTest(pin=pin), mock.patch.object(subject, "get_json") as get:
                with self.assertRaises(subject.ValidationError):
                    subject.validate(TOKEN, pin)
                get.assert_not_called()

    def test_missing_malformed_and_oversized_token_fail_before_network(self):
        for token in ("", TOKEN + "\n", TOKEN + "\rX-Evil: yes", "a" * 16385):
            with self.subTest(length=len(token)), mock.patch.object(subject, "get_json") as get:
                with self.assertRaises(subject.ValidationError):
                    subject.validate(token, PIN)
                get.assert_not_called()

    def test_wrong_token_identity_stops_before_resource_read(self):
        with mock.patch.object(subject, "get_json", return_value=ACTIVE) as get:
            with self.assertRaises(subject.ValidationError):
                subject.validate(TOKEN, "0" * 64)
            self.assertEqual(get.call_count, 1)

    def test_inactive_or_invalid_verification_fails(self):
        for result in (None, [], {"status": "expired", "id": TOKEN_ID}, {"status": "active"}):
            with self.subTest(result=result), mock.patch.object(subject, "get_json", return_value={"result": result}) as get:
                with self.assertRaises(subject.ValidationError):
                    subject.validate(TOKEN, PIN)
                self.assertEqual(get.call_count, 1)

    def test_each_resource_mismatch_fails(self):
        for field in ("hostname", "zone_id", "zone_name", "service", "environment"):
            response = copy.deepcopy(DOMAINS)
            response["result"][0][field] = "wrong-resource"
            with self.subTest(field=field), mock.patch.object(subject, "get_json", side_effect=[ACTIVE, response]):
                with self.assertRaises(subject.ValidationError):
                    subject.validate(TOKEN, PIN)

    def test_missing_duplicate_and_extra_domains_fail(self):
        for domains in (None, [], [DOMAINS["result"][0]] * 2, DOMAINS["result"] * 2, [None, None]):
            with self.subTest(domains=domains), mock.patch.object(subject, "get_json", side_effect=[ACTIVE, {"result": domains}]):
                with self.assertRaises(subject.ValidationError):
                    subject.validate(TOKEN, PIN)

    def connection(self, status=200, body=None):
        connection = mock.MagicMock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = json.dumps(ACTIVE).encode() if body is None else body
        return connection

    def test_https_transport_pins_host_and_get_without_proxy_or_redirects(self):
        connection = self.connection()
        with mock.patch.object(subject.http.client, "HTTPSConnection", return_value=connection) as factory:
            subject.get_json(subject.VERIFY_PATH, TOKEN)
        self.assertEqual(factory.call_args.args, ("api.cloudflare.com",))
        self.assertEqual(factory.call_args.kwargs["timeout"], 15)
        self.assertTrue(factory.call_args.kwargs["context"].check_hostname)
        connection.request.assert_called_once_with("GET", subject.VERIFY_PATH, headers={
            "Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
        })
        connection.close.assert_called_once()

    def test_non_allowlisted_path_rejected_without_connection(self):
        with mock.patch.object(subject.http.client, "HTTPSConnection") as factory:
            with self.assertRaises(subject.ValidationError):
                subject.get_json("https://untrusted.invalid/", TOKEN)
            factory.assert_not_called()

    def test_redirect_and_non_200_never_read_body_or_follow(self):
        for status in (201, 301, 302, 307, 401, 403, 500):
            connection = self.connection(status=status)
            with self.subTest(status=status), mock.patch.object(subject.http.client, "HTTPSConnection", return_value=connection):
                with self.assertRaises(subject.ValidationError):
                    subject.get_json(subject.VERIFY_PATH, TOKEN)
                connection.getresponse.return_value.read.assert_not_called()
                self.assertEqual(connection.request.call_count, 1)
                connection.close.assert_called_once()

    def test_oversized_or_malformed_provider_response_fails(self):
        for body in (b"x" * (subject.MAX_RESPONSE_BYTES + 1), b"not-json", b"[]", b'{"success": false}'):
            with self.subTest(length=len(body)), mock.patch.object(subject.http.client, "HTTPSConnection", return_value=self.connection(body=body)):
                with self.assertRaises((ValueError, subject.ValidationError)):
                    subject.get_json(subject.VERIFY_PATH, TOKEN)

    def test_failure_output_never_contains_credentials_or_provider_body(self):
        output = io.StringIO()
        stdin = io.TextIOWrapper(io.BytesIO(TOKEN.encode()))
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "argv", ["validator"]), \
             mock.patch.dict(os.environ, {"EXPECTED_CLOUDFLARE_TOKEN_ID_SHA256": PIN}), \
             mock.patch.object(subject, "get_json", side_effect=RuntimeError(TOKEN)), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(subject.main(), 1)
        self.assertEqual(output.getvalue(), "cloudflare-org-auth:FAIL\n")

    def test_workflow_has_exact_org_binding_and_auth_before_ssh(self):
        workflow = (ROOT / ".github/workflows/jeeb-staging-edge-deploy.yml").read_text()
        self.assertNotIn("secrets.CLOUDFLARE_API_TOKEN", workflow)
        self.assertIn("secrets.JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_API_TOKEN", workflow)
        self.assertLess(workflow.index("python3 scripts/verify_cloudflare_org_auth.py"), workflow.index("Install pinned cloudflared and configure strict SSH"))
        validator = (ROOT / ".github/workflows/jeeb-cloudflare-org-auth-check.yml").read_text()
        self.assertIn("github.ref_protected == true", validator)
        self.assertIn("github.actor == 'oudaykhaled'", validator)
        self.assertIn("environment: staging", validator)
        self.assertNotIn("environment: production", validator)


if __name__ == "__main__":
    unittest.main()
