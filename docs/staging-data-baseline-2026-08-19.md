# Jeeb staging data baseline: 2026-08-19

## Purpose

This record documents the staging-only user cleanup performed on the active
Jeeb staging environment at `192.168.2.20` (`olivium-ephemerals`). It records
the authorized scope, retained identities, safety snapshot, datastore changes,
and post-operation evidence without containing credentials or tokens.

The authoritative environment and deployment contract remains
[`deploy/staging-192.168.2.20.md`](../deploy/staging-192.168.2.20.md).

## Authorized scope

The operation removed every staging application user except Nour and Karim,
along with data owned by the removed users. It was restricted to the isolated
staging datastores documented in the deployment runbook.

Retained application identities:

| Identity | User ID | Roles used by the staging smoke test |
|---|---|---|
| Nour | `d1000000-0000-4000-8000-000000000001` | `customer`, `driver` |
| Karim | `d1000000-0000-4000-8000-000000000002` | `customer`, `driver` |

No genuine `Admin` user existed in `jeeb-user-management_staging`. Rows whose
names contained `admin` were synthetic test/probe users and were not retained.
CMS administrator authentication is separate from the application user roster;
its runtime configuration and CMS data were not changed.

The unsuffixed development databases, Redis database 0, production resources,
Cloudflare configuration, GitHub secrets, and application source repositories
were outside the deletion scope.

## Safety snapshot

Before deletion, the following host-owned snapshot was created:

```text
/home/ec2-user/jeeb-staging-user-purge/20260819T152107Z
```

It contains:

- 18 PostgreSQL custom-format dumps, one for every `*_staging` database;
- one gzip-compressed archive of MongoDB `jeeb_notifications_staging`;
- `removed_user_ids.txt`, containing the 361 deleted user IDs; and
- `SHA256SUMS`, covering all 20 artifacts.

All 20 checksum entries passed after the operation. Redis staging databases are
ephemeral logical databases and were not included in the snapshot. Firestore
database `staging` and `/opt/jeeb-staging-cdn/uploads` were verified empty, so
there was no Firestore or CDN payload to capture.

## Changes performed

### PostgreSQL

All commands targeted databases whose names end in `_staging`. Reference and
configuration data, schema migrations, legal content, CMS surfaces, service
templates, and service configuration were preserved.

The cleanup removed or pruned user-owned data from:

- user management and device ownership;
- OTP phone challenges;
- feedback, ratings, and review reports;
- geolocation pings and user availability;
- push-notification registrations and dispatch state;
- wallet holders, wallets, transactions, and earnings;
- contract parties, signatures, snapshots, and contracts;
- legacy gateway users, requests, exports, notifications, settlements, and
  user audit actions;
- KYC submissions and terms acceptances; and
- state-service cases, disputes, user audit history, user work items,
  broadcast history, sagas, and idempotency state.

Append-only guards in the state database initially rejected deletion and
rolled that transaction back. The final state cleanup ran as one transaction:
only the four relevant user triggers were temporarily disabled, all requested
rows were deleted, the triggers were re-enabled before commit, and every trigger
was verified in enabled state afterward.

Rows shared between a retained and deleted user were removed when retaining the
row would preserve data belonging to the deleted user. Transient OTP,
idempotency, and staging cache records were cleared when they could not be
safely attributed to one retained account.

### MongoDB

In `jeeb_notifications_staging`, documents were retained only for Nour or
Karim:

| Collection | Before | Deleted | Remaining |
|---|---:|---:|---:|
| `dead_letter_notifications` | 15 | 13 | 2 |
| `delivered_notifications` | 67 | 66 | 1 |
| `notifications` | 364 | 303 | 61 |

### Firestore, Redis, and CDN

- Firestore named database `staging` in project `jeeb-5a293` had zero
  top-level collections.
- Redis databases 1 through 6 were cleared. Database 3 changed from five keys
  to zero; the other staging logical databases already contained zero keys.
- Redis database 0 remained unchanged at 26 keys.
- `/opt/jeeb-staging-cdn/uploads` contained zero files.

## Resulting retained data

The user-management roster changed from 363 users to exactly two. Selected
retained user-owned row counts after cleanup were:

| Store | Retained rows |
|---|---:|
| Feedback ratings | 24 |
| Location pings and user status | 72 |
| Push dispatches and registrations | 36 |
| Contracts | 2 |
| Legacy gateway delivery requests | 84 |
| KYC submissions | 2 |
| State-service cases | 3 |
| MongoDB notification documents | 64 |

These rows passed identity-column checks proving that their user fields refer
only to Nour or Karim. A second scan across every non-system PostgreSQL column
found zero occurrences of any of the 361 deleted user IDs.

## Validation evidence

The following checks passed after the cleanup:

| Check | Result |
|---|---|
| Public Super Login Plus roster | Exactly Nour and Karim |
| Nour token and `GET /v1/users/me` | HTTP 200 |
| Karim token and `GET /v1/users/me` | HTTP 200 |
| Gateway `GET /health/ready` | `Healthy`; 18/18 checks healthy |
| Active Swarm services | 24/24 at `1/1` |
| Notification candidate | Intentionally disabled at `0/0` |
| Public CMS | HTTP 200 |
| Staging user-management count | 2 |
| Dev user-management count | 363, unchanged |
| Removed-ID PostgreSQL residual scan | 0 |
| Snapshot checksum verification | 20/20 passed |

The gateway root is protected and may return HTTP 401. This is not a health
failure; `/health/ready` is the authoritative unauthenticated gateway probe.

## Operating rules after this baseline

- Staging workflows must reference only the datastores listed in the canonical
  `.20` runbook; an unsuffixed database name is a release-blocking error.
- Do not seed bulk dev users into staging. Add only data explicitly required for
  a staging test, and attach it to an approved staging identity.
- Do not create an application `Admin` row as a substitute for the separate CMS
  administrator authentication mechanism.
- Before any future destructive staging cleanup, create a fresh staging-only
  snapshot and verify its checksums.
- Validate both retained logins, the public roster, gateway readiness, CMS, and
  Swarm replicas after a data operation.
- Never place SSH passwords, API tokens, private keys, Firebase JSON, JWT keys,
  or administrator passcodes in documentation or source control.
