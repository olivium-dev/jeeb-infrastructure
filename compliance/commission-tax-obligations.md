# Tax Obligations — Platform Commission Income

| Field | Value |
| --- | --- |
| Version | 1.0 (DRAFT) |
| Effective Date | TBD — gated by chartered accountant sign-off |
| Owner | Finance |
| Audience | Founders, Finance, Chartered Accountant, Legal Counsel |
| Linked ticket | T-legal-003 |

> **Disclaimer.** This document is an engineering/operations summary of the Lebanese tax obligations expected to attach to Jeeb SAL's commission revenue. It is **not** tax advice. Rates and thresholds in this document reflect the law as the engineering team understood it during MVP planning; **every numeric value here MUST be re-verified by the engaged chartered accountant (expert-comptable) against the Ministry of Finance circulars in force at the time of incorporation** before the first invoice is issued or filing made.

## 1. Scope

Jeeb SAL's only revenue stream at MVP is the **platform commission** defined in BR-2 (a percentage of the delivery fee, never the goods cost). This document summarizes the tax obligations attaching to that revenue stream in Lebanon. Out of scope: founder personal taxation, employee payroll tax (no salaried employees at MVP launch — see §6), foreign-source revenue (none at MVP).

## 2. Tax types at a glance

| Tax | Approximate rate | Frequency | Filed with | Notes |
| --- | --- | --- | --- | --- |
| Value-Added Tax (VAT / TVA) | 11% (Law 379/2001 as amended) | Quarterly (simplified) or monthly | Ministry of Finance | Triggered above registration threshold — see §3 |
| Corporate Income Tax (CIT) | 17% on net profit (Law 144 amendments) | Annual | Ministry of Finance | Filed by 30 April for prior year |
| Distribution / Dividend tax | 10% on distributed dividends | At distribution | Ministry of Finance | Triggered only on dividends paid out |
| Withholding on payments to self-employed individuals | 3% (Article 41, Income Tax Law) | Monthly remit | Ministry of Finance | Open — may apply to Jeeber payouts. See §5 |
| Built Property Tax (BPT) on rented office | Per property regime | Annual | Ministry of Finance | Applies to Beirut HQ lease |
| NSSF (CNSS) employer contributions | ~23% of employee gross wage | Quarterly + annual | NSSF | Applies once Jeeb has employees (Jeebers are NOT employees) |
| Municipal trade license tax | Per Beirut municipality schedule | Annual | Beirut municipality | Standard for any commercial entity |
| Stamp duty | 4 per mille (typical) | Per contract execution | Ministry of Finance | Applies to settlement-provider MSAs, lease, etc. |

**All rates and thresholds in this table are subject to chartered-accountant confirmation against in-force MoF circulars.**

## 3. VAT (Value-Added Tax)

### 3.1 Registration threshold

Lebanese VAT registration is mandatory above an annual taxable-turnover threshold (historically LBP 100,000,000 across rolling four quarters; this threshold has been revised multiple times and **must** be confirmed by the chartered accountant against the current MoF circular). Below the threshold, voluntary registration is available.

**Recommendation.** Jeeb SAL should **register voluntarily for VAT at incorporation**, irrespective of whether the threshold will be crossed in year 1. Reasons:

1. The Beirut pilot is designed to reach commission-collection rates that will likely cross the threshold within the first 4–6 months. Pre-registration avoids a mid-year change-of-regime accounting event.
2. Settlement-provider counterparties (OMT, Whish, primary bank) prefer VAT-registered B2B counterparties because their own input-VAT claims rely on VAT-bearing invoices.
3. The user-facing receipt referenced in `commission-invoicing-template.md` §2 only carries the "Tax Invoice" title and VAT number if Jeeb is registered.

### 3.2 VAT on commission

Platform commission is treated as consideration for an electronic platform service supplied by Jeeb SAL to the Jeeber. Expected VAT treatment:

- **Standard-rated** at the prevailing rate (11% as of last verified MoF circular).
- VAT is added to the commission line on the weekly invoice (`commission-invoicing-template.md` §4 worked example).
- Output VAT is collected from the Jeeber via netting against the Jeeber's earnings receivable (BR-4) and remitted by Jeeb SAL to MoF.

**Key open item (chartered accountant).** Some jurisdictions treat "digital platform services consumed by a non-VAT-registered counterparty" with a different rate or with reverse-charge mechanics. Confirm Lebanese practice. If Jeebers (who are typically not VAT-registered themselves) cannot pass the VAT through, then the VAT is an **economic cost on the Jeeber's net earnings**, not a wash-through — and this must be communicated transparently in the in-app earnings dashboard (FR-11.2 net-earnings line).

