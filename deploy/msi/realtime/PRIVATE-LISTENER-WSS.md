# MSI private tracking listener and exact WSS ingress

Scope: native MSI development host `ouday-GT70-2OC-2OD` only. This is a record of
the approved 2026-09-10 correction and a future operator review checklist, not an
automatic deploy/retry procedure. No staging/production workflow is retargeted.

## Applied configuration

| Component | Exact change | Preserved boundary |
| --- | --- | --- |
| Realtime runtime config | Minimal `HTTP_BIND_ADDRESS` literal-IP backport described below | Existing older source, auth, Redis and Origin behavior |
| Realtime systemd | [zzzz-msi-http-bind.conf](zzzz-msi-http-bind.conf) at `/etc/systemd/system/jeeb-realtime.service.d/zzzz-msi-http-bind.conf` | Adds only `HTTP_BIND_ADDRESS=127.0.0.1`; retains PORT5804/MIX_ENVdev and prior Redis override |
| MSI nginx | [Exact socket fragment](nginx-msi-realtime-location.conf) inside the existing default port80 backoffice server | Only `/socket/websocket`; all other routes and units unchanged |
| Existing Cloudflare tunnel | No change; `msi.olivium.space` already routes to `http://localhost:80` | No DNS, hostname, tunnel or provider credential mutation |

The public API remains `https://msi.olivium.space/gateway`. The intended tracking
socket authority/path is `wss://msi.olivium.space/socket/websocket`, **without** a
`/gateway` path prefix. Local ingress verification does not attest that public
TLS or authenticated websocket traffic succeeds. Do not update a descriptor or
declare installed APK compatibility merely from this intended URL.

The nginx fragment checks original TCP peer127.0.0.1/::1, exact Host, exact raw
path, GET, websocket Upgrade/version13, and absent or exact
`https://msi.olivium.space` Origin. It requires the compiled real-IP module.
Other local processes can reach loopback; peer restriction is not process
authentication. Guardian authentication/topic authorization remain mandatory.

The proxy preserves path/query to `http://127.0.0.1:5804` with75-second timeouts.
It disables inherited request headers and forwards only the minimal websocket
headers. Authorization, Cookies, Cloudflare identity, subprotocols and compression
are not forwarded. Query-bearing access/error logging is disabled in this
location. The exact fragment retains its original draft header to preserve its
reviewed byte hash; the header is not the runtime-status record.

## Minimal old-runtime backport, not a full source deployment

The incumbent runtime forced IPv4 wildcard whenever PORT was set, overriding
dev.exs loopback. An unsupported HTTP_IP environment variable would do nothing;
unsetting PORT would change the port. The reviewed backport introduces the
following inline parser before the existing PORT block:

```elixir
http_bind_address =
  case System.get_env("HTTP_BIND_ADDRESS") do
    nil ->
      nil

    address ->
      with false <- String.contains?(address, "%"),
           {:ok, ip} <- :inet.parse_strict_address(String.to_charlist(address)) do
        ip
      else
        _ -> raise "HTTP_BIND_ADDRESS must be an unscoped IPv4 or IPv6 literal"
      end
  end

if http_bind_address do
  config :live_comm, LiveCommWeb.Endpoint, http: [ip: http_bind_address]
end
```

Only the existing PORT block's HTTP options become:

```elixir
http: [ip: http_bind_address || {0, 0, 0, 0}, port: String.to_integer(port)]
```

The later production HTTP block's IP becomes:

```elixir
ip: http_bind_address || {0, 0, 0, 0, 0, 0, 0, 0}
```

Absent override preserves prior defaults; explicit invalid/empty values fail
closed. Only unscoped IP literals are accepted, with no DNS lookup or fallback.
The explicit percent-sign rejection prevents OTP silently discarding an IPv6
interface suffix. Address override preserves the configured port even when PORT
is absent. No application module or new dependency is required by this backport.

Canonical source implementation: realtime-comunication-service commit
`a4766be85378dc5cb7feb1e7c685f7fe5d46beab`. The MSI operator applied only those
runtime-config expressions to the verified older file. **Full realtime main and
the Mint1.10.0 dependency remediation were not deployed by this operation.**
Do not replace the old runtime with the entire current runtime or pull unrelated
key-rotation/auth changes into this configuration correction.

## Hash and verification record

These hashes identify the approved bytes, not a reusable authorization to
overwrite future changes. Full configuration and private operational receipts
remain on the operator host; no credentials or full environment dumps belong here.

