#!/usr/bin/env python3
"""Authenticate the incumbent staging token; seal only to GitHub's org key."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from nacl.public import PublicKey, SealedBox
import verify_cloudflare_org_auth as auth

ORG_PUBLIC_KEY = "I9rr0LBjzYIHSNBWSnbKF9caF/5pxqWbZ7dXPBb8rQk="
ORG_KEY_ID = "3380204578043523366"
DESTINATION = "JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_API_TOKEN"


def seal(token):
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,16384}", token):
        raise ValueError("format")
    # Discover identity from the existing explicitly selected staging source.
    result = auth.get_json(auth.VERIFY_PATH, token).get("result", {})
    if result.get("status") != "active" or not isinstance(result.get("id"), str):
        raise ValueError("inactive")
    pin = hashlib.sha256(result["id"].encode()).hexdigest()
    # Existing validator asserts the exact staging account, Worker and domains.
    auth.validate(token, pin)
    return {
        "schema": 1,
        "organization": "olivium-dev",
        "repository": "olivium-dev/jeeb-infrastructure",
        "source_environment": "staging",
        "source_name": "CLOUDFLARE_API_TOKEN",
        "destination": DESTINATION,
        "key_id": ORG_KEY_ID,
        "encrypted_value": base64.b64encode(
            SealedBox(PublicKey(base64.b64decode(ORG_PUBLIC_KEY))).encrypt(token.encode())
        ).decode(),
        "token_id_sha256": pin,
    }


def main():
    try:
        token = os.environ.pop("SOURCE_CLOUDFLARE_TOKEN", "")
        if (sys.argv[1:] or os.environ.get("GITHUB_REPOSITORY") != "olivium-dev/jeeb-infrastructure"
                or os.environ.get("GITHUB_REF") != "refs/heads/main"
                or os.environ.get("GITHUB_ACTOR") != "oudaykhaled"
                or os.environ.get("GITHUB_REF_PROTECTED") != "true"
                or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
            raise ValueError("context")
        sha = os.environ.get("GITHUB_SHA", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha != os.environ.get("EXPECTED_SHA"):
            raise ValueError("revision")
        envelope = seal(token)
        token = ""
        envelope.update(commit=sha, run_id=os.environ["GITHUB_RUN_ID"], run_attempt=os.environ["GITHUB_RUN_ATTEMPT"])
        destination = Path(os.environ["RUNNER_TEMP"]) / "cloudflare-github-sealed.json"
        with destination.open("x") as out:
            json.dump(envelope, out)
        print("existing-cloudflare-seal:PASS")
        return 0
    except Exception:
        print("existing-cloudflare-seal:FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
