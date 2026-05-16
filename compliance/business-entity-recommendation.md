# Business Entity Recommendation — Jeeb Lebanon Operations

| Field | Value |
| --- | --- |
| Version | 1.0 (DRAFT) |
| Effective Date | TBD — gated by Lebanese legal counsel sign-off |
| Owner | Finance + Legal |
| Audience | Founders, Finance, Legal Counsel, Banking Partners |
| Linked ticket | T-legal-003 |

> **Disclaimer.** This document is an engineering/operations interpretation of Lebanese commercial-law options for the Jeeb platform. It is **not** legal advice. The recommendation below must be validated by a licensed Lebanese lawyer (avocat-conseil inscrit au barreau) and a registered chartered accountant (expert-comptable) before any incorporation step is executed.

## 1. Why an entity is required before launch

The Jeeb platform commission model (BR-2, BR-4, FR-10.3) generates **commercial revenue from Lebanese-resident Jeebers** in Lebanese territory. To lawfully:

- Invoice that commission (T-legal-003 AC-2),
- Open a corporate bank account capable of receiving OMT / Whish Money / inter-bank settlements (FR-10.4),
- Register for VAT and corporate income tax with the Lebanese Ministry of Finance (T-legal-003 AC-3),
- Sign settlement-provider master agreements (T-legal-003 AC-4),
- Sign user-facing contracts (Terms of Service party identification),

Jeeb must operate through a **registered Lebanese commercial entity** before the Beirut pilot accepts a single live delivery for paid commission.

Operating commissioned activity in Lebanon as an unregistered or foreign-only entity exposes founders to personal tax liability, criminal exposure under the Commercial Code, and immediate rejection by any Lebanese bank during account opening due-diligence.

## 2. Entity options considered

The following Lebanese vehicles were evaluated against five criteria: shareholder liability, capitalization burden, governance overhead, banking acceptance, and ability to scale to investor rounds.

### 2.1 Société Anonyme Libanaise (SAL) — "Lebanese joint-stock company"

| Attribute | Value |
| --- | --- |
| Governing law | Lebanese Code of Commerce, Articles 76–215 |
| Minimum capital | LBP 30,000,000 (nominal — at official rate; effectively very low in USD terms but bankers typically expect USD-equivalent funding evidence) |
| Minimum shareholders | 3 |
| Liability | Limited to capital contribution |
| Board | Board of Directors required (min. 3, max. 12) |
| Auditor | Statutory auditor mandatory |
| Annual filings | Audited financial statements, AGM minutes filed with Commercial Register |
| Investor friendliness | High — shares freely transferable, standard for VC term sheets |
| Banking acceptance | High — preferred form for B2B commercial activity |

### 2.2 Société à Responsabilité Limitée (SARL) — "Lebanese limited-liability company"

| Attribute | Value |
| --- | --- |
| Governing law | Lebanese Code of Commerce, Articles 216–245 |
| Minimum capital | LBP 5,000,000 |
| Minimum shareholders | 3 (no single-member SARL in Lebanon) |
| Maximum shareholders | 20 |
| Liability | Limited to capital contribution |
| Governance | Single manager (gérant) sufficient; no board required |
| Auditor | Not statutorily required below LBP 1bn capital |
| Annual filings | Manager's report + AGM minutes |
| Investor friendliness | Medium — share transfers require unanimous consent unless bylaws override |
| Banking acceptance | Medium — accepted but banks scrutinize gérant authority |

### 2.3 Offshore (Article 1 of Decree-Law No. 46/1983)

Not applicable. An offshore company may **not** conduct commercial activity inside Lebanese territory, which is exactly what Jeeb does (intra-Lebanon B2C commissioned deliveries). Disqualified.

### 2.4 Foreign-parent + Lebanese branch (succursale)

A foreign parent (e.g., Delaware Inc., DIFC, ADGM) can register a branch with the Lebanese Commercial Register and operate commercially. This is viable but has two practical drawbacks for the MVP:

- Branches are taxed as Lebanese permanent establishments — same VAT and CIT exposure as a local SAL but with higher accounting complexity (parent + branch consolidation).
- Lebanese banks have historically applied more rigorous KYC/source-of-funds review to branches than to locally incorporated SALs.

Deferred to Phase-2 if/when an offshore investor mandates a foreign holding structure.

### 2.5 Sole proprietorship (commerçant individuel)

