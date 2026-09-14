import base64
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nacl.public import PrivateKey, SealedBox


SCRIPT = Path(__file__).resolve().parents[1] / "seal_existing_msi_transport.py"
SPEC = importlib.util.spec_from_file_location("subject", SCRIPT)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
PASSWORD = "SYNTHETIC-PASSWORD-CANARY-NEVER-EMIT"
KNOWN_HOSTS = "ssh-msi.example ssh-ed25519 SYNTHETIC-PUBLIC-HOST-KEY"


class MsiTransportSealingTests(unittest.TestCase):
    def test_both_values_are_decryptable_only_by_destination_key(self):
        private = PrivateKey.generate()
        public = base64.b64encode(bytes(private.public_key)).decode()
        values = {
            "SOURCE_MSI_SSH_PASSWORD": PASSWORD,
            "SOURCE_MSI_SSH_KNOWN_HOSTS": KNOWN_HOSTS,
        }
        with mock.patch.object(subject, "ORG_PUBLIC_KEY", public):
            result = subject.seal(values)
        self.assertEqual(values, {})
        self.assertEqual(result["visibility"], "selected")
        self.assertEqual(result["selected_repositories"], subject.REPOSITORIES)
        self.assertEqual({item["destination"] for item in result["secrets"]},
                         {"MSI_SSH_PASSWORD", "MSI_SSH_KNOWN_HOSTS"})
        encoded = str(result)
        self.assertNotIn(PASSWORD, encoded)
        self.assertNotIn(KNOWN_HOSTS, encoded)
        recovered = {
            item["destination"]: SealedBox(private).decrypt(
                base64.b64decode(item["encrypted_value"])
            ).decode()
            for item in result["secrets"]
        }
        self.assertEqual(recovered, {
            "MSI_SSH_PASSWORD": PASSWORD,
            "MSI_SSH_KNOWN_HOSTS": KNOWN_HOSTS,
        })
        with self.assertRaises(Exception):
            SealedBox(PrivateKey.generate()).decrypt(
                base64.b64decode(result["secrets"][0]["encrypted_value"])
            )

    def test_missing_or_oversized_source_fails_before_encryption(self):
        for password in ("", "x" * 65537):
            values = {
                "SOURCE_MSI_SSH_PASSWORD": password,
                "SOURCE_MSI_SSH_KNOWN_HOSTS": KNOWN_HOSTS,
            }
            with self.subTest(size=len(password)), mock.patch.object(subject, "SealedBox") as box:
                with self.assertRaises(ValueError):
                    subject.seal(values)
                box.return_value.encrypt.assert_not_called()

    def test_wrong_context_removes_sources_and_emits_no_value(self):
        output = io.StringIO()
        environment = {
            "SOURCE_MSI_SSH_PASSWORD": PASSWORD,
            "SOURCE_MSI_SSH_KNOWN_HOSTS": KNOWN_HOSTS,
        }
        with mock.patch.dict(os.environ, environment, clear=True), \
             mock.patch.object(subject, "seal") as seal, \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(subject.main(), 1)
            seal.assert_not_called()
            self.assertNotIn("SOURCE_MSI_SSH_PASSWORD", os.environ)
            self.assertNotIn("SOURCE_MSI_SSH_KNOWN_HOSTS", os.environ)
        self.assertEqual(output.getvalue(), "existing-msi-transport-seal:FAIL\n")

    def test_main_writes_only_ciphertext_envelope(self):
        private = PrivateKey.generate()
        environment = {
            "SOURCE_MSI_SSH_PASSWORD": PASSWORD,
            "SOURCE_MSI_SSH_KNOWN_HOSTS": KNOWN_HOSTS,
            "GITHUB_REPOSITORY": "olivium-dev/jeeb-infrastructure",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_ACTOR": "oudaykhaled",
            "GITHUB_TRIGGERING_ACTOR": "oudaykhaled",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": "a" * 40,
            "EXPECTED_SHA": "a" * 40,
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.dict(os.environ, {**environment, "RUNNER_TEMP": directory}, clear=True), \
             mock.patch.object(subject, "ORG_PUBLIC_KEY", base64.b64encode(bytes(private.public_key)).decode()), \
             mock.patch.object(subject.sys, "argv", [str(SCRIPT)]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(), 0)
            body = (Path(directory) / "msi-transport-github-sealed.json").read_text()
        self.assertNotIn(PASSWORD, body)
        self.assertNotIn(KNOWN_HOSTS, body)


if __name__ == "__main__":
    unittest.main()
