# jeeb-infrastructure

Deployment infrastructure for the Jeeb platform using Docker Swarm + nginx on host, following the organization's proven pattern.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  GitHub Actions Runner                                                      │
│  ┌──────────────────┐    cloudflared access tcp    ┌──────────────────┐    │
│  │ Build & Push    │ ──────────────────────────▶ │ Jeeb VPS         │    │
│  │ GHCR Image      │    (SSH over CF Tunnel)      │ approved VPS     │    │
│  └──────────────────┘                             └──────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                                            │
                    ┌───────────────────────────────────────┴───────────┐
                    │                                               │
                    ▼                                               ▼
            ┌──────────────┐                              ┌──────────────┐
            │ nginx (host) │                              │ Docker Swarm │
            │ :80 → :443   │─────proxy_pass────────────▶ │ Single-node  │
            │ TLS LE       │      localhost:10000         │ Manager      │
            └──────────────┘                              └──────────────┘
                                                               │
                                                    ┌──────────┴──────────┐
                                                    │                     │
                                                    ▼                     ▼
                                            ┌──────────────┐     ┌──────────────┐
                                            │ jeeb-gateway │     │   Future     │
                                            │  ghcr:image  │     │  services    │
                                            └──────────────┘     └──────────────┘
```

### Design Principles (from Rahma/Cremat/Saawt analysis)

- **nginx on host** (not Traefik in container): TLS termination at host level
- **Docker Swarm** single-node: Zero-downtime rolling updates via `docker service update`
- **GHCR images** tagged with `:<github.run_id>`: Immutable, traceable deployments
- **Cloudflare Tunnel**: No SSH port exposed to internet; GitHub Actions connect via `cloudflared access tcp`
- **GitHub Actions**: All deploys automated; manual SSH only for emergency

## Environments

The authoritative active-staging contract is
[`deploy/staging-192.168.2.20.md`](deploy/staging-192.168.2.20.md). It identifies
`192.168.2.20` (`olivium-ephemerals`) as the live staging host; older VPS
bootstrap examples below are historical setup guidance, not the active staging
target. The current isolated-data baseline and 2026-08-19 cleanup record are in
[`docs/staging-data-baseline-2026-08-19.md`](docs/staging-data-baseline-2026-08-19.md).

| Env        | Deployment Method                              | TLS                         | URL |
| ---------- | ---------------------------------------------- | --------------------------- | --- |
| local      | `docker compose` (legacy-compose/)             | none                        | http://localhost:5000 |
| staging    | GitHub Actions manual dispatch → Swarm on `.20` | Cloudflare edge + nginx LE | https://app.jeeb.fds-1.com and https://cms.jeeb.fds-1.com |
| production | GitHub Actions → Swarm (manual + approval)     | Let's Encrypt               | https://jeeb.fds-1.com |

## Quick Start — Local Development

For local development, use the legacy compose files:

```bash
cd legacy-compose
cp ../.env.example .env
# Edit .env: POSTGRES_PASSWORD, JWT_KEY

