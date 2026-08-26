#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit


CONFIG = Path(__file__).resolve().parents[1] / "nginx" / "jeeb-direct-tls.conf"
TUNNEL_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "cloudflare"
    / "cloudflared-ingress.yml.template"
)
WORKER = (
    Path(__file__).resolve().parents[1]
    / "cloudflare"
    / "jeeb-staging-router.mjs"
)
WRANGLER = (
    Path(__file__).resolve().parents[1]
    / "cloudflare"
    / "wrangler.toml"
)
EDGE_WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "jeeb-staging-edge-deploy.yml"
)
SUDOERS = Path(__file__).resolve().parents[1] / "sudoers" / "jeeb-staging-edge-deploy"
RENEWAL_HOOK = (
    Path(__file__).resolve().parents[1]
    / "letsencrypt"
    / "renewal-hooks"
    / "deploy"
    / "jeeb-nginx"
)
WELL_KNOWN = Path(__file__).resolve().parents[1] / "well-known"
AASA = WELL_KNOWN / "apple-app-site-association"
ASSET_LINKS = WELL_KNOWN / "assetlinks.json"

APPLE_APP_ID = "K5RDQ8J7AN.com.olivium.jeeb"
ANDROID_PACKAGE = "com.olivium.jeeb"
PLAY_APP_SIGNING_SHA256 = (
    "42:76:6A:BB:4B:EA:1F:A4:88:00:96:6F:78:A1:E5:4F:"
    "A0:EA:12:B8:A1:6A:58:AF:07:5A:02:01:0B:B5:58:E9"
)
UPLOAD_CERT_SHA256 = (
    "7A:E6:A6:20:BA:89:E8:43:85:13:E4:2C:F5:9E:69:E3:"
    "CF:0F:CD:CE:8C:87:D7:71:3B:07:8C:80:3D:A2:E3:BA"
)
OTP_VERIFY_LOCATION = "location ~ ^/(?:v1/)?auth/otp/verify/?$ {"
OTP_VERIFY_PROBLEM_JSON = (
    '{"type":"about:blank","title":"Service Unavailable","status":503,'
    '"detail":"The service is temporarily unavailable. Please try again."}'
)


