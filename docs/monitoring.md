# Monitoring, alerting, and structured logging

This document covers how every Jeeb service must integrate with the observability
stack defined in [`monitoring/`](../monitoring) and brought up by
`docker-compose.monitoring.yml`.

The pillars:

| Pillar       | Sink                          | Source of truth                          |
| ------------ | ----------------------------- | ---------------------------------------- |
| Metrics      | Prometheus (via OTel Collector) | `http.server.request.duration` histogram |
| Traces       | Sentry Performance            | OTLP → Collector → Sentry OTLP ingest    |
| Logs         | Container stdout (JSON)       | Service's structured logger              |
| Exceptions   | Sentry Issues                 | Sentry SDK in each service               |
| Mobile crashes | Firebase Crashlytics        | `firebase_crashlytics` in jeeb-mobile    |

Trace IDs propagate through every layer via W3C `traceparent`, and structured
logs include `trace_id` / `span_id` so a Grafana query can hop straight to the
Sentry trace.

## 1. OpenTelemetry — backend services

Every service exports OTLP to the collector. The collector then fans out:

- **Metrics** → Prometheus scrape (`:8889/metrics`)
- **Traces** → Sentry OTLP ingest
- **Logs** → container stdout, scraped by Promtail and indexed in Loki

Promtail picks up the stdout of any container that carries the
`logging: "promtail"` Docker label. The base `docker-compose.monitoring.yml`
adds that label to `jeeb-gateway`; each new service must do the same in its
own compose override.

### Required env (already injected by `docker-compose.yml`)

```
OTEL_SERVICE_NAME=<service-name>
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=staging,service.namespace=jeeb
```

### .NET (ASP.NET Core 8) — jeeb-gateway and any .NET service

Add packages:

```
OpenTelemetry.Extensions.Hosting
OpenTelemetry.Instrumentation.AspNetCore
OpenTelemetry.Instrumentation.Http
OpenTelemetry.Instrumentation.EntityFrameworkCore
OpenTelemetry.Exporter.OpenTelemetryProtocol
Sentry.OpenTelemetry
Serilog.AspNetCore
Serilog.Sinks.OpenTelemetry
Serilog.Formatting.Compact
```

Wire-up in `Program.cs`:

```csharp
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService(
        serviceName: builder.Configuration["OTEL_SERVICE_NAME"]
                  ?? "jeeb-gateway"))
    .WithMetrics(m => m
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()
        .AddOtlpExporter())
    .WithTracing(t => t
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddEntityFrameworkCoreInstrumentation()
        .AddOtlpExporter());

builder.Host.UseSerilog((ctx, lc) => lc
    .Enrich.FromLogContext()
    .Enrich.WithProperty("service", "jeeb-gateway")
    .WriteTo.Console(new CompactJsonFormatter()));
```

The `AspNetCoreInstrumentation` is what produces the
`http.server.request.duration` histogram that the Grafana dashboard plots —
**do not remove it**.

### Node.js (NestJS / Express)

```
npm i @opentelemetry/sdk-node \
       @opentelemetry/auto-instrumentations-node \
       @opentelemetry/exporter-trace-otlp-grpc \
       @opentelemetry/exporter-metrics-otlp-grpc \
       pino pino-http
```

Bootstrap before `app.listen`:

```ts
import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-grpc";

new NodeSDK({
  traceExporter: new OTLPTraceExporter(),
  instrumentations: [getNodeAutoInstrumentations()],
}).start();
```

### Python (FastAPI / Flask)

```
pip install opentelemetry-distro opentelemetry-exporter-otlp \
            structlog sentry-sdk[fastapi]
opentelemetry-bootstrap -a install
```

Run with `opentelemetry-instrument uvicorn app:app …` — the distro auto-detects
the FastAPI/Flask app and emits the standard histograms.

### Elixir (Phoenix) — unified_payment_gateway and friends

```elixir
# mix.exs
{:opentelemetry, "~> 1.5"},
{:opentelemetry_api, "~> 1.3"},
{:opentelemetry_exporter, "~> 1.8"},
{:opentelemetry_phoenix, "~> 1.2"},
{:opentelemetry_ecto, "~> 1.2"},
```

```elixir
# config/runtime.exs
config :opentelemetry,
  resource: [service: %{name: "unified-payment-gateway"}]

config :opentelemetry_exporter,
  otlp_protocol: :grpc,
  otlp_endpoint: System.fetch_env!("OTEL_EXPORTER_OTLP_ENDPOINT")
```

## 2. Structured JSON logs with trace IDs

Every log line MUST be a single JSON object on one line, and MUST include at
minimum:

```json
{
  "ts": "2026-05-15T12:00:00.123Z",
  "level": "info",
  "service": "jeeb-gateway",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "msg": "POST /api/offers 201"
}
```

The trace ID lets you click from a Grafana panel into Sentry and see the same
request across every service it touched.

Per-stack helpers:

- **.NET** — Serilog with `CompactJsonFormatter` + `Enrich.WithSpan()` from
  `Serilog.Enrichers.OpenTelemetry`.
