# Runbook — Jeeb Production Deploy

Owner: principal-devops-sre
Audience: anyone with `production` environment access in GitHub
Last reviewed: 2026-08-19

## Policy

Production deployments are fix-forward only. Swarm/Compose updates pause on
failure and the failed candidate remains visible for diagnosis. Recovery means
correcting the fault, producing a new immutable image, and dispatching a fresh
deployment.

## Preconditions

- The requested `ghcr.io/olivium-dev/jeeb-gateway:<tag>` image exists.
- The operator belongs to the protected production deployer group.
- The production host has its required runtime secrets.

## Deploy

1. Open **Actions → Deploy to Production → Run workflow**.
2. Enter the exact immutable image tag and type `PRODUCTION`.
3. Approve the protected GitHub environment.
4. Confirm the job verifies the registry image, deploys it, and receives HTTP
   200 from the public health endpoint.
5. Independently verify:

   ```bash
   curl -fsS https://api.jeeb.app/health/live
   ```

## Failure response

Do not replace the candidate with an older image. Capture the service/task
state and logs, correct the root cause, let CI build a new immutable image, and
deploy that exact image through the protected workflow.

| Symptom | Response |
|---|---|
| Image not found | Re-run the source repository build for the intended commit. |
| Update paused | Inspect service tasks/logs, correct the fault, and deploy a new image. |
| Database migration failed | Stop; restore data only through the database recovery procedure and involve the DBA. |
| Public health fails but tasks are healthy | Diagnose DNS, TLS, tunnel, and proxy routing before another deployment. |

## Escalation

| Severity | Page |
|---|---|
| Production fully unavailable for more than five minutes | PagerDuty: `jeeb-prod` |
| Data loss suspected | PagerDuty: `jeeb-data` and the technical lead |
| Region-wide cloud outage | Incident commander and status page |

Every alert must link to this runbook.
