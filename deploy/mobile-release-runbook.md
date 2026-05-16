# Mobile Release Runbook — TestFlight + Play Internal

Owner: principal-devops-sre · On-call: mobile-platform · Severity ladder: P3 → P2 (release blocked) → P1 (in-flight outage).

This runbook covers shipping `jeeb-mobile` to **Apple TestFlight** and **Google Play Internal Testing** via Fastlane, driven by the `Mobile Release` GitHub Actions workflow (`jeeb-mobile/.github/workflows/mobile-release.yml`).

## 1. What runs where

| Stage   | Trigger                                        | Workflow job  | Fastlane lane           |
|---------|------------------------------------------------|---------------|-------------------------|
| Android | `workflow_dispatch` or `vX.Y.Z` tag            | `android`     | `deploy_internal`       |
| iOS     | `workflow_dispatch` or `vX.Y.Z` tag            | `ios`         | `deploy_testflight`     |

Both lanes call into the existing `build_release` lane, then push to the respective store.

## 2. Build number policy (acceptance criterion)

```
CI_BUILD_NUMBER = GITHUB_RUN_NUMBER + BUILD_NUMBER_OFFSET
```

- `GITHUB_RUN_NUMBER` is monotonic per workflow per repo — perfect for `versionCode` / `CFBundleVersion`.
- `BUILD_NUMBER_OFFSET` (env var, default `10000`) lets us leapfrog historical builds from any legacy CI without breaking store ordering.
- **Never** lower the offset; never reset GitHub run history. Either action will get a release rejected by Apple ("a build with that version already exists") or Google ("APK has the same version code").

If we ever migrate CIs, bump `BUILD_NUMBER_OFFSET` to `max(prior_versionCode) + 1` in the workflow `env:` block and open a follow-up to record the new floor in this runbook.

## 3. Required secrets

All in the `mobile-release` GitHub Environment (which has manual approval gating for `production`). Nothing is committed; the org secret-scan hook blocks plaintext credentials at commit time and that hook stays on.

### Android (Play Internal)
| Secret                          | Format                                           | Source / rotation                                |
|---------------------------------|--------------------------------------------------|--------------------------------------------------|
| `ANDROID_KEYSTORE_BASE64`       | `base64 -i upload-keystore.jks`                  | Generated once with `keytool`; rotate only on compromise (re-enrollment with Play App Signing). |
| `ANDROID_KEYSTORE_PASSWORD`     | string                                           | Vault → DevOps; rotate yearly.                   |
| `ANDROID_KEY_ALIAS`             | string (e.g. `upload`)                           | Set at keystore creation.                        |
| `ANDROID_KEY_PASSWORD`          | string                                           | Vault → DevOps; rotate yearly.                   |
| `PLAY_STORE_JSON_KEY_B64`       | `base64 -i play-store-service-account.json`      | GCP service account with the `Release manager` Play Console role. Rotate every 90 days. |

### iOS (TestFlight)
| Secret                       | Format                                       | Source / rotation                                   |
|------------------------------|----------------------------------------------|-----------------------------------------------------|
| `ASC_KEY_ID`                 | 10-char string                               | App Store Connect → Users & Access → Integrations. |
| `ASC_ISSUER_ID`              | UUID                                         | Same page.                                          |
| `ASC_KEY_CONTENT`            | base64-encoded `.p8`                         | Generated once; rotate every 180 days.              |
| `APPLE_TEAM_ID`              | 10-char string                               | Apple developer team.                               |
| `MATCH_GIT_URL`              | https URL of the private signing repo        | Stored as the URL only; auth via PAT below.        |
| `MATCH_GIT_BASIC_AUTH`       | base64 of `username:PAT`                     | GitHub PAT with `repo:read` on signing repo. Rotate every 90 days. |
| `MATCH_PASSWORD`             | string                                       | match encryption passphrase. Rotate only on compromise. |
| `MATCH_KEYCHAIN_PASSWORD`    | string                                       | Per-runner ephemeral keychain password. Any strong random string. |

## 4. Shipping a build

### 4.1 From a release tag (preferred)
1. Decide the marketing version (e.g. `v1.4.0`) and update `pubspec.yaml` `version:`.
2. Commit, push, then push the tag: `git tag v1.4.0 && git push origin v1.4.0`.
3. The `Mobile Release` workflow auto-fires for both stores with `flavor=production`.
4. Approve the `mobile-release` environment gate in the GitHub UI.

