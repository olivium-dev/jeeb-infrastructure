import base64
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
from nacl.public import PrivateKey, SealedBox

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import seal_existing_cloudflare_secret as subject

CANARY = "SYNTHETIC-CLOUDFLARE-CANARY-NEVER-EMIT"


class SealingTests(unittest.TestCase):
    def test_ciphertext_is_decryptable_only_by_destination_key(self):
        key = PrivateKey.generate()
        public = base64.b64encode(bytes(key.public_key)).decode()
        with mock.patch.object(subject, "ORG_PUBLIC_KEY", public), \
             mock.patch.object(subject.auth, "get_json", return_value={"result": {"status": "active", "id": "test-id"}}), \
             mock.patch.object(subject.auth, "validate") as validate:
            envelope = subject.seal(CANARY)
        validate.assert_called_once()
        self.assertNotIn(CANARY, str(envelope))
        sealed = base64.b64decode(envelope["encrypted_value"])
        self.assertEqual(SealedBox(key).decrypt(sealed).decode(), CANARY)
        with self.assertRaises(Exception):
            SealedBox(PrivateKey.generate()).decrypt(sealed)

    def test_rejects_missing_source_before_network(self):
        with mock.patch.object(subject.auth, "get_json") as get:
            for token in ("", "x", CANARY + "\n"):
                with self.assertRaises(ValueError):
                    subject.seal(token)
            get.assert_not_called()

    def test_wrong_resource_prevents_encryption(self):
        with mock.patch.object(subject.auth, "get_json", return_value={"result": {"status": "active", "id": "test-id"}}), \
             mock.patch.object(subject.auth, "validate", side_effect=ValueError(CANARY)), \
             mock.patch.object(subject, "SealedBox") as encrypt:
            with self.assertRaises(ValueError):
                subject.seal(CANARY)
            encrypt.assert_not_called()

    def test_untrusted_context_never_authenticates_or_emits_source(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"SOURCE_CLOUDFLARE_TOKEN": CANARY}, clear=True), \
             mock.patch.object(subject, "seal") as seal, \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(subject.main(), 1)
            seal.assert_not_called()
            self.assertNotIn("SOURCE_CLOUDFLARE_TOKEN", os.environ)
        self.assertEqual(output.getvalue(), "existing-cloudflare-seal:FAIL\n")


if __name__ == "__main__":
    unittest.main()
