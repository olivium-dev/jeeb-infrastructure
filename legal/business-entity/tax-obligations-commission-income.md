# Tax Obligations on Platform Commission Income (Lebanon)

> **Status:** DRAFT v0.1 — DO NOT use as filing guidance until reviewed by a
> LACPA-registered CPA. Rates and thresholds are correct as of the document
> date but Lebanese tax law has been amended in every budget law since 2017
> and may change again at the next one.

## 1. Quick reference matrix

| # | Tax                                                                          | Statute                       | Rate                                  | Cadence    | Who pays         | Filed on      |
|---|------------------------------------------------------------------------------|-------------------------------|---------------------------------------|------------|------------------|---------------|
| 1 | **Corporate Income Tax (CIT)** on Jeeb's net profit                          | Decree-Law 144/1959 as amended| **17%** of net taxable profit         | Annual     | Jeeb SAL         | Form F1, by 31 May |
| 2 | **VAT (TVA)** on every commission invoice                                    | Law 379/2001                  | **11%** standard rate                 | Quarterly  | Charged to recipient; remitted by Jeeb | VAT return Q+20d |
| 3 | **Withholding on services** paid to non-VAT-registered Jeebers/Merchants     | Law 497/2003                  | **7.5%** of gross service payment     | Monthly    | Jeeb withholds   | Form R10 by 15th |
| 4 | **Withholding on dividends** distributed to shareholders                     | Decree-Law 144/1959 Art. 72   | **10%**                               | On distrib.| Jeeb withholds   | Form R5      |
| 5 | **Built-property tax** on office (if owned)                                  | Law 38/1968                   | progressive 4–14%                     | Annual     | Owner            | March        |
| 6 | **Stamp duty** on contracts                                                  | Decree-Law 67/1967            | **0.4%** of contract value            | On signing | Either party     | At signing   |
| 7 | **NSSF** for Jeeb's own employees only                                       | Decree-Law 13955/1963         | ~23.5% employer + 3% employee         | Monthly    | Jeeb (employer)  | Monthly       |
| 8 | **Municipal fees** (Beirut municipality, sign tax, etc.)                     | Law 60/1988                   | Variable                              | Annual     | Jeeb             | Per notice    |

> Jeebers (independent contractors) are NOT registered to NSSF by Jeeb — see
> [entity-recommendation-lebanon.md](./entity-recommendation-lebanon.md) §5.

## 2. Corporate Income Tax (CIT) on commission revenue

**Taxable base:** worldwide net profit (commission revenue minus deductible
operating costs and depreciation), Decree-Law 144/1959 Art. 4.

**Computation outline:**

```
Commission revenue (LBP, exclusive of VAT)
  − Payroll & NSSF employer contributions
  − Hosting / SaaS / software amortization
  − Marketing & customer acquisition
  − Rent & utilities
  − Statutory auditor + legal counsel fees
  − Depreciation (per Decree 5451/2001 brackets)
  − Bad-debt provisions (within Art. 5 limits)
  = Net taxable profit
  × 17%
  = CIT due
```

**Loss carry-forward:** up to **3 fiscal years** (Art. 6 bis).

**Estimated payments:** Lebanon does NOT require quarterly CIT prepayments;
the full balance is due with the F1 return by **31 May** of year N+1 for
fiscal year N.

**Documentation:** keep contemporaneous transfer-pricing notes if Jeeb SAL
charges or receives intra-group fees (e.g., a future Olivium parent).

## 3. VAT on commission

**Registration threshold:** mandatory registration once **four consecutive
quarters of taxable revenue exceed LBP-equivalent of approximately
USD 100,000** (current MoF threshold; verify at registration time).

**Place-of-supply rule for digital intermediation services**
(Law 379/2001 Art. 16–17):
- Recipient in Lebanon → 11% VAT charged.
- Recipient outside Lebanon AND service consumed outside Lebanon →
  **0% (export of services)**, with input-VAT recovery preserved.
- Recipient outside Lebanon but service consumed in Lebanon (e.g., a foreign
  Merchant whose Jeebers deliver to Beirut Clients) → **11%**.

