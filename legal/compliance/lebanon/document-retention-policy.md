# Jeeb Lebanon — KYC Document Retention Policy

| Field            | Value                            |
| ---------------- | -------------------------------- |
| Version          | 0.1 (DRAFT)                      |
| Effective date   | TBD — pilot launch               |
| Last reviewed    | 2026-05-16                       |
| Owner            | Data Protection Officer (DPO)    |
| Co-owner         | Compliance Officer (CO)          |
| Binding language | English                          |

> **Draft notice.** Retention durations below reflect the **5-year minimum**
> imposed by Lebanon's Law 44/2015 (Fighting Money Laundering and the
> Financing of Terrorism), Article 4, applied from the **end of the business
> relationship** or the **date of the last transaction**, whichever is later.
> Counsel must confirm before publication.

## 1. Principles

1. **Minimum necessary.** We collect only what KYC requires; we discard the
   rest at upload time (e.g. extra pages of a passport).
2. **Time-bound.** Every datum has a defined retention period and an
   automated deletion job, NOT a manual cleanup.
3. **Defensible deletion.** Deletion is logged, reviewable, and reversible
   only via legal-hold before deletion executes.
4. **Locality.** Personal data of Lebanese residents is stored primarily in
   the EU region of our object-storage provider, with restricted replication;
   processed-data does not leave the provider's EU/Middle East footprint.
5. **Separation of duties.** No single engineer can both extend a retention
   window and execute deletion; the CO sets policy and the SRE on-call
   operates the job.

## 2. Retention schedule

| Data category                            | Storage                                          | Minimum retention                                  | Maximum retention                                 | Deletion trigger                                  |
| ---------------------------------------- | ------------------------------------------------ | -------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------- |
| Raw ID images (front, back)              | Object storage, KMS-encrypted, object-lock=compliance | 5 years from last transaction (Law 44/2015)        | 7 years from last transaction                     | Scheduled job — first day of month after expiry   |
| Selfie images & liveness frames          | Object storage, separate prefix                  | 5 years from last transaction                      | 7 years from last transaction                     | Same schedule as ID images                        |
| Extracted KYC fields (name, DoB, ID#)    | `auth-service` Postgres (`kyc_subjects`)         | 5 years from last transaction                      | 10 years from last transaction (for AML pattern analysis) | Logical deletion at 5 y; physical at 10 y |
| Decision / match-score / liveness-score  | Append-only audit log                            | 5 years from decision                              | 10 years                                          | Roll-off via partitioned table drop               |
| Sanctions/PEP screening evidence (T3)    | Object storage, audit prefix                     | 5 years from decision                              | 10 years                                          | Roll-off                                          |
| Manual reviewer notes                    | Audit log (append-only)                          | 5 years from decision                              | 10 years                                          | Roll-off                                          |
| Vetting-partner reference IDs            | `auth-service` Postgres                          | 5 years (linkage required to re-pull evidence)     | 10 years                                          | Roll-off                                          |
| Rejected applications (never onboarded)  | Object storage + Postgres                        | 1 year from rejection (anti-fraud re-use)          | 1 year hard cap                                   | Daily job — delete records aged > 365 days        |
| Failed/abandoned captures (no decision)  | Object storage                                   | 30 days                                            | 30 days                                           | Daily job                                         |

### 2.1 Why two windows (minimum vs maximum)?

- **Minimum** = the regulatory floor; deletion before this is non-compliant.
- **Maximum** = the limit we voluntarily impose to avoid hoarding. Going
  beyond the maximum requires a written CO-approved legal-hold or a policy
  amendment.

## 3. The deletion job

- **Frequency:** runs nightly at 02:00 Asia/Beirut.
- **Implementation:** Bash + AWS CLI (S3-compatible API) for object-store,
  scheduled SQL via the `jeeb-infrastructure/scripts/` directory; logs to
  the `compliance-deletion` log stream and to S3 object-lock evidence bucket.
- **Dry-run first:** every change to the policy SQL ships with a 7-day
  dry-run period; the on-call SRE reviews the would-have-deleted manifest.
- **Idempotent:** if an object is already absent, the job records "no-op"
  rather than erroring; partial failures retry up to 3× with exponential
  backoff, then page the on-call SRE.

### 3.1 Evidence of deletion

Each deletion run emits, to the evidence bucket (object-lock = compliance,
retention = 10 years):

- `manifest-YYYY-MM-DD.json` — list of object keys + Postgres row IDs deleted.
- `summary-YYYY-MM-DD.json` — counts by category, errors, operator on-call.
- A signed hash chain — each day's manifest hashes the previous, so any
  tampering breaks the chain.

This is what we would surrender to a SIC information request to prove
deletion happened on the date claimed.

## 4. Legal hold

When a user's data is subject to a legal hold (SIC information request,
court order, internal investigation):

1. CO files a `LegalHold` record (ticket-tracked, written justification).
2. Hold suspends the deletion job for the affected user's data set.
3. Hold is reviewed every 90 days; CO must re-affirm or release.
4. Release of the hold triggers immediate re-evaluation: if retention has
   expired, deletion runs on the next nightly cycle.

A hold can extend retention indefinitely but **never** shorten the minimum
retention.

## 5. Data-subject rights

The Lebanese position on personal-data rights is evolving; we apply
GDPR-equivalent baseline:

- **Access (Art. 15 analogue):** subject may request their stored KYC
  artefacts; we respond within 30 days.
- **Rectification (Art. 16 analogue):** corrections to extracted fields are
  applied immediately; raw ID images are NOT mutated — we record a
  superseding capture.
- **Erasure (Art. 17 analogue):** we honour erasure requests only AFTER the
  Law 44/2015 minimum retention has elapsed; the user is told this and
  shown the earliest possible deletion date.
- **Portability (Art. 20 analogue):** extracted fields are exportable as
  JSON; raw images are not exported by default (privacy of the on-document
  embossed/holographic features) but may be released to the subject on
  written request.

## 6. Right to be forgotten — cap

We will refuse erasure requests that would put us in breach of Law 44/2015.
The refusal is in writing, names the legal basis, and gives the date on
which erasure WILL be honoured. This is the only refusal we allow ourselves
on KYC erasure.

## 7. Backups

- Backups containing KYC data are encrypted with a separate KMS key.
- Backup retention follows the **same** schedule as primary storage; we do
  not extend retention via backups.
- Backup restoration into a lower-environment is forbidden; staging uses
  synthetic data only.

## 8. Cross-border transfer

- Vetting partner: a named processor under written DPA; data leaves Lebanon
  only to the vetting partner's EU region; encrypted at rest and in
  transit; processor cannot retain after a 90-day verification window.
- No transfers to jurisdictions on the FATF black list.
- The internal `unified_payment_gateway` receives only opaque identifiers,
  COD amounts, collection/reconciliation status, and audit metadata. It does
  not receive raw KYC artefacts and is not a bank or external payout provider.
- Any separately contracted operational payout provider is governed by its
  own approved data-processing terms and is outside UPG's COD-owner role.

## 9. Audit cadence

- Quarterly self-audit by DPO + CO; sampled 25 deletion runs and 25
  legal-hold reviews.
- Annual external audit by independent counsel.
- Every audit produces a written attestation kept in
  `compliance/lebanon/audits/YYYY-Q#-attestation.md`.

## 10. Exceptions log

Any deviation from this policy — even a one-off — is recorded with
justification, CO approval, and a closure date. The exceptions log is part
of the quarterly audit scope.