docker compose up -d
curl http://localhost:5000/health/live
```

## GitHub Actions Workflows

### Infrastructure Workflows (jeeb-infrastructure)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `deploy-nginx.yml` | Push to `nginx/**` | Validate, apply, and verify nginx config |
| `deploy-static-pages.yml` | Push to `static-pages/**` | Deploy static HTML/assets |
| `update-ssl-certificate.yml` | Schedule 2× daily | Renew Let's Encrypt certs via DNS-01 |
| `verify-server.yml` | Schedule daily + manual | Diagnostic: Swarm, nginx, SSL, cloudflared status |
| `jeeb-staging-edge-deploy.yml` | Manual, default branch only | Deploy and live-gate staging nginx, association files, and Cloudflare Worker with automatic restoration |
| `deployment-safety.yml` | PR + push to `main` | Enforce strict edge access, health gates, and restoration authority |

### Service Deploy Workflows (jeeb-gateway, etc.)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `build.yml` | Push to `main` | Build, test, and publish an immutable image |
| `deploy-to-jeeb.yml` | Manual | Deploy the build-produced digest and verify the exact runtime |

## File Structure

```
jeeb-infrastructure/
├── nginx/
│   ├── nginx.conf                    # Main nginx config
│   ├── sites-available/            # Per-domain site configs
│   │   └── jeeb.fds-1.com.conf     # Main site: TLS + proxy to :10000
│   └── sites-enabled/              # Symlinks (managed by deploy-nginx.yml)
├── static-pages/                   # Static HTML assets
│   └── index.html                  # Default welcome page
├── scripts/
│   ├── bootstrap-vps.sh            # ONE-TIME: Bootstrap fresh VPS
│   ├── smoke-test.sh               # Local smoke test
│   ├── shorebird-*.sh              # Mobile OTA (unchanged)
│   └── verify-*.sh                 # Verification scripts
├── .github/
│   ├── actions/
│   │   └── cloudflare-ssh/         # Composite action for CF tunnel SSH
│   │       └── action.yml
│   └── workflows/
│       ├── deploy-nginx.yml        # Gold-standard nginx deploy (Rahma pattern)
│       ├── deploy-static-pages.yml # Static assets deploy
│       ├── update-ssl-certificate.yml # Certbot renewal
│       ├── verify-server.yml       # Diagnostic checks
│       ├── jeeb-staging-edge-deploy.yml # Staging edge deploy + restoration
│       └── deployment-safety.yml    # Deployment safety policy gate
├── legacy-compose/                 # PREVIOUS: Docker Compose + Traefik
│   ├── docker-compose*.yml         # (Local dev only — not production)
│   ├── deploy/*.sh                 # (Old deploy scripts)
│   ├── workflows/                  # (Old workflows)
│   └── README.md                   # Migration notes
├── redis/                          # Redis config (for local dev)
├── monitoring/                     # Prometheus/Grafana (opt-in)
├── docs/                           # ADRs, runbooks
└── README.md                       # This file
```

## Required GitHub Secrets

Configure these via `gh secret set`:

| Secret | Purpose |
|--------|---------|
| `JEEB_SSH_PRIVATE_KEY` | ed25519 private key (base64-encoded) for VPS access |
| `JEEB_SSH_HOST` | Cloudflare tunnel hostname: `ssh.jeeb.fds-1.com` |
| `JEEB_DEPLOY_USER` | SSH user: `ec2-user` |
| `CF_API_TOKEN` | Cloudflare API token (for certbot DNS-01) |
| `JEEB_STAGING_SSH_PRIVATE_KEY` | Dedicated staging ed25519 key |
| `JEEB_STAGING_SSH_HOST` | Pinned staging Cloudflare SSH hostname |
| `JEEB_STAGING_DEPLOY_USER` | Staging deployment user |
| `JEEB_STAGING_SSH_KNOWN_HOSTS` | Exact staging SSH host-key entry |
| `CLOUDFLARE_API_TOKEN` | Scoped token for the staging Worker and Custom Domains |

### For Production Environment

| Secret/Variable | Purpose |
|-----------------|---------|
| `PRODUCTION_DOMAIN` | `jeeb.fds-1.com` |
| `PRODUCTION_URL` (variable) | `https://jeeb.fds-1.com` |

## Bootstrap a Fresh VPS (One-Time)

This is the **only** manual SSH step. After this, everything is GitHub Actions.

### 1. Generate Deploy Key

```bash
ssh-keygen -t ed25519 -f ./jeeb-deploy-key -N "" -C "jeeb-gh-actions"
# Public key: jeeb-deploy-key.pub (for VPS authorized_keys)
# Private key: jeeb-deploy-key (for GH secret)
```

### 2. Copy Bootstrap Script to VPS

```bash
# From your laptop, while on the same network as the VPS
JEEB_BOOTSTRAP_HOST=approved-hostname.example
ssh "ec2-user@$JEEB_BOOTSTRAP_HOST" 'install -d -m 700 .jeeb-bootstrap'
scp scripts/bootstrap-vps.sh \
  "ec2-user@$JEEB_BOOTSTRAP_HOST:.jeeb-bootstrap/bootstrap-vps.sh"
```

### 3. Run Bootstrap (on VPS)

```bash
ssh "ec2-user@$JEEB_BOOTSTRAP_HOST" 'sudo \
  BOOTSTRAP_DOMAIN=jeeb.fds-1.com \
  GH_DEPLOY_PUBKEY="ssh-ed25519 AAAAC3..." \
  CF_API_TOKEN="your-cloudflare-token" \
  SWARM_ADVERTISE_ADDR="approved-private-address" \
  bash .jeeb-bootstrap/bootstrap-vps.sh'
```

The bootstrap script:
- Installs Docker, nginx, certbot, cloudflared, fail2ban
- Initializes Docker Swarm single-node
- Creates Cloudflare tunnel systemd units
- Enables UFW firewall (unlike Rahma/Cremat which leave it off)
- Hardens SSH: key-only auth, no passwords
- Sets up Let's Encrypt with Cloudflare DNS-01

### 4. Configure Cloudflare Tunnels (on VPS)

```bash
# SSH to VPS (via lab network or after bootstrap)
ssh "ec2-user@$JEEB_BOOTSTRAP_HOST"

# Login and create tunnels
cloudflared tunnel login
cloudflared tunnel create jeeb-http
cloudflared tunnel create jeeb-ssh

# Note the tunnel IDs and update the config files
# Then create DNS routes
cloudflared tunnel route dns jeeb-http jeeb.fds-1.com
cloudflared tunnel route dns jeeb-http '*.jeeb.fds-1.com'
cloudflared tunnel route dns jeeb-ssh ssh.jeeb.fds-1.com

# Update config files with tunnel IDs
# /home/ec2-user/.cloudflared/jeeb-http.yml
# /home/ec2-user/.cloudflared/jeeb-ssh.yml

# Start tunnels
sudo systemctl start cloudflare-http-tunnel cloudflare-ssh-tunnel
```

### 5. Obtain SSL Certificate

```bash
ssh "ec2-user@$JEEB_BOOTSTRAP_HOST"
sudo certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d jeeb.fds-1.com -d '*.jeeb.fds-1.com' \
  --agree-tos --non-interactive --email admin@jeeb.fds-1.com

sudo nginx -t && sudo systemctl reload nginx
```

### 6. Store Secrets in GitHub

```bash
# From your laptop
cat jeeb-deploy-key | base64 | gh secret set JEEB_SSH_PRIVATE_KEY -R olivium-dev/jeeb-infrastructure

echo "ssh.jeeb.fds-1.com" | gh secret set JEEB_SSH_HOST -R olivium-dev/jeeb-infrastructure
echo "ec2-user" | gh secret set JEEB_DEPLOY_USER -R olivium-dev/jeeb-infrastructure

cat cf-token.txt | gh secret set CF_API_TOKEN -R olivium-dev/jeeb-infrastructure

# Production environment
echo "jeeb.fds-1.com" | gh secret set PRODUCTION_DOMAIN -R olivium-dev/jeeb-infrastructure
echo "https://jeeb.fds-1.com" | gh variable set PRODUCTION_URL -R olivium-dev/jeeb-infrastructure
```

Delete the local key file after storing:
```bash
rm -f jeeb-deploy-key jeeb-deploy-key.pub
```

## Deploy a Microservice

Application deployment authority lives only in each canonical service
repository. Its workflow must build the image, consume that build step's
repository digest, update-or-create the service with pause-on-failure, and
verify the exact service, task, container, and image identities. This
infrastructure repository deliberately carries no generic Swarm mutation
workflow and does not accept caller-provided image tags.

Datastores are pre-provisioned runtime dependencies. Application deployment
workflows verify those dependencies but do not recreate or replace them.

## Failed deployments

Swarm updates use `failure_action: pause`. A failed candidate remains visible
for diagnosis; fix the fault, build a new immutable image, and deploy that image.

## Monitoring & Observability

The optional monitoring stack (Prometheus + Grafana) is still available in `legacy-compose/docker-compose.monitoring.yml` for local development.

For production monitoring:
- Swarm built-in: `docker service ps <service>`
- Health endpoints: `https://jeeb.fds-1.com/health/live`
- Verify workflow: Run `verify-server.yml` on-demand for diagnostics

## Security Improvements vs. Reference Servers

This implementation closes the gaps identified in the Rahma/Cremat/Saawt analysis:

| Gap | Rahma/Cremat/Saawt | Jeeb (this setup) |
|-----|-------------------|-------------------|
| SSH password | `P@ssw0rd768` hardcoded | ed25519 key-only from day one |
| Firewall | UFW inactive | UFW enabled with proper rules |
| Cloudflared | Single combined unit (outdated 2025.8.1) | Two separate units (latest) |
| SSL certs | Mixed DNS-01 + self-signed hack | Clean DNS-01 only |
| Secrets | On-disk, world-readable | GitHub environment secrets |

## Migration from Old Setup

If you have a previous Traefik-based deployment:

1. **Keep the VPS** — the bootstrap script is idempotent and can upgrade in-place
2. **Drain the old compose stack**: `docker compose -f legacy-compose/docker-compose.production.yml down`
3. **Run bootstrap** to ensure nginx, cloudflared, Swarm are configured
4. **Deploy services** via each canonical service repository's exact-digest workflow
5. **Update nginx** via `deploy-nginx.yml` to add the location blocks
6. **Delete old compose** once verified working

The legacy compose files are preserved under `legacy-compose/` for local development parity.

## Troubleshooting

### SSH Connection Fails in GitHub Actions

1. Check Cloudflare tunnel is running: `sudo systemctl status cloudflare-ssh-tunnel`
2. Verify SSH key: `ssh -o ProxyCommand='cloudflared access tcp --hostname ssh.jeeb.fds-1.com' ec2-user@localhost`
3. Check `JEEB_SSH_PRIVATE_KEY` is base64-encoded in GitHub secrets

### Nginx Config Test Fails

1. Run `verify-server.yml` to see nginx error log
2. Check SSL certificates exist: `sudo certbot certificates`
3. Test locally: `sudo nginx -t`

### Swarm Service Won't Start

1. Check image exists in GHCR: `docker manifest inspect ghcr.io/olivium-dev/<service>:<tag>`
2. Check VPS can reach GHCR: `docker pull ghcr.io/olivium-dev/<service>:<tag>`
3. View service logs: `docker service ps <service>` and `docker service logs <service>`

## Related Repositories

- `olivium-dev/jeeb-gateway` — BFF/gateway service (.NET 8)
- `olivium-dev/jeeb-admin` — Admin panel (React + Vite)
- `olivium-dev/jeeb-mobile` — Flutter app
- `olivium-dev/jeeb-infrastructure` — This repo (deployment infrastructure)
