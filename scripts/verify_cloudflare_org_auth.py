#!/usr/bin/env python3
"""Verify the exact staging token and Worker domains using read-only HTTPS."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import ssl
import sys

ACCOUNT_ID = "58198ae51392a2cc2d391867fb65da7e"
ZONE_ID = "f277cc7892442f400198ddc947a5a3bd"
WORKER_NAME = "jeeb-staging-host-router"
HOSTNAMES = {"app.jeeb.fds-1.com", "cms.jeeb.fds-1.com"}
VERIFY_PATH = "/client/v4/user/tokens/verify"
DOMAINS_PATH = (f"/client/v4/accounts/{ACCOUNT_ID}/workers/domains"
                f"?service={WORKER_NAME}&zone_id={ZONE_ID}")
MAX_RESPONSE_BYTES = 65536
MAX_CREDENTIAL_BYTES = 16384


class ValidationError(ValueError):
    pass


def get_json(path: str, token: str) -> dict:
    if path not in (VERIFY_PATH, DOMAINS_PATH):
        raise ValidationError("endpoint")
    connection = http.client.HTTPSConnection(
        "api.cloudflare.com", timeout=15, context=ssl.create_default_context()
    )
    try:
        connection.request("GET", path, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json",
        })
        response = connection.getresponse()
        if response.status != 200:
            raise ValidationError("authentication")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValidationError("response-size")
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("success") is not True:
            raise ValidationError("response-schema")
        return value
    finally:
        connection.close()


def validate(token: str, expected_token_id_sha256: str) -> None:
    # Reject missing identity metadata before sending a credential anywhere.
    if not re.fullmatch(r"[0-9a-f]{64}", expected_token_id_sha256):
        raise ValidationError("identity-pin")
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,16384}", token):
        raise ValidationError("credential-format")
    verification = get_json(VERIFY_PATH, token).get("result")
    if not isinstance(verification, dict) or verification.get("status") != "active":
        raise ValidationError("inactive")
    token_id = verification.get("id")
    if not isinstance(token_id, str) or not hmac.compare_digest(
        hashlib.sha256(token_id.encode()).hexdigest(), expected_token_id_sha256
    ):
        raise ValidationError("identity")
    domains = get_json(DOMAINS_PATH, token).get("result")
    if (
        not isinstance(domains, list)
        or len(domains) != 2
        or any(not isinstance(domain, dict) for domain in domains)
        or {domain.get("hostname") for domain in domains} != HOSTNAMES
        or any(domain.get("zone_id") != ZONE_ID for domain in domains)
        or any(domain.get("zone_name") != "fds-1.com" for domain in domains)
        or any(domain.get("service") != WORKER_NAME for domain in domains)
        or any(domain.get("environment", "") not in ("", "production") for domain in domains)
    ):
        # Cloudflare's default Worker environment label is 'production'; this
        # Worker and these two hostnames are exclusively Jeeb staging resources.
        raise ValidationError("resource")


def main() -> int:
    try:
        if sys.argv[1:]:
            raise ValidationError("arguments")
        raw = sys.stdin.buffer.read(MAX_CREDENTIAL_BYTES + 1)
        if len(raw) > MAX_CREDENTIAL_BYTES:
            raise ValidationError("credential-size")
        validate(raw.decode("ascii"), os.environ.pop("EXPECTED_CLOUDFLARE_TOKEN_ID_SHA256", ""))
    except Exception:
        print("cloudflare-org-auth:FAIL")
        return 1
    print("cloudflare-org-auth:PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
