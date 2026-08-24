# Jeeb staging deployment: 192.168.2.20

## Current status

`192.168.2.20` (`olivium-ephemerals`) is the active Jeeb staging host. It was
reactivated on 2026-08-18, superseding its previous decommissioned status.
Historical retirement evidence remains historical; it must not be used to
block approved staging deployments to this host.

The environment was last fully validated on 2026-08-19 after datastore
isolation, fleet deployment, public ingress validation, and a staging-only
user-data cleanup. The public Super Login Plus roster intentionally contains
only Nour and Karim. CMS administrator authentication is a separate control;
there is no corresponding `Admin` row in the user-management database.

The detailed data-operation record and verification evidence are in
[`docs/staging-data-baseline-2026-08-19.md`](../docs/staging-data-baseline-2026-08-19.md).

## Deployment contract

- Target: `olivium-ephemerals` at `192.168.2.20`.
- Public gateway hostname: `app.jeeb.fds-1.com`.
- Public CMS hostname: `cms.jeeb.fds-1.com`.
- GitHub Actions SSH hostname: `jeeb-staging-ssh.fds-1.com`.
- Workflow name in every active repository: `jeeb-staging-deploy`.
- Trigger: manual `workflow_dispatch` on the repository default branch.
- GitHub environment: `staging`.
- Runtime: single-node Docker Swarm on the encrypted, attachable
  `jeeb-staging-net` overlay network.
- Images: immutable Git-SHA tags in GHCR.
- Update policy: stop-first with fail-closed health gates and bounded CPU,
  memory, and JSON log rotation.
- Failure policy: single-replica host-mode services update stop-first with
  automatic rollback and rollback-order stop-first. Preserve and verify the
  incumbent digest before mutation. The staging edge separately restores the
  exact incumbent Worker version and nginx configuration when any public live
  gate fails.

The workflow rejects a target unless both the hostname and `192.168.2.20` are
present. GitHub-hosted runners reach SSH through Cloudflare Access using a
strict `known_hosts` entry. Each run uses an isolated, temporary remote Docker
credential directory so repository-scoped GHCR tokens cannot race with other
deployments.

## Cloudflare and ingress

The locally managed tunnel `jeeb-staging-192-168-2-20` is run by the enabled
systemd unit `cloudflared-jeeb-staging.service`. It follows the same tunnel
pattern as the other working servers; no router port forwarding is required.

- Worker `jeeb-staging-host-router` owns the exact Custom Domains
  `app.jeeb.fds-1.com` and `cms.jeeb.fds-1.com` and injects a runtime origin key.
- The Worker maps those names to the proxied tunnel-only hostnames
  `jeeb-app-origin.fds-1.com` and `jeeb-cms-origin.fds-1.com` respectively.
- `cloudflared` forwards both hidden hostnames to nginx TLS on loopback, using
  the corresponding public hostname for certificate and HTTP Host validation.
- TCP/SSH remains at `jeeb-staging-ssh.fds-1.com` and routes to the server SSH
  daemon.
- The superseded web hostname `jeeb-staging.fds-1.com` has no DNS record or
  tunnel ingress. It may remain as an opaque JWT issuer value until token
  consumers are migrated in a separately coordinated identity change.
- `/home/ec2-user/.cloudflared/cert.pem` and the tunnel credential file are
  server-owned Cloudflare material and must never be copied into a repository.

Cloudflare automatically manages the public edge certificates for both Worker
Custom Domains. Their DNS validation TXT records must remain in the zone for
renewal. nginx terminates a separate Let's Encrypt ECDSA certificate named
`jeeb-staging-edge`, containing both public names. It is issued through DNS-01
with a zone-scoped Cloudflare token stored only in the root-readable file
`/etc/letsencrypt/jeeb-secrets/cloudflare.ini`. The enabled certbot timer renews
it, and `/etc/letsencrypt/renewal-hooks/deploy/jeeb-nginx` validates the nginx
configuration before reload.

