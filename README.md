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

| Service        | Image                  | Host:Container | Purpose                    |
| -------------- | ---------------------- | -------------- | -------------------------- |
| jeeb-gateway   | Built from ../jeeb-gateway | 5000:8080  | BFF gateway (ASP.NET Core) |
| postgres       | postgres:16-alpine     | 5432:5432      | Primary database           |
| redis          | redis:7-alpine         | 6379:6379      | Cache / session store      |

The gateway container listens on `:8080` internally and is published as `:5000`
on the host. The `/health/live` endpoint is the readiness/liveness probe used
by Docker `HEALTHCHECK`, the staging deploy verifier, and the smoke test.

## Smoke test (local + CI)

```bash
cp .env.example .env  # adjust as needed
./scripts/smoke-test.sh         # uses default 180s timeout
./scripts/smoke-test.sh 60      # custom timeout
```

The smoke test brings the stack up via Docker Compose, polls
`http://localhost:5000/health/live` until it returns 200, then tears the stack
down. It is also run by `.github/workflows/backend-ci.yml` on every PR.

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

## File Structure

```
jeeb-infrastructure/
├── docker-compose.yml            # Local dev environment
├── docker-compose.staging.yml    # Staging overrides
├── .env.example                  # Environment variable template
├── deploy/
│   ├── staging-deploy.sh         # SSH-based staging deploy
│   └── rollback.sh               # Rollback to a previous tag
├── .github/
│   ├── workflows/
│   │   ├── backend-ci.yml        # CI: lint + smoke (per PR)
│   │   └── deploy-staging.yml    # CI: deploy on merge to main
│   └── CODEOWNERS
├── scripts/
│   └── smoke-test.sh             # Compose-up + /health/live probe
└── README.md
```
