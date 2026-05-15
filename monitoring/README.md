# Jeeb monitoring stack

End-to-end observability for the Jeeb backend and mobile app:

- **OpenTelemetry Collector** — single ingest point for OTLP metrics, traces,
  and logs emitted by every backend service.
- **Prometheus** — long-term metric store, scrapes the Collector's
  `/metrics` endpoint.
- **Loki + Promtail** — log aggregation. Promtail scrapes container stdout
  from any container labelled `logging=promtail`, parses the JSON line, and
  pushes labelled streams (`service_name`, `level`) to Loki.
- **Grafana** — dashboards and ad-hoc exploration; auto-provisions
  Prometheus + Loki datasources and the `api-latency` + `structured-logs`
  dashboards at startup. Loki's `trace_id` derived field links log lines
  back to traces.
- **Sentry** — backend exception capture (.NET, Node, Python). The Collector
  also forwards spans with `exception` events to Sentry's OTLP ingest.
- **Crashlytics** — mobile crash + non-fatal capture for the Flutter app.
  Wired in `jeeb-mobile` via `firebase_crashlytics`.

## Run it locally

```bash
# From repo root
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  --profile monitoring up -d

# Grafana          → http://localhost:3000  (admin / admin)
# Prometheus       → http://localhost:9090
# Loki             → http://localhost:3100
# OTel Collector   → otlp:4317 (grpc), 4318 (http), /metrics on 8889
```

The `monitoring` profile keeps the dev compose lean by default; only engineers
working on observability opt in.

## Service integration

Every backend service exports OTLP to the collector. Settings come from env:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SERVICE_NAME=<service-name>
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=staging
```

See `docs/monitoring.md` for the per-stack wire-up (.NET, Node, Python,
Elixir, Flutter).

## Dashboards

`grafana/dashboards/api-latency.json` plots p50 / p95 / p99 request duration
per `http_route` for every service, sourced from the
`http_server_request_duration_seconds` histogram that the .NET
`AspNetCoreInstrumentation` and Node `@opentelemetry/instrumentation-http`
auto-emit. `grafana/dashboards/structured-logs.json` queries Loki for the
parsed JSON log stream, faceted by `service_name` and `level`, with a
clickable `trace_id` derived field so a single log line can be pivoted
into the Sentry trace it belongs to. New dashboards drop into the same
folder — provisioning picks them up on Grafana restart.

## Alerts

Prometheus alert rules live in `prometheus/alerts.yml`. The starter pack
covers:

- `ApiHighErrorRate` — >5% 5xx over 5m
- `ApiHighLatencyP95` — p95 > 1s over 10m
- `ServiceDown` — scrape target down for 2m
- `ContainerHighCpu` / `ContainerHighMemory` — per-service capacity
- `NodeHighCpu` / `NodeHighMemory` — per-node capacity

The capacity alerts are paired with [`../docs/scaling-runbook.md`](../docs/scaling-runbook.md)
and rely on the `cadvisor` and `node-exporter` sidecars added by
`docker-compose.monitoring.yml`.

Alertmanager is intentionally out of scope for MVP; Sentry handles error
alerts and Grafana's built-in alerting is enough for latency until traffic
warrants a dedicated routing layer.
