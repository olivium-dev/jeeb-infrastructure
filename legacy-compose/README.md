# Legacy Docker Compose Files

## Status: DEPRECATED for Production

These Docker Compose files and deployment scripts are **preserved for local development only**. They are no longer used for production deployments.

## New Production Architecture

Production now uses:
- **nginx on host** (not Traefik in container)
- **Docker Swarm** single-node orchestration
- **GHCR images** tagged with `:<github.run_id>`
- **Cloudflare Tunnel** for SSH access
- **GitHub Actions** for all deployments

See the main repository README and `.github/workflows/` for current production workflows.

## Files in this Directory

| File | Purpose | Status |
|------|---------|--------|
| `docker-compose.yml` | Local development stack | Local-dev only |
| `docker-compose.staging.yml` | Staging overrides (legacy) | Deprecated |
| `docker-compose.production.yml` | Production overrides (legacy) | Deprecated |
| `docker-compose.monitoring.yml` | Monitoring stack (legacy) | Deprecated |
| `deploy/production-deploy.sh` | Deploy script (legacy) | Deprecated |
| `deploy/staging-deploy.sh` | Deploy script (legacy) | Deprecated |

## Local Development Usage

For local development (on your laptop), these still work:

```bash
cd legacy-compose
cp ../.env.example .env
# Edit .env with local values

docker compose up -d
curl http://localhost:5000/health/live
```

## Why the Change?

The organization standardized on the pattern used by Rahma, Cremat, and Saawt VPSes:
- nginx on host for TLS termination and routing
- Docker Swarm for service orchestration
- Cloudflare Tunnels for secure access
- GitHub Actions for CI/CD

This provides:
- Consistency across all product lines
- Better security (no port 22 exposed to internet)
- Zero-downtime rolling deployments
- Explicit pause-on-failure and fix-forward recovery

## Migration Path

If you need to migrate from the old compose-based production setup:

1. Bootstrap the new VPS using `scripts/bootstrap-vps.sh`
2. Use `.github/workflows/swarm-bootstrap-service.yml` to create services
3. Use `.github/workflows/swarm-deploy.yml` for updates
4. Keep these compose files for local development parity

## Questions?

See the main README.md or refer to the organization's deployment analysis document.
