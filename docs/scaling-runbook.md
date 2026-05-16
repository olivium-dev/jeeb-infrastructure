# Horizontal scaling runbook — Jeeb API

Owner: DevOps on-call. Ticket: T-devops-008.

This runbook is paged by the `ContainerHighCpu`, `ContainerHighMemory`,
`NodeHighCpu`, or `NodeHighMemory` alerts in
[`monitoring/prometheus/alerts.yml`](../monitoring/prometheus/alerts.yml).

**SLO: a new replica or Swarm worker node MUST be addable within 4 hours of
the page firing.** Anything longer means the alert thresholds (70% CPU,
80% memory, both sustained for 15 m) leave too little headroom — escalate to
the Staff DevOps lead.

## 0. TL;DR — what to do when you are paged

| Alert                  | Cause                                  | Immediate action                                  |
| ---------------------- | -------------------------------------- | ------------------------------------------------- |
| `ContainerHighCpu`     | One service is CPU-bound               | §2 Scale the service replica count                |
| `ContainerHighMemory`  | One service is memory-bound (OOM soon) | §2 Scale the service replica count                |
| `NodeHighCpu`          | The whole Swarm node is hot            | §3 Add a Swarm worker node                        |
| `NodeHighMemory`       | The whole Swarm node is hot            | §3 Add a Swarm worker node                        |

If both container and node alerts fire on the same target, do §3 first —
adding replicas on a saturated node will not help.

## 1. Diagnose

1. Open Grafana → `Jeeb / Capacity` dashboard (or `Jeeb / API latency` if
   the capacity board is not yet provisioned).
2. Confirm which alert is firing and on which `name` (container) or
   `instance` (host) label:
   ```bash
   curl -s http://prometheus:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'
   ```
3. Cross-check with `docker service ls` on the Swarm manager:
   ```bash
   ssh "${DEPLOY_USER}@${DEPLOY_HOST}" docker service ls
   ssh "${DEPLOY_USER}@${DEPLOY_HOST}" docker service ps jeeb_jeeb-gateway --no-trunc
   ```
4. Decide: container-level (§2) or node-level (§3).

## 2. Scale a service horizontally (container-level)

Use this when one specific service is hot but the underlying node still has
spare CPU/memory headroom.

```bash
# From the operator machine — Cloudflare-SSH into the Swarm manager.
ssh "${DEPLOY_USER}@${DEPLOY_HOST}"

# Inspect current replica count.
docker service inspect jeeb_jeeb-gateway \
  --format '{{.Spec.Mode.Replicated.Replicas}}'

# Scale up. Doubling is the default first step; do not jump beyond 2x
# without confirming node capacity in §3.
docker service scale jeeb_jeeb-gateway=4

# Watch tasks converge.
docker service ps jeeb_jeeb-gateway
```

**Verification — must be true before resolving the page:**

- `docker service ps jeeb_jeeb-gateway` shows N running tasks (no `Pending`).
- The Prometheus alert clears within one evaluation cycle after the new
  replicas stabilise (`ContainerHighCpu` / `ContainerHighMemory` returns to
  inactive).
- p95 latency (`Jeeb / API latency` dashboard) returns to baseline.

If replicas land but stay in `Pending` with "no suitable node" — the
cluster is full. Proceed to §3.

## 3. Add a Swarm worker node (cluster-level)

Use this when `NodeHighCpu` / `NodeHighMemory` fires, or when §2 cannot
place new replicas.

### 3.1 Pre-flight (≤ 30 min)

- Capacity in cloud account confirmed (quota check via cloud console).
- Image name / size matches the existing worker fleet (same kernel, same
  Docker engine major version — check with `docker version` on an existing
  worker).
- Network reachability: the new VM must reach the Swarm manager on
  TCP 2377, TCP/UDP 7946, UDP 4789.

### 3.2 Provision the VM (≤ 60 min)

Either the IaC path (preferred) or the manual path:

```bash
# Option A — IaC (preferred when terraform/ is wired)
cd infra/terraform/swarm
terraform apply -var "worker_count=$((CURRENT + 1))"

# Option B — manual via cloud CLI (example: Hetzner)
hcloud server create \
  --name jeeb-swarm-worker-N \
  --type cpx31 \
  --image debian-12 \
  --ssh-key ops \
  --network jeeb-prod
```

