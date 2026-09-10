# MSI full development backend contract

Status: required target; **live completion is not attested by this document**.

The owner requires MSI to run the complete active Jeeb backend, not a reduced
set sufficient for one mobile test. This document defines that target. It does
not authorize deployment, restart, migration, credential changes, test-data
creation, or alterations to staging/production controls.

## Environment purpose is not a framework switch

MSI is a **development environment**. `ASPNETCORE_ENVIRONMENT` and equivalent
framework settings independently select application behavior; their values
neither establish data isolation nor prove that a full backend is running.

The current gateway skips generic downstream readiness checks in Development
and Testing. Consequently, a green gateway `/health/ready` is not evidence that
MSI's owners are reachable. Do not change the framework environment merely to
make a dashboard green, and do not relax authentication or readiness gates.
Verify each required owner directly using its current contract.

## Mandatory active fleet

All **24** entries below belong to the full development target, including the
gateway. Feature-gated or degraded/non-fatal gateway dependencies remain required
fleet members. Such classifications are not permission to omit services.

The table records source contracts, not observed runtime status. No MSI listener,
unit, image, or process identity is inferred from staging's Swarm inventory.
The timestamped snapshot below supplies observed MSI ports, but does not attest
every unit/process or immutable revision.

| Repository | GET probe | What success establishes / remaining gap |
|---|---|---|
| `jeeb-gateway` | `/health/live`, `/health/ready` | Process and registered checks; Development omits generic owner probes |
| `jeeb-state-service` | `/health/ready` | PostgreSQL readiness; verify configured owner/auth/work capabilities separately |
| `user-management` | `/health/ready` | PostgreSQL and schema readiness |
| `one-time-password` | `/health/ready` | PostgreSQL/schema and mode-specific Twilio configuration; no proof of SMS delivery |
| `wallet-service` | `/health` | PostgreSQL and required schema |
| `feedback-service` | `/swagger/index.html` | Documentation reachability only; no dependency readiness route established |
| `remote-user-preferences` | `/api-docs/openapi.json` | Documentation reachability only; PostgreSQL remains unverified |
| `ban-service` | `/health` | Process liveness; Redis/moderation persistence remains unverified |
| `kyc-service` | `/health/ready` | PostgreSQL readiness |
| `notification-service` | `/health/ready` | MongoDB and required relay/auth/profile checks |
| `push-notification` | `/health/ready` | Database and scoped-caller/Firebase configuration; not device delivery |
| `chat-service` | `/api/Health/check`, `/api/Health/firebase` | Configuration gate plus bounded Firestore read; not end-to-end chat arrival |
| `cdn-service` | `/health/live` | Process only; `/health/ready` creates/deletes a temporary storage probe and is not strictly zero-write |
| `geolocation-service` | `/health` | Process only; location-store readiness remains unverified |
| `delivery-service` | `/health` | Process only; PostgreSQL/schema and event/callback operation remain unverified |
| `offer-service` | `/health/ready` | PostgreSQL read; `/health` alone is liveness |
| `heart-beat` | `/health/ready` | Redis readiness; authenticated presence operation remains unverified |
| `settlement-service` | `/health/ready` | PostgreSQL, auth configuration and timezone support |
| `bundler-service` | `/health/ready` | PostgreSQL; require expected response identity, not a proxy's generic 200 |
| `realtime-comunication-service` | `/health/ready` | PostgreSQL, Redis and PubSub; not Jeeb chat transport |
| `voice-transcription-service` | `/readyz` | Configured readiness checks; transcription-provider check does not make a paid provider call |
| `contract-signing-service` | `/health` | Process only; PostgreSQL/template operation remains unverified |
| `form-builder-service` | `/openapi.json` | Documentation only; database and required templates remain unverified |
| `compliment-service` | `/health` | Process only; PostgreSQL remains unverified |

Older infrastructure inventory uses weaker probes for several services. Confirm
the deployed revision supports the current route before declaring a route failure
an outage. Conversely, a weaker historical route must not substitute for required
dependency readiness. A 401/403, missing mapping, timeout, or generic proxy page is
unverified, never a pass. Avoid logging raw probe bodies that may expose internal
exception details.

## Retired and excluded services

