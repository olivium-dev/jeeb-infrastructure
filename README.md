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
| redis          | redis:7-alpine         | 6379 | Geo / pub-sub / cache / rate-limit (see [`redis/`](./redis/)) |

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
├── redis/
│   ├── redis.conf                # Geo / pub-sub / cache / rate-limit config
│   ├── smoke-test.sh             # Validates Redis workloads post-up
│   └── README.md                 # Workload contract + ops notes
├── .github/
│   ├── workflows/
│   │   └── deploy-staging.yml    # CI: deploy on merge to main
│   └── CODEOWNERS
└── README.md
```