### 3.3 Input VAT recovery

Jeeb SAL accumulates input VAT on:

- Cloud infrastructure invoiced from in-Lebanon providers (limited at MVP — most infra is foreign-supplier).
- Foreign-supplied cloud / SaaS — typically zero-VAT export-of-services from supplier side, no input VAT to recover, but a possible **reverse-charge VAT obligation** on the buyer. **Open item — confirm with accountant.**
- Lebanese office lease, utilities, professional services (legal, accounting).

Input VAT is offset against output VAT in each quarterly return. Net position is paid to MoF if positive, carried forward if negative.

### 3.4 Filing cadence

| Regime | Cadence | Due date |
| --- | --- | --- |
| Standard | Quarterly | 20th of month following quarter end |
| Large taxpayer | Monthly | 20th of following month |

Jeeb SAL at MVP scale is expected to qualify for the quarterly regime.

## 4. Corporate Income Tax (CIT)

### 4.1 Rate and base

- **Rate.** 17% on net taxable profit (post Law 144 amendments; chartered accountant to confirm the rate in force on incorporation).
- **Base.** Net profit per Lebanese GAAP, with statutory add-backs (non-deductible expenses, related-party transactions outside arm's length, etc.).
- **Loss carry-forward.** Available for 3 fiscal years subsequent to the loss year (chartered accountant to verify current rule).

### 4.2 Filing and payment

- **Annual return.** Due 30 April for prior fiscal year (calendar year aligned per [business-entity-recommendation.md](./business-entity-recommendation.md) §3.1).
- **Provisional installments.** Lebanese practice involves provisional CIT installments paid during the fiscal year against expected liability. Schedule and percentages — confirm with chartered accountant.
- **Settlement.** Balance settled with annual return.

### 4.3 Year-1 expectation

The Beirut pilot is unlikely to generate a CIT-paying profit in year 1 due to capex (incorporation, legal, infrastructure, marketing). The CIT return still **must be filed** annually, even for a loss-making year. Failure to file triggers MoF penalties even when no tax is owed.

## 5. Withholding tax on Jeeber payouts (open item)

This is the single **largest open tax question** affecting MVP launch.

### 5.1 The question

Article 41 of the Income Tax Law imposes a 3% withholding on payments made by Lebanese companies to self-employed Lebanese individuals for services rendered to the company. The question is whether each Jeeber's weekly settlement (FR-10.4) is in scope.

The settlement flow nets two opposing flows:

- **From Jeeber to Jeeb:** Platform commission earned in the week.
- **From Jeeb to Jeeber:** None at MVP — Jeeb does not custody the goods-cost reimbursement money (BR-3). The Client pays the Jeeber directly in cash at handover (FR-10.2).

If Jeeb never pays cash to the Jeeber, Article 41 may be inapplicable: the platform-commission invoice (`commission-invoicing-template.md`) is a *receivable on the Jeeber*, not a payment from Jeeb to the Jeeber.

But Lebanese law historically taxes the **service performed** rather than the direction of cash flow. The Jeeber's services to Jeeb (use of identity, vehicle, time to perform deliveries on the platform's behalf) may still trigger withholding.

### 5.2 Possible outcomes and platform implications

| Counsel finding | Platform implication |
| --- | --- |
| **No withholding applies** (Article 41 inapplicable to pure netting arrangement) | Invoice template per §4 of `commission-invoicing-template.md` stands as-is. No withholding line. |
| **3% withholding on commission consideration applies, payable by Jeeb** | Commission invoice grosses up by 3% withholding (Jeeb retains the 3% and remits monthly to MoF). Withholding line appears on every invoice. `wallet-service` calculates and reports monthly. |
| **Withholding applies but on Jeeber's gross earnings (not just commission)** | Material change — would require Jeeber to opt into a tax regime and Jeeb to issue a Form 2074-equivalent annual statement to each Jeeber summarizing income and withholding. Significant scope. |

The MVP design assumes **option 1 (no withholding)**, on the engineering interpretation that the platform is a non-custodial marketplace. **This assumption must be validated with counsel before launch.** The fallback (option 2) is engineering-feasible but requires invoice-template and `wallet-service` changes.

## 6. NSSF — National Social Security Fund (CNSS)

### 6.1 Jeeb SAL employer registration

Per [business-entity-recommendation.md](./business-entity-recommendation.md) §4, NSSF registration is required even if Jeeb has no salaried staff at MVP. The registration carries a near-zero ongoing obligation until the first hire.