| Artifact | SHA-256 |
| --- | --- |
| Older runtime before backport | `7a54aa0ef53a292e1da175d64172391c812b606d7ebd42693807b933ae5ecb9b` |
| Runtime after minimal backport | `5325c3679d3918eac4e1f47cfc39bc0c0edbb3bf81b36243ffd2151fb35a061e` |
| Exact nginx insertion fragment | `bc4df706e975d44d598f954d47d0531c91647ade6d7cec47da4c8e4dbde2c029` |
| Full incumbent backoffice nginx file before insertion | `7155d18b50534b8197fe3f87d78520d69220623248f78a8fee75cad17a6de531` |
| Full backoffice nginx file after insertion | `ca47098f26bbb96fadc70ba286c7685da637fcc0b688cb5d6c43edbdb6f348dd` |
| Unchanged `/etc/cloudflared-msi/config.yml` | `1e1d04859dbca09a321004ee72d05279b4134946c2cc2978f1c6d6719f9b436b` |

The prepared runtime passed36 inert full-config cases using the actual MSI
Elixir/OTP, including dev/prod defaults, explicit IPv4/IPv6, PORT preservation
and invalid values. No live credentials or backend calls were used in that
configuration evaluation. After one realtime restart, process1673853 was stable,
owned by the original service identity, strict-ready with all four booleans
(database/redis/pubsub/draining)true, and bound only to127.0.0.1:5804. Existing
environment settings and secrets were preserved, with no automatic restarts.

An independent Studio receipt established positive MSI22/80 connectivity and
5804ECONNREFUSED. Chat5803 timed out and was **not** certified private by that
receipt. The nginx apply required a fresh hash-pinned Studio receipt within ten
minutes and independently rechecked the same private realtimePID/readiness.

At **2026-09-10 08:42 UTC**, operator evidence recorded:

- Exact candidate and installed nginx syntax passed; one nginx reload, not a
  restart, preserved master2077755 and started a new worker generation.
- All other nginx config, unit and tunnel identities were preserved; realtime
  process1673853 remained private and strict-ready.
- Fourteen negative local probes passed: invalid token403; disallowed Origin403;
  wrong Host and normalized/escaped path aliases404; wrong Upgrade/version400;
  wrong method405. Absent/allowed Origin with an invalid token matched the
  private owner's rejection, without ever using a valid credential.
- Seven previous route probes retained status/content type. Frozen full-file
  comparison established that no unrelated route configuration changed.
- The nonsecret invalid-token diagnostic marker was absent from the checked
  nginx file logs and unit journal. Raw logs, query URLs and tokens were not
  published. This does not attest Cloudflare edge/provider logging.

Private nginx receipt: `/var/tmp/jeeb-msi-nginx-wss-apply-odia3tp_/receipt.json`.
It records local ingress verification, not product-level completion.

## Guarded future operation and acceptance limits

Before any future operator action, independently resolve exact host, source,
PID/user, unit/drop-in inventory, framework mode and existing secret injection.
Verify source/config hashes and metadata; preserve or reject ACLs/xattrs rather
than losing them. Archive originals privately; stage exact reviewed bytes;
write/fsync an intent before installation and keep phase/failure receipts. Check
same-filesystem atomic replacement, effective configuration and fresh private
listener/LAN proof. Never blindly rerun this historical operation.

Systemd `daemon-reload` can clear ExecStart start/stop timestamps and PID metadata
even while the incumbent process is unchanged. Compare verified **static command
identity** separately from activePID/state; do not treat changing runtime fields
as command drift. One initial bind attempt stopped safely before restart on this
overstrict comparison; the operator verified installed state and used a separately
reviewed forward-resume restart. There was no automatic reinstall or rollback.

Require syntax checks before and after an nginx-file replacement and at most one
authorized nginx reload, preserving its master and unrelated services. An
incomplete gate remains failed and requires fresh forward diagnosis. Do not
weaken authentication, Origin/TLS validation, rate limiting, or gateway's
Staging-only proxy restriction to obtain a pass. Gateway remains framework
Production; MSI's intended purpose remains development.

Still **not passed by this record**: public certificate/hostname and edge route,
authenticated WSS101, exact authorized delivery-channel join, heartbeat beyond
75seconds, cross-topic/publish denial, actual two-phone location updates,
foreground/background reconnect, installed mobile defines, or full-fleet
functional acceptance. A gateway descriptor must be verified separately, and
only designated test actors/flows may be used for subsequent authorized tests.
Jeeb chat stays Firebase-only; this fragment does not restore chat descriptors,
membership tickets or fan-out. No fee collection, order creation or test-credit
mutation is justified by these configuration checks.

Local repository checks (no live operation):

```sh
python3 -m unittest discover -s deploy/msi/realtime/tests -p 'test_*.py' -v
python3 scripts/check-deployment-safety-policy.py
```
