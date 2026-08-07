#!/usr/bin/env python3
"""Validate an immutable Jeeb CMS release directory without trusting its contents."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import socket
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote_to_bytes, urlsplit


RELEASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST_LINE_RE = re.compile(r"([0-9a-fA-F]{64}) [ *](.+)\Z")
WEB_ORIGIN_RE = re.compile(
    rb"(?:(?:https?|wss?)://|(?<=[\"'`(=])//)"
    rb"(?P<authority>\[[^\]\s\"'<>/]+\]|[^\s\"'<>/?#]+)",
    re.IGNORECASE,
)
SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")
RAW_STORAGE_URL_RE = re.compile(rb"(?:s3|gs|r2|az)://[^\s\"'<>]+", re.IGNORECASE)
SIGNED_HTTP_URL_RE = re.compile(
    rb"(?:(?:https?|wss?):)?//[^\s\"'<>?]+[^\s\"'<>]*[?&](?:"
    rb"x-amz-(?:algorithm|credential|signature)|"
    rb"x-goog-(?:algorithm|credential|signature)|"
    rb"awsaccesskeyid|sig|signature)=",
    re.IGNORECASE,
)
BACKSLASH_WEB_URL_RE = re.compile(
    rb"(?:https?|wss?):[\\/]+[^\s\"'<>]+", re.IGNORECASE
)
SOURCE_MAP_MARKER_RE = re.compile(rb"sourceMappingURL\s*=", re.IGNORECASE)
PRIVATE_KEY_RE = re.compile(
    rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY(?: BLOCK)?-----"
)
REQUIRED_FILES = {
    "index.html",
    "release.json",
    "mf/cases/remoteEntry.js",
    "mf/deliveries/remoteEntry.js",
    "mf/settlements/remoteEntry.js",
}
SAFE_LIBRARY_LOCALHOST_PATTERNS = (
    # Axios browser-environment origin fallback. In a browser the left side is
    # the current document URL; localhost is never a configured service URL.
    re.compile(
        rb'[A-Za-z_$][\w$]*&&window\.location\.href\|\|"http://localhost"'
    ),
    # React Router memory-history URL construction for a relative path.
    re.compile(
        rb'createURL:[A-Za-z_$][\w$]*=>new URL\('
        rb'[A-Za-z_$][\w$]*\([A-Za-z_$][\w$]*\),"http://localhost"\)'
    ),
    # React Router DOM origin selection: the placeholder is immediately
    # replaced with the real window origin/href when a window is present.
    re.compile(
        rb'function [A-Za-z_$][\w$]*\('
        rb'[A-Za-z_$][\w$]*,[A-Za-z_$][\w$]*,[A-Za-z_$][\w$]*=!1\)\{'
        rb'let [A-Za-z_$][\w$]*="http://localhost";'
        rb'[A-Za-z_$][\w$]*&&\('
        rb'[A-Za-z_$][\w$]*="null"!==[A-Za-z_$][\w$]*\.location\.origin\?'
        rb'[A-Za-z_$][\w$]*\.location\.origin:'
        rb'[A-Za-z_$][\w$]*\.location\.href\)'
    ),
    # React Router relative-path decomposition. The resulting URL is reduced
    # immediately to pathname/search/hash and is never used as a fetch origin.
    re.compile(
        rb'let [A-Za-z_$][\w$]*="string"==typeof [A-Za-z_$][\w$]*\?'
        rb'[A-Za-z_$][\w$]*:[A-Za-z_$][\w$]*\([A-Za-z_$][\w$]*\);'
        rb'[A-Za-z_$][\w$]*=[A-Za-z_$][\w$]*\.replace\(/ \$/,"%20"\);'
        rb'let [A-Za-z_$][\w$]*=[A-Za-z_$][\w$]*\.test\([A-Za-z_$][\w$]*\)\?'
        rb'new URL\([A-Za-z_$][\w$]*\):new URL\('
        rb'[A-Za-z_$][\w$]*,"http://localhost"\);return\{'
        rb'pathname:[A-Za-z_$][\w$]*\.pathname,'
        rb'search:[A-Za-z_$][\w$]*\.search,'
        rb'hash:[A-Za-z_$][\w$]*\.hash\}'
    ),
)


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def load_release_metadata(release_dir: Path) -> dict[str, object]:
    metadata_path = release_dir / "release.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"release.json is unreadable or invalid JSON: {exc}")

    if not isinstance(metadata, dict):
        fail("release.json must contain a JSON object")

    required_strings = ("releaseId", "cmsCommit", "gatewayCommit", "openapiSha256", "builtAt")
    for key in required_strings:
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            fail(f"release.json field {key!r} must be a non-empty string")

    if not RELEASE_ID_RE.fullmatch(str(metadata["releaseId"])):
        fail("releaseId contains unsafe characters or is too long")
    if not GIT_SHA_RE.fullmatch(str(metadata["cmsCommit"])):
        fail("cmsCommit must be a lowercase 40-character Git SHA")
    if not GIT_SHA_RE.fullmatch(str(metadata["gatewayCommit"])):
        fail("gatewayCommit must be a lowercase 40-character Git SHA")
    if not SHA256_RE.fullmatch(str(metadata["openapiSha256"])):
        fail("openapiSha256 must be a lowercase SHA-256 digest")

    built_at = str(metadata["builtAt"])
    try:
        parsed = dt.datetime.fromisoformat(built_at.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"builtAt must be an ISO-8601 timestamp: {exc}")
    if parsed.tzinfo is None:
        fail("builtAt must include a timezone")

    return metadata


def inventory_files(release_dir: Path) -> set[str]:
    files: set[str] = set()
    for root, directories, filenames in os.walk(release_dir, followlinks=False):
        root_path = Path(root)
        for name in [*directories, *filenames]:
            candidate = root_path / name
            if candidate.is_symlink():
                fail(f"release contains a symbolic link: {candidate.relative_to(release_dir)}")
        for name in filenames:
            candidate = root_path / name
            if not candidate.is_file():
                fail(f"release contains a non-regular file: {candidate.relative_to(release_dir)}")
            relative = candidate.relative_to(release_dir)
            if any(part.startswith(".") for part in relative.parts):
                fail(f"release contains a hidden path segment: {relative}")
            files.add(relative.as_posix())
    return files


def load_manifest(release_dir: Path) -> dict[str, str]:
    manifest_path = release_dir / "SHA256SUMS"
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        fail(f"SHA256SUMS is unreadable: {exc}")
    if not lines:
        fail("SHA256SUMS is empty")

    manifest: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        match = MANIFEST_LINE_RE.fullmatch(line)
        if not match:
            fail(f"SHA256SUMS line {line_number} is malformed")
        digest, name = match.groups()
        if "\\" in name:
            fail(f"SHA256SUMS line {line_number} uses a non-POSIX path")
        pure_name = PurePosixPath(name)
        if pure_name.is_absolute() or not pure_name.parts or any(part in {"", ".", ".."} for part in pure_name.parts):
            fail(f"SHA256SUMS line {line_number} contains an unsafe path")
        normalized = pure_name.as_posix()
        if normalized == "SHA256SUMS":
            fail("SHA256SUMS must not checksum itself")
        if normalized in manifest:
            fail(f"SHA256SUMS contains a duplicate entry: {normalized}")
        manifest[normalized] = digest.lower()
    return manifest


def verify_hashes(release_dir: Path, manifest: dict[str, str]) -> None:
    for name, expected in manifest.items():
        candidate = release_dir / name
        if not candidate.is_file() or candidate.is_symlink():
            fail(f"manifest entry is not a regular file: {name}")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if not hmac.compare_digest(actual, expected):
            fail(f"SHA-256 mismatch: {name}")


def scrub_safe_library_localhost(content: bytes) -> bytes:
    scrubbed = content
    for pattern in SAFE_LIBRARY_LOCALHOST_PATTERNS:
        scrubbed = pattern.sub(
            lambda match: match.group(0).replace(
                b"http://localhost", b"https://example.invalid"
            ),
            scrubbed,
        )
    return scrubbed


def normalize_backslash_web_url(match: re.Match[bytes]) -> bytes:
    scheme, remainder = match.group(0).split(b":", 1)
    remainder = re.sub(rb"\\/", b"/", remainder)
    remainder = re.sub(
        rb"\\(?!u[0-9a-f]{4}|x[0-9a-f]{2})", b"/", remainder, flags=re.IGNORECASE
    )
    return scheme + b"://" + remainder.lstrip(b"/\\")


def decode_javascript_escapes(content: bytes) -> bytes:
    """Expose URL-relevant JavaScript escapes without parsing JavaScript.

    Unicode/hex escapes and escaped newlines have the same byte-level security
    significance wherever they occur. Escaped slashes are intentionally left
    for ``BACKSLASH_WEB_URL_RE`` so regex literals such as /\/gateway/ are not
    rewritten into protocol-relative URLs.
    """

    def decode(match: re.Match[bytes]) -> bytes:
        try:
            codepoint = int(match.group(1), 16)
            if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                return match.group(0)
            return chr(codepoint).encode("utf-8")
        except (ValueError, UnicodeEncodeError):
            return match.group(0)

    decoded = re.sub(
        rb"\\(?:\r\n|[\n\r]|\xe2\x80[\xa8\xa9])",
        b"",
        content,
    )
    decoded = re.sub(rb"\\u\{([0-9a-f]{1,6})\}", decode, decoded, flags=re.IGNORECASE)
    decoded = re.sub(rb"\\u([0-9a-f]{4})", decode, decoded, flags=re.IGNORECASE)
    decoded = re.sub(rb"\\x([0-9a-f]{2})", decode, decoded, flags=re.IGNORECASE)
    return decoded


def normalize_web_spacing(content: bytes) -> bytes:
    """Expose browser-equivalent protocol-relative URL spellings."""

    normalized = re.sub(
        rb"([\"'`(=])\s*(?:\\/){2}", rb"\1//", content
    )
    return re.sub(rb"([\"'`(=])\s+//", rb"\1//", normalized)


def legacy_ipv4(hostname: str) -> ipaddress.IPv4Address | None:
    try:
        packed = socket.inet_aton(hostname)
    except OSError:
        return None
    return ipaddress.IPv4Address(socket.inet_ntoa(packed))


def object_storage_host(hostname: str) -> bool:
    aws_suffix = hostname.endswith(".amazonaws.com") or hostname.endswith(".amazonaws.com.cn")
    aws_s3 = aws_suffix and any(
        label == "s3" or label.startswith("s3-")
        for label in hostname.split(".")
    )
    google = hostname in {"storage.googleapis.com", "storage.cloud.google.com"} or hostname.endswith(
        (".storage.googleapis.com", ".storage.cloud.google.com")
    )
    cloudflare = hostname.endswith(".r2.cloudflarestorage.com") or hostname == "r2.cloudflarestorage.com"
    azure_suffixes = (
        ".blob.core.windows.net",
        ".dfs.core.windows.net",
        ".blob.core.chinacloudapi.cn",
        ".dfs.core.chinacloudapi.cn",
        ".blob.core.usgovcloudapi.net",
        ".dfs.core.usgovcloudapi.net",
        ".blob.storage.azure.net",
    )
    return aws_s3 or google or cloudflare or hostname.endswith(azure_suffixes)


def unsafe_web_origin(match: re.Match[bytes]) -> str | None:
    raw_origin = match.group(0)
    origin = raw_origin.decode("ascii", errors="ignore")
    if origin.startswith("//"):
        origin = "https:" + origin
    try:
        hostname = urlsplit(origin).hostname
    except ValueError:
        return None
    if not hostname:
        return None
    hostname = hostname.rstrip(".").lower()

    if hostname == "localhost" or hostname.endswith(".localhost"):
        return "localhost"

    address_text = hostname.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        address = legacy_ipv4(address_text)
    if address is not None and (
        not address.is_global
        or address.is_multicast
        or getattr(address, "is_site_local", False)
        or (isinstance(address, ipaddress.IPv4Address) and address in SHARED_ADDRESS_SPACE)
    ):
        return "non-public IP address"

    if object_storage_host(hostname):
        return "object-storage endpoint"
    special_use_names = ("home.arpa", "consul")
    if (
        "." not in hostname
        or hostname in special_use_names
        or hostname.endswith(tuple(f".{name}" for name in special_use_names))
        or hostname.endswith(
            (".local", ".internal", ".lan", ".home", ".test", ".svc", ".localdomain")
        )
    ):
        return "local DNS name"
    return None


def scan_url_variant(content: bytes, name: str) -> None:
    for match in WEB_ORIGIN_RE.finditer(content):
        reason = unsafe_web_origin(match)
        if reason:
            fail(f"{reason} web service URL found in static asset: {name}")
    if RAW_STORAGE_URL_RE.search(content):
        fail(f"raw storage URL found in static asset: {name}")
    if SIGNED_HTTP_URL_RE.search(content):
        fail(f"signed HTTP URL found in static asset: {name}")


def looks_like_source_map(content: bytes) -> bool:
    if SOURCE_MAP_MARKER_RE.search(content):
        return True
    stripped = content.lstrip()
    if not stripped.startswith(b"{"):
        return False
    try:
        value = json.loads(stripped)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("version") == 3 and "sources" in value and "mappings" in value


def scan_static_assets(release_dir: Path, names: set[str]) -> None:
    source_maps = sorted(name for name in names if name.lower().endswith(".map"))
    if source_maps:
        fail(f"public source maps are forbidden: {source_maps[0]}")

    for name in sorted(names):
        # Scan every checksummed public asset. Nginx can serve arbitrary files
        # from the release, so extension-based filtering creates an exfiltration
        # gap for SVG/XML/TXT and unknown emitted asset types.
        content = (release_dir / name).read_bytes()
        current = scrub_safe_library_localhost(content)
        scan_url_variant(current, name)
        # Close canonicalization over composed encodings. Each operation is
        # monotonic for these byte spellings; the hard round limit prevents a
        # hostile asset from turning validation into unbounded work.
        for _round in range(6):
            candidate = normalize_web_spacing(current)
            candidate = decode_javascript_escapes(candidate)
            candidate = BACKSLASH_WEB_URL_RE.sub(
                normalize_backslash_web_url, candidate
            )
            candidate = unquote_to_bytes(candidate)
            candidate = html.unescape(
                candidate.decode("utf-8", errors="ignore")
            ).encode()
            if candidate == current:
                break
            scan_url_variant(candidate, name)
            current = candidate
        else:
            # A payload that still changes at the bound may reveal an unsafe
            # URL on the next browser decoding step. Never accept an artifact
            # whose browser-relevant canonical form did not converge.
            fail(f"static asset decoding did not converge safely: {name}")
        if PRIVATE_KEY_RE.search(content):
            fail(f"private key material found in static asset: {name}")
        if looks_like_source_map(content):
            fail(f"source map content found in static asset: {name}")


def validate(release_dir: Path, expected_release_id: str | None) -> tuple[str, int]:
    if not release_dir.is_dir() or release_dir.is_symlink():
        fail("release path must be a real directory")

    metadata = load_release_metadata(release_dir)
    release_id = str(metadata["releaseId"])
    if expected_release_id is not None and release_id != expected_release_id:
        fail(f"releaseId {release_id!r} does not match expected {expected_release_id!r}")

    files = inventory_files(release_dir)
    missing = sorted(REQUIRED_FILES - files)
    if missing:
        fail(f"release is missing required file: {missing[0]}")
    if "SHA256SUMS" not in files:
        fail("release is missing SHA256SUMS")

    manifest = load_manifest(release_dir)
    expected_manifest_files = files - {"SHA256SUMS"}
    if set(manifest) != expected_manifest_files:
        untracked = sorted(expected_manifest_files - set(manifest))
        absent = sorted(set(manifest) - expected_manifest_files)
        if untracked:
            fail(f"file is not covered by SHA256SUMS: {untracked[0]}")
        fail(f"SHA256SUMS references an absent file: {absent[0]}")

    verify_hashes(release_dir, manifest)
    scan_static_assets(release_dir, expected_manifest_files)
    return release_id, len(expected_manifest_files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--expected-release-id")
    parser.add_argument("--print-release-id", action="store_true")
    args = parser.parse_args()

    try:
        release_id, file_count = validate(args.release_dir, args.expected_release_id)
    except ValidationError as exc:
        print(f"release validation failed: {exc}", file=sys.stderr)
        return 1

    if args.print_release_id:
        print(release_id)
    else:
        print(f"release {release_id} valid ({file_count} checksummed files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
