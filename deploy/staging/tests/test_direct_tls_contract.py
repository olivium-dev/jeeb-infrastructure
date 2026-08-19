#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


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
RENEWAL_HOOK = (
    Path(__file__).resolve().parents[1]
    / "letsencrypt"
    / "renewal-hooks"
    / "deploy"
    / "jeeb-nginx"
)


class DirectTlsContractTests(unittest.TestCase):
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
        self.assertEqual(self.text.count("add_header Strict-Transport-Security"), 2)
        self.assertEqual(self.text.count("add_header X-Content-Type-Options"), 2)
        self.assertNotIn("ssl_protocols TLSv1 ", self.text)

    def test_worker_origin_requires_root_owned_runtime_secret(self) -> None:
        self.assertIn("include /etc/nginx/jeeb-origin-key.map;", self.text)
        self.assertEqual(self.text.count("if ($jeeb_origin_authorized = 0)"), 2)
        self.assertEqual(self.text.count('proxy_set_header X-Jeeb-Origin-Key "";'), 2)
        self.assertNotIn("x-jeeb-origin-key ", self.text)

    def test_gateway_targets_local_staging_gateway(self) -> None:
        app = self.text.split("server_name app.jeeb.fds-1.com;", 1)[1].split(
            "server_name cms.jeeb.fds-1.com;", 1
        )[0]
        self.assertIn("proxy_pass http://127.0.0.1:10000;", app)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", app)
        self.assertIn("proxy_hide_header Strict-Transport-Security;", app)
        self.assertIn("proxy_hide_header X-Content-Type-Options;", app)

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
        self.assertNotIn("jeeb-staging.fds-1.com", worker)

    def test_wrangler_owns_exact_custom_domains_without_workers_dev(self) -> None:
        config = WRANGLER.read_text(encoding="utf-8")
        self.assertIn('name = "jeeb-staging-host-router"', config)
        self.assertIn('main = "jeeb-staging-router.mjs"', config)
        self.assertIn("workers_dev = false", config)
        self.assertEqual(config.count("custom_domain = true"), 2)
        self.assertIn('pattern = "app.jeeb.fds-1.com"', config)
        self.assertIn('pattern = "cms.jeeb.fds-1.com"', config)
        self.assertNotIn("ORIGIN_KEY", config)


if __name__ == "__main__":
    unittest.main()
