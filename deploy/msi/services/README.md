# MSI per-service deployment scripts

Forward-only deployment entrypoints for the **24 active MSI development backend
owners**. There is no rollback/restore command, automatic previous-release
fallback, deploy-all command, or cleanup command. These scripts are prepared and
locally tested tooling, **not evidence that a candidate has been deployed or that
the full backend has passed E2E**.

The target is exclusively `ouday-GT70-2OC-2OD` / `192.168.2.39`. The scripts run
on MSI using its existing native systemd services: 22 system-manager units and
two user-manager units. They do not create replacement containers, retarget
staging/production, or provision an empty host. Host access and sudo use the
already approved operator access path; no SSH credentials or connection
workarounds are included here.

## Start with the offline plan

From this repository:

```bash
deploy/msi/services/scripts/plan-all.sh
deploy/msi/services/scripts/chat-service.sh
deploy/msi/services/scripts/chat-service.sh --help
```

The default action is `plan`: no network, host commands, deployment, or
application startup. `plan-all.sh` orders known prerequisites, places gateway
last, and lists excluded and auxiliary projects. This order is not a claim that
all runtime dependencies are acyclic or ready. The service plan includes the
catalog SHA and the exact startup-effects acknowledgment hash.

## Entry points

Each script is in `scripts/` and accepts the same actions. Ports below identify
the current owned listener, not permission to widen exposure.

| Script | Runtime | Existing unit | Port | Probe strength |
| --- | --- | --- | ---: | --- |
| `jeeb-gateway.sh` | .NET 8 | `jeeb-gateway.service` | 10090 | Dependency |
| `jeeb-state-service.sh` | .NET 8 | `jeeb-state.service` | 10073 | Dependency |
| `user-management.sh` | .NET 8 | `jeeb-user-management.service` | 10001 | Dependency |
| `one-time-password.sh` | .NET 8 | `jeeb-otp.service` | 10037 | Dependency |
| `wallet-service.sh` | .NET 8 | `jeeb-wallet.service` | 10014 | Dependency |
| `feedback-service.sh` | .NET 8 | `jeeb-feedback.service` | 10064 | Documentation |
| `remote-user-preferences.sh` | Rust | `jeeb-rup.service` **(ec2-user, UID 1001)** | 10067 | Documentation |
| `ban-service.sh` | Rust | `jeeb-ban.service` | 10065 | Liveness |
| `kyc-service.sh` | .NET 8 | `jeeb-kyc.service` | 10074 | Dependency |
| `notification-service.sh` | Python | `jeeb-notification.service` | 10026 | Dependency |
| `push-notification.sh` | Python | `jeeb-push.service` | 10040 | Dependency |
| `chat-service.sh` | .NET 8 | `jeeb-chat.service` | 5803 | Dependency |
| `cdn-service.sh` | .NET 8 | `jeeb-cdn.service` | 10072 | Liveness |
| `geolocation-service.sh` | Python | `jeeb-geolocation.service` | 10060 | Liveness |
| `delivery-service.sh` | Go | `jeeb-delivery.service` | 5802 | Liveness |
| `offer-service.sh` | Elixir / OTP | `jeeb-offer.service` | 5801 | Dependency |
| `heart-beat.sh` | Go | `jeeb-heartbeat.service` | 10075 | Dependency |
| `settlement-service.sh` | .NET 8 | `settlement-service.service` **(ouday, UID 1000)** | 10078 | Dependency |
| `bundler-service.sh` | Go | `jeeb-bundler-native.service` | 11058 | Dependency |
| `realtime-comunication-service.sh` | Elixir / OTP | `jeeb-realtime.service` | 5804 | Dependency |
| `voice-transcription-service.sh` | Python | `jeeb-voice-candidate.service` | 10063 | Configuration |
| `contract-signing-service.sh` | Python | `jeeb-contract-signing.service` | 10071 | Liveness |
| `form-builder-service.sh` | Python | `jeeb-form-builder.service` | 10070 | Documentation |
| `compliment-service.sh` | Python | `jeeb-compliment.service` | 10036 | Liveness |

The existing voice redirect from gateway target `10062` to owner `10063` is
preserved. Do not restart the old voice unit or change that route. The two
user-manager services are addressed through their own managers, not converted
to system services or installed globally under `/etc/systemd/user`.

The source-backed [catalog](service-catalog.json) records each repository,
default branch, entrypoint, dependencies, startup effects and probe contract.
The [full-backend contract](../FULL-DEVELOPMENT-BACKEND.md) remains authoritative
for active ownership. Matching, unified payment gateway, masked-call and catalog
are not activated by this tool. An already running legacy matching unit is
preserved. Background workers, optional private artifacts, frontends, clients,
datastores, ingress and other auxiliary projects are explicitly classified,
not silently redeployed.

## Reviewed single-service workflow

1. Build and test the exact approved service commit for **Linux x64** using its
   repository's existing SDK/runtime/dependency-lock contract. The deployer does
   not build code, fetch branch heads, install packages or run migrations.
