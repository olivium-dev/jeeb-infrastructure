# Jeeb Lebanon — KYC & National ID Verification

| Field            | Value                                  |
| ---------------- | -------------------------------------- |
| Version          | 0.1 (DRAFT)                            |
| Effective date   | TBD — pilot launch                     |
| Last reviewed    | 2026-05-16                             |
| Owner            | Compliance Officer                     |
| Binding language | English (Arabic translation parity required before launch) |

> **Draft notice.** Verification thresholds, accepted document set, and
> retention periods herein are aligned with BdL Basic Circular 83 (AML/CFT)
> and Law 44/2015. They MUST be confirmed by qualified Lebanese counsel
> before the pilot opens.

## 1. Scope

This document governs identity verification ("KYC") for:

- **Clients** — end users who request a delivery, errand, or service.
- **Jeebers** — independent contractors who fulfil Client requests.
- **Merchants** — businesses listing services on the platform.

Stronger verification applies to Jeebers and Merchants than to Clients because
they receive payouts and have direct customer contact.

## 2. Risk-tiered KYC

We apply a risk-tiered model rather than a single one-size process. Tier is
assigned at onboarding and re-evaluated on trigger events (large transaction,
adverse-media hit, complaint, etc.).

| Tier | Who                                              | Verification depth                            | Transaction caps (LBP equivalent / month) |
| ---- | ------------------------------------------------ | --------------------------------------------- | ----------------------------------------- |
| T0   | New Client, mobile-only, no payment instrument   | Phone OTP only                                | Read-only; cannot transact                |
| T1   | Client with payment instrument                   | Phone OTP + name + DoB + ID number captured   | Equivalent of USD 500                     |
| T2   | Client, elevated cap or repeat user              | T1 + ID-document image + selfie liveness      | Equivalent of USD 2,000                   |
| T3   | Jeeber / Merchant                                | T2 + address proof + sanctions/PEP screening  | Eligible for payouts; no cap, monitored   |

Tier upgrades require an explicit user action AND a successful additional
check; tiers never auto-upgrade silently.

## 3. Accepted identity documents

### 3.1 Lebanese nationals

| Document                                            | Arabic name             | Notes                                                        |
| --------------------------------------------------- | ----------------------- | ------------------------------------------------------------ |
| Lebanese National ID Card (new biometric)           | بطاقة الهوية الجديدة    | **Preferred.** Front + back required. MRZ parsed where present. |
| Lebanese National ID Card (legacy, pre-2023)        | بطاقة الهوية القديمة    | Accepted with manual review queue; phased out by EOY 2026.   |
| Lebanese Passport                                   | جواز السفر اللبناني     | Machine-readable zone (MRZ) parsed; biometric page only.     |
| `إخراج قيد` (Civil Status Excerpt, issued ≤ 3 months) | إخراج قيد إفرادي         | Accepted ONLY as supplementary document when ID is contested. |

Driving licences are **not accepted as primary ID** for KYC (they do not carry
the full data set required by BdL Circular 83), but they may be accepted as a
secondary document for Jeeber onboarding alongside vehicle registration.

### 3.2 Foreign nationals resident in Lebanon

| Document                                                  | Notes                                                       |
| --------------------------------------------------------- | ----------------------------------------------------------- |
| Foreign passport (biometric page)                         | Required for all non-Lebanese.                              |
| Lebanese residency permit (`إقامة`) — valid, not expired   | Required in addition to passport. Expired residency = block. |
| UNHCR registration card                                   | Accepted for refugee onboarding under T1 cap only; manual review. |
| Syrian / Palestinian special documents                     | Manual review; CO approval required per applicant.          |

### 3.3 Documents we will NEVER accept

- Photocopies of photocopies, screen-shots of screens, or photos of monitors.
- Documents with redactions, stickers, or visible tampering.
- Documents whose MRZ or machine-readable elements fail checksum.
- Documents flagged in our internal block-list (lost/stolen reports).

## 4. Verification flow

