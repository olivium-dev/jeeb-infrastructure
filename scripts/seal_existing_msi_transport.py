#!/usr/bin/python3 -I
"""Seal the two incumbent MSI transport values to GitHub's organization key."""
import base64
import json
import os
from pathlib import Path
import re
import sys

from nacl.public import PublicKey, SealedBox


ORG_PUBLIC_KEY = "I9rr0LBjzYIHSNBWSnbKF9caF/5pxqWbZ7dXPBb8rQk="
ORG_KEY_ID = "3380204578043523366"
ORGANIZATION = "olivium-dev"
DESTINATIONS = (
    ("SOURCE_MSI_SSH_PASSWORD", "MSI_SSH_PASSWORD"),
    ("SOURCE_MSI_SSH_KNOWN_HOSTS", "MSI_SSH_KNOWN_HOSTS"),
)
REPOSITORIES = {
    "olivium-dev/chat-service": 944428103,
    "olivium-dev/push-notification": 988257631,
    "olivium-dev/user-management": 864937800,
}


def require(value):
    if not value:
        raise ValueError("contract")


def seal(values):
    require(set(values) == {source for source, _ in DESTINATIONS})
    key = PublicKey(base64.b64decode(ORG_PUBLIC_KEY, validate=True))
    box = SealedBox(key)
    envelopes = []
    for source, destination in DESTINATIONS:
        value = values.pop(source)
        require(isinstance(value, str) and 0 < len(value.encode()) <= 65536 and "\x00" not in value)
        envelopes.append({
            "source_repository": "olivium-dev/jeeb-infrastructure",
            "source_name": destination,
            "destination": destination,
            "key_id": ORG_KEY_ID,
            "encrypted_value": base64.b64encode(box.encrypt(value.encode())).decode(),
        })
        value = ""
    return {
        "schema": 1,
        "organization": ORGANIZATION,
        "visibility": "selected",
        "selected_repositories": REPOSITORIES,
        "secrets": envelopes,
    }


def main():
    values = {source: os.environ.pop(source, "") for source, _ in DESTINATIONS}
    try:
        require(not sys.argv[1:])
        require(os.environ.get("GITHUB_REPOSITORY") == "olivium-dev/jeeb-infrastructure")
        require(os.environ.get("GITHUB_REF") == "refs/heads/main")
        require(os.environ.get("GITHUB_REF_PROTECTED") == "true")
        require(os.environ.get("GITHUB_ACTOR") == "oudaykhaled")
        require(os.environ.get("GITHUB_TRIGGERING_ACTOR") == "oudaykhaled")
        require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch")
        revision = os.environ.get("GITHUB_SHA", "")
        require(re.fullmatch(r"[0-9a-f]{40}", revision))
        require(revision == os.environ.get("EXPECTED_SHA"))
        result = seal(values)
        result.update(commit=revision, run_id=os.environ["GITHUB_RUN_ID"],
                      run_attempt=os.environ["GITHUB_RUN_ATTEMPT"])
        destination = Path(os.environ["RUNNER_TEMP"]) / "msi-transport-github-sealed.json"
        with destination.open("x", encoding="utf-8") as output:
            json.dump(result, output, sort_keys=True, separators=(",", ":"))
        print("existing-msi-transport-seal:PASS")
        return 0
    except Exception:
        print("existing-msi-transport-seal:FAIL")
        return 1
    finally:
        values.clear()


if __name__ == "__main__":
    raise SystemExit(main())
