# Jeeb staging Cloudflare edge

This directory is the non-secret source of truth for the Jeeb staging Worker
and tunnel ingress. Wrangler owns the two exact public Custom Domains; the two
hidden origin names route to the existing staging tunnel.

Required runtime material is deliberately external:

- `CLOUDFLARE_API_TOKEN`: the staging organization token with Workers Scripts:Edit
  on the exact account, consumed by the protected edge release workflow.
- `ORIGIN_KEY`: one random value stored as a Worker secret and in the root-only
  nginx map `/etc/nginx/jeeb-origin-key.map` on `.20`.
- The existing tunnel credentials under `/etc/cloudflared-jeeb-staging/`.
- The DNS-01 token under `/etc/letsencrypt/jeeb-secrets/`.

Use the protected `jeeb-staging-edge-deploy.yml` workflow for releases. It uploads
a version and deploys that exact version with Wrangler 4.120.0 while verifying
that the two existing Custom Domain associations remain unchanged. Initial domain
provisioning is separate from this release token and workflow.

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

## Staging organization credential

The edge release and manual `jeeb-cloudflare-org-auth-check.yml` workflow use only
`JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_API_TOKEN` from organization
`olivium-dev`, with access selected only for `jeeb-infrastructure`. Do not create
a repository or Environment secret with that same name: it would override the
organization value. The legacy generic Environment token is not a fallback.

Set the repository variable
`JEEB_STAGING_JEEB_INFRASTRUCTURE_CLOUDFLARE_TOKEN_ID_SHA256` to the SHA-256 of
the new token's public ID from its provider metadata. This is not a credential
value or its hash. Missing or mismatched metadata fails before Worker reads.
Before dispatch, verify that the organization name has exactly this one repository
ACL and no same-name repository or staging Environment override.

Use Account Workers Scripts:Edit only on account
`58198ae51392a2cc2d391867fb65da7e`. Version uploads, version deployments, and
Worker-domain reads use that permission. This account permission cannot be scoped
to one Worker. The workflow fixes `jeeb-staging-host-router`, `fds-1.com`, and the
two staging hostnames; no Zone/DNS permission is needed for its operations.

The manual check is restricted to the protected `main` branch, the exact supplied
commit, and the authorized actor. It verifies the pinned active token plus the
exact two Worker domain associations using GET requests to Cloudflare only.
It prints only PASS/FAIL and neither deploys nor reads application data. The edge
release repeats the same authentication before any SSH access or remote mutation.
A successful check proves credential access; it is not an edge deployment or
physical-device acceptance result. Development uses existing MSI tunnel transport
and does not need a Cloudflare API token. Production is excluded.

Permission references:
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/
- https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/
