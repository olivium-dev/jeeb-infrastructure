#!/usr/bin/env bash
# Read-only source custody for the single opt-in protected ingress diagnostic.
set -euo pipefail
fail() { printf '%s\n' 'Protected ingress source guard refused.' >&2; exit 1; }
[[ "$#" = 0 && "${PROTECTED_INGRESS:-}" = true ]] || fail
[[ "${GITHUB_REPOSITORY:-}" = olivium-dev/jeeb-infrastructure ]] || fail
[[ "${GITHUB_EVENT_NAME:-}" = workflow_dispatch ]] || fail
[[ "${GITHUB_REF:-}" = refs/heads/main && "${SOURCE_DEFAULT_BRANCH:-}" = main ]] || fail
[[ "${SOURCE_REF_PROTECTED:-}" = true && "${GITHUB_RUN_ATTEMPT:-}" = 1 ]] || fail
[[ "${GITHUB_ACTOR:-}" = oudaykhaled && "${GITHUB_TRIGGERING_ACTOR:-}" = oudaykhaled ]] || fail
[[ "${REVIEWED_SHA:-}" =~ ^[0-9a-f]{40}$ && "${GITHUB_SHA:-}" = "$REVIEWED_SHA" ]] || fail
[[ "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ ]] || fail
[[ "$(git rev-parse HEAD)" = "$REVIEWED_SHA" && -z "$(git status --porcelain)" ]] || fail
gh api --hostname github.com repos/olivium-dev/jeeb-infrastructure/branches/main 2>/dev/null |
  jq -e --arg sha "$REVIEWED_SHA" '.protected == true and .commit.sha == $sha' >/dev/null 2>&1 || fail
gh api --hostname github.com "repos/olivium-dev/jeeb-infrastructure/actions/runs/$GITHUB_RUN_ID" 2>/dev/null |
  jq -e --arg sha "$REVIEWED_SHA" --arg id "$GITHUB_RUN_ID" '
    (.id | tostring) == $id and .head_sha == $sha and .head_branch == "main" and
    .event == "workflow_dispatch" and .run_attempt == 1 and
    .path == ".github/workflows/jeeb-staging-readiness-inventory.yml" and
    .repository.full_name == "olivium-dev/jeeb-infrastructure" and
    .actor.login == "oudaykhaled" and .triggering_actor.login == "oudaykhaled"' >/dev/null 2>&1 || fail
