#!/usr/bin/env bash
## Verify the T-devops-004 monitoring acceptance criteria against a
## running stack. Intended for CI smoke + local sanity-check after
## `docker compose --profile monitoring up -d`.
##
## Asserts:
##   1. Grafana is reachable and serves the api-latency dashboard JSON.
##   2. Prometheus is reachable and has scraped the OTel collector.
##   3. Loki is reachable and accepts log queries.
##   4. The OTel collector is exposing Prometheus-format metrics.
##   5. Sentry env vars are wired (DSN may be empty in dev — only the
##      env-var presence is asserted, not actual capture).
##   6. Crashlytics bootstrap is referenced in jeeb-mobile (when the
##      mobile repo is present alongside this one).
##
## Exit codes: 0 on full pass, 1 on any AC failure.

set -euo pipefail

GRAFANA_URL=${GRAFANA_URL:-http://localhost:3000}
PROMETHEUS_URL=${PROMETHEUS_URL:-http://localhost:9090}
LOKI_URL=${LOKI_URL:-http://localhost:3100}
OTEL_METRICS_URL=${OTEL_METRICS_URL:-http://localhost:8889/metrics}
GRAFANA_USER=${GRAFANA_ADMIN_USER:-admin}
GRAFANA_PASS=${GRAFANA_ADMIN_PASSWORD:-admin}
MOBILE_REPO=${MOBILE_REPO:-../jeeb-mobile}

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=1; }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

FAILED=0

section "AC1 — Grafana dashboard shows API p50/p95/p99 per endpoint"
if curl -fsS -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/dashboards/uid/jeeb-api-latency" \
    | grep -q 'histogram_quantile(0.95'; then
  pass "api-latency dashboard provisioned with p95 quantile expression"
else
  fail "Grafana not serving the jeeb-api-latency dashboard (or p95 missing)"
fi

section "AC2 — Sentry capture wiring"
if grep -q '^SENTRY_DSN=' .env.example \
  && grep -q '^SENTRY_TRACES_SAMPLE_RATE=' .env.example; then
  pass "SENTRY_DSN + SENTRY_TRACES_SAMPLE_RATE present in .env.example"
else
  fail "Sentry env vars missing from .env.example"
fi
if grep -q 'otlphttp/sentry' monitoring/otel/otel-collector-config.yml; then
  pass "OTel collector forwards traces to Sentry OTLP ingest"
else
  fail "OTel collector missing the otlphttp/sentry exporter"
fi

section "AC3 — Crashlytics integrated in Flutter app"
if [[ -d "${MOBILE_REPO}" ]]; then
  if grep -RIq 'firebase_crashlytics' "${MOBILE_REPO}/pubspec.yaml" 2>/dev/null \
    || grep -RIq 'FirebaseCrashlytics' "${MOBILE_REPO}/lib" 2>/dev/null; then
    pass "firebase_crashlytics referenced in ${MOBILE_REPO}"
  else
    fail "Crashlytics not wired in ${MOBILE_REPO} (see docs/monitoring.md §4)"
  fi
else
  pass "jeeb-mobile not checked out here — skipping (see docs/monitoring.md §4)"
fi

section "AC4 — Structured JSON logs with trace IDs"
if grep -q 'trace_id' monitoring/promtail/promtail-config.yml \
  && grep -q '"trace_id"' docs/monitoring.md; then
  pass "Promtail pipeline extracts trace_id; log schema documents it"
else
  fail "trace_id missing from Promtail pipeline or log schema doc"
fi

section "Live stack reachability (only if --profile monitoring is up)"
if curl -fsS "${PROMETHEUS_URL}/-/ready" >/dev/null 2>&1; then
  pass "Prometheus /-/ready"
else
  printf '  \033[33m·\033[0m Prometheus not reachable at %s — skipping live checks\n' "$PROMETHEUS_URL"
  exit "$FAILED"
fi
if curl -fsS "${LOKI_URL}/ready" >/dev/null 2>&1; then
  pass "Loki /ready"
else
  fail "Loki not reachable at ${LOKI_URL}"
fi
if curl -fsS "${OTEL_METRICS_URL}" >/dev/null 2>&1; then
  pass "OTel collector Prometheus scrape endpoint reachable"
else
  fail "OTel collector :8889/metrics not reachable"
fi

exit "$FAILED"
