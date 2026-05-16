# Commission Invoicing Template — Weekly Jeeber Settlement

| Field | Value |
| --- | --- |
| Version | 1.0 (DRAFT) |
| Effective Date | TBD — gated by chartered accountant sign-off |
| Owner | Finance |
| Audience | Finance ops, chartered accountant, Backend (`wallet-service`, `jeeb-admin`) |
| Linked ticket | T-legal-003 |

> **Disclaimer.** This template is an engineering/finance-team interpretation of Lebanese Ministry of Finance invoicing requirements for VAT-registered SALs. It is **not** legal or tax advice. The chartered accountant (expert-comptable) engaged at incorporation must validate this template, sample-test a generated PDF, and sign off before the first live commission invoice is issued.

## 1. What this invoice is

Per **BR-2** and **BR-4**, the Jeeb platform commission is the only revenue Jeeb SAL collects from each delivery. The platform never custodies goods-cost money (BR-3). The commission accrues per-delivery and is **settled weekly** to one cumulative amount per Jeeber.

This template is the **commission invoice that Jeeb SAL issues to the Jeeber** (a B2B-style invoice — the Jeeber is treated as a self-employed service provider receiving a deduction on services rendered TO Jeeb, where Jeeb's commission is consideration for use of the platform).

Equivalently, this is a "Platform Services Invoice" from Jeeb to the Jeeber for the right to use the matching, routing, rating, and payments-orchestration platform.

It is **not** the same as:

- The **per-delivery digital receipt** issued to the Client at handover (FR-10.5) — that is a different document, owned by `delivery-service`, and is not a tax invoice; it itemizes goods cost + delivery fee + commission breakdown for transparency.
- A wage statement or NSSF payslip — Jeebers are not employees (see [business-entity-recommendation.md](./business-entity-recommendation.md) §5 open question 4).

## 2. Mandatory fields (Lebanese MoF invoice standard)

The Lebanese VAT Law (Law 379/2001 and successor amendments) and MoF circulars define mandatory fields on a "tax invoice" (`فاتورة ضريبية` / *facture fiscale*). The template below is the engineering interpretation of those requirements pending chartered-accountant validation.

| # | Field | Required | Notes |
| --- | --- | --- | --- |
| 1 | Invoice title | Yes | "Tax Invoice" / "فاتورة ضريبية" — must literally appear |
| 2 | Sequential invoice number | Yes | Strictly monotonically increasing, gap-free across the fiscal year. Cancellations use credit notes (§5), never gaps. |
| 3 | Issuance date | Yes | Settlement run timestamp, ISO-8601 (`2026-05-15`) |
| 4 | Issuer legal name | Yes | "Jeeb SAL" — registered name per Commercial Register |
| 5 | Issuer Commercial Register number (RC / Sijill al-Tijari) | Yes | From incorporation extract |
| 6 | Issuer MoF Taxpayer ID (TIN) | Yes | From MoF registration |
| 7 | Issuer VAT registration number | Yes (if VAT-registered) | If Jeeb is under the VAT threshold and not registered, this field is omitted and §4 VAT line drops out — see [commission-tax-obligations.md](./commission-tax-obligations.md) §3 |
| 8 | Issuer registered address | Yes | Beirut HQ, full street address |
| 9 | Recipient legal name | Yes | Jeeber's full legal name as on KYC-approved ID (`auth-service`) |
| 10 | Recipient TIN | Conditional | Required if Jeeber is VAT-registered (rare at MVP). Otherwise: Jeeber's National ID number, prefixed "ID:" to make the distinction explicit. |
| 11 | Recipient address | Yes | Jeeber's primary address as held in `auth-service` profile, OR "Lebanese Resident — Beirut Governorate" if no street address is on file |
| 12 | Recipient phone | Recommended | Jeeber's verified phone (E.164) |
| 13 | Service description | Yes | "Platform commission — week ending YYYY-MM-DD" + line-item count |
| 14 | Service period | Yes | Settlement week start/end dates (inclusive) |
| 15 | Itemized line items | Yes | One row per delivery in the settlement period — see §3 |
| 16 | Subtotal (commission ex-VAT) | Yes | Sum of all line-item commissions |
| 17 | VAT rate | Yes (if VAT-registered) | 11% per Law 379/2001 (subject to change — verify on each fiscal year start) |
| 18 | VAT amount | Yes (if VAT-registered) | Subtotal × VAT rate |
| 19 | Total amount due (incl. VAT) | Yes | Subtotal + VAT |
| 20 | Currency | Yes | "USD" or "LBP" — single currency per invoice. If a Jeeber's deliveries spanned USD and LBP pricing in one week, issue **two** invoices. |
| 21 | Payment terms | Yes | "Settled by deduction from Jeeber's earnings remitted on YYYY-MM-DD" or "Payable on receipt via OMT/Whish/bank transfer if earnings insufficient (BR-4)" |
| 22 | Settlement method | Yes | "OMT", "Whish Money", "Bank transfer to IBAN ending XXXX" — as elected by Jeeber per FR-10.4 |
| 23 | Withholding tax line | Conditional | If Lebanese counsel confirms 3% withholding applies to commission paid by company to self-employed individuals — see [commission-tax-obligations.md](./commission-tax-obligations.md) §5 — show as negative line. Open question, may be omitted in v1. |
| 24 | Net amount payable | Yes | Total − any withholding − offset against Jeeber's earnings receivable |
| 25 | Bilingual rendering | Recommended | Arabic + English side-by-side; primary legal text in Arabic per MoF convention |
| 26 | Issuer signature / stamp | Recommended | Digital signature acceptable; e-invoice future state per any in-force MoF e-invoicing mandate |

## 3. Line-item structure

One row per **delivered, OTP-confirmed** delivery (per BR-5; non-OTP-confirmed deliveries do not generate commission and therefore do not appear). Settlements are per ISO week, Monday 00:00 Asia/Beirut to Sunday 23:59 Asia/Beirut.

```
| # | Delivery ID | Date         | Tier      | Delivery fee | Commission rate | Commission |
|---|-------------|--------------|-----------|--------------|-----------------|------------|
| 1 | DLV-2026-…  | 2026-05-08   | Express   | USD 4.00     | 15%             | USD 0.60   |
| 2 | DLV-2026-…  | 2026-05-08   | Standard  | USD 3.00     | 12%             | USD 0.36   |
| 3 | DLV-2026-…  | 2026-05-09   | Eco       | USD 2.50     | 10%             | USD 0.25   |
| … |             |              |           |              |                 |            |
```

Constraints:

- **Tier** values are the FR-5 / BR-2 enum: Flash, Express, Standard, On-the-way, Eco.
- **Commission rate** must match the rate **in force at delivery time**, not the rate at invoice-generation time. `wallet-service` is the source of truth and stamps the rate onto the `delivery_commission_event` row.
- **Goods cost is never listed** on this invoice (BR-3). The platform does not invoice for goods cost.
- **Tips** (if implemented in any phase) are never listed — they bypass the platform.
- The Delivery ID column must be the same `delivery_id` shown to the Client on the digital receipt (FR-10.5), so a Jeeber or auditor can cross-reference.

## 4. Worked example

A Jeeber named *Karim Haddad*, Lebanese ID `XXXXXXX`, has completed 38 deliveries in the week ending Sunday 2026-05-10. The platform commission accrued is USD 9.42 (sum of per-delivery commissions). Jeeb SAL is VAT-registered. The Jeeber's election is settlement by deduction from earnings.

```
                            JEEB SAL
                  فاتورة ضريبية / TAX INVOICE

Invoice #             : INV-2026-000142
Issuance date         : 2026-05-12
Service period        : 2026-05-04 — 2026-05-10 (ISO week 19)

Issuer:
  Jeeb SAL
  RC (Sijill al-Tijari)  : 1234567 — Beirut
  MoF Taxpayer ID        : 1234567890
  VAT Reg. No.           : 1234567890-VAT
  Address                : [Registered Beirut HQ address]

Recipient (Service consumer):
  Karim Haddad
  ID: XXXXXXX (Lebanese National ID)
  Address: Lebanese Resident — Beirut Governorate
  Phone   : +961-X-XXXXXX

Description:
  Platform commission for delivery services performed via the Jeeb
  platform during the service period.  38 deliveries — see line items.

Line items: (38 rows — abbreviated for illustration)
  #1 DLV-2026-00001  2026-05-04  Express   USD 4.00  15%  USD 0.60
  #2 DLV-2026-00002  2026-05-04  Standard  USD 3.00  12%  USD 0.36
  …
  #38 DLV-2026-00038 2026-05-10  Eco       USD 2.50  10%  USD 0.25

Subtotal (commission, ex-VAT)        :    USD 9.42
VAT @ 11%                            :    USD 1.04
Total amount due                     :    USD 10.46
Withholding (3%, if applicable)      :  (USD 0.00)   — pending counsel confirmation
Net amount payable                   :    USD 10.46

Settlement method : Deduction from earnings remittance
                    scheduled 2026-05-12 (BR-4)
Payment terms     : Settled on receipt by netting against the
                    Jeeber's earnings receivable for the period.

Authorized signatory : [Digital signature — Jeeb SAL Finance Lead]
```

## 5. Credit notes and corrections

Invoices are **immutable** once issued. Corrections happen via credit notes.

| Scenario | Document issued | Numbering |
| --- | --- | --- |
| Delivery later refunded to Client (dispute resolution, BR-4 / FR-18) | Credit Note against original invoice | `CN-YYYY-NNNNNN`, separate sequence |
| Commission recalculated because rate config changed retroactively | Credit Note + new invoice | Original invoice stays; CN cancels disputed amount; new invoice issues at correct rate |
| Jeeber identity dispute on submitted invoice | Credit Note + re-issue under corrected counterparty | Original archived, audit trail preserved |

Gaps in the invoice number sequence are **prohibited**. If a draft invoice fails generation (system error), the system MUST issue a "void" record under that sequence number with zero amount, not skip it, so the chartered accountant can reconcile.

## 6. Storage, retention, and access

- **Issued invoice store.** Object storage, encrypted at rest (AES-256). PDF + canonical JSON twin per invoice. Path: `s3://jeeb-finance-archive/invoices/{YYYY}/{NNN}.pdf`.
- **Retention.** Minimum **10 years** from issuance date — per Lebanese commercial-records statute as interpreted in [data-retention-policy.md](./data-retention-policy.md). Confirmed by chartered accountant.
- **Access.** Read-only access for Finance role, chartered accountant role (delegated read with audit), and the issued-to Jeeber via the in-app earnings dashboard (FR-11.5: monthly PDF download).
- **Tamper evidence.** Each invoice PDF is hashed (SHA-256); hash committed to an append-only log row in `wallet-service` (`invoice_audit_log`).

## 7. Generation contract (engineering)

`wallet-service` owns invoice generation. Inputs and outputs are pinned here to make this template machine-implementable rather than a document-only artifact.

**Trigger.** Weekly cron at Monday 02:00 Asia/Beirut, generating the previous ISO-week settlement.

**Input.** Closed `delivery_commission_event` rows where `delivery.status == 'delivered'` (OTP-confirmed) and `service_week == prior_week`, grouped by `jeeber_user_id` and `currency`.

**Pre-flight validations (hard fail = no invoice issued).**

1. Jeeber's KYC status MUST be `approved` at the end of the service period (per FR-2.5).
2. Jeeber MUST have an active settlement method on file (FR-10.4 election).
3. The sum of line items MUST be > 0; otherwise no invoice is generated.
4. The commission rate stamped on each line item MUST be present and non-null.
5. No prior invoice for the same `(jeeber_user_id, service_week, currency)` triple may exist.

**Output.** A canonical JSON document conforming to a schema fixed by `wallet-service` (registered in `cross-repo-api-contracts` per `cross-repo-api-contracts` skill), rendered to PDF via the same template engine that produces the user-facing receipt (`delivery-service`).

**Idempotency.** Re-running the generator for the same `(jeeber_user_id, service_week, currency)` triple MUST be a no-op that returns the previously generated invoice.

**Audit log row.** Every generation writes `{invoice_id, jeeber_user_id, service_week, subtotal, vat, total, pdf_sha256, generated_by, generated_at}` to `invoice_audit_log`.

**Delivery to the Jeeber.** Push notification (FR-14.1: "Your weekly statement is ready") with deep link to the in-app PDF view (FR-11.5).

## 8. Open questions for chartered accountant

Each item below is a launch blocker for the first live invoice.

1. **Is "platform commission" the correct VAT classification, or does Lebanese practice classify this as an "electronic services" supply with a different rate or zero-rating regime?**
2. **Withholding tax on payments to self-employed Lebanese individuals** — Article 41 of the Income Tax Law touches 3% withholding on services. Does this apply when the company is the *invoicer* (not the payer) and the consideration is netted against an earnings receivable? Confirm direction-of-payment classification.
3. **Currency.** Are USD-denominated invoices acceptable for VAT-registered Lebanese SALs under the in-force MoF circulars, or must the LBP equivalent at official rate also appear on the face of the invoice?
4. **E-invoicing.** Is any MoF e-invoicing mandate in force at the time of incorporation that requires structured XML/UBL output beyond the PDF + JSON twin described in §7?
5. **Bilingual mandate.** Confirm whether Arabic-only is required for legal validity or whether bilingual is sufficient.

## 9. Cross-references

- Entity name and TIN that appears as issuer — [business-entity-recommendation.md](./business-entity-recommendation.md) §3.1
- Tax rates (VAT, withholding, CIT) referenced — [commission-tax-obligations.md](./commission-tax-obligations.md)
- Settlement methods enumerated — [settlement-provider-requirements.md](./settlement-provider-requirements.md)
- Underlying business rules — `../../jeeb-v2-non-tech-requirement/02-requirements.md` (BR-2, BR-3, BR-4, FR-10, FR-11)
- Retention — [data-retention-policy.md](./data-retention-policy.md)
- User-facing tax-language Terms reference — `../legal/terms-of-service.en.md`
