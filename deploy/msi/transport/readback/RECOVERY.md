# ROW-20 readback custody recovery — proposal, execution HOLD

The owner has no preserved bridge or audit copies. This proposal replaces the
request to restore those unavailable files. It neither reconstructs the bridge
nor retrieves, stores, or changes a sudo credential.

## Scope and immutable inputs

Source baseline: protected infrastructure
`962ac6815be32174a9e8dca2119fe9f32ac808e5`, bootstrap v9. Installed-helper and
policy pins come from that commit's transport manifest. Active UM receipt
semantics come from protected helper source
`d3dad46e5d7e7d7dea3c70c180732b4722068d08`, SHA-256
`5d79348bbc589d0e2d1bb259c89f75f09249bf038dd2a81ac0120f600ce350aa`.
The audit verifies exact installed helper bytes through held root-owned file descriptors, drops the whole final main guard after AST validation, and loads their fixed definitions in memory under non-main module names. It calls only the independently reviewed read-only validation functions; no helper CLI, stage, activate, restart, or application binary is invoked. Standard-library imports and top-level definitions in both pinned sources are included in review.

Only development host `ouday-GT70-2OC-2OD`, address `192.168.2.39`, is admitted.
Every operational path is fixed or derived from the fixed, validated UM release
receipt. No arguments, target selectors, input bundle, or caller environment
configuration are accepted. Script stdin must be `/dev/null` and empty.

## Existing managed paths assessed

- The installed push `--preflight` helper provides useful selected-service
  identity evidence through its protected workflow. It does not audit the
  complete policy, UM active receipt, SMTP bundle, or UM predecessor.
- The UM Firebase/SMTP preflights enforce their activation-incumbent layouts;
  they are not a post-activation audit of the current `90/95/96` runtime.
- Gateway diagnostics workflow rebuilds and replaces the gateway. It must not
  be used to recover read-only evidence.
- The infrastructure staging workflow only stages the pinned v9 archive as
  `msi-access`; it does not grant root readback. The v9 installer can perform
  writes even on an intended rerun. It is not an audit.

None of the existing 14 literal sudo delegations admits this script. Do not add
an interpreter, shell, generic file command, wildcard, or new persistent sudo
delegation. A future repository-owned readback workflow would require a
separately reviewed narrowly scoped capability and protected rollout; it cannot
be created by treating an existing mutation command as an audit.

## Proposed owner-controlled custody boundary

This procedure is PREPARATION ONLY. Independent source review does not authorize
execution or credential access. The owner must separately approve this exact
script digest and the bounded in-memory data access below. A human who can
authenticate as an MSI administrator through their own trusted terminal must
perform any custody transfer and execution; no password or authentication
material enters an agent tool, script, file, clipboard, or transcript.

After protected review/merge and exact-head validation, the owner obtains the
credential-free `audit.py` from that immutable commit and verifies its recorded
SHA-256. No value is trusted merely because its filename matches.

The owner stages those exact bytes using their own authenticated administrative
file transfer at this fixed destination:

| Object | Required metadata |
| --- | --- |
| `/root/jeeb-row20-readback-v1` | real directory, root:root, `0700` |
| `/root/jeeb-row20-readback-v1/audit.py` | regular file, root:root, `0500`, link count 1; approved SHA-256 |

All parent directories must be real, root-owned, and not group/other writable.
The owner verifies the digest **after** custody transfer and **before** running
the file. Do not execute directly from an upload path, home directory, checkout,
symlink, or runtime-writable directory. Existing unexpected destination bytes
are a stop condition, not permission to overwrite. This proposal intentionally
contains no bridge-reconstruction or automated privileged-install command.

The one proposed invocation, only after that separate owner approval, is:

```text
/usr/bin/sudo -- /root/jeeb-row20-readback-v1/audit.py < /dev/null
```

This is one fixed script-file action with empty stdin, executed by the human
administrator in their trusted terminal. It is not an agent-dispatched inline
root program, and no delegated `msi-access` privilege is added. Authentication,
if required, stays between the owner and sudo's trusted terminal prompt. Do not
use `sudo -S`, askpass, a new bridge, password arguments, or captured prompts.

Exact missing execution requirement: independent review and protected release
of this new script, plus owner approval and an owner-operated authenticated MSI
administrator session capable of establishing the specified root-owned custody.
Neither the old bridge nor an unspecified backup is a dependency.

## Audit behavior and data access

The audit checks its host and root execution context before service reads. It
uses bounded descriptor-based reads with `O_NOFOLLOW` for custody verification and its own reads, and validates directory ownership/path components. Exact pinned read-only helper functions also use pathname reads under verified protected chains; a shared lock excludes reviewed deployers, and explicit size/tree/deadline guards bound those reads. The audit hook rejects mutation operations, unexpected subprocess vectors, and non-allowlisted connections as defense in depth, not as an isolation boundary against hostile root code. It pins
six helper hashes and the policy hash, checks policy metadata and `visudo`, then
checks the fixed UM unit, active release/receipt/archive, predecessor executable,
development Firebase binding and SMTP source/runtime credential equivalence.