nginx listens for HTTPS only on `127.0.0.1` and `::1`, and rejects requests
that do not carry the Worker's origin key. The matching key exists only as a
Worker secret and in root-owned `/etc/nginx/jeeb-origin-key.map`; it must never
be committed. The gateway is published on host port `10000` behind the app
virtual host. The CMS virtual host proxies the LAN-only MSI origin at
`192.168.2.39`, while its private callback paths fail closed. Microservice host
ports remain staging-LAN services. A callback relay on `10090` is restricted by
UFW to the local Docker gateway subnet and forwards the exact case callback
paths to the gateway's loopback listener.

Install repository-owned origin files deterministically; provision the two
runtime secrets separately before validation:

```bash
sudo install -o root -g root -m 0644 deploy/staging/nginx/jeeb-direct-tls.conf \
  /etc/nginx/sites-available/jeeb-direct-tls.conf
sudo ln -sfn /etc/nginx/sites-available/jeeb-direct-tls.conf \
  /etc/nginx/sites-enabled/jeeb-direct-tls.conf
sudo install -o root -g root -m 0600 \
  deploy/staging/cloudflare/cloudflared-ingress.yml.template \
  /etc/cloudflared-jeeb-staging/config.yml
sudo install -o root -g root -m 0755 \
  deploy/staging/letsencrypt/renewal-hooks/deploy/jeeb-nginx \
  /etc/letsencrypt/renewal-hooks/deploy/jeeb-nginx
sudo cloudflared --config /etc/cloudflared-jeeb-staging/config.yml \
  tunnel ingress validate
sudo nginx -t
sudo systemctl restart cloudflared-jeeb-staging nginx
```

The gateway staging workflow derives the exact `docker_gwbridge` gateway used
by the host-mode published port and configures only that single address as a
trusted forwarded-header proxy; it does not trust the bridge or application
overlay ranges. It also allowlists only `https://app.jeeb.fds-1.com` and
`https://cms.jeeb.fds-1.com` for admin session origins. The public app and CMS
session probes must reach `csrf_rejected` when deliberately sent without a CSRF
token; `origin_rejected` indicates a broken proxy contract.

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
- MongoDB: `JEEB_MONGO_PORT`. The `192.168.2.20` MongoDB instance currently has no
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

## Staging datastore isolation

PostgreSQL 16, MongoDB 7, and Redis 7 run as native systemd services on
`192.168.2.20`; no Jeeb database engine runs in Docker. Staging application
containers use only the following staging-owned databases and Redis logical
indexes. The unsuffixed databases remain separate source/dev stores and must
not be referenced by a staging workflow.

| Owner | Staging datastore |
|---|---|
| user-management | PostgreSQL `jeeb-user-management_staging` |
| one-time-password | PostgreSQL `jeeb-otpdb_staging` |
| wallet-service | PostgreSQL `jeeb-wallet_staging` |
| feedback-service | PostgreSQL `feedback_service_staging` |
| jeeb-state-service | PostgreSQL `jeeb_state_staging` |
| kyc-service | PostgreSQL `jeeb_kyc_staging` |
| push-notification | PostgreSQL `jeeb-push-notifications_staging` |
| realtime-comunication-service | PostgreSQL `jeeb_realtime_comm_staging`; Redis db 5 |
| contract-signing-service | PostgreSQL `jeeb_contract_signing_staging` |
| form-builder-service | PostgreSQL `jeeb_form_builder_staging` |
| geolocation-service | PostgreSQL `jeeb-location_staging` |
| delivery-service | PostgreSQL `delivery_staging` |
| compliment-service | PostgreSQL `compliment_staging` |
| offer-service | PostgreSQL `offer_service_staging` |
| remote-user-preferences | PostgreSQL `jeeb_remote_user_preferences_staging` |
| settlement-service | PostgreSQL `jeeb_settlement_staging` |
| bundler-service | PostgreSQL `jeeb_bundler_staging` |
| notification-service | MongoDB `jeeb_notifications_staging` |
| chat-service | Firestore named database `staging` in project `jeeb-5a293` |
| ban-service | Redis db 3 |
| heart-beat | Redis db 4 |
| voice-transcription-service | Redis db 6 |
| jeeb-gateway | Redis db 1; rate limiting in Redis db 2; current main is PostgreSQL-free |
| cdn-service | Host path `/opt/jeeb-staging-cdn/uploads` |

Database basenames are enforced in the repository-scoped staging workflows;
opaque URL secrets are insufficient on their own. Before the 2026-08-19
cutover, every PostgreSQL and MongoDB source was captured to a timestamped,
host-owned dump and restored into the corresponding staging target. Future
schema or seed changes must target only the owning staging datastore.

