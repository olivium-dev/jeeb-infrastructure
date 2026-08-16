# Jeeb staging deployment: [decommissioned-host]

## Deployment contract

- Target: `olivium-ephemerals` at `[decommissioned-host]`.
- Public application hostname: `jeeb-staging.fds-1.com`.
- GitHub Actions SSH hostname: `jeeb-staging-ssh.fds-1.com`.
- Workflow name in every active repository: `jeeb-staging-deploy`.
- Trigger: manual `workflow_dispatch` on the repository default branch.
- GitHub environment: `staging`.
- Runtime: single-node Docker Swarm on the encrypted, attachable
  `jeeb-staging-net` overlay network.
- Images: immutable Git-SHA tags in GHCR.
- Update policy: stop-first with health-gated rollback and bounded CPU, memory,
  and JSON log rotation.

The workflow rejects a target unless both the hostname and `[decommissioned-host]` are
present. GitHub-hosted runners reach SSH through Cloudflare Access using a
strict `known_hosts` entry. Each run uses an isolated, temporary remote Docker
credential directory so repository-scoped GHCR tokens cannot race with other
deployments.

## Cloudflare and ingress

The locally managed tunnel `jeeb-staging-192-168-2-20` is run by the enabled
systemd unit `cloudflared-jeeb-staging.service`.

- HTTP and HTTPS route `jeeb-staging.fds-1.com` to the server's nginx ingress.
- TCP/SSH routes `jeeb-staging-ssh.fds-1.com` to the server SSH daemon.
- `https://jeeb-staging.fds-1.com/__tunnel_health` is the ingress smoke check.
- `/home/ec2-user/.cloudflared/cert.pem` and the tunnel credential file are
  server-owned Cloudflare material and must never be copied into a repository.

The gateway is published on host port `10000`. nginx is the only public HTTP
entry point; microservice host ports remain staging-LAN services. A callback
relay on `10090` is restricted by UFW to the local Docker gateway subnet and
forwards the exact case callback paths to the gateway's loopback listener.

## GitHub secrets

The following organization Actions secrets are selected for all active
microservice repositories:

- `JEEB_STAGING_SSH_HOST`
- `JEEB_STAGING_DEPLOY_USER`
- `JEEB_STAGING_SSH_PRIVATE_KEY`
- `JEEB_STAGING_SSH_KNOWN_HOSTS`

Runtime values belong in each repository's `staging` environment, never in a
workflow or source file. The fleet uses the following secret names as needed:

- PostgreSQL: `JEEB_DB_HOST`, `JEEB_DB_PORT`, `JEEB_DB_USERNAME`,
  `JEEB_DB_PASSWORD`, `JEEB_DATABASE_URL`, `JEEB_DB_CONNECTION`,
  `JEEB_STATE_DATABASE_URL`, `KYC_DATABASE_URL`, `JEEB_RTC_DATABASE_URL`.
- MongoDB: `JEEB_MONGO_PORT`. The `[decommissioned-host]` MongoDB instance currently has no
  `security.authorization` setting; access is constrained by its private bind
  addresses and UFW. The notification staging URI therefore contains no
  username or password. If MongoDB authentication is enabled later, rotate to
  a dedicated staging user and update this contract in the same change.
- Redis: `JEEB_REDIS_URL`, `HEARTBEAT_REDIS_URL`.
- Identity and application: `JEEB_JWT_SIGNING_KEY`, `JEEB_JWT_ISSUER`,
  `JEEB_SUPERADMIN_PASSCODE`, `JEEB_PHONE_HASH_PEPPER`,
  `JEEB_FIREBASE_JSON`, `CASE_GATEWAY_CALLBACK_URL`.

`JEEB_FIREBASE_JSON` may be stored as raw service-account JSON or base64. The
workflow validates and normalizes it without logging it, then creates a
service-specific Docker config. No secret value should appear in this runbook,
workflow logs, commits, or shell history.

## Active service inventory