Approved data access must explicitly include reading the fixed process
environment, Firebase credential file, UM/chat receipts, staged chat credential,
SMTP credentials, and fixed chat systemd metadata/environment in memory.
Only allowlisted comparisons are emitted; transient values remain in memory only, with core dumps disabled. No raw content, email,
credential digest, principal identity, request body, or provider response is
output. The only direct HTTP operations are bounded local UM readiness and the existing chat predecessor Firebase health GET. The latter can exercise the service’s existing read-only provider readiness path; owner approval includes that fixed health check. The audit makes no direct provider connection, token mint, email/push send, or non-health application request.

The existing root-owned deployment lock is opened read-only and acquired using
nonblocking shared `flock`; a competing deployment causes HOLD. This changes
only transient kernel lock state during eventual execution and prevents the
reviewed exclusive-lock deployers from mutating during the snapshot. No lock
file is created, truncated, chmodded, or deleted. It is released on every exit.
Before/after unit identity must match. This remains point-in-time evidence;
functional Auth GO is always false in its output and needs ROW-03 acceptance.

The audit changes no service, credential, policy, receipt, or release. It is
idempotent and has a wall-clock deadline. Failures emit only a fixed phase and
fixed status. A failure stops the cutover and requires ROW-20 reconciliation;
there is no rollback command because this audit has no service mutation.
Do not clean residue, retry a provider operation, or rerun the installer.

## Remaining acceptance boundaries

READBACK-PASS proves only the complete local checks emitted as passed, including current chat stage-receipt currency. It is not Auth acceptance, mailbox delivery, Firestore release, push receipt, or OTP proof. Every output keeps step5PrerequisitesReady=false, cutoverGo=false, and functionalAuthGo=false because external proof gates remain separate. A failed phase is failed; phases not reached are not-run, never silently passed. It does not restore the old bridge or authorize future root
mutations. ROW-20 must refresh exact protected heads and lane prerequisites
again before any later mutation. v10 packaging remains held behind Step 6.

Production is locked and untouched. The script must never run on another host.

## Complete Step 5 gate map

| Prerequisite | Prepared proof path | Owner / remaining status |
| --- | --- | --- |
| Six installed v9 helpers, exact policy/visudo, root archive custody | audit transport + policy | ROW-20; execution unapproved |
| Shared deployment lock, no overlapping reviewed deployment | audit nonblocking shared lock held across all checks | ROW-20; execution unapproved |
| UM effective development binding, exact 90/95/96, no SMTP shadows, read-only credential ACL/equivalence, ready/schema_ok | exact-H9 verify_candidate with bounded read-only adapter + explicit binding and drop-in checks | ROW-20; execution unapproved |
| Active source/archive/receipt, exact protected release tree, current selector, no superseded residue | H9 read_stage_receipt + exact root members and selector checks | ROW-20; execution unapproved |
| Preserved UM rollback contract | fixed fragment/base drop-in/executable digests; legacy environment ownership/mode only, exactly as H9’s predecessor contract | ROW-20; no claim of historical environment-content digest or tested rollback |
| Sibling baseline continuity | all five fixed units active with unchanged before/after selected properties | ROW-20; no sibling deployment/rollback acceptance implied |
| Chat staged credential and current baseline currency | exact-af540 read-only stage-equivalent checks, fixed predecessor health | ROW-01/20; execution unapproved |
| Current protected heads and exact-head successful reviews/CI | existing read-only GitHub APIs by lane owners immediately before GO | ROW-03/20; not certified by local audit |
| Current push preflight | protected push preflight run; never activate/direct receipt | ROW-02 reports exact-head preflight run34884591463 at protected97faa17403575cc82800a7212855b1d2600e493f, independently recheck head/result before counting |
| Gateway signing/transport/probe secret availability and valid probe lifetime | existing reviewed ROW-03 owner-local provisioner and metadata checks, no values in evidence | ROW-03; separate lane proof required |
| One-attempt gateway deployment consent and bounded acceptance/rollback contract | ROW-03 protected gateway workflow only after ROW-20’s serialized GO and owner authorization | ROW-03/20; HOLD until full checkpoint |

No agent implementation is deferred for local root-readback gaps: this prepared audit contains the UM credential, runtime, residue, predecessor and chat readback checks. External workflow/identity/probe/acceptance work stays with its existing reviewed lane paths. A future protected head/helper change invalidates these fixed pins and requires re-review; it is not an argument or configuration override.

## Preparation status and local verification

This source is a new local proposal. Protected merge, exact-head CI, owner
execution approval, administrative custody transfer, and root execution have
not occurred. Do not label this local review as a protected release.

Offline tests run using `python3 -B -m unittest discover -s
deploy/msi/transport/readback/tests -v` from the isolated infrastructure
worktree. They cover real descriptor replacement/symlink/hardlink/ownership
and size boundaries, fixed argv and redaction (including a secret-bearing
late failure after synthetic credentials are held), actual isolated Python
audit-hook interception of write/socket calls, pinned-main-guard exclusion,
and real v9 credential ACL/member/drop-in falsifiers plus archive/receipt
mutation fixtures. No test opens a host connection or runs the root entrypoint.

The native archive's observed size 12,298,240 bytes is recorded in
`claude-handover/STATUS.md` Step 4 record-gap closure. This proposal admits at
most 16 MiB for that fixed archive and 32 MiB total expanded members; exact archive
digest remains mandatory, so a changed archive cannot be admitted by size.
The helper's bounded tree preguard allows at most 256 entries/eight levels.
Local source tests do not establish Linux live PASS, complete external
prerequisites, historical environment-content identity, or a tested rollback.
