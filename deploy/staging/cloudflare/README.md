# Jeeb staging Cloudflare edge

This directory is the non-secret source of truth for the Jeeb staging Worker
and tunnel ingress. Wrangler owns the two exact public Custom Domains; the two
hidden origin names route to the existing staging tunnel.

Required runtime material is deliberately external:

- `CLOUDFLARE_API_TOKEN`: a scoped deploy token with Workers Scripts and the
  required zone Custom Domain permissions.
- `ORIGIN_KEY`: one random value stored as a Worker secret and in the root-only
  nginx map `/etc/nginx/jeeb-origin-key.map` on `.20`.
- The existing tunnel credentials under `/etc/cloudflared-jeeb-staging/`.
- The DNS-01 token under `/etc/letsencrypt/jeeb-secrets/`.

From this directory, deploy the Worker and its Custom Domains with the pinned
Wrangler release:

```bash
npx --yes wrangler@4.120.0 deploy --config wrangler.toml
```

On first provisioning or intentional key rotation, pipe the same newly
generated key to `npx --yes wrangler@4.120.0 secret put ORIGIN_KEY --config
wrangler.toml`, then install the matching nginx map as root without printing
the key. Never place the value in this directory, a command argument, a log, or
shell history.

Provision the hidden tunnel DNS names with the existing authenticated
`cloudflared` installation:

```bash
cloudflared tunnel route dns f029ab58-b82d-4bf3-906a-508ffe4c5661 \
  jeeb-app-origin.fds-1.com
cloudflared tunnel route dns f029ab58-b82d-4bf3-906a-508ffe4c5661 \
  jeeb-cms-origin.fds-1.com
```

Install and validate the server files with the commands in
`deploy/staging-192.168.2.20.md`. Cloudflare Custom Domains create their public
DNS records and edge certificates. Retain every Cloudflare-created DCV TXT
record for automatic renewal of the nested-host certificates.
