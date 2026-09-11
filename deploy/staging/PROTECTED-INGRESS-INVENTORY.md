# Opt-in protected ingress observation

The existing **Jeeb staging read-only readiness inventory** workflow retains its
default unprivileged inventory. The optional `protected_ingress` input defaults
to false. When true, it selects a separate diagnostic instead of the default
Docker/service inventory and requires `reviewed_sha` to equal the protected,
current `main` commit. Only the existing designated owner can run it, on attempt
one, in the protected staging environment. Source/run identity is checked before
transport preparation and again immediately before the credential-bearing step.

The user confirmed that the infrastructure repository's existing
`MSI_SSH_PASSWORD` also authenticates `ec2-user` sudo on `olivium-ephemerals`,
`192.168.2.20`. This confirmation is specific to that account and host; it is not
a general cross-environment credential allowance. The secret is available only
to the opt-in runner step. It is not copied to another repository, remote file,
command argument, output, artifact, or SSH child environment.

The pinned Cloudflare/SSH transport uses `jeeb-staging-ssh.fds-1.com`, `ec2-user`,
and the existing strict known-host binding. In the same SSH session, a fixed
unprivileged preflight proves the exact host name, IPv4 address and user. Only
after validating its bounded response does the runner send one newline-delimited
password on SSH stdin, then close the stream. There are no interactive prompts,
credential retries, fallback routes, installations or permission changes.

The remote command runs only the reviewed, SHA-256-pinned collector source via
fixed sudo and isolated Python arguments. That source argument is not a secret.
This is **diagnostic-only source transport**, not execution of an installed,
root-owned script file. The collector does not read a root script path or claim
that provenance. The validated output envelope instead binds the reviewed
source commit, collector digest, GitHub run and attempt.

The collector closes inherited stdin and gives every child command empty stdin.
It reuses the fixed tunnel observer's root-owned, mode-0600, single-link config
checks, no-follow ancestor traversal, bounded reads and repeated file/process/unit
identity checks. It reads no referenced credential file or process environment.
Only the fixed active tunnel unit's bound process is inspected. Three additional
fixed firewall read commands produce bounded counts and policy-presence facts,
not raw rules. Component failures use fixed enums, and tunnel failures do not
prevent independent firewall observations.

No Docker access, service change, restart, configuration write, policy grant,
token minting or identity activation is included. Every report keeps
`activationAuthorized`, `effectiveIngressProven` and
`externalConnectorsExcluded` false. A matching local unit/process/config snapshot
does not prove effective ingress isolation, exclude other connectors, or prove
which config bytes the running process loaded. Errors and partial observations
remain explicit gaps, never authorization.

Raw SSH/collector stdout and stderr are captured privately with strict time/size
limits. Only a fixed-schema validated report is retained as the protected ingress
artifact; arbitrary fields, strings and exception text are rejected. Failed
transport emits only a bounded fixed-stage failure result and does not upload an
unvalidated artifact. The existing exact runner SSH credential-file cleanup
continues to run on failure.

Local tests use fake subprocesses and no credentials or running services.
Root-owned filesystem fixtures are skipped when not running as Linux root; the
existing staging-edge contract workflow runs them on its disposable, credential-
free hosted Ubuntu runner. Never run those fixtures on staging or MSI.
