# Jeeb Lebanon — Beirut Pilot Compliance Checklist

| Field            | Value                                     |
| ---------------- | ----------------------------------------- |
| Version          | 0.1 (DRAFT)                               |
| Effective date   | TBD — pilot launch                        |
| Last reviewed    | 2026-05-16                                |
| Owner            | Compliance Officer (CO)                   |
| Binding language | English                                   |

> **This checklist is go/no-go.** Every item must be Green — signed by the
> named owner, evidence linked — before the Beirut pilot opens to its first
> external user. A single Yellow or Red blocks launch.

## 0. Named accountabilities

| Role                       | Name              | Email                       |
| -------------------------- | ----------------- | --------------------------- |
| Compliance Officer (CO)    | TBD               | `compliance@jeeb.app`       |
| Data Protection Officer    | TBD               | `dpo@jeeb.app`              |
| SRE on-call lead           | TBD               | `sre@jeeb.app`              |
| Legal counsel (Lebanon)    | TBD (named firm)  | TBD                         |
| SIC liaison (backup)       | TBD               | TBD                         |

Until all four `TBD`s are filled the checklist cannot move past Section 1.

## Legend

- 🟢 **Green** — done, evidence linked.
- 🟡 **Yellow** — in progress, dated commitment to Green.
- 🔴 **Red** — not started or blocked.

---

## 1. Regulatory & legal foundations

| # | Item                                                                                                  | Status | Owner | Evidence                                              |
| - | ----------------------------------------------------------------------------------------------------- | ------ | ----- | ----------------------------------------------------- |
| 1.1 | Lebanese counsel engaged and on retainer                                                            | 🔴     | CEO   | Engagement letter                                     |
| 1.2 | Company entity registered with Lebanese commercial registry                                          | 🔴     | CEO   | Commercial registry extract                           |
| 1.3 | BdL position on Jeeb's classification confirmed (PSP / intermediary / out-of-scope) in writing       | 🔴     | CO + counsel | Letter from counsel summarising BdL response  |
| 1.4 | SIC reporting channel established; named liaison registered                                          | 🔴     | CO    | SIC acknowledgement                                   |
| 1.5 | Terms of Service and Privacy Policy reviewed by Lebanese counsel and translated to Arabic            | 🔴     | DPO   | Counsel sign-off + locale parity check                |
| 1.6 | Prohibited-items list reviewed against Lebanese law                                                   | 🔴     | CO + counsel | Annotated diff to `legal/en/prohibited-items.md` |

## 2. KYC programme

| # | Item                                                                                                  | Status | Owner | Evidence                                              |
| - | ----------------------------------------------------------------------------------------------------- | ------ | ----- | ----------------------------------------------------- |
| 2.1 | KYC tiering matrix matches Law 44/2015 thresholds                                                     | 🟡     | CO    | This pack — [`kyc-id-verification.md`](./kyc-id-verification.md) |
| 2.2 | Vetting partner DPA signed, named processor identified                                                | 🔴     | DPO   | Executed DPA                                          |
| 2.3 | Sanctions/PEP screening live for Tier 3                                                               | 🔴     | CO    | Test run against synthetic positive case              |
| 2.4 | Manual review queue staffed with named reviewers + 4-eyes rule documented                              | 🔴     | CO    | Rota + RACI                                           |
| 2.5 | Liveness thresholds validated on a held-out eval set of ≥ 500 captures                                | 🔴     | ML/Eng | Eval report with FAR/FRR by tier                     |
| 2.6 | Age-gate enforced: Clients ≥ 18, Jeebers ≥ 21                                                         | 🔴     | Eng   | Feature flag + automated test                         |
| 2.7 | Block-list of lost/stolen IDs ingested daily from official source                                     | 🔴     | Eng + CO | Daily ingest job + last-run timestamp metric       |
| 2.8 | Bilingual UX strings for KYC flow reviewed (English + Arabic)                                         | 🔴     | Product | Screenshot pack                                     |

## 3. Data protection & retention

