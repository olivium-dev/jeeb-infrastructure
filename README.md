# jeeb-infrastructure

Deployment configs, Docker Compose, and CI templates for the Jeeb product.

## Environments

| Env        | Compose files                                  | Trigger                                  | TLS                       | URL pattern                |
| ---------- | ---------------------------------------------- | ---------------------------------------- | ------------------------- | -------------------------- |
| local      | `docker-compose.yml`                           | `docker compose up`                      | none                      | http://localhost:5000      |
| staging    | `docker-compose.yml` + `docker-compose.staging.yml` | auto on merge to `develop`           | Let's Encrypt (staging issuer by default) | https://api.staging.jeeb.app |
| production | `docker-compose.yml` + `docker-compose.production.yml` | manual (`workflow_dispatch` + env protection) | Let's Encrypt (prod)      | https://api.jeeb.app       |

Staging and production share the same topology (gateway + Postgres + Redis +
Traefik + MinIO) but differ in resource limits, replica counts, restart
policies, and ACME issuer.

## Quick Start — Local Development

```bash
cp .env.example .env
# Edit .env: at minimum POSTGRES_PASSWORD and JWT_KEY

docker compose up -d
docker compose ps
curl http://localhost:5000/health/live
```

## Services

| Service        | Image                                | Local port | Purpose                       |
| -------------- | ------------------------------------ | ---------- | ----------------------------- |
| traefik        | `traefik:v3.1`                       | 80, 443    | TLS + ingress (staging/prod)  |
| jeeb-gateway   | built from `../jeeb-gateway`         | 5000:8080  | BFF gateway (ASP.NET Core)    |
| postgres       | `postgres:16-alpine`                 | 5432:5432  | Primary database              |
| redis          | `redis:7-alpine`                     | 6379:6379  | Geo / pub-sub / cache / rate-limit (see [`redis/`](./redis/)) |
| minio          | `minio/minio:RELEASE.2025-01-20…`    | n/a        | S3-compatible object storage  |

The gateway listens on `:8080` internally. Locally it is published at `:5000`;
in staging/production Traefik fronts it on `:443` and the host port is unbound.

## Smoke test (local + CI)

```bash
cp .env.example .env
./scripts/smoke-test.sh
./scripts/smoke-test.sh 60   # custom timeout in seconds
```

Brings the local stack up, polls `/health/live` until 200, then tears down.
Also run in `.github/workflows/backend-ci.yml` on every PR.

## Deploy — Staging

Staging deploys **automatically on merge to `develop`** via
`.github/workflows/deploy-staging.yml`. To deploy a specific tag manually,
use **Actions → Deploy to Staging → Run workflow** with an `image_tag` input.

Manual from a shell:
```bash
REGISTRY=ghcr.io/olivium-dev IMAGE_TAG=latest \
  DEPLOY_HOST=staging.example.com DEPLOY_USER=deploy \
  GATEWAY_DOMAIN=api.staging.jeeb.app \
  ./deploy/staging-deploy.sh
```

## Deploy — Production

Production has **no `on: push` trigger**. Deploys are dispatched manually:

1. **Actions → Deploy to Production → Run workflow**
2. Inputs: `image_tag` (e.g. `sha-3f9a1c2`, `v1.2.3`) and `confirm_production`
   (must equal the literal string `PRODUCTION`).
3. Approve the `production` environment gate (required reviewer).

The deploy script captures the currently-running tag before rolling out and
auto-rolls-back on `/health/live` failure.

Full procedure + failure modes: [`deploy/runbook-production.md`](deploy/runbook-production.md).

## Rollback

| Env        | Method                                            | SLO        |
| ---------- | ------------------------------------------------- | ---------- |
| staging    | `./deploy/rollback.sh <tag>`                      | best-effort |
| production | **Actions → Rollback Production**, or `./deploy/production-rollback.sh [tag]` | **< 5 min** |

If `image_tag` is omitted from the production rollback workflow, the script
reads the last entry from `/opt/jeeb/.deploy-history` (written automatically
by every successful deploy).

## Mobile OTA (Shorebird)

Dart-only hotfixes ship over-the-air via Shorebird Code Push instead of a
full store review cycle. Native (Kotlin/Swift), plugin, or `pubspec.yaml`
changes still require a store release.

