# Settlement Provider (PSP / Acquirer) — Contractual Requirements

> **Status:** DRAFT v0.1 — non-negotiable clauses for any Lebanese PSP,
> acquirer, or payment aggregator that settles client funds to Jeeb. Reviewed
> by Lebanese counsel before signing. Maps directly to the technical
> integration in `unified_payment_gateway`.

## 1. Counterparty eligibility

The PSP MUST be one of:
- A Lebanese bank with an acquiring license.
- A BdL-licensed Electronic Payment Service Provider under **Basic Circular 69**.
- A foreign PSP operating under a BdL no-objection letter (Circular 83) for
  cross-border collection, with a Lebanese correspondent bank.

For each, request copies of:
- The BdL license/no-objection (date, scope, expiry).
- PCI-DSS Attestation of Compliance (AoC), current.
- ISO 27001 certificate (or equivalent SOC 2 Type II report).
- The most recent year's financial statements with statutory auditor sign-off.
- Sanctions / AML compliance attestation (OFAC, EU, UK consolidated lists,
  plus the **Lebanese Special Investigation Commission** lists under
  Law 44/2015).

## 2. Mandatory contract clauses

### 2.1 Identification & licensing
- Full PSP legal name, registration country, BdL license number(s),
  authorized representative.
- Schedule listing all sub-processors (card schemes, wallets, KYC vendors).

### 2.2 Scope of services
- Card acquiring (Visa/Mastercard/Amex), local wallets, bank transfer
  (OMT, Whish, etc.) — list each with per-rail fees.
- Settlement currency (LBP primary; USD shadow account allowed only with
  explicit BdL notification).
- T+N settlement promise per rail; remedy for late settlement.

### 2.3 Fees & FX
- Per-transaction MDR (Merchant Discount Rate) with **all-in** disclosure
  (interchange + scheme + acquirer markup + FX).
- Chargeback fees (per case), refund fees, retrieval-request fees, MID setup.
- FX margin disclosed in basis points over BdL middle rate.
- **No silent fee changes** — minimum **60-day** notice; right to terminate
  fee-free on increase.

### 2.4 Funds custody & client-money protection
- Settlement account is in Jeeb's name (NOT pooled with other PSP merchants).
- If pooled is unavoidable, PSP must hold funds in a segregated trust
  account, with explicit acknowledgement that pooled funds are NOT part of
  the PSP's insolvency estate (Lebanese trust law is thin — get a written
  legal opinion).
- Maximum holdback / rolling reserve: cap stated in the contract; release
  schedule defined and audit-checkable.
- No setoff against unrelated debts.

### 2.5 KYC / AML / sanctions
- PSP performs KYC on Jeeb (corporate KYC, beneficial owners, source of
  funds) per Lebanese Law 44/2015 and BdL Circular 126.
- Jeeb performs KYC on Jeebers and Merchants per its own AML program.
- Both parties commit to screening every transaction against UN, OFAC, EU,
  UK, and Lebanese SIC lists.
- Reporting of suspicious transactions to SIC remains each party's own
  obligation (no delegation).

### 2.6 Data protection & residency
- PSP must comply with Lebanese Law 81/2018 (electronic transactions and
  personal data) and, where relevant, GDPR for EU cardholders.
- Cardholder data MUST NOT be transmitted to or stored on Jeeb systems —
  tokenization at the PSP edge; Jeeb only ever stores a network token
  reference.
- Data-residency: if PSP stores transaction data outside Lebanon, the
  contract must disclose host countries and confirm legal basis for
  transfer.

### 2.7 Reporting, reconciliation, audit
- Daily settlement report in machine-readable format (JSON or CSV)
  delivered by 09:00 Beirut time the following business day. Schema must
  include `transaction_id`, `merchant_ref`, `gross`, `mdr`, `fx_rate`,
  `net`, `settlement_date`, `currency`.
- Real-time webhooks for status changes (`authorized`, `captured`,
  `refunded`, `disputed`, `charged_back`, `reversed`).
- Reconciliation tolerance: 0.00 — any unreconciled item is escalated within
  one business day.
- Right of Jeeb (or its auditor) to audit PSP's processing of Jeeb data
  with 30-day notice, at Jeeb's cost.

### 2.8 Service levels
| Metric                          | Target                 | Remedy on breach           |
|---------------------------------|------------------------|----------------------------|
| Authorization API availability  | 99.95% monthly         | Service credit, escalation |
| Authorization latency p99       | < 1500 ms              | Service credit             |
| Webhook delivery success        | 99.9% within 60s       | Service credit             |
| Daily settlement file by 09:00  | 99% of days            | Service credit             |
| Incident comms first ack        | within 15 minutes      | Reportable; review at QBR  |

