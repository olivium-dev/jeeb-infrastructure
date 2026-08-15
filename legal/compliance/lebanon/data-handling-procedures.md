# Jeeb Lebanon — Data Handling Procedures for Identity Documents

| Field            | Value                                  |
| ---------------- | -------------------------------------- |
| Version          | 0.1 (DRAFT)                            |
| Effective date   | TBD — pilot launch                     |
| Last reviewed    | 2026-05-16                             |
| Owner            | Data Protection Officer (DPO)          |
| Co-owner         | Principal SRE                          |
| Binding language | English                                |

> **Draft notice.** Operational details (specific bucket names, IAM roles,
> KMS key ARNs) are placeholders until the Beirut pilot environment is
> provisioned. The procedures themselves are launch-blocking.

## 1. Purpose

This document is the operational counterpart to
[`kyc-id-verification.md`](./kyc-id-verification.md) (policy) and
[`document-retention-policy.md`](./document-retention-policy.md) (retention).
Anyone who handles a Lebanese identity document inside Jeeb — engineer,
support agent, reviewer, on-call SRE — operates under these procedures.

## 2. Lifecycle: capture → use → archive → delete

```
+---------+   +-----------+   +----------+   +-----------+   +----------+
| Capture |-->| Transport |-->| Analysis |-->| Decision  |-->| Archive  |
+---------+   +-----------+   +----------+   +-----------+   +----+-----+
                                                                  |
                                                                  v
                                                            +-----+-----+
                                                            | Delete    |
                                                            | (scheduled|
                                                            |  & logged)|
                                                            +-----------+
```

### 2.1 Capture (in the mobile app)

- **In-app only.** No email, no chat, no upload from desktop. The mobile SDK
  is the single capture channel.
- **Direct-to-storage upload.** The app receives a short-lived pre-signed PUT
  URL (TTL 5 min) from `auth-service` and uploads directly to the KYC bucket.
  The backend never holds the raw image in transit memory longer than
  request-scope.
- **Memory hygiene.** The mobile SDK overwrites the in-memory buffer after
  upload and removes any temp file. Captures are NEVER written to the
  device's gallery.
- **Re-capture flow.** On rejection, the SDK requests a fresh pre-signed URL
  rather than re-uploading the original buffer.

### 2.2 Transport

- TLS 1.3 only on all hops. TLS 1.2 is permitted only at egress to legacy
  partners; TLS 1.1 is hard-rejected.
- mTLS between internal services that touch raw images: `auth-service`,
  vetting-partner egress proxy.
- HSTS enforced on `*.jeeb.app`.

### 2.3 Analysis

- Vetting-partner request happens from a dedicated egress proxy with a
  pinned source IP and SPIFFE identity; no other workload can reach the
  partner endpoint.
- Partner is sent the **minimum image set** required — front + back + selfie
  + the user's submitted name (for OCR cross-check). No phone number, email,
  or transaction history is sent.
- Partner responses are cached for 24 h keyed by capture hash to avoid
  duplicate billing/processing on re-decisions.

### 2.4 Decision

- Decisions are written to the append-only audit log AND to the
  user-facing record in the same database transaction (outbox pattern).
- Decisions include: `partner_decision`, `internal_decision`,
  `reviewer_id` (if manual), `tier_assigned`, `decision_at`.

### 2.5 Archive

- Long-term storage is on the KYC bucket only. There is no secondary copy
  in a data lake, BI warehouse, or analytics export.
- Field-level extracts go to Postgres; full images stay on object storage.

### 2.6 Delete

- Automated only — see [`document-retention-policy.md`](./document-retention-policy.md) §3.

## 3. Access control

| Role / surface                | Read raw images? | Read extracted fields? | Decide / override? |
| ----------------------------- | ---------------- | ---------------------- | ------------------ |
| App user (data subject)       | Their own only, via DSAR | Their own only            | No                 |
| Frontline support agent       | No               | Limited fields (name, status) | No            |
| KYC manual reviewer           | Yes — only with an open review ticket | Yes              | Decide within tier |
| Compliance Officer            | Yes — any time, logged                | Yes              | Yes — override     |
| Data Protection Officer       | Yes — for DSAR / audit only           | Yes              | No                 |
| On-call SRE                   | Operational metadata only (not image content) | Counts/metrics only | No             |
| Engineer (steady-state)       | No                                    | No               | No                 |
| Engineer (incident, break-glass) | Yes — 4-hour grant, dual-approval, every action logged | Yes | No |

### 3.1 Implementation notes

- IAM enforced via the object-storage bucket policy AND a thin proxy
  service that mediates list/get; engineers never get raw bucket
  credentials.
