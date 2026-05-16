# Mobile OTA Runbook — Shorebird Code Push

Owner: principal-devops-sre · On-call: mobile-platform · Severity ladder: P3 → P2 (bad patch reaching beta/production) → P1 (in-flight outage from patch).

Companion to [`mobile-release-runbook.md`](./mobile-release-runbook.md). The store-release runbook ships full AAB/IPA builds; this runbook ships **Dart-only OTA patches** via Shorebird (decision: [ADR 0001](../docs/adr/0001-shorebird-ota.md)).

## 1. When OTA is the right tool

| Change                                                  | Use OTA? |
|---------------------------------------------------------|----------|
| Dart UI tweak (copy, layout, color, OMDS swap)          | Yes |
| Dart business logic fix (validation, formatting)        | Yes |
| Dio interceptor change (auth header rename, retry)      | Yes |
| New asset already referenced from Dart                  | Yes |
| New asset NOT referenced from the AAB/IPA in field      | No — store release |
| Anything in `android/` or `ios/`                        | No — store release |
| Adding/removing a Flutter plugin                        | No — store release |
| Bumping a `pubspec.yaml` version that changes native code | No — store release |
| Permission, entitlement, Info.plist, Manifest change    | No — store release |

`scripts/shorebird-patch.sh` enforces the "No" cases by diffing
`android/`, `ios/`, `pubspec.yaml`, and `pubspec.lock` against the
last-good ref before calling `shorebird patch`.

## 2. What runs where

| Stage   | Trigger                                    | Workflow                                                                                       |
|---------|--------------------------------------------|------------------------------------------------------------------------------------------------|
| Android | `workflow_dispatch`                        | `jeeb-mobile/.github/workflows/mobile-ota-shorebird.yml` job `android`                          |
| iOS     | `workflow_dispatch`                        | same workflow, job `ios`                                                                       |
| Both    | `workflow_dispatch` with `platform=both`   | both jobs run, gated by the `mobile-release` GitHub Environment (same approval as store releases) |

The workflow shells out to `jeeb-infrastructure/scripts/shorebird-patch.sh`, which is also runnable locally for emergency hotfixes when GitHub Actions is degraded.

## 3. Required secrets

In the **`mobile-release`** GitHub Environment (reuses the same env as store releases; no new approval surface).

| Secret              | Format                                  | Source / rotation                                                                   |
|---------------------|-----------------------------------------|-------------------------------------------------------------------------------------|
| `SHOREBIRD_TOKEN`   | string from `shorebird login:ci`        | Shorebird console → API tokens. Rotate every **90 days**. Vault → DevOps. Never log; the script uses `:?` guards. |

Reuse: no separate App Store / Play secrets are needed — Shorebird does
not interact with the stores; it ships patches via its own CDN.

## 4. Shipping an OTA patch

### 4.1 Staging (default)
1. Land the Dart-only fix on `develop` (or a topic branch).
2. GitHub → Actions → **Mobile OTA (Shorebird)** → **Run workflow**.
3. Inputs:
   - `platform`: usually `android` for first verification, then `ios`, then `both`.
   - `track`: **`staging`**.
   - `release_version`: the marketing+build of the store build the patch targets (e.g. `1.4.0+12345`). Take from `mobile-release` workflow notice line.
   - `flavor`: leave blank (defaults to `track`).
   - `dry_run`: `false`.
4. Approve the `mobile-release` environment gate.
5. Watch the **Cut Shorebird patch** step for the published patch number.

### 4.2 Beta / production
Same flow with `track=beta` or `track=production`. **Never** promote to `production` without a staging soak of ≥ 30 min on internal devices.

### 4.3 Dry-run (no patch published)
Set `dry_run=true`. The workflow installs the CLI, runs the
native-change check, and prints the `shorebird patch` command that
*would* run. Used in PR review and as a smoke test after rotating
`SHOREBIRD_TOKEN`.

### 4.4 Local emergency hotfix (when CI is down)
```bash
cd ~/code/olivium-dev
export SHOREBIRD_TOKEN=...               # from Vault
./jeeb-infrastructure/scripts/shorebird-patch.sh \
    android staging 1.4.0+12345 staging
```
The script must be run from a checkout where `jeeb-mobile` and
`jeeb-infrastructure` are sibling directories (matches the org's
mono-checkout convention).

## 5. Verifying success

