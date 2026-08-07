# Commission Invoice Template (Lebanon, Bilingual AR/EN)

> **Status:** DRAFT v0.1 — final format must be validated by a LACPA-registered
> CPA against the MoF VAT decision in force at go-live (currently MoF Decision
> 644/2003 as amended). Sequential numbering, Arabic primacy, and TVA/VAT
> breakdown are non-negotiable.

## 1. Mandatory fields under Lebanese MoF rules

Per Law 379/2001 (VAT) and MoF Decision 644/2003 every invoice issued by a
VAT-registered taxable person MUST contain the following — failure to display
any single field invalidates the invoice for input-VAT purposes and exposes
the issuer to a penalty under Law 379/2001 Art. 41:

1. The word `فاتورة` / "Invoice" displayed prominently.
2. A **sequential serial number** with no gaps, per fiscal year, per series.
3. **Issue date** in dd/mm/yyyy format.
4. Issuer (Jeeb SAL):
   - Full legal name in Arabic and Latin script.
   - Commercial Register number (`رقم السجل التجاري`).
   - MoF financial number (`الرقم المالي` / Tax ID).
   - VAT number (`رقم التسجيل في الـ TVA`).
   - Registered office address (Lebanese physical address).
5. Recipient (Jeeber or Merchant):
   - Full legal name.
   - MoF financial number if VAT-registered; national ID number otherwise.
   - Address.
6. **Description of the taxable supply** — for Jeeb this is *"عمولة منصة
   الوساطة الرقمية عن الفترة …"* / "Digital intermediation platform
   commission for period …".
7. Period covered (start/end date) for recurring commission invoices.
8. Quantity / unit (for commission: number of completed orders).
9. Unit price excluding VAT (HT / `قبل الضريبة`).
10. Total excluding VAT.
11. **VAT rate (currently 11%)** and VAT amount.
12. Total including VAT (TTC / `بعد الضريبة`) — in **LBP**; foreign-currency
    equivalent shown for information only.
13. Withholding-tax notice when paying a non-VAT-registered service provider
    (reverse invoice case).
14. Currency exchange reference rate (BdL middle rate of issue date) if any
    line is denominated in a foreign currency.
15. Payment terms and bank account details.
16. Issuer signature (electronic signature compliant with Law 81/2018 is
    acceptable for B2B platform invoices).

## 2. Bilingual template — Jeeb → Jeeber (or Merchant)

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          فاتورة عمولة  /  COMMISSION INVOICE              │
├───────────────────────────────────────────────────────────────────────────┤
│  المُصدر / Issuer                                                          │
│  جيب ش.م.ل. / Jeeb SAL                                                     │
│  السجل التجاري / CR No.        : [CR-XXXXX] Beirut                         │
│  الرقم المالي / MoF Tax ID     : [XXXXXXX]                                 │
│  رقم التسجيل في الـ TVA / VAT  : [XXXXXXX-601]                             │
│  العنوان / Address             : [Street, Building, Beirut, Lebanon]       │
│  هاتف / Phone                  : +961 X XXX XXX                            │
│  بريد إلكتروني / Email         : finance@jeeb.app                          │
├───────────────────────────────────────────────────────────────────────────┤
│  العميل / Recipient                                                        │
│  الاسم / Name                  : [Jeeber / Merchant legal name]            │
│  الرقم المالي/الهوية / Tax-ID  : [XXXXXXX] أو رقم هوية وطنية              │
│  العنوان / Address             : [Address]                                 │
├───────────────────────────────────────────────────────────────────────────┤
│  رقم الفاتورة / Invoice No.    : JEEB-COMM-YYYY-NNNNNN                     │
│  تاريخ الإصدار / Issue Date    : DD/MM/YYYY                                │
│  الفترة / Period               : DD/MM/YYYY → DD/MM/YYYY                   │
│  العملة / Currency             : LBP (USD shown for reference only)        │
│  سعر صرف مرجعي / FX rate (BdL) : 1 USD = [BdL middle rate] LBP             │
├───────────────────────────────────────────────────────────────────────────┤
│  البيان / Description                                                      │
│  عمولة منصة الوساطة الرقمية عن [N] طلبات منجزة                              │
│  Digital intermediation platform commission for [N] completed orders       │
├───────────┬──────────┬──────────────┬──────────────┬─────────────────────┤
│ الكمية /  │ سعر الوحدة│ الإجمالي قبل  │ ض.ق.م 11% /  │ الإجمالي بعد        │
│ Quantity  │ Unit price│ الضريبة /     │ VAT 11%      │ الضريبة /            │
│           │ (LBP HT)  │ Subtotal HT   │              │ Total TTC            │
├───────────┼──────────┼──────────────┼──────────────┼─────────────────────┤
│   [N]     │ [unit]   │ [subtotal]   │ [vat]        │ [total]              │
└───────────┴──────────┴──────────────┴──────────────┴─────────────────────┘

