# Settlement Provider — Contractual Requirements

| Field | Value |
| --- | --- |
| Version | 1.0 (DRAFT) |
| Effective Date | TBD — gated by legal counsel sign-off |
| Owner | Finance + Legal |
| Audience | Founders, Legal Counsel, Finance, Backend (`unified_payment_gateway`, `wallet-service`) |
| Linked ticket | T-legal-003 |

> **Disclaimer.** This document is an engineering/operations specification of the contractual terms Jeeb SAL must secure from each settlement provider before the Beirut pilot can route a single real transaction. It is **not** legal advice. Each Master Services Agreement (MSA) drafted from this spec must be reviewed by Lebanese legal counsel and (for cross-border or USD-denominated terms) by counsel familiar with current BDL and MoF circulars.

## 1. Why this document exists

Per **FR-10.4**, Jeebers select one of three settlement methods at onboarding: **OMT, Whish Money, or bank transfer**. The MVP must contract with all three so a Jeeber's choice is honored.

A settlement provider failure (refused transfer, KYC rejection, account freeze, AML flag) is a **direct revenue blocker** — commission cannot be collected, and Jeebers experience a missed-payday incident that destroys platform trust. To prevent this, each settlement provider MSA must satisfy a defined set of contractual requirements, captured below.

This document is the **input specification** for the MSA-negotiation work that Legal will execute in weeks W-3 / W-2 of the launch roadmap ([business-entity-recommendation.md](./business-entity-recommendation.md) §4).

## 2. Counterparty inventory

| Provider | Type | Role at MVP | Volume tier expected |
| --- | --- | --- | --- |
| OMT (Online Money Transfer S.A.L.) | Lebanese money-transfer operator with retail-counter network | Primary cash-out for Jeebers without bank accounts | High |
| Whish Money | Lebanese mobile-wallet operator | Digital-wallet cash-out for Jeebers with smartphones | High |
| Primary commercial bank (counterparty TBD) | Lebanese commercial bank, account-holder for Jeeb SAL | Bank-transfer cash-out for Jeebers with bank accounts; corporate operational account | Medium |
| Secondary commercial bank (counterparty TBD) | Lebanese commercial bank | Failover / multi-bank redundancy | Low — failover only |

The choice of **specific** commercial bank counterparties is a Finance + Legal decision dependent on the bank's onboarding posture at the time of incorporation (post-2019 Lebanese banking environment is volatile; the recommendation is to maintain at least one secondary bank relationship from day 1).

`unified_payment_gateway` (Elixir) is the **only** integration surface for Jeeb services. Per the locked-in atlas policy, no Jeeb microservice may integrate directly with OMT / Whish / banks; all flows route through `unified_payment_gateway`.

## 3. Required clauses — by category

The following clauses are **mandatory** in every settlement-provider MSA. Missing or weakened versions of any item below are a launch-blocker until counsel confirms a written waiver.

### 3.1 Identity and counterparty

- **3.1.1** Counterparty named is the Lebanese registered entity (e.g., "OMT S.A.L.", with its Commercial Register number and TIN).
- **3.1.2** Jeeb SAL is the named contracting party with its Commercial Register number, TIN, and registered Beirut HQ address.
- **3.1.3** A clean, exclusive list of named individuals authorized to bind Jeeb SAL is appended (per the Articles of Incorporation).
- **3.1.4** Notice addresses for both parties are explicit, including email AND physical.

### 3.2 Service scope and definitions

- **3.2.1** "Services" enumerated unambiguously — for OMT: outbound cash-payout to recipient using cash-pickup code; inbound USD/LBP transfer to Jeeb SAL operational account; transaction-status webhook.
- **3.2.2** "Transaction" defined with explicit success / partial / failure semantics that map 1:1 onto the FR-10 and BR-4 settlement events.
- **3.2.3** "Settlement date" defined — must be at most T+1 business day from initiation for outbound payouts.
- **3.2.4** Currency support enumerated — USD, LBP, or both — and which currency the *settlement to the recipient* occurs in (FX margin clauses follow in 3.4).
- **3.2.5** Geographic scope — Lebanese-resident recipients only at MVP. Cross-border payouts not in scope.