Disqualified. Unlimited personal liability, no protection of founder personal assets against platform liabilities (delivery accidents, prohibited-items violations, settlement defaults). Also not investable.

## 3. Recommendation

**Incorporate Jeeb operations as a Société Anonyme Libanaise (SAL)** with the following parameters.

### 3.1 Proposed parameters

| Parameter | Recommendation | Rationale |
| --- | --- | --- |
| Legal name (registered) | "Jeeb SAL" or "Jeeb Lebanon SAL" (subject to name-availability search at the Commercial Register) | Brand alignment; "SAL" suffix mandatory by Article 79 |
| Trade name (user-facing) | "Jeeb" | Used on user-facing branding (`legal/terms-of-service.en.md`) |
| Capital | USD 50,000 equivalent (LBP at fresh-money rate at incorporation date) | Above the LBP 30M minimum; signals seriousness to bankers and KYB-running settlement providers |
| Capital paid up at incorporation | 100% (Lebanese practice prefers full payment; partial payment is legal but slows banking) | Smooths corporate-account opening |
| Shareholders at incorporation | Minimum 3 (founders + nominee if necessary; investor-friendly structure) | Statutory minimum |
| Object clause | "Operation of a digital platform connecting clients and delivery agents; collection of platform commission; ancillary technology services" | Narrow enough to defend non-money-transmitter classification (see §5); broad enough to scope wallet/Phase-2 |
| Registered office | Beirut (pilot region); ideally a real coworking-grade address with mail handling, not a virtual office | Mandatory for Commercial Register; banks reject PO-box addresses |
| Board of Directors | 3 members at incorporation (founder-CEO, founder-CTO, independent or investor director) | Statutory minimum; aligns with future VC governance |
| Chairman / General Manager | Single person preferred at MVP stage | Lebanese banks default to single signatory at onboarding |
| Statutory auditor | Appointed at incorporation (mandatory for SAL) | Required for AGM-1 |
| Fiscal year | 1 January – 31 December | Aligns with Lebanese tax filing calendar (April CIT, monthly VAT) |
| Reporting currency | USD (with LBP statutory presentation as required by MoF) | Operational reality; required by USD-pricing partners |

### 3.2 Why SAL over SARL

The SARL has lower capital requirements and lighter governance, which is attractive for a 3-founder MVP. We still recommend SAL because:

1. **Investor optionality.** Every VC term sheet for a Lebanese tech company assumes SAL. Converting SARL → SAL mid-round is possible but burns 4–8 weeks of legal time and notarization cost that an MVP team cannot afford to spend at the exact moment of fundraising.
2. **Share transfer mechanics.** SAL shares are freely transferable subject to the bylaws; SARL part transfers require explicit shareholder approval, which is hostile to ESOP and to bridge financing.
3. **Banking optics.** Lebanese banks treat SAL applicants more favorably during account opening because audited statements are statutorily mandatory.
4. **Commission counterparty credibility.** OMT, Whish Money, and bank wire counterparties prefer to contract with audited SAL entities for B2B settlement volume (T-legal-003 AC-4).
5. **The capital delta is not the bottleneck.** USD 50k of incorporated capital is a recoverable working-capital float, not sunk cost.

The SAL choice should be revisited only if Lebanese legal counsel identifies a current restriction (e.g., banking-sector capital injection moratorium, BDL circular limiting fresh-money incoming wires for capitalization) that makes SAL capitalization infeasible at the time of incorporation. The fallback in that case is SARL, with a planned conversion to SAL at the Series-A.

## 4. Incorporation roadmap (target: 8 weeks pre-launch)