Do not resurrect `matching-service` (delivery owns matching), `role-service`
(user-management owns roles), removed score-taking services, or the retired Jeeb
chat fan-out/SignalR paths. The COD-only product does not use
`unified-payment-gateway`. Redundant `auth-service`, local-only
`masked-call-service`, and empty `catalog-service` are outside this active fleet.
Old client registrations or stale health comments are not activation authority.

## External dependencies and isolation

Before application rollout, establish the intended development identity and
reachability of PostgreSQL, MongoDB, Redis, durable media/object storage, Firebase,
and required provider configuration. Verify database/schema names, Redis logical
namespaces, storage buckets/prefixes and tenant/project boundaries through private
owner-approved checks. A framework label or reachable database alone proves none
of these. Do not silently reuse staging/production data or credentials.

Record only redacted identity attestations and configuration-presence booleans in
reports. Never commit credentials, raw environment/config dumps, DSNs, private
keys, user data, or credential-file contents. Secure credential mounts, scoped
service authentication, schema readiness and durable storage are prerequisites;
missing credentials must not be replaced with bypasses or fake health responses.

## Chat and tracking contracts

Chat remains Firebase-only for realtime message transport, with chat-service as
the authenticated conversation/message owner. Verify the canonical Jeeb Firebase
identity, supported Firestore database, valid service identity, and authorization
rules. Never enable permissive Firestore rules or restore legacy realtime chat
fan-out to satisfy a health check. Readiness does not prove two-party arrival;
that requires separately authorized evidence on the actual app/runtime revisions.

Tracking remains bound to the authenticated delivery participant and correct
delivery/location owner. Verify route/proxy alignment, identity propagation,
location persistence and retrieval, availability/presence dependencies, and
foreground/background recovery. Cached coordinates or a successful process probe
do not prove fresh tracking. Do not invent coordinates or create deliveries to
claim verification without separate authorization.

## Ordered verification and rollout planning

1. Reconcile all 24 repository identities against actual MSI units/containers,
   listeners, gateway routes and immutable revisions. Preserve incumbent services.
2. Verify isolated datastores, storage, credentials and schema readiness first.
   Any migration or repair requires its own reviewed operational plan.
3. Establish state, identity, OTP, wallet and other durable owners; then delivery,
   offer, geolocation/presence, settlement and supporting content/KYC owners.
4. Verify push before notification's required relay gate, and Firebase before
   chat. Verify voice storage/queue/provider configuration and remaining gated
   capabilities. This is dependency ordering, not permission to restart services.
5. Reconcile gateway configuration to the verified owners. Probe all fleet members
   independently even if gateway aggregate health is green.
6. Perform only separately authorized functional checks, recording tested,
   blocked and not-tested outcomes without promoting liveness to functional pass.

## Completion evidence

Completion requires a timestamped, per-service record tying repository/revision
to actual MSI runtime identity, listener and gateway target, health route/status,
dependency/isolation evidence and unresolved gaps. Include external dependencies
and explicitly distinguish documentation reachability from readiness.

### Realtime correction — 2026-09-10 07:34 UTC

The approved MSI operator verified the actual realtime process environment had
no Redis URL override and used the development default `localhost:6379`, where
connections were refused. The existing dedicated `jeeb-redis` container publishes
its Redis endpoint on `127.0.0.1:6380`; DB0 and the rate-limit namespace were
checked before changing the destination. The deployed runtime config applies
`REDIS_URL` in every environment.

The reviewed [two-setting drop-in](realtime/zzzz-msi-redis.conf) now explicitly
selects `redis://127.0.0.1:6380/0` and preserves the existing pool size5. Only
realtime restarted. Its user, source directory, MIX_ENV and previous secret
settings were preserved; no data was flushed, migrated or directly modified by
the correction. Existing unit/drop-in contents were retained privately on MSI.

After restart, repeated strict readiness returned HTTP200 with `status=ready`
and booleantrue database/redis/pubsub/draining checks. The new process remained
stable without automatic restarts, and its invocation logged Redis-backed rate
limiting. Replay initialization was observed, but its backend metadata was not
visible; Redis-backed replay is **not yet attested**. No prior-release rollback
or broad service restart was performed.

This supersedes only the Redis diagnosis/readiness gap in the historical snapshot
below. It does not establish secure public WSS, physical-device tracking, full
fleet functional acceptance, or deployment of the chat/gateway/mobile fixes.
Those remain separate gates. The gateway's actual process directory must be used
when projecting appsettings: its launch wrapper can change directory after
systemd's declared WorkingDirectory.

