# Jeeb CMS hosting on MSI

This directory contains the MSI hosting foundation for the Jeeb back-office CMS. It deliberately does not modify the public `jeeb.fds-1.com` Docker Swarm deployment. Native nginx is preferred when root access exists; the reviewed Docker host-network path below is the no-sudo fallback for the current MSI host.

The intended request path is:

`Cloudflare Access -> Cloudflare Tunnel -> 127.0.0.1:10100 nginx -> static CMS or 127.0.0.1:10090 gateway`

DNS, the Cloudflare tunnel, and Access policy are external prerequisites. These files do not create or modify them.

## Release artifact contract

A release is one immutable directory containing the shell and all three essential remotes:

```text
artifact/
├── index.html
├── release.json
├── SHA256SUMS
└── mf/
    ├── cases/remoteEntry.js
    ├── deliveries/remoteEntry.js
    └── settlements/remoteEntry.js
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

After all four production builds succeed, assemble and validate the immutable artifact:

```bash
python3 scripts/assemble-release.py \
  --shell /path/to/ofc-cms-shell/dist \
  --cases /path/to/ofl-cms-cases-mfe/dist \
  --deliveries /path/to/ofl-cms-deliveries-mfe/dist \
  --settlements /path/to/ofl-cms-settlements-mfe/dist \
  --output /path/to/release-artifact \
  --release-id <release-id> \
  --cms-commit <merged-cms-sha> \
  --gateway-commit <merged-gateway-sha> \
  --openapi-sha256 <gateway-openapi-sha256>
