# MSI development runtime activation transport

This directory defines the least-privileged bridge from the existing public
`msi-access` Cloudflare SSH account to four reviewed development credential
activators. It does not grant a shell, an interpreter, direct `systemctl`, file
copy, Docker, sudoers editing, staging access, or production access.

The one-time installation is an MSI administrator action. Install only helpers
whose service-repository revision and SHA-256 have been reviewed, then validate
the sudoers file before making it active:

```bash
sudo install -o root -g root -m 0755 REVIEWED_CHAT_HELPER \
  /usr/local/sbin/jeeb-msi-chat-firebase-admin
sudo install -o root -g root -m 0755 REVIEWED_PUSH_HELPER \
  /usr/local/sbin/jeeb-msi-push-firebase-admin
sudo install -o root -g root -m 0755 REVIEWED_USER_MANAGEMENT_FIREBASE_HELPER \
  /usr/local/sbin/jeeb-msi-user-management-firebase-admin
sudo install -o root -g root -m 0755 REVIEWED_USER_MANAGEMENT_SMTP_HELPER \
  /usr/local/sbin/jeeb-msi-user-management-smtp-admin
sudo visudo -cf deploy/msi/transport/jeeb-msi-runtime-activation.sudoers
sudo install -o root -g root -m 0440 \
  deploy/msi/transport/jeeb-msi-runtime-activation.sudoers \
  /etc/sudoers.d/jeeb-msi-runtime-activation
sudo visudo -cf /etc/sudoers.d/jeeb-msi-runtime-activation
```

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
`chat-service`, `push-notification`, and `user-management`; the service
workflows then receive transport without widening any application-credential
ACL. Application credentials remain selected to their existing single
repository and are not copied into infrastructure.

## Coordinated migration order

1. All four helpers and workflows pass repository tests. Install the reviewed
   helpers and this exact sudoers policy through the existing administrator
   route. Run the fixed push and user-management preflight commands; chat
   exposes only its separate stage and activate operations.
2. Stage chat and user-management credentials without restarting. Preserve the
   live `jeeb-5a293` files and drop-ins.
3. Activate user-management Firebase and verify Auth against
   `jeeb-development-msi`. Deploy the reviewed user-management build and stage
   its five SMTP credentials before the SMTP activation.
4. Release the reviewed development Firestore rules and required composite
   index, then immediately activate chat and require project
   `jeeb-development-msi`, database `(default)`, and Firestore mode.
5. Activate push and require readiness to report
   `firebase_project_id=jeeb-development-msi` before any exact-device FCM test.
6. Run the separately authorized application journeys. Never send a topic or
   broadcast push. Do not treat an HTTP 200 from the old project as completion.

If a candidate fails, its service-specific helper restores only the preserved
incumbent binding and verifies that predecessor. Stop the coordinated sequence;
do not apply later steps or use a broad service restart.