| Week | Step | Owner | Output |
| --- | --- | --- | --- |
| W-8 | Engage Lebanese legal counsel + chartered accountant | Founders | Engagement letters |
| W-7 | Name availability search at Commercial Register | Legal counsel | Name reservation receipt |
| W-7 | Draft articles of incorporation (bylaws) — bilingual Arabic / French / English | Legal counsel | Draft bylaws |
| W-6 | Founders sign bylaws before a Notary Public | Legal counsel + notary | Notarized deed |
| W-6 | Deposit capital in escrow account at chosen Lebanese bank | Founders + bank | Bank capital-deposit certificate |
| W-5 | File at the Commercial Register (Beirut) | Legal counsel | Commercial Register extract (Sijill al-Tijari) |
| W-4 | Register at the Ministry of Finance (MoF) — obtain Taxpayer ID | Chartered accountant | MoF registration certificate + RC number |
| W-4 | VAT registration (if revenue forecast > LBP 100M / 4 quarters — see [commission-tax-obligations.md](./commission-tax-obligations.md) §3) | Chartered accountant | VAT certificate |
| W-3 | Register with National Social Security Fund (NSSF / CNSS) — required even if no salaried staff yet | Chartered accountant | NSSF employer number |
| W-3 | Open operational bank account (separate from capital-deposit account) | Founders + bank | Operational IBAN |
| W-2 | Register with Ministry of Labor (Beneficial Owner declaration under Law 75/2016) | Legal counsel | Filing acknowledgement |
| W-2 | Sign settlement-provider master agreements (OMT, Whish, primary bank — see [settlement-provider-requirements.md](./settlement-provider-requirements.md)) | Founders + legal | Signed MSAs |
| W-1 | First test invoice issued under new entity (commission settlement dry-run) | Finance | Invoice #1 archived |
| W-0 | Beirut pilot launches | All | Live commission collection |

This 8-week critical path is the **primary risk** of the Beirut pilot launch date and should be tracked as a launch-blocker in `compliance-checklist-beirut-pilot.md`.

## 5. Open questions for legal counsel (launch blockers)

The following are explicit asks for the engaged Lebanese legal counsel. Each is a launch-blocker until answered.

1. **Money-transmitter classification.** Does the Jeeb commission flow — where the platform deducts commission from a Jeeber's settlement payout but never custodies goods-cost money (BR-3) — require a license under BDL Basic Circular 69 (Payment Services) or any successor BDL circular in force on the incorporation date? The non-custodial design is deliberate to avoid this license. **Counsel must confirm the design holds under current BDL guidance.**
2. **Foreign-currency commission billing.** May commission invoices be denominated and settled in USD given the post-2019 multi-rate regime, BDL Circular 151 / 161 successor regime, and any in-force capital-control measures, without triggering a Lebanese-Pound conversion obligation?
3. **Beneficial-owner disclosure regime.** Confirm current Law 75/2016 amendments and any post-FATF-grey-list (2023+) reporting cadence for ultimate beneficial owners.
4. **Withholding on Jeeber payouts.** Are the weekly settlements paid to Jeebers (FR-10.4) classified as (a) reimbursements (no withholding), (b) self-employed contractor payments (3% withholding on services rendered to companies, per Article 41 of Income Tax Law — to be confirmed), or (c) something else? This drives whether Jeeb must withhold and remit per FR-10.4 settlement. See [commission-tax-obligations.md](./commission-tax-obligations.md) §5.
5. **Data Controller registration.** Does Law 81/2018 require a Data Controller declaration to the Ministry of Economy and Trade for Jeeb operations (parallels the open item already in `README.md`)?

## 6. Recurring annual obligations after incorporation

Tracked centrally; finance owner runs this calendar.

| Obligation | Cadence | Owner |
| --- | --- | --- |
| VAT return | Quarterly (for SALs under the simplified regime) — see [commission-tax-obligations.md](./commission-tax-obligations.md) §3 | Chartered accountant |
| Corporate Income Tax (CIT) declaration | Annual, by 30 April for prior year | Chartered accountant |
| Audited financial statements | Annual, by AGM (within 6 months of year-end) | Statutory auditor |
| AGM minutes filing at Commercial Register | Annual | Legal counsel |
| NSSF employer declaration | Quarterly + annual | Chartered accountant / HR |
| Beneficial-owner update | On any change + annual confirmation | Legal counsel |
| Commercial Register renewal | Per current MoF/Commerce schedule | Chartered accountant |
| Trade license renewal (Beirut municipality) | Annual | Operations |

## 7. Cross-references

- Commission invoicing template — [commission-invoicing-template.md](./commission-invoicing-template.md)
- Tax obligation summary — [commission-tax-obligations.md](./commission-tax-obligations.md)
- Settlement provider contractual requirements — [settlement-provider-requirements.md](./settlement-provider-requirements.md)
- Launch checklist — [compliance-checklist-beirut-pilot.md](./compliance-checklist-beirut-pilot.md)
- Commission business rule — `../../jeeb-v2-non-tech-requirement/02-requirements.md` (BR-2, BR-3, BR-4, FR-10)
- User-facing Terms of Service (Jeeb SAL named as contracting party) — `../legal/terms-of-service.en.md`