Service credits cap at 25% of monthly fees; uncapped indirect damages are
NOT excluded for breach of confidentiality, IP infringement, fraud, or
gross negligence.

### 2.9 Chargebacks & disputes
- 90-day chargeback liability allocation aligned with card scheme rules.
- Evidence submission deadline ≥ 7 calendar days before scheme deadline.
- PSP provides a chargeback portal with API access.
- Excessive-chargeback program: PSP must notify Jeeb in writing within 5
  business days of approaching scheme thresholds (Visa CB-to-tx ratio
  ≥ 0.9%; Mastercard ECP ≥ 1.5%).

### 2.10 Termination & exit
- Either party may terminate for convenience with **90-day** notice.
- Immediate termination by Jeeb for: PSP license loss, PCI-DSS lapse, BdL
  enforcement action, insolvency, material breach uncured for 30 days.
- Wind-down obligations: PSP continues processing for **180 days** after
  termination notice; releases all funds + provides full data export
  (transactions, tokens, KYC records) in machine-readable format within
  30 days; cooperates with migration to successor PSP.
- Survival: confidentiality, indemnity, audit, data-protection clauses
  survive termination.

### 2.11 Indemnity, liability, insurance
- PSP indemnifies Jeeb for: scheme fines arising from PSP non-compliance,
  data-breach incidents in PSP systems, regulatory fines from PSP's
  licensing failures.
- Liability cap: 12 months' fees paid; carve-outs above for confidentiality,
  IP, fraud, gross negligence, indemnities.
- PSP carries cyber-liability insurance of at least USD 5,000,000 per claim
  and produces a certificate annually.

### 2.12 Governing law & dispute resolution
- Governing law: **Lebanese law**.
- Forum: Lebanese courts of Beirut (commercial chamber); OR Lebanese
  Center for Arbitration (CLA) under its 2018 Rules — single arbitrator,
  Arabic + English bilingual proceedings, seat Beirut. Negotiate arbitration
  for cross-border PSPs; courts for purely-Lebanese PSPs.

### 2.13 Compliance with Olivium policies
- The contract must reference Olivium's **payment routing policy**:
  payments only via `unified_payment_gateway` (Elixir); no direct PSP
  callbacks to feature services. The PSP must accept that webhook URLs,
  IP allow-lists, and signing keys are managed at the gateway, not in
  per-service config.
- Secret material (API keys, signing secrets, mTLS certs) must be
  provisioned out-of-band (sealed envelope or hardware token) and rotated
  per the org's `cicd-secrets-rotation-playbook`. Plain-text secrets in
  email are grounds for immediate rotation at PSP's cost.

## 3. Pre-signing diligence checklist

- [ ] BdL license verified at source (`bdl.gov.lb` license registry).
- [ ] PCI-DSS AoC dated within 12 months.
- [ ] Sanctions screening of PSP entity, directors, UBOs.
- [ ] Reference calls with two existing Lebanese merchant customers.
- [ ] Sandbox tested end-to-end through `unified_payment_gateway`.
- [ ] Lebanese counsel sign-off on final draft.
- [ ] LACPA-registered CPA sign-off on fee schedule + tax treatment of MDR.
- [ ] Compliance Officer sign-off on AML carve-out.
- [ ] Tech Lead sign-off on API contract + webhook schema.

## 4. Post-signing operational integration

1. Provision MID(s) and store identifiers in `unified_payment_gateway`
   configuration only — never in feature services.
2. Configure webhook signing keys via the secrets manager; rotation cadence
   per the policy.
3. Wire daily settlement file ingest into the wallet-service reconciliation
   job; on any non-zero diff page the on-call finance engineer.
4. Add PSP availability + latency to the SLO dashboard; multi-window burn
   alerts per the `slo-multi-window-burn-rate-alerts` skill.
5. Schedule quarterly business review with PSP — fees, incidents,
   chargeback ratio, roadmap.

## 5. References

- BdL Basic Circulars 69 (PSP licensing), 81 (e-banking), 83 (e-payment), 126 (AML).
- Law 44/2015 (Fighting Money Laundering and Terrorism Financing).
- Law 81/2018 (electronic transactions and personal data).
- PCI-DSS v4.0.1 (current version at document date).
- Visa/Mastercard chargeback rule books (current versions).
- Lebanese Center for Arbitration — 2018 Rules.
- Olivium policy: payments via `unified_payment_gateway` only
  (see `olivium-payment-routing` skill).