2. Prepare a finite, secret-free, regular-file-only USTAR artifact and its exact
   file inventory. Keep source/build/test evidence separate. See the
   [manifest contract](MANIFEST.md) for required pins and examples.
3. Review the actual launch command, runtime, environment-source behavior,
   configuration files and every relative persistent/generated-data path.
   Preserve credential custody and the existing framework/provider mode.
4. On MSI, use `inspect` with a pinned observation-input manifest and a new
   output file in a private root-owned directory. It captures redacted metadata
   and hashes without sourcing environment files, probing providers, reloading
   a manager or starting an application. Assemble and approve the full candidate
   manifest using that fresh baseline; do not commit private manifests/reports.
5. Run `preflight`. Review startup effects and obtain explicit authorization for
   any worker, provider, schema or persistent-data effects before `deploy`.
   Possessing or copying the acknowledgment hash is **not** that authorization.
6. Run `deploy` once for that exact service and manifest. It stages one immutable
   release, installs one narrowly scoped drop-in, reloads the selected manager,
   restarts only that selected unit, and verifies identity and its catalog probe.
   Run `verify` afterward if a fresh check of the same candidate is needed.

Commands below are an interface example, not a prepared or approved live
deployment. Replace the private paths and hashes with independently reviewed
values, and run through the approved MSI administrative access mechanism:

```bash
python3 -I /ABSOLUTE/TOOLING/msi_deploy.py --service chat-service inspect \
  --manifest /root/PRIVATE/inspect-input.json \
  --manifest-sha256 APPROVED_INSPECT_INPUT_SHA256 \
  --capture-baseline /root/PRIVATE/new-baseline.json

python3 -I /ABSOLUTE/TOOLING/msi_deploy.py --service chat-service preflight \
  --manifest /root/PRIVATE/candidate.json \
  --manifest-sha256 APPROVED_CANDIDATE_SHA256

python3 -I /ABSOLUTE/TOOLING/msi_deploy.py --service chat-service deploy \
  --manifest /root/PRIVATE/candidate.json \
  --manifest-sha256 APPROVED_CANDIDATE_SHA256 \
  --ack-effects APPROVED_STARTUP_EFFECTS_SHA256

python3 -I /ABSOLUTE/TOOLING/msi_deploy.py --service chat-service verify \
  --manifest /root/PRIVATE/candidate.json \
  --manifest-sha256 APPROVED_CANDIDATE_SHA256
```

`preflight` and `verify` use read-only metadata operations and GET probes; they
also acquire the local deployment lock. Some dependency probes perform bounded
database/provider reads. Neither command starts the service. A failed or stale
preflight is not permission to weaken a gate or replace a baseline with invented
values. In particular, gateway HTTP 200 with `status: Degraded` is a failure.

## Failure behavior — forward fixes only

Failures exit nonzero and stop this deployment operation. There is no automatic
restore, second restart, migration, service disable/enable, removal, or restart
of another service. The unit's **existing systemd restart policy is retained**;
the deployer does not disable that independent manager behavior.

The candidate release, new drop-in and private phase evidence remain where the
failure occurred. After drop-in installation—even before an explicit restart—
the new launch configuration may be selected by a later manager operation.
Reports identify completed phases and intentions; a report is not proof that an
interrupted operation completed. Inspect the actual state and prepare a reviewed
forward correction with a new run ID. Never rerun the same deployment ID as a
retry, switch an old release back, delete evidence, or treat a failed receipt as
success. Existing releases remain in place; none is registered as a fallback.

## What verification does and does not establish

The tool checks the exact host, currently running peer-unit inventory, selected
service identity, runtime/configuration hashes, declared persistent-path
identities, new release bytes, final process, environment-value hashes, listener
ownership/address preservation, and the catalog response contract. Reports do
not include raw environment values, response bodies or application journals.
All operators must honor the same host lock; this is not protection against a
concurrent root administrator deliberately changing the machine.

Fourteen probes test declared dependencies, six are liveness-only, three are
documentation-only and one is configuration-only. These are not interchangeable.
They do not prove chat delivery, WSS/channel joins, coordinates reaching another
device, role propagation, payments, storage writes, template correctness or full
mobile E2E. Public CDN intentionally uses `/health/live`: its readiness endpoint
can write/delete storage probes. No paid transcription, SMS, notification send,
account-export claim or financial transaction is a verification action.

Some applications themselves perform work on startup: bundler unconditionally
migrates, other services may initialize schema or templates, and configured
workers may consume existing queues. These are real deployment effects, not
neutral health checks. There is no invented skip flag or automatic migration
approval. Resolve these conditions before authorizing a restart.

## Local verification

```bash
python3 -m unittest discover -s deploy/msi/services/tests -p 'test_*.py' -v
python3 -O -m unittest discover -s deploy/msi/services/tests -p 'test_*.py' -v
python3 scripts/check-deployment-safety-policy.py
```

Tests use synthetic files and blocked/mocked host operations. Four additional
inert launcher tests exercise actual memfd sealing, Bash export behavior and
descriptor closure on non-root Linux; they explicitly skip on macOS. No test
activates systemd units or proves live E2E. The CI change adds these tests only;
it does not deploy the fleet on push.
