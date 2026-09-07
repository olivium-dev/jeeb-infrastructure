#!/usr/bin/env python3
"""Fixed, read-only staging diagnostics. Never serialize raw engine/HTTP data."""

import json
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


FLEET = (
    "jeeb-state-service", "user-management", "one-time-password", "wallet-service",
    "feedback-service", "remote-user-preferences", "ban-service", "kyc-service",
    "notification", "push-notification", "chat-api", "realtime-comunication-service",
    "cdn-service", "voice-transcription-service", "contract-signing-service",
    "form-builder-service", "geolocation-service", "delivery-service",
    "compliment-service", "offer-service", "heart-beat", "settlement-service",
    "bundler-service", "jeeb-gateway",
)
TELEMETRY = (
    "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES", "OTEL_EXPORTER_OTLP_HEADERS", "SENTRY_DSN",
    "SENTRY_ENVIRONMENT", "SENTRY_RELEASE", "Sentry__Dsn",
    "Otel__Endpoint",
)
MONITORS = ("otel-collector", "prometheus", "loki", "promtail", "grafana",
            "node-exporter", "cadvisor")
FLAGS = (
    "PUSH_PIPELINE_REQUIRED", "PUSH_AUTH_MODE", "PUSH_DELIVERY_REQUIRED",
    "DISPATCH_WORKER_ENABLED", "WEBHOOK_ENABLED", "Features__Heatmap__Enabled",
    "FeatureFlags__UseUpstream__Delivery", "FeatureFlags__UseUpstream__Voice",
    "FeatureFlags__UseUpstream__Realtime", "Features__RealtimeWebSocketProxy__Enabled",
)
CREDENTIAL_KEYS = (
    "DELIVERY_SERVICE_TOKEN_FILE", "Services__Delivery__ServiceTokenFile",
    "DELIVERY_SERVICE_TOKEN", "Services__Delivery__ServiceToken",
    "GF_SECURITY_ADMIN_PASSWORD", "GF_SECURITY_ADMIN_PASSWORD__FILE",
    "GF_AUTH_ANONYMOUS_ENABLED", "SENTRY_DSN", "OTEL_EXPORTER_OTLP_HEADERS",
)
TEMPLATES = {"jeeb_kyc_form_builder.json", "jeeb_onboarding_form_builder.json",
             "generated_jeeb_jeeber_v1.json", "generated_generated_jeeb_jeeber_v1.json"}


class DiagnosticError(Exception):
    pass


def command(args):
    # No shell, no arbitrary command input, bounded execution, and no stderr output.
    try:
        return subprocess.run(args, check=True, timeout=15, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError):
        raise DiagnosticError("fixed read-only command unavailable") from None


def structured(args):
    try:
        return json.loads(command(args))
    except (ValueError, TypeError):
        raise DiagnosticError("invalid diagnostic response") from None


def environment(rows):
    result = {}
    for row in rows or []:
        if not isinstance(row, str) or "=" not in row:
            continue
        key, value = row.split("=", 1)
        if key in result:
            raise DiagnosticError("duplicate runtime environment key")
        result[key] = value
    return result


def nonempty(env, keys):
    return {key: bool(env.get(key, "").strip()) for key in keys}


def safe_image(value):
    # Only known organization/name plus immutable digest, never tags/userinfo.
    if isinstance(value, str) and re.fullmatch(
        r"ghcr\.io/olivium-dev/[a-z0-9-]+@sha256:[a-f0-9]{64}", value
    ) and value.split("/")[-1].split("@")[0] in {*FLEET, "notification-service", "chat-service"}:
        return value
    return None


def builder_contract(env, container):
    individual = all(env.get(key) for key in ("DB_HOST", "DB_NAME", "DB_USERNAME", "DB_PASSWORD"))
    if individual:
        host, database = env["DB_HOST"], env["DB_NAME"]
        source = "individual"
        port = env.get("DB_PORT", "5432")
        known = bool(re.fullmatch(r"[0-9]+", port)) and 0 < int(port) < 65536
        # These values are interpolated into a SQLAlchemy URL by the application.
        known = known and not any(c in host + database for c in "/?@#")
        known = known and not any(c in env["DB_USERNAME"] + env["DB_PASSWORD"] for c in "/?@#")
        routing_clear = known
    else:
        source = "DATABASE_URL"
        host, database, port, known, routing_clear = postgres_url_target(env.get("DATABASE_URL", ""))
    mounts = container.get("Mounts", [])
    relevant = []
    for mount in mounts:
        target = mount.get("Target", "")
        # The only output paths are fixed application paths, never arbitrary sources.
        if target in {"/app", *["/app/" + name for name in TEMPLATES]}:
            relevant.append({"target": target, "bind": mount.get("Type") == "bind",
                             "readonly": mount.get("ReadOnly") is True,
                             "source_is_scoped_staging_path": str(mount.get("Source", "")).startswith("/opt/jeeb-staging-")})
    configured = [part.strip() for part in env.get("TEMPLATE_JSON_FILES", "").split(",") if part.strip()]
    return {"database_source": source, "database_target_unambiguous": known,
            "database_routing_overrides_absent": routing_clear,
            "database_host_matches_staging": host == "192.168.2.20" if known else None,
            "database_port_matches_staging": int(port) == 5432 if known else None,
            "database_name_matches_staging": database == "jeeb_form_builder_staging" if known else None,
            "templates": [name for name in configured if name in TEMPLATES],
            "unknown_template_present": any(name not in TEMPLATES for name in configured),
            "relevant_mounts": relevant,
            "other_mount_present": len(mounts) != len(relevant)}