class DirectTlsContractTests(unittest.TestCase):
    def test_edge_workflow_uses_exact_root_owned_rollout_helper(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "ORIGIN_ROLLOUT_HELPER: /usr/local/sbin/jeeb-edge-origin-rollout",
            workflow,
        )
        self.assertIn("root:root:755", workflow)
        self.assertIn("expected_rollout_sha=$(sha256sum", workflow)
        self.assertIn('[ "$(hostname -s)" = olivium-ephemerals ]', workflow)
        self.assertIn('sudo -n "$ORIGIN_ROLLOUT_HELPER"', workflow)
        self.assertIn("sudo -n /usr/sbin/nginx -T >/dev/null", workflow)
        self.assertIn("sudo -n /usr/sbin/nginx -t", workflow)
        self.assertNotIn("--strict", workflow)
        self.assertNotIn("sudo bash -s", workflow)
        self.assertNotIn("sudo -n bash -s", workflow)

    def test_sudoers_grants_only_edge_read_and_forward_helper(self) -> None:
        policy = SUDOERS.read_text(encoding="utf-8")
        self.assertIn("/usr/sbin/nginx -T", policy)
        self.assertIn("/usr/sbin/nginx -t", policy)
        self.assertIn("/usr/bin/systemctl is-active --quiet nginx", policy)
        self.assertIn(
            "/usr/bin/systemctl is-active --quiet cloudflared-jeeb-staging",
            policy,
        )
        self.assertIn("/usr/local/sbin/jeeb-edge-origin-rollout apply *", policy)
        self.assertIn("/usr/local/sbin/jeeb-edge-origin-rollout finalize *", policy)
        self.assertNotIn("/usr/bin/bash", policy)
        self.assertNotIn("systemctl restart", policy)

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CONFIG.read_text(encoding="utf-8")

    def test_exact_public_hosts_are_loopback_only(self) -> None:
        self.assertIn("server_name app.jeeb.fds-1.com;", self.text)
        self.assertIn("server_name cms.jeeb.fds-1.com;", self.text)
        self.assertEqual(self.text.count("listen 127.0.0.1:443 ssl;"), 2)
        self.assertEqual(self.text.count("listen [::1]:443 ssl;"), 2)
        self.assertNotIn("listen 443 ssl;", self.text)
        self.assertNotIn("listen [::]:443 ssl;", self.text)
        self.assertNotIn("listen 80;", self.text)

    def test_shared_letsencrypt_certificate_and_modern_protocols(self) -> None:
        self.assertEqual(
            self.text.count(
                "ssl_certificate /etc/letsencrypt/live/jeeb-staging-edge/fullchain.pem;"
            ),
            2,
        )
        self.assertEqual(self.text.count("ssl_protocols TLSv1.2 TLSv1.3;"), 2)
        self.assertEqual(self.text.count("add_header Strict-Transport-Security"), 5)
        self.assertEqual(self.text.count("add_header X-Content-Type-Options"), 5)
        self.assertNotIn("ssl_protocols TLSv1 ", self.text)

    def test_worker_origin_requires_root_owned_runtime_secret(self) -> None:
        self.assertIn("include /etc/nginx/jeeb-origin-key.map;", self.text)
        self.assertEqual(self.text.count("if ($jeeb_origin_authorized = 0)"), 2)
        self.assertEqual(self.text.count('proxy_set_header X-Jeeb-Origin-Key "";'), 3)
        self.assertNotIn("x-jeeb-origin-key ", self.text)

    def test_gateway_targets_local_staging_gateway(self) -> None:
        app = self.text.split("server_name app.jeeb.fds-1.com;", 1)[1].split(
            "server_name cms.jeeb.fds-1.com;", 1
        )[0]
        self.assertIn("proxy_pass http://127.0.0.1:10000;", app)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", app)
        self.assertIn("proxy_hide_header Strict-Transport-Security;", app)
        self.assertIn("proxy_hide_header X-Content-Type-Options;", app)

    def test_otp_verify_freeze_returns_exact_generic_problem_without_logging(self) -> None:
        app = self.text.split("server_name app.jeeb.fds-1.com;", 1)[1].split(
            "server_name cms.jeeb.fds-1.com;", 1
        )[0]
        self.assertIn(OTP_VERIFY_LOCATION, app)
        freeze = app.split(OTP_VERIFY_LOCATION, 1)[1].split("\n    }", 1)[0]

        self.assertIn("access_log off;", freeze)
        self.assertIn("default_type application/problem+json;", freeze)
        self.assertIn('add_header Cache-Control "no-store" always;', freeze)
        self.assertIn(
            'add_header Strict-Transport-Security "max-age=31536000" always;',
            freeze,
        )
        self.assertIn('add_header X-Content-Type-Options "nosniff" always;', freeze)
        self.assertIn(f"return 503 '{OTP_VERIFY_PROBLEM_JSON}';", freeze)
        self.assertNotIn("proxy_pass", freeze)
        self.assertNotIn("Retry-After", freeze)
        self.assertNotIn("$args", freeze)
        self.assertNotIn("$request_body", freeze)

        problem = json.loads(OTP_VERIFY_PROBLEM_JSON)
        self.assertEqual(
            problem,
            {
                "type": "about:blank",
                "title": "Service Unavailable",
                "status": 503,
                "detail": "The service is temporarily unavailable. Please try again.",
            },
        )
        self.assertNotIn("instance", problem)
        self.assertNotIn("code", problem)
        self.assertNotIn("errorCode", problem)
        self.assertNotIn("retryAfter", problem)

    def test_otp_verify_freeze_matches_both_aliases_slashes_and_queries_only(self) -> None:
        pattern = OTP_VERIFY_LOCATION.removeprefix("location ~ ").removesuffix(" {")
        matcher = re.compile(pattern)

        frozen_targets = (
            "/v1/auth/otp/verify",
            "/v1/auth/otp/verify/",
            "/v1/auth/otp/verify?source=contract",
            "/v1/auth/otp/verify/?source=contract",
            "/auth/otp/verify",
            "/auth/otp/verify/",
            "/auth/otp/verify?source=contract",
            "/auth/otp/verify/?source=contract",
        )
        for target in frozen_targets:
            with self.subTest(target=target):
                self.assertIsNotNone(
                    matcher.fullmatch(urlsplit(target).path),
                    "nginx selects regex locations using the URI path without arguments",
                )

        forwarded_targets = (
            "/v1/auth/otp/request",
            "/v1/auth/otp/request?source=contract",
            "/auth/otp/request",
            "/auth/otp/request/",
            "/v1/auth/otp/verify/extra",
            "/auth/otp/verify-extra",
            "/health/ready",
            "/v1/users/me",
        )
        for target in forwarded_targets:
            with self.subTest(target=target):
                self.assertIsNone(matcher.fullmatch(urlsplit(target).path))

        app = self.text.split("server_name app.jeeb.fds-1.com;", 1)[1].split(
            "server_name cms.jeeb.fds-1.com;", 1
        )[0]
        self.assertLess(app.index(OTP_VERIFY_LOCATION), app.index("location / {"))
        catch_all = app.split("location / {", 1)[1].split("\n    }", 1)[0]
        self.assertIn("proxy_pass http://127.0.0.1:10000;", catch_all)
        self.assertEqual(app.count(OTP_VERIFY_LOCATION), 1)

    def test_exact_phoenix_socket_route_uses_gateway_only_ingress(self) -> None:
        app = self.text.split("server_name app.jeeb.fds-1.com;", 1)[1].split(
            "server_name cms.jeeb.fds-1.com;", 1
        )[0]
        self.assertIn("location = /socket/websocket {", app)
        socket = app.split("location = /socket/websocket {", 1)[1].split(
            "\n    }", 1
        )[0]
        self.assertIn(
            "proxy_pass http://127.0.0.1:10000/socket/websocket;", socket
        )
        self.assertNotIn("10069", socket)
        self.assertIn("proxy_set_header Upgrade $http_upgrade;", socket)
        self.assertIn(
            "proxy_set_header Connection $jeeb_staging_connection_upgrade;", socket
        )
        self.assertIn("proxy_buffering off;", socket)
        self.assertIn("access_log off;", socket)
        self.assertNotIn("location /socket", app)

    def test_well_known_documents_are_exact_json_locations(self) -> None:
        for public_path, filename in (
            ("/.well-known/apple-app-site-association", "apple-app-site-association"),
            ("/.well-known/assetlinks.json", "assetlinks.json"),
        ):
            self.assertIn(f"location = {public_path} {{", self.text)
            self.assertIn(
                f"alias /var/www/jeeb-staging-well-known/current/{filename};",
                self.text,
            )
            location = self.text.split(f"location = {public_path} {{", 1)[1].split(
                "\n    }", 1
            )[0]
            self.assertIn(
                'add_header Strict-Transport-Security "max-age=31536000" always;',
                location,
            )
        self.assertGreaterEqual(self.text.count("default_type application/json;"), 2)

    def test_cms_targets_lan_host_and_callbacks_fail_closed(self) -> None:
        body = self.text.split("server_name cms.jeeb.fds-1.com;", 1)[1]
        self.assertIn("proxy_pass http://192.168.2.39:80;", body)
        self.assertIn("proxy_set_header Host $host;", body)
        self.assertIn("proxy_set_header X-Forwarded-Host $host;", body)
        self.assertNotIn("backoffice.jeeb.fds-1.com", body)
        self.assertIn("access_log off;", body)
        self.assertIn("proxy_hide_header Strict-Transport-Security;", body)
        self.assertIn("proxy_hide_header X-Content-Type-Options;", body)
        self.assertIn("location ~* ^/gateway/svc-callbacks", body)
        self.assertIn("location ~* ^/gateway/v1/case-events", body)
        self.assertNotIn("proxy_cookie_domain", body)
        self.assertNotIn("proxy_cookie_path", body)

    def test_no_retired_gateway_public_host(self) -> None:
        self.assertNotIn("jeeb-staging.fds-1.com", self.text)

    def test_renewal_hook_validates_before_reload(self) -> None:
        hook = RENEWAL_HOOK.read_text(encoding="utf-8")
        self.assertIn("set -eu", hook)
        self.assertIn("validation_output=$(/usr/sbin/nginx -t 2>&1)", hook)
        self.assertIn("/bin/systemctl reload nginx", hook)
        self.assertLess(hook.index("nginx -t"), hook.index("systemctl reload nginx"))

    def test_tunnel_validates_nginx_certificate_for_each_origin(self) -> None:
        tunnel = TUNNEL_CONFIG.read_text(encoding="utf-8")
        for public, hidden in (
            ("app.jeeb.fds-1.com", "jeeb-app-origin.fds-1.com"),
            ("cms.jeeb.fds-1.com", "jeeb-cms-origin.fds-1.com"),
        ):
            self.assertIn(f"hostname: {hidden}", tunnel)
            self.assertIn(f"originServerName: {public}", tunnel)
            self.assertIn(f"httpHostHeader: {public}", tunnel)
        self.assertNotIn("noTLSVerify", tunnel)
        self.assertNotIn("jeeb-staging.fds-1.com", tunnel)

    def test_worker_maps_only_exact_public_hosts_and_injects_origin_key(self) -> None:
        worker = WORKER.read_text(encoding="utf-8")
        self.assertIn('"app.jeeb.fds-1.com": "jeeb-app-origin.fds-1.com"', worker)
        self.assertIn('"cms.jeeb.fds-1.com": "jeeb-cms-origin.fds-1.com"', worker)
        self.assertIn('headers.set("x-jeeb-origin-key", env.ORIGIN_KEY);', worker)
        self.assertIn('status: 421', worker)
        self.assertIn('if (upstream.protocol !== "https:")', worker)
        self.assertIn('status: 308', worker)
        self.assertIn('"cache-control": "no-store"', worker)
        self.assertNotIn("jeeb-staging.fds-1.com", worker)

    def test_apple_association_uses_the_store_app_identity(self) -> None:
        payload = json.loads(AASA.read_text(encoding="utf-8"))
        details = payload["applinks"]["details"]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["appIDs"], [APPLE_APP_ID])
        paths = {component["/"] for component in details[0]["components"]}
        self.assertIn("/chat/*", paths)
        self.assertIn("/orders/*", paths)
        self.assertIn("/profile/*", paths)

    def test_android_association_uses_play_signing_not_upload_identity(self) -> None:
        payload = json.loads(ASSET_LINKS.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 1)
        self.assertEqual(
            payload[0]["relation"], ["delegate_permission/common.handle_all_urls"]
        )
        target = payload[0]["target"]
        self.assertEqual(target["namespace"], "android_app")
        self.assertEqual(target["package_name"], ANDROID_PACKAGE)
        self.assertEqual(
            target["sha256_cert_fingerprints"], [PLAY_APP_SIGNING_SHA256]
        )
        self.assertNotIn(UPLOAD_CERT_SHA256, ASSET_LINKS.read_text(encoding="utf-8"))

    def test_wrangler_owns_exact_custom_domains_without_workers_dev(self) -> None:
        config = WRANGLER.read_text(encoding="utf-8")
        self.assertIn('name = "jeeb-staging-host-router"', config)
        self.assertIn('main = "jeeb-staging-router.mjs"', config)
        self.assertIn("workers_dev = false", config)
        self.assertEqual(config.count("custom_domain = true"), 2)
        self.assertIn('pattern = "app.jeeb.fds-1.com"', config)
        self.assertIn('pattern = "cms.jeeb.fds-1.com"', config)
        self.assertNotIn("ORIGIN_KEY", config)

    def test_public_gate_records_legacy_tls_and_checks_both_redirects(self) -> None:
        workflow = EDGE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            'if [ "$code" = 200 ] \\\n'
            "                  && grep -Eiq",
            workflow,
        )
        self.assertIn("HTTPS 200 with required HSTS within 60 seconds", workflow)
        self.assertIn(
            "^strict-transport-security: max-age=31536000[[:space:]]*$",
            workflow,
        )
        self.assertIn("^healthy[[:space:]]*$", workflow)
        self.assertIn(
            "^content-type: application/json(;[^[:cntrl:]]*)?[[:space:]]*$",
            workflow,
        )
        self.assertIn(
            "^x-jeeb-realtime-proxy: gateway[[:space:]]*$",
            workflow,
        )
        self.assertNotIn(r"\r?$", workflow)
        self.assertIn("verify_public_tls_floor()", workflow)
        self.assertIn("-min_protocol \"$protocol\"", workflow)
        self.assertIn("-max_protocol \"$protocol\"", workflow)
        self.assertIn("-cipher 'ALL:@SECLEVEL=0'", workflow)
        for host in ("app.jeeb.fds-1.com", "cms.jeeb.fds-1.com"):
            self.assertIn(f"verify_public_tls_floor {host}", workflow)
            self.assertIn(
                f"verify_http_redirect {host} /edge-redirect-probe?source=release",
                workflow,
            )
        self.assertIn("Accepted staging TLS risk", workflow)
        self.assertIn("policy=advisory", workflow)
        self.assertIn("cloudflare-free-no-advanced-certificate-manager", workflow)
        self.assertNotIn("::error::Legacy TLS was accepted", workflow)
        legacy_probe = workflow.split("for protocol in TLSv1 TLSv1.1; do", 1)[1]
        legacy_probe = legacy_probe.split(
            "output=$RUNNER_TEMP/tls-${host//./-}-TLSv1-2", 1
        )[0]
        self.assertNotIn("return 1", legacy_probe)
        self.assertNotIn("exit 1", legacy_probe)
        self.assertIn("Public TLS 1.2 was not accepted", workflow)
        self.assertIn("protocol=TLSv1.2 result=accepted policy=hard", workflow)
        self.assertIn("^x-jeeb-realtime-proxy: gateway", workflow)
        self.assertNotIn("127.0.0.1:10069", workflow)


if __name__ == "__main__":
    unittest.main()