### Current staging data baseline

As of the 2026-08-19 cleanup:

- `jeeb-user-management_staging` contains exactly two application users: Nour
  (`d1000000-0000-4000-8000-000000000001`) and Karim
  (`d1000000-0000-4000-8000-000000000002`).
- The separate CMS administrator authentication and CMS configuration were
  preserved. Do not create a synthetic user-management `Admin` row to
  represent that administrator.
- All staging PostgreSQL references to the 361 deleted user IDs were scanned;
  zero residual references remained.
- MongoDB notification documents are retained only when their receiver or
  target is Nour or Karim.
- Firestore database `staging` had zero top-level collections, and the staging
  CDN upload path had zero files.
- Redis databases 1 through 6 are staging-owned. They were cleared during the
  cleanup; Redis database 0 is the separate dev store and was not modified.
- The unsuffixed dev user-management database remained at 363 users.

The verified safety snapshot is stored on the staging host at
`/home/ec2-user/jeeb-staging-user-purge/20260819T152107Z`. It contains 18
PostgreSQL custom-format dumps, the staging MongoDB archive, the deleted-ID
manifest, and a 20-entry SHA-256 manifest. This is a recovery artifact for the
destructive data operation, not a deployment-reversion mechanism.

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
| `settlement-service` | `settlement-service` | internal only | `/health/ready` |
| `bundler-service` | `bundler-service` | 10056 | `/health/ready` |
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
- the Swarm advertises `192.168.2.20` and `jeeb-staging-net` exists.
- PostgreSQL, MongoDB, and Redis listen on their intended private interfaces;
  UFW allows their ports only from the local Docker gateway subnet.
- `/opt/jeeb-staging-cdn/uploads` exists with deployment-user/Docker ownership.
- nginx, the staging Cloudflare service, the certbot timer, and the pre-existing
  Nextcloud AIO stack remain enabled and healthy.

## Operating procedure

1. Confirm the Cloudflare systemd unit, nginx, certbot timer, and the public
   tunnel health endpoint.
2. Confirm Cloudflare SSH reaches hostname `olivium-ephemerals` and that the
   target has `192.168.2.20`.
3. Dispatch `jeeb-staging-deploy` for dependency services first.
4. Require a successful Actions health gate and `1/1` Swarm replicas for every
   dependency.
5. Dispatch `jeeb-gateway` last, then verify its readiness endpoint through
   loopback and public HTTPS.
6. On failure, confirm the workflow restored the recorded incumbent digest or
   edge version, inspect the Actions run and service logs, correct the fault,
   and dispatch a fresh immutable commit. Never bypass the health gate.

Useful non-secret checks:

```bash
curl -fsS https://app.jeeb.fds-1.com/__tunnel_health
curl -fsS https://app.jeeb.fds-1.com/health/ready
curl -fsS https://cms.jeeb.fds-1.com/healthz
cloudflared access ssh --hostname jeeb-staging-ssh.fds-1.com
gh workflow run jeeb-staging-deploy.yml -R olivium-dev/SERVICE_REPOSITORY
docker service ls --format '{{.Name}} {{.Replicas}}' | sort
```

Expected post-cleanup results:

- `https://app.jeeb.fds-1.com/health/ready` reports `Healthy` with all 18
  readiness checks healthy.
- All 24 active `jeeb-staging-*` Swarm services report `1/1`; the intentionally
  disabled `jeeb-staging-notification-candidate` reports `0/0`.
- `https://cms.jeeb.fds-1.com/` returns HTTP 200.
- `GET /api/User/super-login/users` returns exactly Nour and Karim.
- A token minted for either retained user with explicit `customer` and
  `driver` roles can call `GET /v1/users/me` successfully.

The protected gateway root may return HTTP 401 by design. Use `/health/ready`,
not `/`, as the unauthenticated gateway health probe.

Rotate any legacy shared SSH password found in local historical notes and
remove the plaintext copies after access through the dedicated Actions key has
been confirmed. The Actions private key, Cloudflare tunnel credentials,
database credentials, Firebase JSON, and JWT material are deliberately omitted
from this document.