**Input-VAT recovery:** Jeeb can recover input VAT on hosting, marketing,
office, and legal/accounting fees in proportion to taxable supplies.

**Filing & payment:** **quarterly** VAT return on MoF e-services portal,
within **20 days** of the quarter end. Net VAT (output − input) is paid by
wire to MoF's collection account.

**Penalties:** late filing — LBP 500,000 minimum (Law 379/2001 Art. 41);
under-declaration — 10% of underpaid tax plus monthly interest.

## 4. Withholding on payouts to Jeebers and Merchants

Under Law 497/2003 a Lebanese-resident commercial entity paying for services
to a service provider who is **not** registered for VAT must withhold **7.5%**
of the gross payment at source.

**Application to Jeeb:**

| Jeeber / Merchant status                          | Withholding on payout |
|---------------------------------------------------|-----------------------|
| Individual, no commercial register, no VAT        | **7.5% withhold**     |
| Sole prop., commercial register, NO VAT           | **7.5% withhold**     |
| Sole prop. or SARL with VAT registration          | **0% (recipient self-declares)** |
| Foreign service provider, no Lebanese PE          | **2.25%** (Art. 41 of CIT law as amended) |

**Mechanics:** withhold inside the wallet-service settlement step; remit by
the **15th of the following month** on Form R10; issue an annual withholding
certificate to each Jeeber so they can offset against personal income tax.

**Audit-proofing:** persist `withholding_pct`, `withholding_amount`,
`withholding_form_id`, `remittance_ref`, and `remittance_date` on every
payout transaction in the wallet ledger.

## 5. Stamp duty

Every contract — including the master services agreement with Jeebers,
Merchant contracts, the PSP contract, and significant SaaS subscriptions —
attracts **0.4%** stamp duty on the contractual consideration, Decree-Law
67/1967. For the Jeeber click-through agreement Lebanese counsel typically
opines that stamp duty is **nil** because the consideration is variable and
the agreement is not a "valued contract" in the statutory sense — confirm
with counsel before relying on this position.

## 6. NSSF (for Jeeb's own employees only)

| Branch                          | Employer | Employee |
|---------------------------------|----------|----------|
| Sickness & maternity            | 8%       | 3%       |
| Family allowances               | 6%       | 0%       |
| End-of-service indemnity        | 8.5%     | 0%       |
| Work-injury (occupation rated)  | ~1%      | 0%       |

Filed monthly with NSSF; ceilings are revisited by NSSF board decision —
verify the current ceiling at hiring time.

## 7. International tax angles

- **Double-tax treaties:** Lebanon has DTTs with many MENA + EU
  jurisdictions; treaty rates reduce Lebanese withholding on outbound
  royalties / interest / dividends. Apply each treaty case-by-case with
  Form W-1L plus a tax-residency certificate from the counterparty.
- **Transfer pricing:** Lebanon has light TP rules; arm's-length principle
  applies, but no formal documentation template is mandated. Keep
  reasonable contemporaneous benchmarks for any related-party transaction.
- **OECD Pillar Two:** Lebanon is not currently in the Inclusive Framework;
  not relevant for Jeeb at MVP scale.

## 8. Calendar (annual)

| Month             | Filing                                                       |
|-------------------|--------------------------------------------------------------|
| Monthly by 15th   | Form R10 (withholding on services), NSSF, payroll withholding |
| Quarterly +20d    | VAT return                                                   |
| 31 January        | Annual employer payroll declaration (Form R5/R6)             |
| 31 May            | Corporate income tax return Form F1, prior fiscal year       |
| 30 June           | Filed AGM minutes                                            |
| 30 September      | Built-property tax (if applicable)                           |

## 9. References

- Decree-Law 144/1959 (Income Tax) and successive budget law amendments.
- Law 379/2001 (VAT) and MoF Decision 644/2003.
- Law 497/2003 (withholding on services).
- Decree-Law 67/1967 (stamp duty).
- Decree-Law 13955/1963 (NSSF), Law 282/1993.
- Decree 5451/2001 (depreciation brackets).
- MoF e-services portal — official forms and current rates.
- LACPA — engagement letter required before any filing.
