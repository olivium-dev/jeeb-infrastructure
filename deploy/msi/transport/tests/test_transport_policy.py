from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUDOERS = ROOT / "jeeb-msi-runtime-activation.sudoers"
README = ROOT / "README.md"


class MsiRuntimeTransportPolicyTests(unittest.TestCase):
    def test_sudoers_has_only_exact_service_helper_commands(self):
        lines = [
            line.strip()
            for line in SUDOERS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(14, len(lines))
        allowed_helpers = {
            "/usr/local/sbin/jeeb-msi-chat-firebase-admin": {
                "stage", "activate"
            },
            "/usr/local/sbin/jeeb-msi-push-firebase-admin": {
                "--preflight", "--activate"
            },
            "/usr/local/sbin/jeeb-msi-user-management-firebase-admin": {
                "--mode preflight", "--mode activate"
            },
            "/usr/local/sbin/jeeb-msi-user-management-smtp-admin": {
                "preflight", "stage", "activate"
            },
            "/usr/local/sbin/jeeb-msi-otp-twilio-admin": {
                "stage", "activate"
            },
            "/usr/local/sbin/jeeb-msi-gateway-firebase-diagnostics-admin": {
                "preflight", "stage", "activate"
            },
        }
        seen = {name: set() for name in allowed_helpers}
        pattern = re.compile(
            r"^msi-access ALL=\(root\) NOPASSWD: "
            r"(/usr/local/sbin/[a-z0-9-]+) (.+)$"
        )
        for line in lines:
            match = pattern.fullmatch(line)
            self.assertIsNotNone(match)
            helper, arguments = match.groups()
            self.assertIn(helper, allowed_helpers)
            self.assertIn(arguments, allowed_helpers[helper])
            self.assertNotIn(arguments, seen[helper])
            seen[helper].add(arguments)
        self.assertEqual(allowed_helpers, seen)

    def test_policy_cannot_delegate_a_shell_interpreter_or_service_manager(self):
        source = SUDOERS.read_text(encoding="utf-8")
        for forbidden in (
            "NOPASSWD: ALL", "*", "/bin/sh", "/bin/bash", "/usr/bin/env",
            "/usr/bin/python", "/bin/systemctl", "/usr/bin/systemctl",
            "/usr/bin/tee", "sudoedit",
        ):
            self.assertNotIn(forbidden, source)

    def test_documented_transport_keeps_credentials_on_stdin_and_serializes(self):
        source = README.read_text(encoding="utf-8")
        for required in (
            "Credential values enter only on stdin",
            "/run/jeeb-msi-service-deploy.lock",
            "strict host-key checking",
            "service-specific helper restores only the preserved",
            "Do not treat an HTTP 200 from the old project as completion",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
