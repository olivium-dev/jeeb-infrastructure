# Jeeb — Lebanon Compliance Pack (Beirut Pilot)

This directory contains the KYC, identity verification, document-retention, and
regulatory-checklist material specific to the **Beirut pilot launch** of the
Jeeb platform.

> **Status:** DRAFT v0.1 — pending review by qualified Lebanese counsel
> licensed by the Beirut Bar Association and validated against current
> guidance from Banque du Liban (BdL) and the Special Investigation
> Commission (SIC). These drafts establish structure, controls, and
> bilingual parity, but they are NOT a substitute for jurisdiction-specific
> legal advice and MUST be reviewed before the pilot opens to end users.

## Documents

| Document                                | Purpose                                                   |
| --------------------------------------- | --------------------------------------------------------- |
| [kyc-id-verification.md](./kyc-id-verification.md)                       | Accepted Lebanese identity documents, verification flow, liveness, edge cases |
| [document-retention-policy.md](./document-retention-policy.md)           | Retention periods, deletion triggers, legal-hold handling for identity material |
| [compliance-checklist-beirut-pilot.md](./compliance-checklist-beirut-pilot.md) | Go/no-go checklist — every item must be Green before Beirut pilot opens |
| [data-handling-procedures.md](./data-handling-procedures.md)             | Operational procedures for storing, accessing, transferring, and disposing of ID documents |

## Regulatory authorities referenced

- **Banque du Liban (BdL)** — central bank and AML/CFT authority for regulated
  banking and financial activity. Jeeb's UPG is documented here as an internal
  cash-on-delivery record, not as an electronic-payment provider or card
  gateway. Counsel must separately assess any future regulated payout provider.
- **Special Investigation Commission (SIC) / الهيئة الخاصة للتحقيق** —
  Lebanon's Financial Intelligence Unit, established under Law 318/2001 and
  reinforced by Law 44/2015 (Fighting Money Laundering and Terrorist Financing).
- **Ministry of Interior and Municipalities — Directorate General of Personal
  Status** — issuer of the Lebanese national ID card (`بطاقة الهوية`).
- **General Security (Sûreté Générale)** — issuer of passports and residency
  permits used for foreign-national KYC.
- **Lebanese Data Protection** — there is no comprehensive personal data
  protection law in Lebanon as of the drafting date; we apply
  **GDPR-equivalent controls** as a defensive baseline (see
  [`../../en/privacy-policy.md`](../../en/privacy-policy.md)) and monitor the
  draft Lebanese Data Protection Law for enactment.

## Roles

- **Compliance Officer (CO)** — accountable for KYC adequacy, SIC reporting,
  and sign-off on the pilot checklist. Named individual recorded in
  `compliance-checklist-beirut-pilot.md` §0.
- **Data Protection Officer (DPO)** — accountable for retention, access
  controls, and subject-rights handling.
- **Engineering on-call** — operates the verification pipeline; never reads
  raw ID documents outside an authorised support ticket.

## Change process

1. Open a PR against `main` titled `legal(lebanon): <document> v<old>→v<new>`.
2. Tag `@olivium-dev/legal`, `@olivium-dev/compliance`, and `@olivium-dev/sre`
   as reviewers.
3. Any change to retention periods, accepted documents, or data flows requires
   sign-off from the CO **and** the DPO.
4. Once merged, update the in-app compliance notice via the notification
   service and refresh the Beirut pilot runbook in `deploy/`.
