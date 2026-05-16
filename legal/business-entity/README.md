# Jeeb — Business Entity & Commission Collection Pack (Lebanon)

This directory contains the legal-and-financial setup material for Jeeb as the
platform operator collecting commissions in Lebanon. Scope: entity choice,
invoicing format, tax posture, and settlement-provider contracting.

> **Status:** DRAFT v0.1 — pending review by qualified Lebanese counsel
> (Beirut Bar Association) AND a Lebanese certified public accountant
> registered with the Lebanese Association of Certified Public Accountants
> (LACPA). These drafts establish structure and defaults; final figures,
> registration numbers, and clause wording MUST be confirmed before the
> Beirut pilot opens to end users.

## Documents

| Document                                                                                         | Purpose                                                                          |
| ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| [entity-recommendation-lebanon.md](./entity-recommendation-lebanon.md)                           | Recommended legal entity (SAL) with rationale, alternatives, registration steps  |
| [commission-invoice-template.md](./commission-invoice-template.md)                               | Bilingual commission-invoice template + mandatory fields under MoF requirements  |
| [tax-obligations-commission-income.md](./tax-obligations-commission-income.md)                   | Tax summary covering corporate income tax, VAT, withholding, NSSF, stamp duty    |
| [settlement-provider-contract-requirements.md](./settlement-provider-contract-requirements.md)   | Mandatory clauses for the PSP/acquirer/aggregator contract                       |

## How this fits the platform

- **Commission** is the fee Jeeb charges Jeebers (and where applicable,
  Merchants) for matching them with Clients. Commission is the platform's
  primary revenue line; the underlying delivery/service price is the
  Jeeber's revenue, not Jeeb's.
- **Settlement** is the money flow from Client → PSP → Jeeb's collection
  account → split → Jeeber payout + Jeeb commission retention. This pack
  defines the legal-and-tax envelope around that flow; the technical flow
  lives in `unified_payment_gateway`.
- Commission collection is performed exclusively by Jeeb the platform
  operator. Jeebers are NEVER employees; payouts to Jeebers are contractor
  payments, not wages (see `terms-of-service.md` §Independent Contractor).

## Regulatory & professional authorities referenced

- **Lebanese Commercial Code** (Decree-Law 304/1942 as amended) — governs
  joint-stock companies (SAL) and limited-liability companies (SARL).
- **Ministry of Finance — Tax Department / `وزارة المالية`** — corporate
  income tax (Decree-Law 144/1959), VAT (Law 379/2001), withholding tax
  (Law 497/2003 and successors), stamp duty (Decree-Law 67/1967).
- **National Social Security Fund (NSSF) / `الصندوق الوطني للضمان الاجتماعي`** —
  Decree-Law 13955/1963; relevant only for Jeeb's own employees, NOT for
  Jeebers (who are contractors).
- **Banque du Liban (BdL) / `مصرف لبنان`** — Basic Circulars 69, 81, 83
  govern payment service providers and any aggregator settling commissions.
- **Commercial Register / `السجل التجاري`** at the relevant
  Commerce-and-Companies court (Beirut Court for the Beirut pilot).

## Change process

1. Open a PR against `main` titled `legal(business-entity): <document> v<old>→v<new>`.
2. Tag `@olivium-dev/legal`, `@olivium-dev/finance`, and
   `@olivium-dev/compliance` as reviewers.
3. Any change to tax rates, invoicing format, or PSP requirements requires
   sign-off from the Compliance Officer **and** the company's external tax
   advisor (LACPA-registered CPA).
4. Once merged, update the live PSP contract draft in
   `legal/contracts/psp-master-agreement.md` and refresh the finance runbook
   in `deploy/finance/`.
