# MSI SSH Access Through Cloudflare

Last verified: 2026-08-30

## Purpose and scope

Use this procedure to open an SSH shell on the MSI dev/staging server from
outside the local network. The connection goes to Cloudflare's public edge and
then through the dedicated MSI Cloudflare Tunnel. It does not require a
Cloudflare account, a Zero Trust login, a paid Cloudflare feature, or the MSI
server's local address.

This access path is for interactive administration and read-only CI smoke
testing. It does not change DNS, Cloudflare configuration, or any other tunnel.

## Connection model

```text
SSH client -> cloudflared -> ssh-msi.olivium.space -> MSI sshd
```

Cloudflare Free does not proxy a plain public TCP/22 connection. Consequently,
`ssh msi-access@ssh-msi.olivium.space` by itself is not the Cloudflare path;
the `ProxyCommand` shown below is required.

## What you need

1. OpenSSH (`ssh`).
2. The `cloudflared` client in `PATH`.
3. Username `msi-access` and the current password, delivered through a secure
   channel. The password is intentionally not stored in this repository.
4. The expected MSI ED25519 host fingerprint:
   `SHA256:Xs5MI67FcrC2PvP7iRa4GH9nArqUm0BmUR6yylJseUY`.

Install `cloudflared` on macOS:

```bash
brew install cloudflared
```

For Linux and Windows, use the official Cloudflare packages:
<https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>.

## Connect from a terminal

Run this command as one line:

```bash
ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o StrictHostKeyChecking=accept-new \
  -o 'ProxyCommand=cloudflared access ssh --hostname %h' \
  msi-access@ssh-msi.olivium.space
```

On the first connection, compare the displayed ED25519 fingerprint with the
fingerprint above before accepting it. Enter the supplied password only at the
SSH password prompt. A Cloudflare browser login is not expected.

After the first verified connection, use strict host-key checking:

```bash
ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o StrictHostKeyChecking=yes \
  -o 'ProxyCommand=cloudflared access ssh --hostname %h' \
  msi-access@ssh-msi.olivium.space
```

## Optional SSH shortcut

Add this block to `~/.ssh/config` after the host fingerprint has been verified:

```sshconfig
Host msi-cloudflare
    HostName ssh-msi.olivium.space
    User msi-access
    PreferredAuthentications password
    PubkeyAuthentication no
    StrictHostKeyChecking yes
    UserKnownHostsFile ~/.ssh/known_hosts
    ProxyCommand cloudflared access ssh --hostname %h
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Then connect with:

```bash
ssh msi-cloudflare
```

## What this account can do

- `msi-access` is a normal shell account with no `sudo` or Docker membership.
- Root login is disabled.
- SSH agent forwarding, TCP forwarding, X11 forwarding, gateway ports, and SSH
  tunnels are disabled on the Cloudflare path.
- Password authentication for this account is enabled only when sshd receives
  the connection from the local Cloudflare connector. Direct network password
  authentication remains disabled.
- Existing key-based access for the server owner is unchanged.

Anyone who has the shared password can open this non-admin shell. Rotate the
password when a colleague no longer needs access or whenever disclosure is
suspected.

## Public web endpoints

| Purpose | URL | Healthy result |
|---|---|---|
| MSI web application | <https://msi.olivium.space> | HTTP `200` |
| HTTP redirect path | <http://msi.olivium.space> | Redirects to HTTPS, final HTTP `200` |
| MSI API | <https://app.jeeb.fds-1.com> | HTTP `401` at the protected root is expected |
| Realtime socket | `wss://app.jeeb.fds-1.com/socket/websocket` | Requires the application protocol and authentication |

## GitHub Actions smoke test

The manual workflow
[`msi-cloudflare-ssh-smoke.yml`](../../.github/workflows/msi-cloudflare-ssh-smoke.yml)
tests the same public password path. It installs a checksum-pinned `cloudflared`
binary, enforces the pinned SSH host key, forces password authentication, runs
a non-mutating identity check, and verifies the public HTTP endpoints.

Required GitHub Actions secrets in `olivium-dev/jeeb-infrastructure`:

| Secret | Value |
|---|---|
| `MSI_SSH_PASSWORD` | Current password for `msi-access` |
| `MSI_SSH_KNOWN_HOSTS` | Exact `known_hosts` line for `ssh-msi.olivium.space` |

The workflow is manual-only, has no repository write permission, runs only from
the protected default branch, and does not use a Cloudflare token. Dispatch it
from GitHub Actions or with:

```bash
gh workflow run msi-cloudflare-ssh-smoke.yml \
  --repo olivium-dev/jeeb-infrastructure \
  --ref main
```

Success criteria:

- The SSH step prints `MSI_CLOUDFLARE_PASSWORD_SSH_OK`.
- The remote username is `msi-access`.
- The account is confirmed non-privileged.
- Existing key-based operator login remains independent of this workflow.
- The web application returns `200`, and the protected API root returns `401`.

## Troubleshooting

### `cloudflared: command not found`

Install `cloudflared`, close and reopen the terminal, then run
`cloudflared --version`.

### Plain SSH times out

Plain TCP/22 is not the Cloudflare Free tunnel. Use the full command with
`ProxyCommand` or the `msi-cloudflare` SSH shortcut.

### `Permission denied`

Confirm that the username is exactly `msi-access` and obtain the current
password from the server owner. Do not place the password in the command line,
documentation, chat logs, or source control.

### Host key changed

Stop. Do not disable host-key checking or delete the old entry blindly. Ask the
server owner to verify whether the MSI host key was intentionally rotated and
publish the replacement fingerprint before reconnecting.

### GitHub workflow reports missing secrets

An administrator must configure both required Actions secrets. There are no
fallback credentials; the workflow fails closed when either secret is absent.

## Disable or rotate access

This workflow never modifies the server. To revoke shared access, the server
owner must lock `msi-access` or rotate its password through an already-authorized
operator session, then update `MSI_SSH_PASSWORD` if CI access should continue.