### 6.2 Jeebers are not employees

The deliberate design of Jeeb's Jeeber relationship is **independent contractor** (self-employed natural person), not employee. The platform:

- Does not set fixed working hours (FR-19 availability toggle).
- Does not require exclusivity.
- Does not provide tools (Jeebers use their own vehicle, phone, fuel).
- Pays no fixed wage.
- Has no subordination clause in Terms of Service.

**Risk.** Lebanese labor courts (and labor inspectors) can re-characterize a gig-economy relationship as employment if the indicia point that way — long-term continuous service, de facto schedule, platform-imposed pricing (BR-2). If re-characterized, Jeeb SAL would owe NSSF employer contributions retroactively (~23% gross), and possibly Article 8/9 indemnities.

**Mitigation.**

1. Terms of Service explicitly states the contractor relationship (already drafted in `../legal/terms-of-service.en.md`).
2. Onboarding contract with each Jeeber is a services-provision contract, not an employment contract.
3. Platform avoids features that look like employment (no minimum-hours requirement, no platform-imposed pricing — commission is on a freely-set delivery-fee offer per FR-4 / FR-5).
4. Quarterly review by chartered accountant + counsel of the de facto pattern of work against the de jure framing.

## 7. Tax compliance calendar

Maintained by Finance, owned by chartered accountant.

| Month | Filing |
| --- | --- |
| Jan | VAT Q4 (prior year) by 20th; annual NSSF declaration |
| Feb | — |
| Mar | — |
| Apr | CIT annual return by 30th; VAT Q1 by 20th |
| May | — |
| Jun | — |
| Jul | VAT Q2 by 20th |
| Aug | — |
| Sep | — |
| Oct | VAT Q3 by 20th |
| Nov | — |
| Dec | — |

Withholding remittances (if applicable per §5) are **monthly**, due by the 15th of the following month.

## 8. Estimated year-1 cash-tax envelope

For founder-level financial planning only. **Not a forecast.** Conservative assumption that the pilot reaches the BR-2 commission run-rate by Q3.

| Tax | Year-1 expected cash impact |
| --- | --- |
| VAT (net to MoF after input recovery) | Cash-positive to neutral (mostly netted) |
| CIT | Near zero — likely loss-making year |
| Withholding (if Article 41 applies) | 3% of commission, monthly remittance |
| NSSF | Near zero — no salaried staff at MVP |
| Municipal trade license | Small (one-time annual fee) |
| Stamp duty | One-time on each executed contract |

The realistic Year-1 financial exposure is **withholding remittance** if Article 41 applies — operationally significant (monthly), even if numerically small.

## 9. Penalty and audit posture

Lebanese MoF penalties for late filing and underpayment include:

- Late-filing fixed penalty per filing missed.
- Late-payment interest (per current MoF rate schedule).
- 50%+ additional penalties for under-declaration discovered on audit.
- Criminal exposure for willful under-declaration.

**Operational posture.** Jeeb SAL files **every** filing on time, even if zero, from incorporation forward. Penalty avoidance dominates the cost-of-compliance calculus at MVP scale.

## 10. Open questions for chartered accountant

Each item below is a launch blocker.

1. Confirm current **VAT rate and registration threshold** against the MoF circular in force at incorporation date.
2. Confirm current **CIT rate** and any sector-specific incentives (digital economy, post-2024 reform packages, if any in force).
3. Resolve the **withholding-on-Jeeber-payouts question** (§5).
4. Confirm the **reverse-charge VAT** position for foreign cloud and SaaS inputs (§3.3).
5. Confirm whether **USD-denominated tax filings** are permitted, or whether all MoF returns must be in LBP at official rate as of filing date.
6. Confirm **provisional CIT installment schedule** applicable to a first-year SAL.
7. Confirm **stamp duty** applicability and rate on the settlement-provider MSAs to be signed.

## 11. Cross-references

- Entity that pays these taxes — [business-entity-recommendation.md](./business-entity-recommendation.md)
- Invoice template carrying VAT/withholding lines — [commission-invoicing-template.md](./commission-invoicing-template.md)
- Settlement providers (whose fees may carry input VAT) — [settlement-provider-requirements.md](./settlement-provider-requirements.md)
- Underlying commission rules — `../../jeeb-v2-non-tech-requirement/02-requirements.md` (BR-2, BR-3, BR-4, FR-10)
- Launch checklist — [compliance-checklist-beirut-pilot.md](./compliance-checklist-beirut-pilot.md)