| Repository | Swarm service suffix | Host port | Health gate |
|---|---|---:|---|
| `jeeb-state-service` | `jeeb-state-service` | 10073 | `/health/ready` |
| `user-management` | `user-management` | 10001 | `/health/ready` |
| `one-time-password` | `one-time-password` | 10037 | `/api/OTP/check` |
| `wallet-service` | `wallet-service` | 10014 | `/health` |
| `feedback-service` | `feedback-service` | 10064 | `/swagger/index.html` |
| `remote-user-preferences` | `remote-user-preferences` | 10067 | `/api-docs/openapi.json` |
| `ban-service` | `ban-service` | 10065 | `/health` |
| `kyc-service` | `kyc-service` | 10074 | `/health/ready` |
| `notification-service` | `notification` | 10026 | `/health` |
| `push-notification` | `push-notification` | 10040 | `/health` |
| `chat-service` | `chat-api` | 10028 | `/api/Health/check` |
| `realtime-comunication-service` | `realtime-comunication-service` | 10069 | `/health` |
| `cdn-service` | `cdn-service` | 10072 | `/health/ready` |
| `voice-transcription-service` | `voice-transcription-service` | 10062 | `/healthz` |
| `contract-signing-service` | `contract-signing-service` | 10071 | `/health` |
| `form-builder-service` | `form-builder-service` | 10070 | `/openapi.json` |
| `geolocation-service` | `geolocation-service` | 10060 | `/health` |
| `delivery-service` | `delivery-service` | 10055 | `/health` |
| `compliment-service` | `compliment-service` | 10036 | `/health` |
| `offer-service` | `offer-service` | 10063 | `/health` |
| `heart-beat` | `heart-beat` | 10075 | `/health/ready` |
| `jeeb-gateway` | `jeeb-gateway` | 10000 | `/health/ready` |

Every full Swarm name is prefixed with `jeeb-staging-`.

Repositories intentionally outside this fleet are not staging deploy targets:
matching is retired, score-taking was removed, unified payment gateway is no
longer used for the COD-only flow, auth-service is redundant, role-service is
RETIRED (owner decision O8, 2026-08-16 - its gateway client, flag and health check
are deleted and the MSI unit is decommissioned; user-management owns roles),
masked-call is local-only, and catalog is empty.

## Server prerequisites

- Docker Engine is active and `ec2-user` is in the `docker` group.
- the Swarm advertises `[decommissioned-host]` and `jeeb-staging-net` exists.
- PostgreSQL, MongoDB, and Redis listen on their intended private interfaces;
  UFW allows their ports only from the local Docker gateway subnet.
- `/opt/jeeb-staging-cdn/uploads` exists with deployment-user/Docker ownership.
- nginx, the staging Cloudflare service, and the pre-existing Nextcloud AIO
  stack remain enabled and healthy.

## Operating procedure

1. Confirm the Cloudflare systemd unit and the public tunnel health endpoint.
2. Confirm Cloudflare SSH reaches hostname `olivium-ephemerals` and that the
   target has `[decommissioned-host]`.
3. Dispatch `jeeb-staging-deploy` for dependency services first.
4. Require a successful Actions health gate and `1/1` Swarm replicas for every
   dependency.
5. Dispatch `jeeb-gateway` last, then verify its readiness endpoint through
   loopback and public HTTPS.
6. On failure, inspect the Actions run and `docker service logs`; do not bypass
   the health gate. Correct configuration or code, publish it, and make a fresh
   dispatch so the run uses the new commit.

Useful non-secret checks:

```bash
curl -fsS https://jeeb-staging.fds-1.com/__tunnel_health
cloudflared access ssh --hostname jeeb-staging-ssh.fds-1.com
gh workflow run jeeb-staging-deploy.yml -R olivium-dev/SERVICE_REPOSITORY
docker service ls --format '{{.Name}} {{.Replicas}}' | sort
```

Rotate any legacy shared SSH password found in local historical notes and
remove the plaintext copies after access through the dedicated Actions key has
been confirmed. The Actions private key, Cloudflare tunnel credentials,
database credentials, Firebase JSON, and JWT material are deliberately omitted
from this document.