```

## One-time native host installation

Prerequisites are nginx, Python 3, curl, and systemd. As root on MSI:

```bash
install -d -m 0755 /opt/jeeb-cms/{releases,tools}
install -m 0755 scripts/*.sh scripts/validate-release.py /opt/jeeb-cms/tools/
install -m 0644 README.md /opt/jeeb-cms/README.md
install -m 0644 nginx/backoffice.jeeb.fds-1.com.conf \
  /etc/nginx/sites-available/backoffice.jeeb.fds-1.com.conf
ln -s /etc/nginx/sites-available/backoffice.jeeb.fds-1.com.conf \
  /etc/nginx/sites-enabled/backoffice.jeeb.fds-1.com.conf
install -m 0644 systemd/jeeb-cms-release.service \
  /etc/systemd/system/jeeb-cms-release.service
install -d -m 0755 /etc/systemd/system/nginx.service.d
install -m 0644 systemd/nginx.service.d/jeeb-cms-release.conf \
  /etc/systemd/system/nginx.service.d/jeeb-cms-release.conf
systemctl daemon-reload
nginx -t
```

Do not open port `10100` in UFW. The nginx listener is loopback-only. Enable `jeeb-cms-release.service` only after the first valid release has been deployed. The nginx systemd drop-in requires that validation unit, so a missing or invalid active release prevents native nginx from starting at boot.

## Deploy and rollback

Copy a complete immutable artifact to a staging location on MSI. Compare the SHA-256 of its `SHA256SUMS` file with the digest published by the trusted build job, then pin that digest during deployment:

```bash
sudo /opt/jeeb-cms/tools/deploy-release.sh \
  --expected-manifest-sha256 <trusted-sha256-of-SHA256SUMS> \
  /path/to/artifact
sudo systemctl enable jeeb-cms-release.service
sudo systemctl restart jeeb-cms-release.service
```

Deployment requires and checks the externally supplied manifest digest, validates the source, copies it to a same-filesystem incoming directory, validates the copy, makes the release root-owned and read-only, moves it to `/opt/jeeb-cms/releases/<releaseId>`, and atomically switches `/opt/jeeb-cms/current`. It then tests and reloads nginx and verifies `/healthz`, `/gateway/health/ready` (override with `JEEB_CMS_GATEWAY_READY_URL`), the complete served `release.json`, and the served `SHA256SUMS` digest. Any failure restores the prior `current` and `previous` symlinks.

## No-sudo Docker nginx on the current MSI host

Use this only when native nginx/root installation is unavailable and `ec2-user` already has Docker access. Docker daemon access is itself privileged; this path does not claim to be a sandbox from that user. It does preserve the network and artifact boundaries required here:

- nginx uses host networking so its upstream `127.0.0.1:10090` still reaches the native gateway;
- the only CMS listener remains `127.0.0.1:10100` (there is no published Docker port);
- the CMS root and both nginx configurations are read-only bind mounts;
- the container root filesystem is read-only, all Linux capabilities are dropped, and `no-new-privileges` is set;
- release symlinks are relative, so a user-owned host root remains valid at the container's `/opt/jeeb-cms` mount;
- the image must be pinned by repository and SHA-256 digest. A tag alone is rejected.

Copy this complete `jeeb-cms` directory to a user-owned location, create the runtime root, and start nginx once using a reviewed digest:

```bash
install -d -m 0755 /home/ec2-user/jeeb-cms/releases
export JEEB_CMS_ROOT=/home/ec2-user/jeeb-cms
export JEEB_CMS_NGINX_IMAGE='nginx@sha256:<reviewed-64-hex-digest>'
./scripts/docker-nginx.sh start
./scripts/docker-nginx.sh status
```

The container deliberately uses Docker restart policy `no`: Docker must not
restart nginx independently of release validation. After the one-time `start`,
install the user-owned boot validation and nginx units as root, and keep the
reviewed digest and non-secret runtime paths in the root-readable environment
file:

```bash
install -d -m 0755 /home/ec2-user/jeeb-cms-hosting
cp -a . /home/ec2-user/jeeb-cms-hosting/
install -d -m 0700 -o ec2-user -g ec2-user /home/ec2-user/.config/jeeb-cms
install -m 0600 -o ec2-user -g ec2-user /dev/null \
  /home/ec2-user/.config/jeeb-cms/nginx.env
# Populate nginx.env with the reviewed JEEB_CMS_ROOT, JEEB_CMS_OWNER='',
# JEEB_CMS_ACTIVATOR=docker, and digest-pinned JEEB_CMS_NGINX_IMAGE values.
install -m 0644 systemd/jeeb-cms-docker-release.service \
  /etc/systemd/system/jeeb-cms-docker-release.service
install -m 0644 systemd/jeeb-cms-nginx.service \
  /etc/systemd/system/jeeb-cms-nginx.service
systemctl daemon-reload
systemctl enable --now jeeb-cms-nginx.service
```

At every boot, systemd validates the active release before `docker-nginx.sh
boot` is allowed to start the existing stopped container. The helper then
revalidates the release, the complete container security contract, and the
loopback health endpoint. A validation or health failure leaves nginx stopped.

Do not use `latest`, bridge networking, `--publish`, a writable CMS mount, or a public `10100` firewall rule. The gateway's forwarded-header defaults trust the immediate loopback proxy; nginx supplies the original HTTPS scheme and public host, which keeps strict origin validation and `__Host-` refresh/CSRF cookies same-origin. Evidence responses remain under `/gateway/admin/v1/deliveries/.../evidence/<opaque-token>`; nginx streams them without buffering, hides upstream cache policy, and applies `no-store` without rewriting cookie paths or domains.

Deploy and roll back as `ec2-user` by selecting the Docker activator. Keep these variables in the operator environment for every release command:

```bash
export JEEB_CMS_ROOT=/home/ec2-user/jeeb-cms
export JEEB_CMS_OWNER=''
export JEEB_CMS_ACTIVATOR=docker
export JEEB_CMS_NGINX_IMAGE='nginx@sha256:<reviewed-64-hex-digest>'

./scripts/deploy-release.sh \
  --expected-manifest-sha256 <trusted-sha256-of-SHA256SUMS> \
  /path/to/artifact
./scripts/verify-current.sh --runtime
./scripts/rollback-release.sh
```

`docker-nginx.sh start` refuses to replace an existing container. `boot`, `status`, `test`, and `reload` require the same digest-pinned image and re-check host networking, restart policy, read-only root, dropped capabilities, security options, UID/GID, state, command, logging limits, restricted tmpfs, and every read-only bind mount before acting. This fallback has not been activated by repository work; deployment still requires an operator-approved image digest, artifact digest, Cloudflare tunnel route, and live validation.

Rollback to the recorded previous release or an explicit retained release:

```bash
sudo /opt/jeeb-cms/tools/rollback-release.sh
sudo /opt/jeeb-cms/tools/rollback-release.sh <release-id>
```

Rollback never edits release contents or domain data. It validates the target and uses the same nginx and served-release gates as deployment.

## Verification

```bash
sudo /opt/jeeb-cms/tools/verify-current.sh --runtime
curl -fsS http://127.0.0.1:10100/healthz
curl -fsS http://127.0.0.1:10100/release.json
curl -fsS http://127.0.0.1:10100/gateway/health/ready
```

Before operator access, additionally verify private TLS/Access, deep links, strict missing-remote 404 behavior, CSP/cache headers, release hashes, and successful Playwright journeys through the private domain.

## Repository tests

The tests do not require root, nginx, systemd, or network access:

```bash
deploy/msi/jeeb-cms/tests/run.sh
```