### 4.2 Ad-hoc dispatch (hotfix / staging)
1. GitHub → Actions → **Mobile Release** → **Run workflow**.
2. Pick `flavor` (`dev` / `staging` / `production`) and `target` (`android` / `ios` / `both`).
3. Approve the environment gate.

### 4.3 What to watch
- Job log line: `::notice title=CI_BUILD_NUMBER::NNN (run #M + offset 10000)`.
- TestFlight: build appears in App Store Connect → TestFlight within ~10 min (processing). The lane sets `skip_waiting_for_build_processing: true` to keep CI fast.
- Play Console: bundle appears in Internal Testing → Releases as a **draft** (lane uses `release_status: "draft"`); promote to live manually.

## 5. Verifying success

| Check                                                                 | Where                                            |
|-----------------------------------------------------------------------|--------------------------------------------------|
| GitHub Action `Mobile Release` green                                  | Actions tab                                      |
| AAB / IPA artifact present (name includes build number)               | Run artifacts                                    |
| Play Console: new draft release in Internal track with correct VC     | https://play.google.com/console                  |
| App Store Connect: new TestFlight build in "Processing" or "Ready"    | https://appstoreconnect.apple.com                |
| Build number > previous build for the same flavor                     | Both consoles                                    |

## 6. Rollback

There is no "rollback an installed TestFlight build" — TestFlight and Play Internal are pre-release tracks, **not** production. Rollback options in order of preference:

1. **Cut a higher-numbered build of the previous good commit**: `git revert <bad-sha> && git tag v1.4.1 && git push --tags`. This is the only safe path because store version numbers must monotonically increase.
2. **Expire the bad TestFlight build**: App Store Connect → TestFlight → select build → **Expire**. Stops new testers installing it. Existing installs are unaffected.
3. **Halt the Play Internal release**: Play Console → Internal testing → release → **Halt rollout**. Does **not** uninstall; new testers cannot install.
4. If a bad build was already promoted to Production: see `production-rollback.sh` for backend, and the **App Store Connect → Phased Release → Pause** action for iOS / **Play Console → Halt rollout** for Android.

**Never** delete a build from a store to "undo" a release — version numbers cannot be reused.

## 7. Common failures

| Symptom                                                                                       | Likely cause                                            | Fix                                                                 |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------|---------------------------------------------------------------------|
| Android: `Failed to read key.properties` / signed with debug key                              | `ANDROID_KEYSTORE_BASE64` missing or wrong env scope    | Confirm secret exists in `mobile-release` environment; re-run.      |
| Android: Play Console rejects `APK has the same version code N`                               | Workflow re-run with same `GITHUB_RUN_NUMBER` (unusual) | Manually bump `BUILD_NUMBER_OFFSET` by 1 and re-run.                |
| iOS: `match` complains `couldn't decrypt`                                                     | `MATCH_PASSWORD` wrong                                  | Rotate; re-encrypt the signing repo if the password was lost.       |
| iOS: `app_store_connect_api_key` 401                                                          | Expired `.p8` or wrong `ASC_KEY_ID`                     | Regenerate key in App Store Connect, update both secrets.           |
| iOS: `Provisioning profile ... doesn't include bundle identifier app.jeeb.mobile`             | New bundle ID never registered                          | Run `match appstore` locally (with write access) to provision; commit to signing repo. |
| Both: workflow dispatch shows no environment-approval prompt                                  | `mobile-release` environment not configured             | Settings → Environments → create `mobile-release` with required reviewers. |

## 8. OTA hotfix path

For Dart-only fixes, prefer a Shorebird OTA patch over a new store build —
it ships in minutes instead of hours and reuses the same `mobile-release`
environment approval. Procedure: [`mobile-ota-runbook.md`](./mobile-ota-runbook.md).
Decision context: [`../docs/adr/0001-shorebird-ota.md`](../docs/adr/0001-shorebird-ota.md).

A store release is **still required** when the diff touches `android/`,
`ios/`, plugin native code, `pubspec.yaml`, or `pubspec.lock` — the
OTA helper script (`scripts/shorebird-patch.sh`) refuses those automatically.

## 9. Escalation

| Severity | Trigger                                                                 | Page                          |
|----------|-------------------------------------------------------------------------|-------------------------------|
| P3       | Workflow red but no release blocked (e.g. caching)                      | Slack #mobile-platform        |
| P2       | Release blocked > 4h before planned ship date                           | Page mobile-platform on-call  |
| P1       | Customer-facing outage attributable to a TestFlight / Play push         | Page IC + mobile + DevOps     |

Blameless retro within 5 business days for any P1/P2. File action items with owners and due dates — no "tribal knowledge" left.
