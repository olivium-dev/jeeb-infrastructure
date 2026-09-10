"""Offline guards for the exact applied MSI fragment; no live nginx/network calls."""
import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
REALTIME = ROOT / "deploy/msi/realtime"
FRAGMENT = REALTIME / "nginx-msi-realtime-location.conf"
DROP_IN = REALTIME / "zzzz-msi-http-bind.conf"


def findings(source):
    code = "\n".join(line.strip() for line in source.splitlines() if not line.lstrip().startswith("#"))
    required = (
        "location = /socket/websocket {",
        "access_log off;", "error_log /dev/null crit;",
        r'if ($realip_remote_addr !~ "^(127\\.0\\.0\\.1|::1)$") { return 403; }',
        'if ($http_host != "msi.olivium.space") { return 404; }',
        r'if ($request_uri !~ "^/socket/websocket(?:\\?.*)?$") { return 404; }',
        "if ($request_method != GET) { return 405; }",
        'if ($http_upgrade !~* "^websocket$") { return 400; }',
        'if ($http_sec_websocket_version != "13") { return 400; }',
        r'if ($http_origin !~ "^(https://msi\\.olivium\\.space)?$") { return 403; }',
        "proxy_pass http://127.0.0.1:5804;", "proxy_http_version 1.1;",
        "proxy_redirect off;", "proxy_intercept_errors off;", "proxy_cache off;",
        "proxy_buffering off;", "proxy_request_buffering off;",
        "proxy_pass_request_body off;", "proxy_pass_request_headers off;",
        "proxy_connect_timeout 5s;", "proxy_send_timeout 75s;", "proxy_read_timeout 75s;",
    )
    errors = ["required directive missing or duplicated" for item in required if code.count(item) != 1]
    if len(re.findall(r"(?m)^location\b", code)) != 1:
        errors.append("unexpected location")
    if len(re.findall(r"(?m)^proxy_pass\b", code)) != 1:
        errors.append("unexpected upstream")
    expected_headers = {
        "Host": "msi.olivium.space", "Upgrade": "websocket", "Connection": "upgrade",
        "Sec-WebSocket-Key": "$http_sec_websocket_key", "Sec-WebSocket-Version": "13",
        "Origin": "$http_origin", "Content-Length": '""',
    }
    headers = re.findall(r"(?m)^proxy_set_header\s+(\S+)\s+([^;]+);$", code)
    if len(headers) != len(expected_headers) or dict(headers) != expected_headers:
        errors.append("unexpected forwarding headers")
    if re.search(r"(?m)^(?:include|listen|server_name|rewrite|set_real_ip_from|real_ip_header)\b", code):
        errors.append("unexpected global routing/identity directive")
    return errors


class MsiPrivateRealtimeIngressTests(unittest.TestCase):
    def test_exact_applied_fragment_bytes(self):
        self.assertEqual(hashlib.sha256(FRAGMENT.read_bytes()).hexdigest(),
                         "bc4df706e975d44d598f954d47d0531c91647ade6d7cec47da4c8e4dbde2c029")

    def test_bind_drop_in_changes_only_explicit_loopback_address(self):
        self.assertEqual(DROP_IN.read_text(), '[Service]\nEnvironment="HTTP_BIND_ADDRESS=127.0.0.1"\n')

    def test_fragment_preserves_private_auth_and_route_boundaries(self):
        self.assertEqual(findings(FRAGMENT.read_text()), [])

    def test_security_regressions_are_rejected(self):
        source = FRAGMENT.read_text()
        mutations = (
            ("location = /socket/websocket", "location /socket"),
            ("if ($realip_remote_addr", "if ($http_x_forwarded_for"),
            ('if ($http_host != "msi.olivium.space") { return 404; }', ""),
            ("$request_uri", "$uri"),
            ("$request_method != GET", "$request_method != POST"),
            ('"^websocket$"', '".*"'),
            ('$http_sec_websocket_version != "13"', '$http_sec_websocket_version != "12"'),
            ("$http_origin", "$ignored_origin"),
            ("access_log off;", "access_log /var/log/nginx/access.log;"),
            ("error_log /dev/null crit;", "error_log /var/log/nginx/error.log debug;"),
            ("proxy_pass_request_headers off;", "proxy_pass_request_headers on;"),
            ("proxy_pass_request_body off;", "proxy_pass_request_body on;"),
            ("http://127.0.0.1:5804;", "http://192.168.2.39:5804;"),
            ("proxy_read_timeout 75s;", "proxy_read_timeout 3600s;"),
            ("proxy_cache off;", "proxy_cache shared;"),
        )
        for old, new in mutations:
            with self.subTest(directive=old):
                changed = source.replace(old, new, 1)
                self.assertNotEqual(changed, source)
                self.assertTrue(findings(changed))
        for extra in (
            "proxy_set_header Authorization $http_authorization;",
            "proxy_set_header Cookie $http_cookie;",
            "proxy_set_header CF-Access-Jwt-Assertion $http_cf_access_jwt_assertion;",
            "location /other { proxy_pass http://127.0.0.1:5804; }",
            "include /etc/nginx/another.conf;",
            "real_ip_header X-Forwarded-For;",
        ):
            with self.subTest(extra=extra):
                self.assertTrue(findings(source + "\n" + extra + "\n"))

    def test_runbook_preserves_acceptance_limits_and_source_provenance(self):
        runbook = (REALTIME / "PRIVATE-LISTENER-WSS.md").read_text()
        for required in (
            "Full realtime main", "not deployed", "authenticated WSS101", "Firebase-only",
            "5325c3679d3918eac4e1f47cfc39bc0c0edbb3bf81b36243ffd2151fb35a061e",
            "ca47098f26bbb96fadc70ba286c7685da637fcc0b688cb5d6c43edbdb6f348dd",
            "static command", "No fee collection", "Cloudflare edge/provider logging",
        ):
            self.assertIn(required, runbook)

    def test_offline_contract_is_wired_into_existing_ci(self):
        workflow = (ROOT / ".github/workflows/deployment-safety.yml").read_text()
        self.assertIn("python3 scripts/check-deployment-safety-policy.py", workflow)
        self.assertIn("python3 -m unittest discover -s deploy/msi/realtime/tests -p 'test_*.py' -v", workflow)
        self.assertNotIn("continue-on-error", workflow)


if __name__ == "__main__":
    unittest.main()
