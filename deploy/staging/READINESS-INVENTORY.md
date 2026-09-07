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
