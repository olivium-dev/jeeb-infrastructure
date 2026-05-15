# jeeb-infrastructure

Deployment configs, Docker Compose, and CI templates for the Jeeb product.

## Quick Start — Local Development

```bash
# 1. Copy environment variables
cp .env.example .env
# Edit .env with real values

# 2. Start all services
docker compose up -d

# 3. Verify
docker compose ps
curl http://localhost:5000/health/live
```

## Services

| Service        | Image                  | Port | Purpose                    |
| -------------- | ---------------------- | ---- | -------------------------- |
| jeeb-gateway   | Built from ../jeeb-gateway | 5000 | BFF gateway (ASP.NET Core) |
| postgres       | postgres:16-alpine     | 5432 | Primary database           |
| redis          | redis:7-alpine         | 6379 | Cache / session store      |

## Staging

Staging deploys automatically on merge to `main` via `.github/workflows/deploy-staging.yml`.

```bash
# Manual staging deploy
REGISTRY=ghcr.io/olivium-dev IMAGE_TAG=latest \
  DEPLOY_HOST=staging.example.com DEPLOY_USER=deploy \
  ./deploy/staging-deploy.sh
```

## Rollback

```bash
REGISTRY=ghcr.io/olivium-dev \
  DEPLOY_HOST=staging.example.com DEPLOY_USER=deploy \
  ./deploy/rollback.sh v1.2.3
```

## Observability

Prometheus + Grafana + OpenTelemetry Collector are bundled as an opt-in
profile so the dev compose stays lean. Sentry handles backend exceptions
and Crashlytics covers the Flutter app — see
[`docs/monitoring.md`](docs/monitoring.md) for the per-stack wire-up.

```bash
# Bring up the API + monitoring stack together
cat .env.example .env.monitoring.example > .env
docker compose \
  -f docker-compose.yml \
  -f docker-compose.monitoring.yml \
  --profile monitoring up -d

# Grafana    → http://localhost:3000  (admin / admin)
# Prometheus → http://localhost:9090
# Loki       → http://localhost:3100
```

The default `Jeeb / API latency` dashboard ships in the repo and shows
p50/p95/p99 per endpoint plus 5xx error ratio. The companion
`Jeeb / Structured logs` dashboard streams JSON-parsed container logs from
Loki with a clickable `trace_id` field that pivots into the same trace in
Sentry. Smoke-test the whole stack with:

```bash
./scripts/verify-monitoring.sh
```

## Capacity & horizontal scaling

CPU > 70% and memory > 80% (sustained 15 m) page the on-call via the
`ContainerHighCpu` / `ContainerHighMemory` / `NodeHighCpu` /
`NodeHighMemory` alert rules in
[`monitoring/prometheus/alerts.yml`](monitoring/prometheus/alerts.yml).
The on-call follows [`docs/scaling-runbook.md`](docs/scaling-runbook.md)
to scale a service replica or join a new Swarm worker within the 4-hour
SLO. Container metrics come from `cadvisor`; host metrics from
`node-exporter` — both run under the `monitoring` profile.

## File Structure

```
jeeb-infrastructure/
├── docker-compose.yml             # Local dev environment
├── docker-compose.staging.yml     # Staging overrides
├── docker-compose.monitoring.yml  # Prometheus + Grafana + OTel (profile: monitoring)
├── .env.example                   # Environment variable template
├── .env.monitoring.example        # Observability env vars (Sentry, OTel, Grafana)
├── deploy/
│   ├── staging-deploy.sh          # SSH-based staging deploy
│   └── rollback.sh                # Rollback to a previous tag
├── docs/
│   ├── monitoring.md              # Per-stack OTel + Sentry + Crashlytics wire-up
│   └── scaling-runbook.md         # Horizontal scaling procedure + 4h SLO (T-devops-008)
├── monitoring/
│   ├── otel/otel-collector-config.yml
│   ├── prometheus/{prometheus,alerts}.yml
│   ├── loki/loki-config.yml
│   ├── promtail/promtail-config.yml
│   └── grafana/{grafana.ini,dashboards,provisioning}/
├── scripts/
│   └── verify-monitoring.sh        # AC smoke-test for T-devops-004
├── .github/
│   ├── workflows/
│   │   └── deploy-staging.yml     # CI: deploy on merge to main
│   └── CODEOWNERS
└── README.md
```
