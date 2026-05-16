# Legal Entity Recommendation — Jeeb (Lebanon Operations)

> **Status:** DRAFT v0.1 — for review by Lebanese counsel (Beirut Bar) and a
> LACPA-registered CPA. Do not register without final professional sign-off.
> All cited statutes refer to Lebanese law as in force on the document date.

## 1. Recommendation

Incorporate **Jeeb SAL** (`شركة جيب ش.م.ل.` — Société Anonyme Libanaise /
Joint-Stock Company) under the Lebanese Commercial Code (Decree-Law 304/1942
as amended), registered with the Beirut Commercial Register
(`السجل التجاري — بيروت`).

## 2. Why SAL over the alternatives

| Form                      | Verdict   | Rationale                                                                                                                                                |
| ------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SAL** (Joint-Stock)     | RECOMMEND | Required if Jeeb ever (a) raises external capital, (b) lists or transfers shares freely, (c) holds a banking-adjacent license, or (d) onboards a PSP that requires SAL counterparties. Mandatory board + statutory auditor add governance the platform needs by Series-A. |
| **SARL** (Limited)        | Reject for go-forward; usable for a 6–12 month MVP only | Cheaper to set up but capped at 20 partners, share transfers require partner consent, and most Lebanese PSPs / acquiring banks will not contract with a SARL above a small monthly volume. Conversion SARL→SAL is non-trivial (notary, re-registration, re-stamping). |
| **Holding (Law 45/1983)** | Reject    | Tax wrapper for owning shares in other companies; cannot itself carry on commercial activity such as commission collection.                              |
| **Offshore (Law 19/2008)**| Reject    | Forbidden from doing business inside Lebanon. Jeeb's customers are Lebanese; an offshore vehicle cannot invoice them.                                    |
| **Free-zone / SAL-O**     | Reject    | Same reason — operates only outside Lebanese customs territory.                                                                                          |
| **Sole proprietorship**   | Reject    | Unlimited personal liability; cannot scale; not bankable for a platform.                                                                                 |

## 3. SAL constitution checklist

| Item                                  | Required                                                                                                                                |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Minimum capital                       | **LBP 30,000,000** authorized; **fully subscribed**, at least **¼ paid in** on incorporation (Commercial Code Art. 81).                 |
| Shareholders                          | Minimum **3**; majority must be Lebanese unless activity is open to foreigners (commission platform: open, but check 2026 MoET notice). |
| Board of Directors                    | **3–12 members**; chairman must be Lebanese resident; chairman-GM unified role permitted.                                               |
| Statutory auditor (`مفوض المراقبة`)   | Mandatory; must be LACPA-registered; appointed for 3 fiscal years.                                                                      |
| Legal counsel (`المستشار القانوني`)   | Mandatory annual retainer with a Beirut-Bar-registered lawyer (Decree-Law 8/1970 thresholds).                                           |
| Articles of Association               | Notarized in Arabic; French/English translations permitted as annexes only.                                                             |
| Registered office                     | Must be a Lebanese physical address; PO boxes not accepted.                                                                             |
| Object clause                         | Must explicitly include: *"تشغيل منصة رقمية للوساطة بين مقدمي خدمات التوصيل والعملاء وتحصيل العمولات"* (operating a digital intermediation platform and collecting commissions). |

## 4. Registration sequence (target: 6–8 weeks)

1. **Name reservation** at the Commercial Register (1–3 business days).
2. **Notarize Articles of Association** before a Beirut notary public.
3. **Deposit paid-in capital** in an escrow account at a Lebanese bank;
   obtain a *Certificat de Blocage*.
4. **Register at Commercial Register, Beirut** — receive
   `رقم السجل التجاري` (CR number) and `رقم المالي` (Tax ID / financial number).
5. **Publish** an excerpt in the Official Gazette (`الجريدة الرسمية`) and
   one Arabic daily.
6. **Register with the Ministry of Finance** (VAT registration mandatory once
   the platform exceeds LBP-equivalent of USD ~100k commission revenue per
   four consecutive quarters — see [tax-obligations-commission-income.md](./tax-obligations-commission-income.md) §3).
7. **Register with the NSSF** before hiring the first employee (Jeebers are
   NOT employees — see §5 below).
8. **Open operating bank account** and unblock paid-in capital.
9. **PSP / acquiring contract** — see [settlement-provider-contract-requirements.md](./settlement-provider-contract-requirements.md).

## 5. Jeebers are contractors, not employees

The platform's commission model relies on Jeebers being **independent
contractors**. To preserve that classification:

- Master agreement must label the relationship `مقدم خدمة مستقل` (independent
  service provider) with no exclusivity, no fixed schedule, no employer
  control over method of work.
- Jeeb does NOT register Jeebers with the NSSF.
- Payouts to Jeebers carry **5% withholding on services** (Law 497/2003) if
  the Jeeber is not VAT-registered; this is reported on Jeeb's monthly tax
  return — see tax document §4.
- No tools, uniforms, or vehicles supplied by Jeeb (other than the optional
  branded gear sold at cost). Compulsory uniforms convert the relationship
  to employment under settled MoL jurisprudence.

## 6. Ongoing obligations (annual)

| Obligation                     | Cadence       | Owner       |
| ------------------------------ | ------------- | ----------- |
| Statutory auditor report       | Annual        | Auditor     |
| AGM + filed minutes            | Annual ≤ 6mo  | Board sec.  |
| MoF corporate tax return (F1)  | Annual by 31 May | CPA      |
| MoF VAT return                 | Quarterly     | Finance     |
| NSSF declaration (employees)   | Monthly       | Finance     |
| Withholding tax declarations   | Monthly       | Finance     |
| Commercial Register update     | On change     | Legal       |

## 7. Open questions for counsel

1. Confirm 2026 foreign-shareholder rules — Law 296/2001 amendments on
   foreign ownership of commercial activity are still being reinterpreted.
2. Confirm SAL is acceptable counterparty for chosen PSP (some BdL
   Circular 69 PSPs require SAL with minimum LBP 1,000,000,000 capital for
   aggregator services).
3. Confirm whether the commission platform triggers a BdL Circular 83
   electronic-payment-services notification (likely NO if Jeeb never holds
   client funds beyond a 24-hour settlement window).

## 8. References

- Lebanese Commercial Code, Decree-Law 304/1942.
- Law 296/2001 on foreign acquisition of real rights (shareholder limits).
- Law 282/1993 (NSSF amendments).
- BdL Basic Circulars 69, 81, 83.
- Beirut Bar Association — directory of corporate counsel.
- LACPA — directory of registered auditors.
