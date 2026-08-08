#!/usr/bin/env python3

from __future__ import annotations

import re
import unittest
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[1] / "nginx" / "backoffice.jeeb.fds-1.com.conf"
SYSTEMD_DIR = Path(__file__).resolve().parents[1] / "systemd"


class NginxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CONFIG.read_text(encoding="utf-8")

    def test_private_listener_and_backoffice_host(self) -> None:
        self.assertIn("listen 80;", self.text)
        self.assertNotIn("listen 127.0.0.1:10100;", self.text)
        self.assertIn("server_name backoffice.jeeb.fds-1.com;", self.text)
        self.assertIn("root /opt/jeeb-cms/current;", self.text)

    def test_gateway_is_same_origin_and_targets_native_msi_gateway(self) -> None:
        gateway = re.search(r"location /gateway/ \{(?P<body>.*?)\n\s*\}", self.text, re.DOTALL)
        self.assertIsNotNone(gateway)
        body = gateway.group("body")
        self.assertIn("proxy_pass http://127.0.0.1:10090/;", body)
        self.assertIn("proxy_hide_header Cache-Control;", body)
        self.assertIn("proxy_buffering off;", body)
        self.assertIn("proxy_set_header Host $host;", body)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", body)
        self.assertNotRegex(body, r"proxy_pass\s+https?://(?!127\.0\.0\.1:10090/)")
        self.assertNotIn("proxy_cookie_domain", body)
        self.assertNotIn("proxy_cookie_path", body)

    def test_public_browser_ingress_never_exposes_owner_callbacks(self) -> None:
        self.assertRegex(
            self.text,
            r"location ~\* \^/gateway/svc-callbacks\(\?:/\|\$\) \{\s*return 404;\s*\}",
        )
        self.assertRegex(
            self.text,
            r"location ~\* \^/gateway/v1/case-events/\?\$ \{\s*return 404;\s*\}",
        )
        self.assertLess(
            self.text.index("location ~* ^/gateway/svc-callbacks"),
            self.text.index("location /gateway/ {"),
        )

    def test_mf_files_fail_closed_before_spa_fallback(self) -> None:
        self.assertRegex(self.text, r"location /mf/ \{\s*try_files \$uri =404;\s*\}")
        self.assertRegex(self.text, r"location ~ \(\^\|/\)\\\. \{\s*return 404;\s*\}")
        self.assertRegex(self.text, r"location / \{\s*try_files \$uri \$uri/ /index\.html;\s*\}")
        self.assertLess(self.text.index("location /mf/"), self.text.index("location / {"))
        self.assertLess(
            self.text.index("location ~ (^|/)\\."),
            self.text.index("location ~* \\.(?:css|js|map"),
        )

    def test_health_release_cache_and_security_contract(self) -> None:
        for fragment in (
            "location = /healthz",
            'return 200 "healthy\\n";',
            "location = /release.json",
            "location = /SHA256SUMS",
            'default                                      "no-store";',
            '"~*\\.[0-9a-f]{8,}\\.(?:css|js)$"',
            '"public, max-age=31536000, immutable"',
            "Content-Security-Policy",
            "connect-src 'self'",
            "script-src 'self'",
            "frame-ancestors 'none'",
            "Strict-Transport-Security",
            'X-Content-Type-Options "nosniff"',
            'X-Frame-Options "DENY"',
            "access_log off;",
            "error_log /dev/null crit;",
        ):
            self.assertIn(fragment, self.text)
        self.assertNotIn("unsafe-eval", self.text)

    def test_boot_dependencies_fail_closed_before_nginx(self) -> None:
        native_drop_in = (
            SYSTEMD_DIR / "nginx.service.d" / "jeeb-cms-release.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("Requires=", native_drop_in)
        self.assertIn("jeeb-cms-release.service", native_drop_in)
        self.assertIn("After=", native_drop_in)


if __name__ == "__main__":
    unittest.main()