A fresh fleet probe at 2026-09-10 07:40:46 UTC returned HTTP 200 from all 24
listed owner endpoints. Chat, bundler and realtime also passed their strict
response-shape checks. This is **not 24 functional passes**; documentation and
liveness-only probe limitations, isolation and physical-device acceptance remain.

### Verified MSI snapshot — 2026-09-09 20:52:22 UTC

Expected host: `ouday-GT70-2OC-2OD`. The running gateway reports framework
environment **Production**; MSI's intended purpose remains **full development**.
Thus the Development-specific probe bypass described above is a general hazard,
not the framework mode observed in this snapshot.

The audit observed **23 of 24 direct probe GETs returning HTTP 200**. This is not
23 full functional passes: the readiness limitations in the fleet table still
apply. The verified destinations below are MSI-specific and supersede neither
staging's topology nor future runtime evidence.

| Repository | Observed MSI port | Probe GET HTTP status |
|---|---:|---:|
| `jeeb-gateway` | 10090 | 200 |
| `jeeb-state-service` | 10073 | 200 |
| `user-management` | 10001 | 200 |
| `one-time-password` | 10037 | 200 |
| `wallet-service` | 10014 | 200 |
| `feedback-service` | 10064 | 200 |
| `remote-user-preferences` | 10067 | 200 |
| `ban-service` | 10065 | 200 |
| `kyc-service` | 10074 | 200 |
| `notification-service` | 10026 | 200 |
| `push-notification` | 10040 | 200 |
| `chat-service` | 5803 | 200 |
| `cdn-service` | 10072 | 200 |
| `geolocation-service` | 10060 | 200 |
| `delivery-service` | 5802 | 200 |
| `offer-service` | 5801 | 200 |
| `heart-beat` | 10075 | 200 |
| `settlement-service` | 10078 | 200 |
| `bundler-service` | 11058 | 200 |
| `realtime-comunication-service` | 5804 | **503** |
| `voice-transcription-service` | 10062 → 10063 | 200 |
| `contract-signing-service` | 10071 | 200 |
| `form-builder-service` | 10070 | 200 |
| `compliment-service` | 10036 | 200 |

Additional verified facts and limits:

- Gateway owner destinations project to `127.0.0.1` using application-settings
  and process-environment projections. Command-line and custom configuration
  providers were **not attested**; this does not by itself prove datastore isolation.
- Voice port 10062 works through the existing checked-in scoped route to active
  candidate port 10063, and the route unit is active. Absence of a process listener
  directly on 10062 is **not a missing voice service**.
- Chat passed its strict readiness shape: `ok=true`, project `jeeb-5a293`, database
  `(default)`, mode `firestore`, and nonnegative integer latency. This is stronger
  than HTTP 200, but not an end-to-end message-arrival test.
- Bundler passed `status=READY` and `checks.database=UP`. Its valid response has
  **no `service` field**; do not reject it for lacking an invented field.
- Realtime returned 503 with `redis=false`; `database`, `pubsub`, and `draining`
  checks were true. Independent Redis PING was refused on local 6379 and returned
  PONG on 6380. Realtime's actual Redis destination remains unverified, so a port
  mismatch is a **hypothesis**, not a diagnosed cause or authority to change it.
- The observed configured public tracking URL was
  `ws://192.168.2.39:5804/socket/websocket`, which is insecure. The MSI public
  gateway is `https://msi.olivium.space/gateway`; secure public tracking ingress
  remains **unverified**. Do not derive a working WSS URL merely by replacing
  its scheme or hostname.
- Filesystem usage was 92%, with approximately 9.7 GiB free. Account for build,
  image and recovery capacity before any separately authorized rollout; this
  observation is not permission to delete data.

No deployments, restarts, or administrator-rights changes were performed for this
historical snapshot. Its then-outstanding realtime readiness gap is superseded
by the correction above. **Full-backend completion remains unverified**: secure
tracking ingress, isolation, immutable runtime identities and remaining
functional/readiness gaps still require evidence.

Source basis: current gateway client/readiness registrations and service health
implementations, cross-checked against the active fleet and exclusions in
[`../staging-192.168.2.20.md`](../staging-192.168.2.20.md). That staging inventory is
a fleet cross-check, not an MSI port/unit authority.
