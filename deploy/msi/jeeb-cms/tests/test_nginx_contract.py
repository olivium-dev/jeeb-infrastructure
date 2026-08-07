#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import re
import subprocess
import unittest
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[1] / "nginx" / "backoffice.jeeb.fds-1.com.conf"
CONTAINER_CONFIG = Path(__file__).resolve().parents[1] / "nginx" / "container-nginx.conf"
DOCKER_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docker-nginx.sh"
CONTAINER_VALIDATOR = (
    Path(__file__).resolve().parents[1] / "scripts" / "validate-nginx-container.py"
)
SYSTEMD_DIR = Path(__file__).resolve().parents[1] / "systemd"


class NginxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CONFIG.read_text(encoding="utf-8")

    def test_private_listener_and_backoffice_host(self) -> None:
        self.assertIn("listen 127.0.0.1:10100;", self.text)
        self.assertNotRegex(self.text, r"(?m)^\s*listen\s+(?:0\.0\.0\.0:)?10100;")
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

    def test_no_sudo_container_preserves_loopback_and_read_only_contract(self) -> None:
        container_config = CONTAINER_CONFIG.read_text(encoding="utf-8")
        script = DOCKER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("include /etc/nginx/conf.d/jeeb-cms.conf;", container_config)
        self.assertIn("pid /tmp/nginx.pid;", container_config)
        for fragment in (
            "--network host",
            "--restart no",
            "--read-only",
            "--runtime runc",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
            "--user 101:101",
            'dst=/opt/jeeb-cms,readonly',
            "@sha256:",
            "validate_active_release",
            "verify_container_contract false",
            "verify_container_contract true",
        ):
            self.assertIn(fragment, script)
        self.assertNotIn("--publish", script)
        self.assertNotIn("--restart unless-stopped", script)

    def test_boot_dependencies_fail_closed_before_nginx(self) -> None:
        native_drop_in = (
            SYSTEMD_DIR / "nginx.service.d" / "jeeb-cms-release.conf"
        ).read_text(encoding="utf-8")
        docker_release_unit = (
            SYSTEMD_DIR / "jeeb-cms-docker-release.service"
        ).read_text(encoding="utf-8")
        docker_unit = (SYSTEMD_DIR / "jeeb-cms-nginx.service").read_text(
            encoding="utf-8"
        )
        for unit in (native_drop_in,):
            self.assertIn("Requires=", unit)
            self.assertIn("jeeb-cms-release.service", unit)
            self.assertIn("After=", unit)
        self.assertIn("jeeb-cms-docker-release.service", docker_unit)
        self.assertIn("After=docker.service jeeb-cms-docker-release.service", docker_unit)
        self.assertIn("Before=jeeb-cms-nginx.service", docker_release_unit)
        self.assertIn("verify-current.sh", docker_release_unit)
        self.assertIn("docker-nginx.sh boot", docker_unit)
        self.assertNotIn("Restart=", docker_unit)


class ContainerRuntimeContractTests(unittest.TestCase):
    image = "nginx@sha256:" + "a" * 64
    base_record = {
        "Config": {
            "Image": image,
            "User": "101:101",
            "Entrypoint": ["nginx"],
            "Cmd": ["-g", "daemon off;"],
            "StopSignal": "SIGQUIT",
        },
        "HostConfig": {
            "NetworkMode": "host",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "RestartPolicy": {"Name": "no"},
            "CapDrop": ["ALL"],
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges"],
            "Devices": [],
            "DeviceRequests": [],
            "DeviceCgroupRules": [],
            "PortBindings": {},
            "PublishAllPorts": False,
            "PidMode": "",
            "IpcMode": "private",
            "UTSMode": "",
            "CgroupnsMode": "private",
            "UsernsMode": "",
            "GroupAdd": [],
            "Runtime": "runc",
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=32m,mode=0700,uid=101,gid=101"
            },
            "LogConfig": {
                "Type": "local",
                "Config": {"max-size": "10m", "max-file": "3"},
            },
        },
        "State": {"Running": True},
        "Mounts": [
            {
                "Type": "bind",
                "Destination": "/opt/jeeb-cms",
                "Source": "/srv/cms",
                "RW": False,
            },
            {
                "Type": "bind",
                "Destination": "/etc/nginx/nginx.conf",
                "Source": "/srv/nginx.conf",
                "RW": False,
            },
            {
                "Type": "bind",
                "Destination": "/etc/nginx/conf.d/jeeb-cms.conf",
                "Source": "/srv/site.conf",
                "RW": False,
            },
        ],
    }

    def validate(self, record: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(CONTAINER_VALIDATOR),
                "--expected-running",
                "true",
                "--image",
                self.image,
                "--cms-root",
                "/srv/cms",
                "--main-config",
                "/srv/nginx.conf",
                "--site-config",
                "/srv/site.conf",
            ],
            input=json.dumps([record]),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_complete_runtime_contract_is_accepted(self) -> None:
        self.assertEqual(self.validate(copy.deepcopy(self.base_record)).returncode, 0)

    def test_each_security_boundary_is_rechecked(self) -> None:
        mutations = (
            lambda value: value["HostConfig"].update(NetworkMode="bridge"),
            lambda value: value["HostConfig"].update(ReadonlyRootfs=False),
            lambda value: value["HostConfig"].update(Privileged=True),
            lambda value: value["HostConfig"]["RestartPolicy"].update(Name="always"),
            lambda value: value["HostConfig"].update(CapDrop=[]),
            lambda value: value["HostConfig"].update(CapAdd=["NET_ADMIN"]),
            lambda value: value["HostConfig"].update(SecurityOpt=[]),
            lambda value: value["HostConfig"].update(
                SecurityOpt=["no-new-privileges", "seccomp=unconfined"]
            ),
            lambda value: value["HostConfig"].update(
                Devices=[{"PathOnHost": "/dev/null", "PathInContainer": "/dev/x"}]
            ),
            lambda value: value["HostConfig"].update(PortBindings={"80/tcp": [{}]}),
            lambda value: value["HostConfig"].update(PidMode="host"),
            lambda value: value["HostConfig"].update(IpcMode="host"),
            lambda value: value["HostConfig"].update(UTSMode="host"),
            lambda value: value["HostConfig"].update(CgroupnsMode="host"),
            lambda value: value["HostConfig"].update(UsernsMode="host"),
            lambda value: value["HostConfig"].update(GroupAdd=["0"]),
            lambda value: value["HostConfig"].update(Runtime="evil"),
            lambda value: value["HostConfig"].update(Tmpfs={}),
            lambda value: value["HostConfig"].update(
                Tmpfs={
                    **value["HostConfig"]["Tmpfs"],
                    "/etc/nginx/conf.d": "rw",
                }
            ),
            lambda value: value["HostConfig"]["LogConfig"].update(Type="json-file"),
            lambda value: value["Config"].update(Image="nginx:latest"),
            lambda value: value["Config"].update(User="0:0"),
            lambda value: value["Config"].update(Cmd=["sleep", "infinity"]),
            lambda value: value["State"].update(Running=False),
            lambda value: value["Mounts"][0].update(RW=True),
            lambda value: value["Mounts"].append(
                {
                    "Type": "volume",
                    "Destination": "/var/cache/nginx",
                    "Source": "/var/lib/docker/volumes/cache/_data",
                    "RW": True,
                }
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                record = copy.deepcopy(self.base_record)
                mutate(record)
                self.assertNotEqual(self.validate(record).returncode, 0)


if __name__ == "__main__":
    unittest.main()