| # | Item                                                                                                  | Status | Owner | Evidence                                              |
| - | ----------------------------------------------------------------------------------------------------- | ------ | ----- | ----------------------------------------------------- |
| 3.1 | Retention policy published and operationalised                                                        | 🟡     | DPO   | [`document-retention-policy.md`](./document-retention-policy.md) + deletion-job code review |
| 3.2 | Encryption at rest verified for KYC bucket and Postgres column                                        | 🔴     | SRE   | Key inventory + KMS policy                            |
| 3.3 | Encryption in transit (TLS 1.3) on all KYC ingress/egress; no TLS 1.1                                 | 🔴     | SRE   | nmap / testssl.sh report                              |
| 3.4 | Object-lock (compliance mode) enabled on KYC bucket                                                   | 🔴     | SRE   | AWS CLI head-bucket showing lock                      |
| 3.5 | Backup retention aligned with primary retention                                                       | 🔴     | SRE   | Backup config diff                                    |
| 3.6 | DSAR (subject-access-request) procedure documented and tested                                         | 🔴     | DPO   | Tabletop drill report                                 |
| 3.7 | Erasure flow refuses pre-minimum requests with a written, dated explanation                            | 🔴     | Eng + DPO | UX screenshots + audit log entry                  |
| 3.8 | Cross-border transfer assessment for vetting partner completed                                        | 🔴     | DPO + counsel | TIA document                                  |
| 3.9 | Synthetic-only data in staging; production data never restored to lower envs                          | 🔴     | SRE   | Backup-restore policy + audit                         |

## 4. Operational readiness

| # | Item                                                                                                  | Status | Owner | Evidence                                              |
| - | ----------------------------------------------------------------------------------------------------- | ------ | ----- | ----------------------------------------------------- |
| 4.1 | Deletion job runs nightly; dry-run output reviewed weekly for first month                              | 🔴     | SRE   | Cron config + first weekly review log                 |
| 4.2 | Evidence-bucket hash chain integrity verified daily                                                   | 🔴     | SRE   | Verification job + alert                              |
| 4.3 | Runbook for "SIC information request" exists and on-call has trained on it                            | 🔴     | CO + SRE | Runbook + training attendance                      |
| 4.4 | Runbook for "KYC pipeline degraded" exists; user-facing message reviewed                              | 🔴     | SRE + Product | Runbook + UX strings                              |
| 4.5 | Incident-response process names a privacy-incident track distinct from security-incident track        | 🔴     | DPO + SRE | IR playbook                                       |
| 4.6 | 72-hour breach-notification clock and stakeholder list documented                                     | 🔴     | DPO   | IR playbook §breach                                   |
| 4.7 | Reconstruction drill: produce full KYC dossier for a sampled user within 15 minutes                   | 🔴     | CO + SRE | Drill log                                          |
| 4.8 | Observability: KYC funnel metrics (capture → pass/review/fail) instrumented and dashboarded            | 🔴     | SRE   | Grafana dashboard URL                                 |

## 5. Vendor & supply chain

| # | Item                                                                                                  | Status | Owner | Evidence                                              |
| - | ----------------------------------------------------------------------------------------------------- | ------ | ----- | ----------------------------------------------------- |
| 5.1 | Vetting partner: SOC 2 Type II or ISO 27001 in date                                                   | 🔴     | DPO   | Cert / report                                         |
| 5.2 | Payment processor (`unified_payment_gateway` upstream): KYC adequacy attested                         | 🔴     | CO    | Counterparty letter                                   |
| 5.3 | Object-storage provider: data-locality contract in place (EU/ME footprint)                            | 🔴     | SRE   | Contract excerpt                                      |
| 5.4 | All KYC-touching third parties listed in a Processor Register                                         | 🔴     | DPO   | Register link                                         |

## 6. Pilot guard-rails (specific to Beirut)

| # | Item                                                                                                  | Status | Owner | Evidence                                              |
| - | ----------------------------------------------------------------------------------------------------- | ------ | ----- | ----------------------------------------------------- |
| 6.1 | Pilot user cap (initial): 500 Clients, 100 Jeebers — enforced via feature flag                        | 🔴     | Product + Eng | Flag config + automated cap test                   |
| 6.2 | Geofence: service area restricted to Beirut governorate                                               | 🔴     | Eng   | Map + integration test                                |
| 6.3 | Currency handling: LBP primary; USD shadow accounting; daily rate-source documented                   | 🔴     | Finance + Eng | Rate-source contract + test                       |
| 6.4 | Sanctions list refresh cadence: monthly minimum, ad-hoc on advisory                                   | 🔴     | CO    | Cron config + last-run                                |
| 6.5 | Pilot-end criteria defined: success metrics, abort triggers, data-handling for wind-down              | 🔴     | Product + CO | Pilot plan document                                |

## 7. Sign-off

The pilot opens to external users **only after** all rows above are 🟢 and
the following sign-offs are on file:

- [ ] CEO — business decision to launch
- [ ] CO — regulatory readiness
- [ ] DPO — data-protection readiness
- [ ] SRE lead — operational readiness
- [ ] Legal counsel — written go-ahead

Sign-offs are stored alongside this file in `audits/launch-signoffs/`.

## 8. Recurring re-validation

After launch, this checklist is re-validated:

- Quarterly during pilot.
- Within 7 days of any incident triggering a privacy or AML
  control failure.
- Annually thereafter once general availability is declared.
