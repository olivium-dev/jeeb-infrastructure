# Read-only staging inventory

`jeeb-staging-readiness-inventory.yml` is a manual, no-input diagnostic for the
designated owner on protected default-branch source and the existing `staging`
environment. It uses the existing staging SSH key and pinned known hosts, with
the pinned Cloudflare binary installed only in the runner's temporary directory.
The remote process verifies both `olivium-ephemerals` and `192.168.2.20` before
any Docker or HTTP access. It accepts no commands, paths, hostnames, or queries
from dispatch inputs.

This is distinct from the disabled legacy `verify-server.yml`, which uses the
older `JEEB_SSH_HOST` VPS contract and broad sudo diagnostics. The disabled
`list-jeeb-services.yml` and `_inspect.yml` no longer exist on current main.
None is enabled, changed, or bypassed. The current deployment safety policy
explicitly permits read-only Swarm inspection; this workflow does not acquire
deployment authority or any new privilege.

The fixed script reports the 24 active staging service identities, known GHCR
image digests, replica/update state, log configuration booleans, approved flag
values and telemetry/credential nonempty booleans. For builder it evaluates
the same individual-DB-variable precedence as the application, emits only
staging host/database match booleans, and reports fixed template/mount targets
without source paths. It does not query a database, inspect submissions, read
generated KYC content, read secret files, or fetch application logs.

Service-spec images and current running task images are compared using fixed
`docker service ps --no-trunc` JSON projection. A positive task-image result
requires all desired replicas to be running with the same allowlisted immutable
digest as the service spec. Tag-plus-digest references are normalized to the
repository/digest; tag text and raw task fields never leave the host. Missing,
transitioning, mismatched or unknown images do not pass. This attests task image
references, not local container image IDs, application readiness, or telemetry.

Only offer has an additional `offer_local_image` projection for the observed
tag-only/unknown-reference case. It binds the one fixed service task to its local
running container through validated engine IDs and Swarm identity labels, resolves
the local immutable image ID to exactly one known offer RepoDigest, and rechecks
task/container stability. Only `ghcr.io/olivium-dev/offer-service@sha256:...` can
leave this projection. Nonlocal/missing containers, transitions, ambiguous or
unknown digests remain unverified; identity/cardinality errors fail closed. No
raw task fields, container IDs, labels, tags, environment or arbitrary RepoDigests
are serialized. This adds read-only projected inspect calls, not container exec,
pulls, registry lookup, remote writes or additional deployment authority. Existing
service-spec/task-reference fields retain their original independent meaning.

Builder target matching rejects query routing overrides, malformed ports and
fragments; unknown/absent targets produce null match results. Percent-encoded
database names stay literal, matching SQLAlchemy 2.0.27. The CDN projection
checks only the exact upload bind mount and reports extra configuration/command
overrides; absent storage settings remain unknown. Heartbeat projection checks
the Redis host, port and database 4, with query overrides treated as ambiguous.
Feedback datastore parsing remains unverified. The gateway's actual
`Otel__Endpoint` setting is included only as a nonempty boolean.

Monitoring inspection covers fixed service/container/systemd names only.
Missing matches do not prove there is no differently named monitoring stack.
Fixed loopback collector, Prometheus, Loki and Grafana GETs report HTTP status;
an unauthenticated Prometheus `up` query emits only aggregate sample counts.
HTTP redirects and environment proxies are disabled. A 401/403 or unreachable
endpoint is unverified, not success. Configuration booleans are not evidence
of telemetry delivery, and a green inventory job is not fleet readiness.

No output contains raw Docker JSON, env values, HTTP bodies, metric labels,
exception messages, token paths, arbitrary container names, or DSNs. All remote
operations are reads, without sudo, restart, deployment, exec-in-container,
customer data access, credential creation or authentication bypass. The only
files written are runner-owned transport files, removed after execution.

Run the local contract suite with:

```sh
python3 -m unittest discover -s deploy/staging/tests -p 'test_*.py'
python3 scripts/check-deployment-safety-policy.py
```
