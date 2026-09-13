#!/usr/bin/env python3
"""Validate the staging Cloudflare token with exact read-only requests."""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import sys
import urllib.error
import urllib.request


ACCOUNT_ID = "58198ae51392a2cc2d391867fb65da7e"
ZONE_ID = "f277cc7892442f400198ddc947a5a3bd"
ZONE_NAME = "fds-1.com"
MAX_RESPONSE_BYTES = 65536
MAX_CREDENTIAL_BYTES = 16384


class ValidationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValidationError("redirect-rejected")


def get_json(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        ).open(request, timeout=15) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValidationError):
        raise ValidationError("provider-authentication") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValidationError("provider-response-size")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationError("provider-response-schema") from None
    if not isinstance(value, dict):
        raise ValidationError("provider-response-schema")
    return value


def read_credential_fd(fd: int) -> str:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(fd, min(4096, MAX_CREDENTIAL_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_CREDENTIAL_BYTES:
            raise ValidationError("credential-size")
    try:
        return b"".join(chunks).decode()
    except UnicodeDecodeError:
        raise ValidationError("credential-format") from None


def validate_live(fd: int) -> None:
    token = read_credential_fd(fd)
    expected_token_id_sha256 = os.environ.pop(
        "EXPECTED_CLOUDFLARE_TOKEN_ID_SHA256", ""
    )
    if len(token) < 20:
        raise ValidationError("credential-missing")
    verification = get_json("https://api.cloudflare.com/client/v4/user/tokens/verify", token)
    if (
        verification.get("success") is not True
        or not isinstance(verification.get("result"), dict)
        or verification["result"].get("status") != "active"
    ):
        raise ValidationError("provider-token-inactive")
    if (
        not isinstance(verification["result"].get("id"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_token_id_sha256)
        or not hmac.compare_digest(
            hashlib.sha256(verification["result"]["id"].encode()).hexdigest(),
            expected_token_id_sha256,
        )
    ):
        raise ValidationError("wrong-environment-identity")
    zone = get_json(f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}", token)
    token = ""
    result = zone.get("result") if isinstance(zone, dict) else None
    if (
        zone.get("success") is not True
        or not isinstance(result, dict)
        or result.get("id") != ZONE_ID
        or result.get("name") != ZONE_NAME
        or not isinstance(result.get("account"), dict)
        or result["account"].get("id") != ACCOUNT_ID
    ):
        raise ValidationError("wrong-environment-resource")


def self_test() -> int:
    canary = "JEEB-SYNTHETIC-CLOUDFLARE-CANARY-DO-NOT-EMIT"
    rendered = "credential-validation-self-test:PASS:fixed-output"
    if canary in rendered:
        return 2
    print(rendered)
    return 0


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    if len(sys.argv) != 3 or sys.argv[1] != "--credential-fd" or not sys.argv[2].isdigit():
        print("credential-validation:FAIL:arguments", file=sys.stderr)
        return 2
    try:
        validate_live(int(sys.argv[2]))
    except ValidationError as error:
        print(f"credential-validation:FAIL:{error.code}", file=sys.stderr)
        return 2
    except Exception:
        print("credential-validation:FAIL:closed", file=sys.stderr)
        return 2
    print("credential-validation:PASS:cloudflare:staging")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