### 3.3 Pricing and fees

- **3.3.1** Per-transaction fee schedule explicit, in writing, by transaction size band.
- **3.3.2** Monthly minimum and any inactivity fees disclosed up-front. No "hidden surface area" — fees that don't appear in the MSA may not be charged.
- **3.3.3** Fee changes require **60 days written notice**. No retroactive repricing.
- **3.3.4** Volume tiers and renegotiation triggers defined (e.g., "above N transactions / month, fee renegotiated").
- **3.3.5** Fees invoiced monthly with itemized statement. Jeeb has 30 days to dispute any line item.

### 3.4 FX and currency

- **3.4.1** If outbound payouts are in LBP but Jeeb's operational currency is USD, the **FX rate basis** is explicit — quoted spot rate from a named index (BDL official, sayrafa successor regime, or bank-published rate), with the **margin** Jeeb pays disclosed in basis points.
- **3.4.2** FX rates are **locked at transaction initiation**, not at execution. Slippage to recipient is the provider's risk, not Jeeb's.
- **3.4.3** No unilateral switching from one rate basis to another without 30 days notice.

### 3.5 SLA — availability and operational

- **3.5.1** **Service availability:** 99.5% monthly, computed on calendar-month basis, excluding planned maintenance announced ≥ 72h in advance.
- **3.5.2** **Payout completion SLA:** outbound payouts to recipient complete within **T+1 business day** of submission for 99% of transactions; T+2 for the remainder.
- **3.5.3** **API response SLA:** p95 latency on transaction-initiation API < 2000ms; p99 < 5000ms.
- **3.5.4** **Webhook delivery SLA:** transaction-status webhook to Jeeb's `unified_payment_gateway` callback URL delivered within 60 seconds of state change, with retry on 5xx for at least 24 hours.
- **3.5.5** **Incident communication:** Sev-1 incidents (full outage, integration unavailable, mass-payout failure) communicated to the named Jeeb on-call contact within 30 minutes of detection, by phone + email.
- **3.5.6** **Service credit regime:** breach of SLA in §3.5.1 / §3.5.2 results in a per-percentage-point fee credit defined explicitly.
- **3.5.7** **No silent denial of service:** the provider may not unilaterally throttle, suspend, or freeze Jeeb's API access without ≥ 24 hours notice except in clear AML / fraud / sanctions situations (§3.7).

### 3.6 KYB and onboarding terms