### 3.3 Join the Swarm (≤ 15 min)

```bash
# On the manager — fetch the worker join token.
JOIN_TOKEN=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
  docker swarm join-token -q worker)
MANAGER_IP=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
  hostname -I | awk '{print $1}')

# On the new worker.
ssh "${DEPLOY_USER}@${NEW_WORKER_HOST}" \
  "docker swarm join --token ${JOIN_TOKEN} ${MANAGER_IP}:2377"

# Verify from the manager.
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" docker node ls
```

### 3.4 Rebalance (≤ 30 min)

Swarm will not pre-emptively migrate existing tasks to a fresh node. Force
a rebalance by triggering a no-op service update — this respects rolling
update policy and stays zero-downtime (per
[`olivium-tech-stack-rules`](https://github.com/olivium-dev): use
`docker service update --image`, never `docker service rm` + create).

```bash
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "
  docker service update --force jeeb_jeeb-gateway
"
```

If the capacity gap was the only reason §2 failed, now re-run the scale
step in §2 to spread additional replicas across the new node.

### 3.5 Verification — must be true before resolving the page

- `docker node ls` lists the new node as `Ready` and `Active`.
- `docker service ps jeeb_jeeb-gateway` shows at least one running task
  scheduled on the new node.
- `NodeHighCpu` / `NodeHighMemory` clears within one evaluation cycle.
- API p95 returns to baseline on the latency dashboard.

## 4. 4-hour SLO budget

| Stage                          | Target time | Cumulative |
| ------------------------------ | ----------- | ---------- |
| Page received → on-call ack    | 5 min       | 0:05       |
| §1 Diagnose                    | 10 min      | 0:15       |
| §2 OR §3.1 Pre-flight          | 30 min      | 0:45       |
| §3.2 Provision VM              | 60 min      | 1:45       |
| §3.3 Join Swarm                | 15 min      | 2:00       |
| §3.4 Rebalance + scale         | 30 min      | 2:30       |
| §3.5 Verification              | 30 min      | 3:00       |
| Buffer (cloud quota, network)  | 60 min      | 4:00       |

If at any stage the cumulative time exceeds the target, escalate to the
Staff DevOps lead and post in `#jeeb-oncall`.

## 5. Scale down (after the incident)

Capacity added under fire should not stay forever. 24 h after the alert
resolves and traffic returns to baseline:

```bash
# Drain the node first so existing tasks reschedule cleanly.
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
  docker node update --availability drain jeeb-swarm-worker-N

# Wait for tasks to migrate.
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
  docker service ps jeeb_jeeb-gateway --filter desired-state=running

# Remove from swarm and destroy.
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
  docker node rm jeeb-swarm-worker-N
# IaC: re-run terraform apply with the previous worker_count.
```

Scale service replicas back down the same way as §2 — `docker service
scale jeeb_jeeb-gateway=<original>`.

## 6. Why these thresholds

- **CPU 70%, sustained 15 m** — leaves 30% headroom for burst traffic and
  GC spikes. Sustained 15 m filters out auto-scaling flap from a single
  noisy request batch.
- **Memory 80%, sustained 15 m** — .NET working-set rarely exceeds 80% of
  the container limit under healthy load; sustained 80% strongly correlates
  with imminent OOM-kill on the gateway's 512M staging limit (see
  [`docker-compose.staging.yml`](../docker-compose.staging.yml)).
- **15 m duration, not 5 m** — operator response budget (5 min ack +
  10 min diagnose) is meaningful only if the alert is durable. Shorter
  durations produced unactionable pages in earlier monitoring iterations.

## 7. Acceptance verification (T-devops-008)

| Criterion                                                  | Where it is satisfied                                                                 |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Scaling runbook documented                                 | This file (§§1–6)                                                                     |
| CPU > 70% alert triggers notification                      | `ContainerHighCpu` + `NodeHighCpu` in [`monitoring/prometheus/alerts.yml`](../monitoring/prometheus/alerts.yml) |
| Memory > 80% alert triggers notification                   | `ContainerHighMemory` + `NodeHighMemory` in [`monitoring/prometheus/alerts.yml`](../monitoring/prometheus/alerts.yml) |
| New node addable within 4 hours of alert                   | §3 procedure + §4 time budget                                                         |