شروط الدفع / Payment terms : net 30 days from issue date, by SWIFT or local
                              wire to the account below.

تفاصيل الحساب البنكي / Bank details :
  Beneficiary    : Jeeb SAL
  Bank           : [bank name]
  IBAN           : LB[XX XXXX XXXX XXXX XXXX XXXX XXXX]
  SWIFT/BIC      : [XXXXLBBX]

في حال كان المتلقي غير مسجل في الـ TVA، تُقتطع ضريبة الخدمات 7.5% (قانون
497/2003) من قبل المُصدر وتُورّد إلى الخزينة شهرياً.
If the recipient is not VAT-registered, a 7.5% withholding on services
(Law 497/2003) is withheld at source by Jeeb and remitted monthly to MoF.

التوقيع / Signature : ____________________________
(توقيع إلكتروني وفق القانون 81/2018 / e-signed per Law 81/2018)
```

## 3. Numbering scheme

- Format: `JEEB-COMM-YYYY-NNNNNN`
  - `YYYY` — fiscal year (resets each Jan 1).
  - `NNNNNN` — strictly monotonic per series, no gaps. Voided invoices keep
    their number and are marked `ملغاة / VOID`; reissue with the next number.
- Storage: every PDF + JSON representation archived for **10 years**
  (Commercial Code Art. 12). The durable COD settlement and reconciliation
  records in UPG are authoritative; the invoice PDF is a derived finance view.

## 4. Edge cases & special invoices

| Case                                             | Invoice variant                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Recipient is VAT-exempt (e.g. diplomatic mission)| Omit VAT line, add exemption reference (decision number).                                  |
| Cross-border recipient (export of services)      | Zero-rated VAT under Law 379/2001 Art. 17; show "VAT 0% — export of services".             |
| Manual reimbursement or invoice correction      | After reviewed COD dispute resolution, issue `JEEB-CN-YYYY-NNNNNN` referencing the original invoice, with negative amounts. No automated refund or card-chargeback flow exists. |
| Multi-currency invoice                           | Primary amounts in LBP; foreign currency shown in brackets; BdL middle rate on issue date. |
| Settlement-net invoicing (we deduct commission)  | Issue commission invoice + a separate **payout statement** documenting the net transfer.   |

## 5. e-Invoicing posture

Lebanon has no mandatory e-invoicing regime at the document date. Jeeb's
internal posture:
- Issue PDF + machine-readable JSON for every invoice.
- Apply qualified e-signature (Law 81/2018) so the invoice is admissible in
  court without paper original.
- Archive in immutable S3-compatible storage with object-lock for 10 years.
- When/if MoF mandates a real-time clearance model (under discussion in the
  2026 budget), the invoice generator will switch to the clearance flow
  without changing UPG's authoritative COD settlement contract.

## 6. References

- Law 379/2001 (VAT) and its implementing decisions, esp. Decision 644/2003.
- Law 497/2003 (withholding on services).
- Commercial Code Art. 12 (10-year retention of commercial books).
- Law 81/2018 on electronic transactions and personal data.
- MoF e-services portal documentation (latest VAT bracket version).