def postgres_url_target(value):
    """Conservative SQLAlchemy URL projection; routing ambiguity yields unknown.

    SQLAlchemy 2.0.27 _parse_url decodes username/password, NOT database. Keep
    percent-encoded database names literal, matching that runtime parser.
    """
    if not value:
        return None, None, None, False, None
    try:
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else 5432
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True) if parsed.query else []
        # Unknown query keywords can become driver connect arguments. Only these
        # documented non-routing options are permitted for target attestation.
        routing_clear = all(key in {"sslmode", "connect_timeout", "application_name"} for key, _ in query)
        valid = (parsed.scheme in {"postgresql", "postgresql+psycopg2", "postgresql+asyncpg"}
                 and bool(parsed.hostname) and bool(parsed.path[1:])
                 and 0 < port < 65536 and not parsed.fragment and routing_clear
                 and parsed.netloc.count("@") <= 1
                 and not any(c in value for c in "\r\n\t"))
        # A colon with an empty port must not silently become the default.
        valid = valid and not parsed.netloc.endswith(":")
        return parsed.hostname, parsed.path[1:], port, bool(valid), routing_clear
    except (ValueError, TypeError):
        return None, None, None, False, False


def heartbeat_contract(env):
    result = {"redis_target_unambiguous": False, "redis_host_matches_staging": None,
              "redis_port_matches_staging": None, "redis_database_matches_staging": None,
              "service_auth_configured": bool(env.get("HEARTBEAT_SERVICE_AUTH_KEY")),
              "jwks_configured": bool(env.get("HEARTBEAT_JWKS_URL"))}
    try:
        value = env.get("REDIS_URL", "")
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else 6379
        # go-redis query arguments can override DB selection; any query is
        # conservatively unknown, including encoded/duplicate db selectors.
        known = (parsed.scheme in {"redis", "rediss"} and bool(parsed.hostname)
                 and not parsed.query and not parsed.fragment and not parsed.netloc.endswith(":")
                 and re.fullmatch(r"/[0-9]+", parsed.path) is not None
                 and 0 < port < 65536 and not any(c in value for c in "\r\n\t"))
        if known:
            result.update(redis_target_unambiguous=True, redis_host_matches_staging=parsed.hostname == "192.168.2.20",
                          redis_port_matches_staging=port == 6379, redis_database_matches_staging=int(parsed.path[1:]) == 4)
    except (ValueError, TypeError):
        pass
    return result


def cdn_contract(env, container):
    mounts = container.get("Mounts", [])
    matches = [m for m in mounts if m.get("Target") == "/app/uploads"]
    mount = matches[0] if len(matches) == 1 else None
    return {"exact_upload_bind_mount": (mount.get("Type") == "bind" and mount.get("Source") == "/opt/jeeb-staging-cdn/uploads"
                                         and mount.get("ReadOnly") is not True) if mount else None,
            "upload_mount_count": len(matches),
            "additional_config_or_command_override": (len(mounts) != len(matches)
                                                       or bool(container.get("Configs"))
                                                       or bool(container.get("Args"))
                                                       or bool(container.get("Command"))),
            "storage_provider_is_local": env["Storage__Provider"].lower() == "local" if "Storage__Provider" in env else None,
            "storage_path_matches_mount": env["LocalStorage__Path"] == "/app/uploads" if "LocalStorage__Path" in env else None}