- The proxy issues per-request pre-signed GETs with TTL ≤ 5 min,
  attaching the reviewer's identity to a server-side query log.
- Break-glass uses a separately-stored set of credentials, rotated after
  every use, and triggers a Slack + PagerDuty + audit-log notification.

### 3.2 4-eyes rule

- Any manual override of an "auto-fail" requires a second reviewer's
  approval before the decision is committed.
- Any access to a user's raw KYC artefacts by the CO or DPO outside an
  active ticket requires a second sign-off from the other officer.
- 4-eyes events are reported in the quarterly audit.

## 4. Logging & observability

| Event                                  | Where                  | Retention | Alerting                                 |
| -------------------------------------- | ---------------------- | --------- | ---------------------------------------- |
| Pre-signed URL issued                  | App-audit log          | 90 days   | Spike detection (10× baseline)           |
| Image uploaded                         | App-audit log          | 90 days   | Failure ratio > 1% pages on-call         |
| Image fetched for review               | Compliance-audit log   | 10 years  | Any non-reviewer principal pages CO      |
| Decision written                       | Compliance-audit log   | 10 years  | Decision-rate anomaly pages CO           |
| Deletion run                           | Compliance-audit log + evidence bucket | 10 years  | Job failure pages on-call          |
| Break-glass access                     | Compliance + SecOps    | 10 years  | Slack + PagerDuty + email to CO          |
| DSAR served                            | DPO log                | 10 years  | Volume report to DPO weekly              |

- **PII never in application logs.** No log line includes ID numbers, raw
  document fields, or selfie URLs. Logs use opaque subject UUIDs.
- **No PII in error reporting tools.** Sentry / equivalent is configured
  with a deny-list of KYC schema field names.

## 5. Sharing & disclosure

- **Inside Jeeb:** strictly need-to-know per §3.
- **To vetting partner:** per §2.3; covered by the executed DPA.
- **To the internal COD owner (`unified_payment_gateway`):** only the opaque
  subject identifier and the minimum status/tier required by the approved COD
  settlement flow; never raw images, evidence URLs, or full ID numbers. UPG
  never holds primary KYC artefacts.
- **To authorities (SIC, courts):** only on a written, lawful request;
  CO + counsel review before release. Production-environment access for
  inspectors is forbidden — we produce a curated dossier instead.
- **To users (DSAR):** their own data only, after subject-identity is
  verified (KYC-grade verification of the requester).

## 6. Sub-processor change-management

- Adding or changing a sub-processor that touches identity documents
  requires:
  1. DPO impact assessment (DPIA-lite).
  2. CO sign-off.
  3. Updated DPA executed before any traffic.
  4. Notice to affected users via in-app banner.
- The Processor Register (linked from
  [`compliance-checklist-beirut-pilot.md`](./compliance-checklist-beirut-pilot.md) §5.4)
  is updated in the same change.

## 7. Incident response — privacy-incident track

A privacy incident is distinct from a security incident and follows its
own track. Triggers include: unauthorised image access, mistaken
disclosure to wrong user, deletion-job failure that exceeds retention
maximums, processor compromise.

| Step | Owner        | Target time                                  |
| ---- | ------------ | -------------------------------------------- |
| Detect & declare | First responder | Immediate                              |
| Triage           | DPO + SRE on-call | Within 1 h of detection                |
| Contain          | SRE on-call    | Within 4 h                                   |
| Notify CO        | DPO            | Within 6 h                                   |
| Subject notification (where required) | DPO + CO | Within 72 h of confirmed scope      |
| Authority notification (where required) | CO + counsel | Per applicable timeline           |
| Post-incident review | DPO + Tech Lead | Within 10 business days                |

Notifications use the templates in `compliance/lebanon/templates/`
(separate PR — out of scope for this ticket but referenced for
completeness).

## 8. Training

- Anyone listed in the access-control table receives an annual training
  refresh on this document.
- New reviewers complete a hands-on shadow shift before independent
  decisions.
- Training completion is part of the quarterly audit evidence.

## 9. Disposal of physical media (hypothetical)

Jeeb does not accept or hold physical identity documents. If a hard-copy
ever enters the office (e.g. a misdelivered envelope), the procedure is:

1. Do not photograph or scan.
2. Hand to the CO (or DPO if CO unavailable).
3. CO returns to user via tracked mail or shreds with witness.
4. Event recorded in the exceptions log.

## 10. Review

This document is reviewed:

- After any change to KYC pipeline architecture.
- After any privacy incident.
- At minimum annually.
