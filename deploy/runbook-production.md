# Runbook — Jeeb Production Deploy & Rollback

Owner: principal-devops-sre
Audience: anyone with `production` environment access in GitHub
Last reviewed: 2026-05-16

## When to use this

- You are deploying a new gateway image to production.
- A production deploy went sideways and needs to be rolled back.
- You're the secondary on-call covering a primary who is unreachable.

## Preconditions

- The image `ghcr.io/olivium-dev/jeeb-gateway:<tag>` must already exist in
  GHCR. CI in `olivium-dev/jeeb-gateway` pushes this on tag creation.
- You must be a member of the `jeeb-prod-deployers` GitHub team (the
  `production` environment's required reviewer set).
- The production host has `/opt/jeeb/.env` populated with real secrets.

---

## 1. Deploy

1. Open **Actions → Deploy to Production → Run workflow**.
2. Inputs:
   - `image_tag`: the SHA-tag or semver tag (e.g. `sha-3f9a1c2`, `v1.2.3`).
   - `confirm_production`: type `PRODUCTION` exactly (case-sensitive).
3. Wait for the `guard` job to pass — this rejects mis-clicks.
4. Approve the `production` environment gate in the GitHub UI (required reviewer).
5. Watch the `deploy` job. The pipeline:
   - Verifies the image exists in GHCR.
   - SSHes to the host and pulls the image.
   - Captures the currently-running tag into `/opt/jeeb/.deploy-history`.
   - Performs a rolling update (`--wait --wait-timeout 120`) with start-first
     ordering and `failure_action: rollback` on the Compose deploy spec.
   - Polls `https://${PRODUCTION_DOMAIN}/health/live` until 200 (180s budget).
6. **Verify**: hit the public health endpoint from your laptop:
   ```bash
   curl -fsS https://api.jeeb.app/health/live
   ```

If the health check inside the pipeline fails, the deploy script auto-rolls
back to the previous tag and exits non-zero. No human action is required.

---

## 2. Rollback (manual)

Use this when production is unhealthy and the in-pipeline auto-rollback
did NOT fire (e.g. the bad version passed `/health/live` but is misbehaving
on real traffic).

**SLO: rollback completes in < 5 minutes.**

### Option A — GitHub UI (preferred, ~2 min)

1. Open **Actions → Rollback Production → Run workflow**.
2. Inputs:
   - `image_tag`: the tag to roll back to. Leave **empty** to use the
     last entry in `/opt/jeeb/.deploy-history` (i.e. the previous good
     tag — written automatically by every deploy).
3. Approve the `production` environment gate.
4. Watch the `rollback` job; on success it prints elapsed time.

### Option B — Shell (~60s, if Actions is unavailable)

```bash
export DEPLOY_HOST=api-host-01.jeeb.app
export DEPLOY_USER=deploy
export REGISTRY=ghcr.io/olivium-dev
export GATEWAY_DOMAIN=api.jeeb.app

# Roll back to last known good (reads /opt/jeeb/.deploy-history)
./deploy/production-rollback.sh

# OR roll back to a specific tag
./deploy/production-rollback.sh sha-3f9a1c2
```

### Verify

```bash
curl -fsS https://api.jeeb.app/health/live
# Expect: HTTP 200, body "Healthy"

ssh deploy@api-host-01 'docker compose -f /opt/jeeb/docker-compose.yml \
  -f /opt/jeeb/docker-compose.production.yml ps'
# Expect: jeeb-gateway containers Healthy on the rolled-back tag
```

---

## 3. Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Deploy job stuck at "verifying" | Cert/Traefik problem; image is up but the public URL isn't routing | `ssh` in, check `docker logs <traefik-container>` for ACME errors. Confirm `GATEWAY_DOMAIN` DNS A-record points at the host. |
| `image not found in registry` | Tag wasn't pushed | Re-run `jeeb-gateway` CI for the commit, then retry deploy with the same tag. |
| Auto-rollback ran but health is still red | Both new AND previous tags are bad | Roll back further: use the GitHub UI rollback workflow with an older tag from `.deploy-history`. |
| Postgres unhealthy after deploy | Container restart raced with migrations | Check `docker compose logs jeeb-gateway` for EF migration errors. If a destructive migration is the culprit, restore from PITR backup — do NOT continue. Page #db-on-call. |
| SSL handshake fails for new domain | First TLS issue; ACME HTTP-01 challenge couldn't reach `:80` | Confirm port 80 is open to 0.0.0.0/0 on the host firewall. Traefik retries every minute. |

---

## 4. Escalation

| Severity | Page | Who |
|---|---|---|
| Prod fully down > 5 min after rollback | PagerDuty: `jeeb-prod` | Primary on-call |
| Data loss suspected | PagerDuty: `jeeb-data` + Slack `#sev1` | DBA + Tech Lead |
| Region-wide cloud outage | Slack `#incidents` + status page | Incident Commander |

Every alert linked from a Grafana dashboard MUST link to this runbook. Alerts
without a runbook link are rejected at code review (see
`runbook-template-with-verification` skill).
