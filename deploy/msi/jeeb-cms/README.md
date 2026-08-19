# Jeeb CMS hosting on MSI

This directory contains the MSI hosting foundation for the Jeeb back-office CMS. It deliberately does not modify the public `jeeb.fds-1.com` deployment. Hosting is native nginx plus systemd releases-and-symlink, matching the MSI's systemd-native stack; there is no container path.

The intended request path is:

`MSI operator LAN -> port 80 nginx -> static CMS or 127.0.0.1:10090 gateway`

The native HTTP listener is intentionally reachable on the trusted MSI operator LAN and its CSP does not upgrade same-origin assets to HTTPS. Public staging access is provided at `cms.jeeb.fds-1.com` through the authenticated `.20` nginx origin and Cloudflare Tunnel. The public shell is reachable so operators can sign in; gateway authentication, capability checks, strict same-origin/CSRF checks, and blocked callback paths form the application boundary. Cloudflare Access is optional defense in depth, not a prerequisite for this public login surface.

## Release artifact contract

A release is one immutable directory containing the shell and all eight CMS remotes:

```text
artifact/
├── index.html
├── release.json
├── SHA256SUMS
└── mf/
    ├── cases/remoteEntry.js
    ├── config/remoteEntry.js
    ├── deliveries/remoteEntry.js
    ├── kyc/remoteEntry.js
    ├── orders/remoteEntry.js
    ├── settlements/remoteEntry.js
    ├── users/remoteEntry.js
    └── wallet/remoteEntry.js
```

Every other emitted file must also be listed in `SHA256SUMS`. `SHA256SUMS` does not list itself. Symbolic links, public source maps, inline source maps, unchecksummed files, configured localhost/private HTTP service URLs, raw storage URLs, signed URLs, and private keys are rejected. Only four pinned browser-library forms are scrubbed before scanning: Axios's browser-origin fallback and React Router's three relative-URL parsing/origin-selection forms. Active localhost fetches, loosely similar code, and localhost ports/paths/queries remain forbidden.

`release.json` uses this schema:

```json
{
  "releaseId": "20260807T010203Z-cms-abcdef0",
  "cmsCommit": "0000000000000000000000000000000000000000",
  "gatewayCommit": "0000000000000000000000000000000000000000",
  "openapiSha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "builtAt": "2026-08-07T01:02:03Z"
}
```

The production CMS must be built with the relative gateway origin `/gateway`. Never place tokens, credentials, signed evidence URLs, or service addresses in the artifact.

After all nine production builds succeed, assemble and validate the immutable artifact:

```bash
python3 scripts/assemble-release.py \
  --shell /path/to/ofc-cms-shell/dist \
  --cases /path/to/ofl-cms-cases-mfe/dist \
  --config /path/to/ofl-cms-config-mfe/dist \
  --deliveries /path/to/ofl-cms-deliveries-mfe/dist \
  --kyc /path/to/ofl-cms-kyc-mfe/dist \
  --orders /path/to/ofl-cms-orders-mfe/dist \
  --settlements /path/to/ofl-cms-settlements-mfe/dist \
  --users /path/to/ofl-cms-users-mfe/dist \
  --wallet /path/to/ofl-cms-wallet-mfe/dist \
  --output /path/to/release-artifact \
  --release-id <release-id> \
  --cms-commit <merged-cms-sha> \
  --gateway-commit <merged-gateway-sha> \
  --openapi-sha256 <gateway-openapi-sha256>
```

## One-time native host installation

Prerequisites are nginx, Python 3, curl, and systemd. Install in this exact order: nginx and the site first, then the first release, and only then the boot gate. Installing the nginx drop-in before any release exists wedges the host — `Requires=jeeb-cms-release.service` pulls the validation unit into every nginx start, the unit fails while `/opt/jeeb-cms/current` does not exist, so nginx cannot start and the first deploy cannot reload it.

Step 1 — install the tools, the site, and start nginx. As root on MSI:

```bash
install -d -m 0755 /opt/jeeb-cms/{releases,tools}
install -m 0755 scripts/*.sh scripts/validate-release.py /opt/jeeb-cms/tools/
install -m 0644 README.md /opt/jeeb-cms/README.md
install -m 0644 nginx/backoffice.jeeb.fds-1.com.conf \
  /etc/nginx/sites-available/backoffice.jeeb.fds-1.com.conf
ln -s /etc/nginx/sites-available/backoffice.jeeb.fds-1.com.conf \
  /etc/nginx/sites-enabled/backoffice.jeeb.fds-1.com.conf
# Disable the distro landing page after the Jeeb site is installed.
test ! -L /etc/nginx/sites-enabled/default || unlink /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
```

If the host's nginx has no `sites-available`/`sites-enabled` layout, install the site conf into `/etc/nginx/conf.d/` instead.

Step 2 — deploy the first release (see the next section) while the boot gate is still uninstalled.

Step 3 — only after the first successful deploy, install and enable the boot-time release validation gate:

```bash
install -m 0644 systemd/jeeb-cms-release.service \
  /etc/systemd/system/jeeb-cms-release.service
install -d -m 0755 /etc/systemd/system/nginx.service.d
install -m 0644 systemd/nginx.service.d/jeeb-cms-release.conf \
  /etc/systemd/system/nginx.service.d/jeeb-cms-release.conf
systemctl daemon-reload
systemctl enable jeeb-cms-release.service
systemctl restart jeeb-cms-release.service
```

Keep port 80 limited to the trusted MSI operator LAN. From step 3 onward the nginx systemd drop-in requires the validation unit, so a missing or invalid active release prevents native nginx from starting at boot.

## Deploy

Copy a complete immutable artifact to a staging location on MSI. Compare the SHA-256 of its `SHA256SUMS` file with the digest published by the trusted build job, then pin that digest during deployment:

```bash
sudo /opt/jeeb-cms/tools/deploy-release.sh \
  --expected-manifest-sha256 <trusted-sha256-of-SHA256SUMS> \
  /path/to/artifact
```

Deployment requires and checks the externally supplied manifest digest, validates the source and copied artifact, makes the release root-owned and read-only, and runs nginx plus gateway dependency preflight before changing `/opt/jeeb-cms/current`. It then atomically activates the candidate, reloads nginx, and verifies `/healthz`, the complete served `release.json`, and the served `SHA256SUMS` digest. A post-activation failure leaves the candidate active for diagnosis and requires a corrected forward deployment.

The staging gateway trusts only the exact private Swarm overlay selected by its deployment workflow; nginx supplies the original HTTPS scheme and public host, which keeps strict origin validation and `__Host-` refresh/CSRF cookies same-origin. Evidence responses remain under `/gateway/admin/v1/deliveries/.../evidence/<opaque-token>`; nginx streams them without buffering, hides upstream cache policy, and applies `no-store` without rewriting cookie paths or domains.

## Verification

```bash
sudo /opt/jeeb-cms/tools/verify-current.sh --runtime
curl -fsS http://127.0.0.1/healthz
curl -fsS http://127.0.0.1/release.json
curl -fsS http://127.0.0.1/gateway/health/ready
```

Before operator access, additionally verify public TLS through the tunnel, exact-origin session handling, deep links, strict missing-remote 404 behavior, CSP/cache headers, release hashes, and successful Playwright journeys through `cms.jeeb.fds-1.com`.

## Repository tests

The tests do not require root, nginx, systemd, or network access:

```bash
deploy/msi/jeeb-cms/tests/run.sh
```
