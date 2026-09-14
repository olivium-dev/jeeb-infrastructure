# MSI development runtime activation transport

This directory defines the least-privileged bridge from the existing public
`msi-access` Cloudflare SSH account to six reviewed development runtime and credential
activators. It does not grant a shell, an interpreter, direct `systemctl`, file
copy, Docker, sudoers editing, staging access, or production access.

The one-time installation is an MSI administrator action. Build the
credential-free archive from the fixed revisions in
`reviewed-runtime-activation-manifest.json`, compare its SHA-256 with the
reviewed build result, transfer it into root custody, and extract it beneath
`/root`. The reviewed v4 archive is staged at
`/home/msi-access/.jeeb-deploy/jeeb-msi-runtime-activation-bootstrap-v4-e40b37a1.tar`
with SHA-256
`e40b37a1c03962e0e496c774c19436ae3120b955a42485442fcba737ba2db22d`.
An authenticated MSI administrator runs this exact root-side command:

```bash
set -euo pipefail
source=/home/msi-access/.jeeb-deploy/jeeb-msi-runtime-activation-bootstrap-v4-e40b37a1.tar
custody=/root/jeeb-msi-runtime-activation-bootstrap-v4-e40b37a1.tar
package=/root/jeeb-msi-runtime-activation-bootstrap-v4
test -d /home/msi-access/.jeeb-deploy
test ! -L /home/msi-access/.jeeb-deploy
test ! -L "$source"
test "$(/usr/bin/stat -c '%u:%g:%a:%h' "$source")" = 1002:1002:600:1
/usr/bin/install -o root -g root -m 0400 "$source" "$custody"
printf '%s  %s\n' e40b37a1c03962e0e496c774c19436ae3120b955a42485442fcba737ba2db22d "$custody" | /usr/bin/sha256sum --check --strict
if test -e "$package" || test -L "$package"; then
  test -d "$package"
  test ! -L "$package"
  test "$(/usr/bin/stat -c '%u:%g:%a' "$package")" = 0:0:700
fi
/usr/bin/tar --extract --file "$custody" --directory /root --no-same-owner
test "$(/usr/bin/stat -c '%u:%g:%a:%h' "$package/install-reviewed-runtime-activation.py")" = 0:0:500:1
printf '%s  %s\n' 603ac883ea2a78ec59de1a51571bcc48198be88f508be2064d99f93f79cae61a "$package/install-reviewed-runtime-activation.py" | /usr/bin/sha256sum --check --strict
/usr/bin/python3 -I "$package/install-reviewed-runtime-activation.py"
```

The installer requires root, the exact MSI hostname and `msi-access` uid/gid,
root-owned mode-0700 package directories, and exact source SHA-256 values. It
validates both sudoers copies with `visudo`, refuses to replace any nonmatching
target, installs the sudoers policy last, and restarts no service. Version 4 can replace only exact reviewed predecessor bytes for the
user-management Firebase helper, plus the earlier exact legacy helpers and
version-1 sudo policy already recognized by version 3. An exact rerun reports every target as already
exact.
If installation fails, it removes exact files created in that run and restores
recognized predecessor bytes in reverse order; recovery is to correct the
external package or host condition and run the same command again.

Do not install from a mutable branch checkout or a path writable by
`msi-access`. Record each installed helper digest before enabling the sudoers
file. The helpers must pin `ouday-GT70-2OC-2OD`, their one systemd unit, the
expected development credential identity and fixed destination. They must use
the existing `/run/jeeb-msi-service-deploy.lock`, preserve the incumbent
configuration, restart only their selected unit, and require exact post-start
identity/readiness. Credential values enter only on stdin and are never printed.

Each service repository owns its manual `development` workflow and its own
organization credential. The workflow connects through
`ssh-msi.olivium.space` as `msi-access`, using `MSI_SSH_PASSWORD` and
`MSI_SSH_KNOWN_HOSTS`, a checksum-pinned `cloudflared`, password-only SSH and
strict host-key checking. It pipes the service credential directly into its
fixed helper command. The transport values originate in this repository. The
protected `seal-existing-msi-transport.yml` workflow first proves the exact
`msi-access` host context, then seals both values to GitHub's fixed organization
public key. Its artifact contains ciphertext only. An organization administrator
can install that ciphertext as same-name organization secrets selected only to
`chat-service`, `push-notification`, `user-management`, `one-time-password`,
and `jeeb-gateway`; the service
workflows then receive transport without widening any application-credential
ACL. Application credentials remain selected to their existing single
repository and are not copied into infrastructure.

## Coordinated migration order

1. All six helpers and workflows pass repository tests. Install the reviewed
   helpers and this exact sudoers policy through the existing administrator
   route. Run the fixed push and user-management preflight commands; chat
   exposes only its separate stage and activate operations.
2. Stage chat and user-management credentials without restarting. Preserve the
   live `jeeb-5a293` files and drop-ins.
3. Activate user-management Firebase and verify Auth against
   `jeeb-development-msi`. Stage and activate the reviewed gateway verifier
   runtime, preserving its incumbent dependency-health baseline. Deploy the
   reviewed user-management build and stage its five SMTP credentials before
   the SMTP activation.
4. Release the reviewed development Firestore rules and required composite
   index, then immediately activate chat and require project
   `jeeb-development-msi`, database `(default)`, and Firestore mode.
5. Activate push and require readiness to report
   `firebase_project_id=jeeb-development-msi` before any exact-device FCM test.
6. Activate OTP only after its exact provider preflight passes; require the
   fixed `LegacyAuthToken` identity and selected-unit readiness before the one
   approved phone verification. Do not reuse the broad voice helper.
7. Run the separately authorized application journeys. Never send a topic or
   broadcast push. Do not treat an HTTP 200 from the old project as completion.

If a candidate fails, its service-specific helper restores only the preserved
incumbent binding and verifies that predecessor. Stop the coordinated sequence;
do not apply later steps or use a broad service restart.
