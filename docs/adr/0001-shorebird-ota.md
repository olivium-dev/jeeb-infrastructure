# ADR 0001 — Flutter OTA via Shorebird Code Push

- Status: **Accepted** (2026-05-16)
- Ticket: T-devops-006
- Owners: principal-devops-sre · principal-flutter-mobile
- Supersedes: —

## Context

`jeeb-mobile` ships through the Apple App Store and Google Play. A full
review cycle on the App Store can be 24–72 h; even an expedited review
blocks any hotfix of a pure-Dart bug behind Apple's queue.

We need an over-the-air (OTA) channel that ships **Dart-only** changes
directly to installed apps within minutes, with:

1. Pushes targeting staging devices before reaching production users.
2. A startup version check so users on a stale patch are prompted to
   update.
3. A rollback path for a bad patch.

Native (Kotlin / Swift) changes, new permissions, and new plugins **must
still go through the App Store / Play** — that is non-negotiable and a
hard constraint of every Flutter OTA solution we evaluated.

## Decision

Adopt **Shorebird Code Push** as the OTA mechanism for `jeeb-mobile`.

- Release channel naming: `staging`, `beta`, `production` (mirrors the
  existing Flutter flavor names in `jeeb-mobile/pubspec.yaml`).
- The Shorebird CLI is driven from a new GitHub Actions workflow,
  `.github/workflows/mobile-ota-shorebird.yml`, gated by the existing
  `mobile-release` environment (manual approval).
- Patches are cut against a specific release version (e.g. `1.4.0+12345`)
  — never against an arbitrary commit. The release version is the AAB /
  IPA already in production for that channel.
- Startup version check is implemented in the Flutter bootstrap using
  the `shorebird_code_push` Dart package and gated by a feature flag so
  it can be disabled per-flavor.
- Rollback is "cut a forward patch from the last-good ref against the
  same release version" — Shorebird channels always serve the latest
  patch for a release, so a forward patch is the canonical undo.

## Alternatives considered

### Microsoft App Center CodePush

- **Status: retired**. Microsoft sunset App Center on 2025-03-31.
  Choosing it in 2026 would mean adopting a discontinued service.
- Even before sunset, CodePush's Flutter support relied on a community
  fork (`flutter_code_push`) that never reached parity with Shorebird's
  Dart-engine patching.

### Self-hosted patch server (custom bundle + `flutter_downloader`)

- Out of policy. Apple's App Store guideline 4.7 / Google Play's
  Developer Program Policies allow OTA of interpreted code only via
  vendor-approved mechanisms (Shorebird qualifies; arbitrary
  side-loaded Dart does not without careful guideline compliance).
- High cost: signing, CDN, patch-diff format, integrity verification —
  Shorebird already solves all of this and costs less than a single
  engineer-week to integrate.

### No OTA, faster store reviews only

- Apple's expedited review is rate-limited (~2 / year per app) and
  cannot be relied on operationally. Median review time has improved
  but still floors at ~6 h.
- Does not satisfy the acceptance criterion "OTA update pushes to
  staging devices".

## Consequences

### Positive

- Dart-only hotfixes ship in **<10 min** end-to-end vs **6–72 h** via
  store review.
- Channels map cleanly onto Flutter flavors (`staging`/`beta`/`production`)
  and onto the existing `mobile-release` GitHub Environment.
- Rollback is a forward patch from a prior commit — a procedure we
  already do for backend releases (`production-rollback.sh`), so the
  team mental model carries over.

### Negative / trade-offs

- Adds a new vendor (Shorebird) and a new secret (`SHOREBIRD_TOKEN`)
  with its own rotation schedule (90 d). Documented in
  `deploy/mobile-ota-runbook.md` §3.
- A patch can only target Dart code. Anything touching `android/`,
  `ios/`, plugin native code, or `pubspec.yaml` dependency versions
  **must** ship as a full store build. The CI workflow refuses to cut a
  patch if those paths changed since the release ref (`shorebird patch
  ... --no-confirm` is wrapped by `scripts/shorebird-patch.sh` which
  performs the path-change check).
- Startup version check adds one network call before first frame in
  production. Budget: < 200 ms p95 to first frame, enforced by
  `core/ota/shorebird_updater_gate.dart` timing out at 800 ms and
  falling back to "no update" rather than blocking UI.
- Shorebird's free tier is rate-limited; we adopt the team plan from
  day one (covered under existing infra budget; see ticket comments).

### Operational

- New runbook: `deploy/mobile-ota-runbook.md`.
- New scripts: `scripts/shorebird-patch.sh`, `scripts/shorebird-rollback.sh`.
- New workflow: `jeeb-mobile/.github/workflows/mobile-ota-shorebird.yml`.
- Existing `deploy/mobile-release-runbook.md` cross-references the OTA
  runbook in a new §8 "OTA hotfix path".
- Existing `mobile-release` GitHub Environment is reused (same
  reviewers, same protection rules — no new approval surface).

## Verification

The runbook ships with a dry-run mode (`SHOREBIRD_DRY_RUN=true`) used by
both scripts and a non-destructive workflow_dispatch input. CI invokes
the dry-run on every PR that touches `lib/` so the patch toolchain is
exercised continuously.