def sanitize_service(name, raw):
    spec = raw.get("Spec", {})
    if spec.get("Name") != name:
        raise DiagnosticError("service identity mismatch")
    task = spec.get("TaskTemplate", {})
    container = task.get("ContainerSpec", {})
    env = environment(container.get("Env"))
    desired = spec.get("Mode", {}).get("Replicated", {}).get("Replicas")
    state = raw.get("UpdateStatus", {}).get("State", "initial")
    result = {"name": name, "present": True, "image": safe_image(container.get("Image")),
              "desired_replicas": desired if type(desired) is int and 0 <= desired < 100 else None,
              "update_state": state if state in {"initial", "completed", "updating", "paused", "rollback_started", "rollback_completed", "rollback_paused"} else "unknown",
              "telemetry_configured": nonempty(env, TELEMETRY),
              "credential_configured": nonempty(env, CREDENTIAL_KEYS),
              "flags": {key: env[key] if env[key].lower() in {"true", "false", "expand", "strict", "1", "0"} else "invalid"
                        for key in FLAGS if key in env},
              "json_logging": task.get("LogDriver", {}).get("Name") == "json-file",
              "log_rotation_configured": all(task.get("LogDriver", {}).get("Options", {}).get(k) for k in ("max-size", "max-file")),
              "promtail_label": container.get("Labels", {}).get("logging") == "promtail"}
    if name == "jeeb-staging-form-builder-service":
        result["builder"] = builder_contract(env, container)
    if name == "jeeb-staging-heart-beat":
        result["heartbeat"] = heartbeat_contract(env)
    if name == "jeeb-staging-cdn-service":
        result["cdn"] = cdn_contract(env, container)
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_probe(port, path, prometheus=False):
    opener = build_opener(NoRedirect(), ProxyHandler({}))
    try:
        with opener.open(Request(f"http://127.0.0.1:{port}{path}"), timeout=4) as response:
            result = {"http_status": response.status}
            if prometheus:
                # No label values, query data, exemplars, or server error messages leave host.
                payload = json.loads(response.read(1_000_001))
                values = payload.get("data", {}).get("result", [])
                result["query_success"] = payload.get("status") == "success"
                result["sample_count"] = len(values) if isinstance(values, list) else None
                result["up_samples"] = sum(v.get("value", [None, None])[1] == "1" for v in values) if isinstance(values, list) else None
            return result
    except HTTPError as error:
        return {"http_status": error.code}
    except (OSError, URLError, ValueError, TypeError, KeyError, IndexError):
        return {"http_status": None}


def monitor_unit(unit):
    try:
        rows = command(["systemctl", "show", unit, "--property=LoadState", "--property=ActiveState"]).splitlines()
        fields = dict(row.split("=", 1) for row in rows if "=" in row)
        return {"loaded": fields.get("LoadState") == "loaded",
                "active": fields.get("ActiveState") == "active", "observed": True}
    except DiagnosticError:
        return {"observed": False}


def collect():
    if command(["hostname", "-s"]).strip() != "olivium-ephemerals":
        raise DiagnosticError("staging hostname mismatch")
    addresses = structured(["ip", "-j", "-4", "addr", "show", "scope", "global"])
    if not any(a.get("local") == "192.168.2.20" for row in addresses for a in row.get("addr_info", [])):
        raise DiagnosticError("staging address mismatch")
    names = set(command(["docker", "service", "ls", "--format", "{{.Name}}"] ).splitlines())
    network = structured(["docker", "network", "inspect", "jeeb-staging-net"])[0]
    result = {"schema": 1, "host_verified": True,
              "network": {"overlay": network.get("Driver") == "overlay",
                          "attachable": network.get("Attachable") is True,
                          "encrypted": "encrypted" in network.get("Options", {})}, "services": []}
    for suffix in FLEET:
        name = "jeeb-staging-" + suffix
        if name not in names:
            result["services"].append({"name": name, "present": False})
            continue
        raw = structured(["docker", "service", "inspect", name])[0]
        entry = sanitize_service(name, raw)
        states = command(["docker", "service", "ps", name, "--filter", "desired-state=running", "--format", "{{.CurrentState}}"] ).splitlines()
        entry["desired_running_tasks"] = len(states)
        entry["running_tasks"] = sum(state.startswith("Running ") for state in states)
        result["services"].append(entry)
    result["monitoring"] = {}
    container_names = set(command(["docker", "ps", "--format", "{{.Names}}"] ).splitlines())
    for suffix in MONITORS:
        allowed = (suffix, "jeeb-" + suffix, "jeeb-staging-" + suffix, "monitoring_" + suffix)
        found = []
        for name in allowed:
            if name in names:
                raw = structured(["docker", "service", "inspect", name])[0]
                env = environment(raw.get("Spec", {}).get("TaskTemplate", {}).get("ContainerSpec", {}).get("Env"))
                found.append({"name": name, "credential_configured": nonempty(env, CREDENTIAL_KEYS)})
        result["monitoring"][suffix] = {
            "matched_services": found,
            "matched_running_container_names": [name for name in allowed if name in container_names],
            "units": {name + ".service": monitor_unit(name + ".service") for name in allowed},
            "scope": "fixed known names only; unmatched deployments remain unverified"}
    result["monitoring"]["local_http"] = {
        "collector": http_probe(13133, "/"), "prometheus": http_probe(9090, "/-/ready"),
        "loki": http_probe(3100, "/ready"), "grafana": http_probe(3000, "/api/health"),
        "prometheus_up": http_probe(9090, "/api/v1/query?query=up", prometheus=True)}
    return result


def main():
    if len(sys.argv) != 1:
        print('{"error":"no command inputs accepted"}')
        return 1
    try:
        result = collect()
    except Exception:
        # Raw Docker, HTTP, environment, or exception payloads may include credentials.
        print('{"error":"read-only inventory failed; no raw diagnostic data emitted"}')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