- **3.6.1** Jeeb SAL completes one-time provider KYB at MSA execution. Required documents enumerated up-front — typically: Sijill al-Tijari extract, MoF certificate, beneficial-owner declaration, audited statements (or auditor's letter for first-year), authorized signatories list.
- **3.6.2** Onboarding decision deadline: provider issues approve/reject decision within **15 business days** of receiving complete KYB pack. No open-ended review.
- **3.6.3** Reasonable refresh cadence (annual) explicit. No on-demand re-onboarding requests outside the annual cycle except for **specific material changes** (beneficial-owner change, control event, registered-address change).

### 3.7 AML, sanctions, and freezes

- **3.7.1** Provider warrants compliance with current Lebanese AML/CTF regime (Law 44/2015 successor regime as in force).
- **3.7.2** Provider's right to freeze a specific transaction on AML/sanctions suspicion is acknowledged. **Mandatory:** Jeeb is informed in writing within 24 hours of the freeze with the legally-permitted level of disclosure.
- **3.7.3** Provider may **not** freeze the operational account based on a single counterparty's frozen transaction without independent AML basis.
- **3.7.4** Sanctions screening lists (OFAC, UN, EU, Lebanese) covered by the provider; provider warrants no obligation flows back to Jeeb for sanctions screening of end-recipients beyond Jeeb's own KYC results.
- **3.7.5** No "broad-discretion" clauses. Provider's discretion to refuse a transaction must be tied to a defined basis (sanctions, AML, technical failure, KYC mismatch).

### 3.8 Data, privacy, audit

- **3.8.1** Jeeber recipient data shared with the provider (name, ID number, phone, payout method identifier) is processed under a written data-sharing addendum compliant with Law 81/2018 (Electronic Transactions and Personal Data) successor regime.
- **3.8.2** Provider commits to a defined retention period for transaction records, with secure deletion after expiry.
- **3.8.3** Audit right: Jeeb may, with 30 days notice and once per year, audit the provider's processing of Jeeb-supplied data, either on-site or via a Type-II SOC report at provider's option.
- **3.8.4** Breach notification: any data incident touching Jeeber data reported to Jeeb within 24 hours.

### 3.9 Dispute resolution

- **3.9.1** Disputed transactions (claimed-paid but not received; double-paid; wrong-recipient) escalated through a defined ladder with response-time commitments — Tier-1 ack within 1 business day, Tier-2 resolution within 5 business days, escalation to provider's executive sponsor at day 10.
- **3.9.2** No "all sales final" clauses for proven provider-side error.
- **3.9.3** Reasonable refund/reversal mechanics enumerated, including time limits.
- **3.9.4** Each provider names a primary commercial relationship manager.

### 3.10 Term, termination, exit

- **3.10.1** Initial term: 12 months. Auto-renewal for 12-month periods.
- **3.10.2** Termination for cause (material breach, AML investigation, bankruptcy event) effective immediately with written notice.
- **3.10.3** Termination for convenience by either party with 90 days written notice — **never less than 60 days**.
- **3.10.4** **Exit assistance.** On termination, provider runs out the in-flight transaction tail through final clearance and provides a complete data export to Jeeb (CSV + signed PDF reconciliation report) within 30 days. Provider may not suspend exit assistance for any reason short of court order.
- **3.10.5** **No exclusivity.** Jeeb retains the unconditional right to integrate competing providers in parallel.

### 3.11 Liability and indemnity

- **3.11.1** Liability cap defined — not less than 12 months of fees paid to the provider, **per claim** (not aggregate).
- **3.11.2** Carve-outs from the cap: provider gross negligence, willful misconduct, IP infringement, breach of confidentiality, AML/sanctions breach.
- **3.11.3** Mutual indemnity for third-party claims arising from each party's breach.

### 3.12 Governing law and forum

- **3.12.1** Governing law: Lebanese law.
- **3.12.2** Forum: Beirut courts. Mediation precedes litigation per a 30-day mediation clause.
- **3.12.3** Arbitration (e.g., Beirut Center for Arbitration) optional, founder decision per provider.

### 3.13 Confidentiality

- **3.13.1** Two-way confidentiality with standard 3-year survival post-termination.
- **3.13.2** Carve-outs: information already public, independently developed, required by law.

### 3.14 Insurance

- **3.14.1** Provider maintains cyber liability and professional indemnity insurance at amounts proportional to expected volume (counsel to set floor).
- **3.14.2** Certificate of insurance furnished annually.

## 4. Provider-specific overlays

### 4.1 OMT (Online Money Transfer S.A.L.)

- **4.1.1** Recipient pickup is via **OMT branch network + cash-pickup code**. Code expiry rules explicit (e.g., 7 days), and Jeeb's options if the recipient fails to collect (auto-reverse to Jeeb at no fee, or hold-and-prompt).
- **4.1.2** Counter-fee model — if the recipient (Jeeber) is charged a separate "collection fee" at the OMT counter, this MUST be disclosed in the MSA and the disclosure mirrored in the in-app earnings UX (FR-11.2 net-earnings line). Surprise fees on Jeebers cause platform-trust incidents.
- **4.1.3** Operating hours of the recipient-counter network defined; SLA in §3.5 adjusted accordingly.

### 4.2 Whish Money

- **4.2.1** Recipient identifier — Whish user ID / phone number — explicit. Validation API exposed by Whish so `unified_payment_gateway` can verify the recipient identifier before initiating a payout.
- **4.2.2** Whish-side recipient KYC level required (e.g., level-1 vs level-2) for the per-transaction amounts Jeeb expects to settle. Exceeded-limit handling explicit.
- **4.2.3** Webhook signature scheme (HMAC algorithm and key rotation) defined.

### 4.3 Primary commercial bank

- **4.3.1** Inter-bank transfer mechanism (in-bank, RTGS, ACH-equivalent) named. Settlement T+0 (same business day) for in-bank; T+1 for cross-bank — confirm with bank.
- **4.3.2** Per-day and per-transaction transfer limits enumerated. Jeeb must operate within the limit OR negotiate an explicit higher limit at MSA execution.
- **4.3.3** Account-protection terms — what conditions allow the bank to freeze Jeeb SAL's operational account, and notification process.
- **4.3.4** Multi-currency support — USD and LBP sub-accounts available; FX conversion terms per 3.4.
- **4.3.5** Cash management and reconciliation report cadence (daily statement file in a defined format) to feed `wallet-service` reconciliation jobs.

### 4.4 Secondary bank (failover)

- **4.4.1** Reduced-scope MSA — only outbound payouts to bank-banked Jeebers, not full operational account. Standby relationship.
- **4.4.2** Activation SLA — if primary bank fails over, secondary bank ready to begin processing within 5 business days.

## 5. Integration contract with `unified_payment_gateway`

The contractual terms above translate into the following integration-level requirements on `unified_payment_gateway` (Elixir). These are derivative of the MSAs, not separately negotiable.

| Integration concern | Source MSA clause | `unified_payment_gateway` obligation |
| --- | --- | --- |
| Transaction id uniqueness, idempotency key | 3.2.2 | Outbound API call carries a Jeeb-side idempotency key; provider must respect it for at least 24h |
| Webhook signature verification | 4.2.3 | HMAC + key rotation per provider |
| Transaction status state machine | 3.2.2 | `initiated → in_flight → completed | failed | reversed` mapped to each provider's verbiage |
| Reconciliation file ingestion | 4.3.5 | Daily settlement file ingested, reconciled against `wallet-service` ledger, mismatches alerted to Finance on-call |
| Retry policy | 3.5.4 | Exponential backoff on 5xx and on missing webhook for > 60s, capped at 24h |
| Audit log | 3.7.2, 3.8.4 | Append-only ledger of every transaction initiation and outcome, retained ≥ 10 years per [data-retention-policy.md](./data-retention-policy.md) |

## 6. Operational runbook touchpoints

These items should be wired into the on-call runbook before launch:

- Sev-1 contact tree per provider (after-hours included).
- Specific procedure for "freeze of a specific transaction" inbound notification.
- Specific procedure for "Jeeber claims paid but did not receive" dispute, including evidence pack to attach when escalating to the provider.
- Failover-to-secondary-bank procedure with explicit decision criteria.

## 7. Open questions for legal counsel

Each item below is a launch blocker.

1. **Money-transmitter classification** (parallels [business-entity-recommendation.md](./business-entity-recommendation.md) §5 item 1). Confirm the contracts above do not collectively re-characterize Jeeb SAL as a payment-services provider requiring BDL licensure.
2. **Stamp duty** on each MSA at execution — quantify cost.
3. **USD-denominated payouts** to Lebanese-resident recipients — confirm legality under in-force BDL Circular 151 / 161 successor regime.
4. **Data-sharing addendum form** — confirm content satisfies Law 81/2018 successor regime.
5. **Settlement-fail accounting** — confirm Lebanese VAT and CIT treatment of a reversed-but-fee-deducted transaction.

## 8. Cross-references

- Entity that signs these MSAs — [business-entity-recommendation.md](./business-entity-recommendation.md)
- Invoice template referencing settlement method — [commission-invoicing-template.md](./commission-invoicing-template.md) §2 field 22
- Tax treatment of provider fees (input VAT) — [commission-tax-obligations.md](./commission-tax-obligations.md) §3.3
- Settlement method election point — FR-10.4 (`../../jeeb-v2-non-tech-requirement/02-requirements.md`)
- Locked-in atlas policy: payments only via `unified_payment_gateway` — SessionStart context, Memory MCP
- Retention for transaction records — [data-retention-policy.md](./data-retention-policy.md)
