# Cash-on-Delivery Settlement Controls

> **Status:** DRAFT v0.1 — pending review by qualified Lebanese counsel and
> an LACPA-registered certified public accountant before launch.

## 1. Scope and system boundary

Jeeb accepts cash on delivery for Requests. The unified payment gateway (UPG)
is the existing durable system of record for the COD obligation, collection
status, settlement batches, reconciliation decisions, audit events, and
idempotent administrative mutations.

UPG is not a card gateway, acquirer, electronic-payment processor, or customer
wallet. Jeeb does not collect card data for Requests. Any separate bank or
wallet transfer used to pay an amount owed to a Jeeber is an operational payout
after COD reconciliation and is outside the customer-payment function of UPG.

## 2. Cash collection record

For every Request, the authoritative COD record must identify:

- Request and delivery identifiers;
- payer and collecting Jeeber identifiers;
- amount and currency as fixed before acceptance;
- collection status and the actor/time for each status change;
- commission, net amount, and settlement version;
- any dispute, resolution, batch, and reconciliation references.

Delivery completion must never be treated as proof that cash was collected.
Collection and reconciliation require explicit owner-side operations.

## 3. Administrative controls

- Browser operators use the Jeeb gateway; browsers do not call UPG directly.
- Read, dispute, resolve, batch, and reconciliation capabilities are distinct.
- Reconciliation requires fresh MFA and an explicit confirmation step.
- Mutations use idempotency keys and compare-and-set versions.
- An unknown network outcome is retried with the same key and payload.
- UPG returns the authoritative state after every accepted mutation.
- Every mutation records the operator, reason, time, old version, and new
  version in an append-only audit trail.

## 4. Reconciliation and discrepancies

Finance reconciles recorded COD collections against the cash handover evidence
and the published settlement schedule. A discrepancy is opened as a durable
dispute; it must not be hidden by editing or deleting the original collection
event. Resolution requires a reason and identifies the resolving operator.

Cash creates no automated refund or card-chargeback path. Any reimbursement is
approved and executed manually, then referenced from the durable dispute record.

## 5. Payout and commission accounting

- Commission and net amounts derive from the immutable Request price and the
  published commission schedule.
- A batch cannot be marked paid without an external payment reference or other
  finance evidence required by the payout procedure.
- UPG records payout reconciliation but does not define or market a customer
  electronic-payment method.
- Tax invoices and retention follow the separate commission and tax documents
  in this directory.

## 6. Data minimisation and retention

UPG receives only the identifiers, amounts, status, and audit metadata required
for COD settlement. It must not receive raw identity documents, card data,
private evidence URLs, or chat content. Settlement and tax records follow the
approved legal-retention schedule; access logs and audit history are retained
for the same accountability period unless counsel requires longer retention.

## 7. Launch evidence

- [ ] UPG production database backup and restore drill passed.
- [ ] COD import/migration totals reconcile to the signed finance source.
- [ ] Duplicate idempotency and stale-version tests passed.
- [ ] Read, dispute, resolve, and reconciliation capability tests passed.
- [ ] Fresh-MFA enforcement and operator audit attribution passed.
- [ ] Manual reimbursement procedure approved by Finance and Compliance.
- [ ] Daily reconciliation report owner and escalation route named.
- [ ] Counsel and CPA sign-off recorded for the launch version.