```
+------------------+      +-------------------+      +--------------------+
|  App: capture    | -->  |  Quality gate     | -->  |  Document analysis |
|  front+back+     |      |  blur / glare /   |      |  OCR + MRZ + tamper |
|  selfie          |      |  framing checks   |      |  + face extraction  |
+------------------+      +-------------------+      +---------+----------+
                                                               |
                                                               v
+------------------+      +-------------------+      +--------------------+
|  Decision: pass  | <--  |  Sanctions / PEP  | <--  |  Liveness + face   |
|  / review / fail |      |  screening (T3)   |      |  match (selfie↔ID) |
+--------+---------+      +-------------------+      +--------------------+
         |
         v
+------------------+
|  Audit log entry |
|  (immutable)     |
+------------------+
```

### 4.1 Liveness

- Active liveness (head turn + blink) is required for T2 and T3.
- Passive liveness (texture/depth heuristics) is accepted for T1 selfie capture.
- Face-match threshold against ID photo: cosine similarity ≥ **0.62** auto-pass,
  0.50–0.62 manual review, < 0.50 auto-fail. Thresholds reviewed quarterly
  against false-accept / false-reject rates on the held-out evaluation set.

### 4.2 Document tamper checks

Performed by the vetting partner:

- MRZ checksum (passports, new ID cards).
- Hologram / OVI heuristic on flash vs no-flash captures.
- Font and spacing consistency vs reference templates.
- Image-EXIF & re-encoding signals (catch second-generation photos).

### 4.3 Sanctions / PEP screening

For Tier 3 only:

- Screen against UN Consolidated List, OFAC SDN, EU consolidated list, and
  any list explicitly required by SIC.
- Re-screen monthly; re-screen on name change or address change.
- A positive hit always escalates to the Compliance Officer; the user is
  **never** auto-blocked solely on a fuzzy-match score.

## 5. Edge cases

| Situation                                              | Handling                                                            |
| ------------------------------------------------------ | ------------------------------------------------------------------- |
| Name on ID has a `ابن` / `بنت` patronymic              | Capture as-is; normalise for sanctions screening with `unicodedata` NFKC + diacritic stripping. |
| Arabic-only ID (legacy)                                 | Run both Arabic and Latin OCR; require manual review if Latin fields missing. |
| Date of birth recorded as `00/00/YYYY` (older records) | Accept; flag DoB as "year-only" in record; do not block.            |
| ID issued ≤ 24 h before submission                      | Manual review (forgery risk).                                       |
| User under 18                                           | Block. Minimum age for Client is 18; Jeeber is 21.                  |
| Foreign national with expired residency                | Block onboarding; allow read-only account; surface in-app guidance. |
| Card photo is partially obscured (case, finger)         | Re-capture prompt; max 3 attempts before manual review queue.        |

## 6. Failure modes & retries

- Auto-fail does not permanently block — user may re-submit after 24 h.
- After 3 auto-fails in 7 days, account moves to manual review queue with
  SLA of 1 business day. User is informed in-app and over SMS.
- Compliance Officer is the sole authority who can override a "fail" decision.

## 7. Data captured & where it lives

| Field                          | Stored where             | Encrypted at rest? | Encrypted in transit? |
| ------------------------------ | ------------------------ | ------------------ | --------------------- |
| Raw ID images (front/back)     | Object storage (S3-compatible), private bucket, KMS-encrypted | Yes (AES-256 via KMS) | Yes (TLS 1.3)         |
| Selfie image                   | Same bucket, separate prefix | Yes              | Yes                   |
| Extracted fields (name, DoB, ID#) | `auth-service` Postgres, `kyc_subjects` schema | Yes (column-level for ID#) | Yes |
| Match score, liveness score    | `auth-service` Postgres                  | Yes                | Yes                   |
| Vetting-partner reference IDs  | `auth-service` Postgres                  | Yes                | Yes                   |
| Decision audit log             | Append-only log + S3 object-lock         | Yes                | Yes                   |

Cross-references: see [`data-handling-procedures.md`](./data-handling-procedures.md)
for access control, and [`document-retention-policy.md`](./document-retention-policy.md)
for retention.

## 8. Out of scope

- Crypto / virtual-asset onboarding (Lebanon position not yet settled).
- Corporate/legal-entity KYB — deferred until post-pilot.
- Payouts to non-Lebanese bank accounts — uses
  `unified_payment_gateway` partner-bank KYC.

## 9. Audit & evidence

The Compliance Officer must be able to reconstruct, for any verified user,
within 15 minutes: the documents submitted, the timestamps, the partner used,
the decision, the human reviewer (if any), and the final tier. This is the
SIC's typical request format and we test it quarterly via tabletop drill.