| Check | Where | Pass condition |
|-------|-------|----------------|
| Workflow `Mobile OTA (Shorebird)` green | GitHub Actions | green |
| Patch listed on Shorebird console | https://console.shorebird.dev/ → app → release `1.4.0+12345` | new patch number, `Created` < 5 min ago |
| Internal staging device receives patch | Force-quit app, relaunch | Update prompt within 800 ms, restart applies patch |
| Crash-free trend for the release | Firebase Crashlytics → release `1.4.0+12345` | ≥ 99.5% over 30 min after rollout to that track |

The startup version check is implemented in
`jeeb-mobile/lib/core/ota/shorebird_updater_gate.dart` (contract in §8).
On staging it surfaces a non-dismissable prompt; on production it
auto-applies on next cold start.

## 6. Rollback

There is **no "delete patch"** in Shorebird — clients that already
pulled a bad patch keep it until they pull the next one. Roll back by
publishing a **forward patch** built from the last-good git ref.

```bash
./jeeb-infrastructure/scripts/shorebird-rollback.sh \
    android production 1.4.0+12345 v1.4.0
```

The script:
1. Saves the current branch/HEAD.
2. Checks out `v1.4.0`.
3. Calls `shorebird-patch.sh` (re-running the native-change check).
4. Restores the original HEAD on exit via `trap`.

SLO: rollback patch published within **5 min**; existing clients pull on
next foreground/cold start.

When to escalate to a full store release instead of OTA rollback:
- The bad patch added a permission prompt the user already declined.
- The bad patch corrupted persisted state (`shared_preferences`,
  `flutter_secure_storage`). OTA cannot un-write user storage; ship a
  full release with a migration.
- The Shorebird console is unreachable for > 10 min — cut a
  store-track hotfix per [`mobile-release-runbook.md` §6](./mobile-release-runbook.md#6-rollback).

## 7. Common failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| `shorebird-patch.sh` exits 2 with "native or pubspec changes detected" | Someone touched `android/`, `ios/`, or `pubspec.yaml` since the release ref | Cut a full store build (`mobile-release.yml`) — OTA cannot ship native diffs |
| `shorebird patch` exits with `Release version X.Y.Z+N not found` | Patching a release that was never published to the store, or a build number that doesn't match | Confirm against the `mobile-release` workflow notice; the build numbers must match exactly |
| `Unauthorized` from CLI | `SHOREBIRD_TOKEN` expired (90 d) | Rotate the secret; re-run |
| Clients on staging not picking up the patch | App was launched before the patch was published and is still warm | Force-quit and relaunch; on iOS, also kill from app switcher |
| Patch ships but UI shows old behavior | App restart not triggered — `restartRequired` ignored | See §8: gate must call `Phoenix.rebirth` (or platform restart) when status is `restartRequired` |

## 8. Flutter contract (handoff to mobile)

The Flutter team owns the in-app gate. Required contract:

**Package:** `shorebird_code_push: ^2.x` in `pubspec.yaml` (dev/test
profile disabled via flavor guard).

**Location:** `lib/core/ota/shorebird_updater_gate.dart` exposing:

```dart
abstract class ShorebirdUpdaterGate {
  /// Called once during bootstrap, before runApp.
  /// MUST time out at 800 ms (p95 budget) and return UpdateOutcome.unavailable
  /// on timeout so cold-start latency is never blocked on the network.
  Future<UpdateOutcome> checkOnLaunch();

  /// Called when the user accepts the prompt.
  Future<void> downloadAndScheduleRestart();
}

enum UpdateOutcome { upToDate, available, downloaded, unavailable }
```

**Behavior by flavor:**
- `dev`: gate is a no-op.
- `staging`: prompt user; auto-download on accept; force restart.
- `production`: silently download; apply on next cold start (no prompt).

**Acceptance test (Flutter team):**
1. Build flavor `staging` with version `1.4.0+12345`, install on device.
2. Cut a Shorebird patch on `staging` track for `1.4.0+12345`.
3. Cold-start the app — prompt appears within 800 ms.
4. Accept — app restarts and shows patched UI.
5. Disable network — cold-start completes within 800 ms with no prompt.

Tracked under `T-mobile-OTA-001` (filed at handoff).

## 9. Escalation matrix

| Severity | Trigger                                                       | Page                                         |
|----------|---------------------------------------------------------------|----------------------------------------------|
| P3       | OTA workflow failed, no user impact                           | Slack #mobile-platform                       |
| P2       | Bad patch reached `beta` or `production` track                | PagerDuty: mobile-on-call (ack ≤ 15 min)     |
| P1       | Patch causes app to crash on launch on > 1% of installs       | PagerDuty: mobile-on-call + incident-commander |

For P1: open an incident bridge, run `shorebird-rollback.sh`, and start
a blameless retro per `incident-retro-blameless`.