- **Node** — `pino` with `pino-http`; the OTel auto-instrumentation injects
  `trace_id` via `pino-otel`.
- **Python** — `structlog` configured with the `add_log_level` and
  `merge_contextvars` processors; bind `trace_id` from
  `opentelemetry.trace.get_current_span().get_span_context()`.
- **Elixir** — `Logger` JSON backend (`LoggerJSON.Formatters.GoogleCloud`) with
  `OpenTelemetry.Tracer.current_span_ctx/0` enrichment.

**No service may log via raw `Console.WriteLine`, `print()`, `console.log()`,
or `IO.puts`** for anything other than crash output before logger init.

## 3. Sentry — backend exception tracking

Each service initialises Sentry once at startup with the DSN from env:

```
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=staging|production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

- **.NET** — `builder.WebHost.UseSentry()` + `.AddSentry()` on the OTel
  builder so spans flow into Sentry Performance.
- **Node** — `Sentry.init({ dsn, integrations: [Sentry.httpIntegration()] })`
  before app boot; use `Sentry.setupExpressErrorHandler(app)`.
- **Python** — `sentry_sdk.init(dsn=..., integrations=[FastApiIntegration()])`.
- **Elixir** — `:sentry` app + `Sentry.PlugCapture` in the Phoenix endpoint.

Releases: every CI build sets `SENTRY_RELEASE=<git-sha>` so source-maps and
stack traces are correctly symbolicated.

## 4. Crashlytics — Flutter mobile

Crashlytics lives in `jeeb-mobile`. The crashlytics setup is:

1. **Firebase project** — one each for `dev`, `staging`, `production`.
2. **Config files** — `android/app/google-services.json` and
   `ios/Runner/GoogleService-Info.plist` per flavor (committed via
   environment-specific paths, never overwritten across flavors).
3. **Plugin** — `firebase_crashlytics: ^4.x` in `pubspec.yaml`.
4. **Bootstrap** in `main.dart`:

```dart
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:flutter/foundation.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();

  FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterFatalError;
  PlatformDispatcher.instance.onError = (error, stack) {
    FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
    return true;
  };

  // Disable capture in debug unless explicitly enabled.
  await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(
    !kDebugMode || const bool.fromEnvironment('CRASHLYTICS_DEBUG_CAPTURE'),
  );

  runApp(const JeebApp());
}
```

5. **Symbol upload** — the Fastlane lanes in `jeeb-mobile/fastlane/Fastfile`
   call `upload_symbols_to_crashlytics` (iOS) and the Gradle plugin
   auto-uploads ProGuard mappings on Android release builds.
6. **Non-fatals** — surface caught exceptions with
   `FirebaseCrashlytics.instance.recordError(e, st, fatal: false)` in the
   global Dio error interceptor.

The mobile-release workflow in `.github/workflows/mobile-release.yml` already
sets up the Firebase service account; no extra wiring needed beyond updating
`pubspec.yaml`.

## 5. Dashboards & alerts

- **Default dashboard** — `monitoring/grafana/dashboards/api-latency.json`
  ships with the repo and auto-provisions on Grafana startup. It shows
  p50/p95/p99 latency per `http_route` with service + route variables, plus
  request rate by status class and a 5xx error ratio stat.
- **Custom dashboards** — drop JSON into `monitoring/grafana/dashboards/`,
  commit, restart Grafana. The provisioner picks them up.
- **Alerts** — Prometheus rules in `monitoring/prometheus/alerts.yml`.
  Currently fire to logs only; once Sentry alerts cover error-rate and a real
  Alertmanager is up, point both `ApiHighErrorRate` and `ServiceDown` at
  PagerDuty / Opsgenie.

## 6. Running it

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  --profile monitoring up -d

# Visit:
# Grafana    → http://localhost:3000  (admin / admin)
# Prometheus → http://localhost:9090
```

The `monitoring` profile keeps the dev compose lean — running `docker compose
up -d` alone does NOT start the observability stack.

## 7. Acceptance verification

Map back to the T-devops-004 acceptance criteria:

| Criterion                                              | Where it's satisfied                                                                          |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| Grafana dashboard shows API p50/p95/p99 per endpoint   | `monitoring/grafana/dashboards/api-latency.json` (panel 1: p50/p95/p99 by `service_name` × `http_route`) |
| Sentry captures backend exceptions with stack traces   | `.env.example` (`SENTRY_DSN`), §3 above, `monitoring/otel/otel-collector-config.yml` (`otlphttp/sentry` exporter) |
| Crashlytics integrated in Flutter app                  | §4 above + `jeeb-mobile` Fastlane symbol upload                                               |
| Structured JSON logs with trace IDs on all services    | §2 above + Loki/Promtail pipeline in `monitoring/{loki,promtail}/` + `structured-logs.json` Grafana dashboard with clickable `trace_id` derived field |

Run `scripts/verify-monitoring.sh` against a live stack to assert each
criterion programmatically; the script also doubles as the CI smoke-test
for this repo.