| Track       | Workflow                                                                             | Helper                            |
| ----------- | ------------------------------------------------------------------------------------ | --------------------------------- |
| staging     | `jeeb-mobile/.github/workflows/mobile-ota-shorebird.yml` (track=staging, default)    | `scripts/shorebird-patch.sh`      |
| beta        | same workflow, track=beta                                                            | `scripts/shorebird-patch.sh`      |
| production  | same workflow, track=production (requires `mobile-release` env approval)             | `scripts/shorebird-patch.sh`      |
| rollback    | n/a — cut a forward patch from the last-good ref                                     | `scripts/shorebird-rollback.sh`   |

Decision: [`docs/adr/0001-shorebird-ota.md`](docs/adr/0001-shorebird-ota.md).
Operating procedure: [`deploy/mobile-ota-runbook.md`](deploy/mobile-ota-runbook.md).

## File Structure

```
jeeb-infrastructure/
├── docker-compose.yml                # Local dev
├── docker-compose.staging.yml        # Staging (Traefik + MinIO + smaller limits)
├── docker-compose.production.yml     # Production (Traefik + MinIO + 2x replicas + always-restart)
├── .env.example                      # All variables (Postgres, JWT, Firebase, S3, TLS, deploy)
├── deploy/
│   ├── staging-deploy.sh             # SSH-based staging deploy
│   ├── rollback.sh                   # Staging rollback to a previous tag
│   ├── production-deploy.sh          # Production deploy with health probe + auto-rollback
│   ├── production-rollback.sh        # Production rollback (5-min SLO)
│   ├── runbook-production.md         # Backend on-call runbook
│   ├── mobile-release-runbook.md     # TestFlight / Play Internal store releases
│   └── mobile-ota-runbook.md         # Shorebird OTA patches (Dart-only)
├── redis/
│   ├── redis.conf                    # Geo / pub-sub / cache / rate-limit config
│   ├── smoke-test.sh                 # Validates Redis workloads post-up
│   └── README.md                     # Workload contract + ops notes
├── docs/
│   └── adr/
│       └── 0001-shorebird-ota.md     # Why Shorebird over CodePush
├── .github/
│   ├── workflows/
│   │   ├── backend-ci.yml            # Per-PR lint + smoke
│   │   ├── deploy-staging.yml        # Auto-deploy on merge to develop
│   │   ├── deploy-production.yml     # Manual deploy with env protection
│   │   └── rollback-production.yml   # One-click rollback
│   └── CODEOWNERS
├── scripts/
│   ├── smoke-test.sh                 # Local + CI smoke
│   ├── shorebird-patch.sh            # Cut an OTA patch (with native-change guard)
│   └── shorebird-rollback.sh         # Forward-patch rollback for a bad OTA
├── legal/                             # Compliance docs (KYC, ToS, etc.)
└── README.md
```

## Required GitHub configuration

**Secrets** (sensitive — store in environment secrets):

| Name                     | Scope             | Purpose                                      |
| ------------------------ | ----------------- | -------------------------------------------- |
| `STAGING_HOST`           | `staging` env     | SSH host                                     |
| `STAGING_USER`           | `staging` env     | SSH user                                     |
| `STAGING_SSH_KEY`        | `staging` env     | SSH private key (ed25519)                    |
| `STAGING_DOMAIN`         | `staging` env     | e.g. `api.staging.jeeb.app`                  |
| `PRODUCTION_HOST`        | `production` env  | SSH host                                     |
| `PRODUCTION_USER`        | `production` env  | SSH user                                     |
| `PRODUCTION_SSH_KEY`     | `production` env  | SSH private key (ed25519)                    |
| `PRODUCTION_DOMAIN`      | `production` env  | e.g. `api.jeeb.app`                          |

**Variables** (non-sensitive — store in environment variables; needed by
`environment.url` which doesn't accept `secrets`):

| Name              | Scope             | Purpose                              |
| ----------------- | ----------------- | ------------------------------------ |
| `STAGING_URL`     | `staging` env     | e.g. `https://api.staging.jeeb.app`  |
| `PRODUCTION_URL`  | `production` env  | e.g. `https://api.jeeb.app`          |

The `production` GitHub environment MUST be configured with required reviewers
and a deployment branch policy (`main` only). The `staging` environment may
remain unrestricted.

## Reuse

This repo extends — it does not replace — the org's existing deploy patterns:

- BFF/gateway aggregation: `jeeb-gateway` (NSwag-generated clients).
- Auth: Firebase Auth (phone OTP + Apple + Google + Facebook).
- Payments: `unified_payment_gateway` (Elixir) — never bypassed.
- Object storage: in-cluster MinIO for staging / managed S3 for production.
