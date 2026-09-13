#!/usr/bin/env python3
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import sys
import unittest
import urllib.parse
from unittest import mock

import validate_cloudflare_credential_only as subject


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return json.dumps(self.body).encode()


class Tests(unittest.TestCase):
    def token_fd(self, token):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, token.encode())
        os.close(write_fd)
        return read_fd

    def test_exact_token_and_zone_identity_read_only(self):
        token = "JEEB-SYNTHETIC-CLOUDFLARE-TOKEN-CANARY"
        token_id = "synthetic-token-id"
        read_fd = self.token_fd(token)
        os.environ["EXPECTED_CLOUDFLARE_TOKEN_ID_SHA256"] = hashlib.sha256(
            token_id.encode()
        ).hexdigest()
        test = self

        class Opener:
            def open(self, request, timeout):
                test.assertEqual(request.method, "GET")
                test.assertEqual(timeout, 15)
                if request.full_url.endswith("/user/tokens/verify"):
                    return Response({
                        "success": True,
                        "result": {"id": token_id, "status": "active"},
                    })
                test.assertEqual(
                    request.full_url,
                    f"https://api.cloudflare.com/client/v4/zones/{subject.ZONE_ID}",
                )
                return Response({
                    "success": True,
                    "result": {
                        "id": subject.ZONE_ID,
                        "name": subject.ZONE_NAME,
                        "account": {"id": subject.ACCOUNT_ID},
                    },
                })

        with mock.patch.object(subject.urllib.request, "build_opener", return_value=Opener()):
            subject.validate_live(read_fd)
        os.close(read_fd)

    def test_wrong_token_identity_fails_before_zone_read(self):
        token = "JEEB-SYNTHETIC-CLOUDFLARE-TOKEN-CANARY"
        read_fd = self.token_fd(token)
        os.environ["EXPECTED_CLOUDFLARE_TOKEN_ID_SHA256"] = "0" * 64

        class Opener:
            calls = 0

            def open(self, request, timeout):
                self.calls += 1
                return Response({
                    "success": True,
                    "result": {"id": "different-token", "status": "active"},
                })

        opener = Opener()
        with mock.patch.object(subject.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(subject.ValidationError, "wrong-environment-identity"):
                subject.validate_live(read_fd)
        os.close(read_fd)
        self.assertEqual(opener.calls, 1)

    def test_failure_never_emits_canary_or_encodings(self):
        canary = "JEEB-SYNTHETIC-CLOUDFLARE-CANARY-DO-NOT-EMIT"
        read_fd = self.token_fd(canary)
        os.environ["EXPECTED_CLOUDFLARE_TOKEN_ID_SHA256"] = "0" * 64
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["validator", "--credential-fd", str(read_fd)]), \
             mock.patch.object(subject, "get_json", side_effect=subject.ValidationError("provider-authentication")), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = subject.main()
        os.close(read_fd)
        rendered = output.getvalue()
        self.assertEqual(result, 2)
        for representation in (
            canary,
            base64.b64encode(canary.encode()).decode(),
            urllib.parse.quote(canary),
            json.dumps(canary),
        ):
            self.assertNotIn(representation, rendered)


if __name__ == "__main__":
    unittest.main()
