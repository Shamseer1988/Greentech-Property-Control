# Accounting Rules — GreenTech Real Estate Control Portal

**Binding for every phase that touches money** (contracts, rent schedules,
receipts, PDCs, landlord payments, expenses, imports). Code review must
check changes in those areas against this document. These rules exist so
the app's figures can always be reconciled against the account software
and survive an audit.

## 1. No hard delete of financial records

Receipts, payment vouchers, rent charges, cheques, and expense entries
are **never** deleted from the database. Wrong entries are **voided**:

- A void sets `status = "voided"`, records `voided_by`, `voided_at`,
  and a mandatory `void_reason`.
- Voided records stay visible (struck through / filtered) and keep
  their voucher number — the numbering sequence must show no gaps.
- If approvals are enabled for voids, the record stays effective until
  the void is approved.

## 2. Posted transactions are immutable

Once a receipt / payment / charge is posted, its amount, date, party,
and allocation are read-only. A correction is a **new record**
(a void + re-entry, or an adjustment entry referencing the original) —
never an UPDATE of the posted row. `updated_at` on financial rows may
only change for non-financial metadata (remarks, attachments).

## 3. Contract changes are dated amendments

Rent reduction, free months, room-count changes, cancellation, and
renewal are **amendment records** with an effective date, linked to the
contract. The original contract row is never rewritten. Any past month's
rent must be reproducible exactly from contract + amendments.

## 4. Sequential, gapless voucher numbering

Receipts (`RV-YYYYMM-NNNN`), payment vouchers (`PV-…`), and contract
numbers are issued sequentially per series. Numbers are never reused,
even for voided documents. Number generation happens inside the DB
transaction that creates the record.

## 5. Period close / lock

Once a month is marked **closed** (after reconciling with the account
software), no financial record dated inside that period may be created,
voided, or amended without an explicit period-reopen by an Admin —
which itself is audited. The fiscal year start comes from
`company.fiscal_year_start_month`.

## 6. Every figure traces to a source document

Receipts and payments carry attachment slots for the cheque copy /
voucher scan. Imported expenses store the source file, import batch id,
and row reference, so any number on a P&L can be traced back to the
account-software export that produced it. Imports are idempotent: the
same file re-imported must not double-post (batch hash check).

## 7. Full audit trail

Every create / void / amendment / approval / period action writes an
`audit_log` row with user, timestamp, and before/after values. This is
already wired via `services/audit.record(...)` — money-touching code
must call it on every state change, inside the same transaction.

## 8. Allocation discipline

Receipts allocate to the oldest open charge first unless the operator
explicitly overrides (override is recorded). Unallocated amounts sit as
client advances — never silently netted against future charges without
an allocation record.

## 9. Cheques are stateful, never edited

A PDC moves through `received → deposited → cleared | bounced →
replaced`. Each transition is a dated event row. A bounced cheque is
never edited into a cleared one; a replacement is a new cheque linked
to the bounced original.

**Revenue recognition happens at `deposited`, not `cleared`.** The
moment the bank has the cheque, a receipt posts for its amount against
the month it covers, so the SOA and the cheque register move together.
`cleared` afterwards is confirmation only — it posts nothing further.
If the cheque later bounces, the receipt `deposited` posted is voided
automatically (the months it settled reopen) — the operator does not
void it by hand. A re-presented cheque (`bounced → deposited` again)
posts a fresh receipt the same way.

## 10. Derived numbers are computed, never stored as truth

Occupancy, totals, ageing buckets, and P&L lines are computed from the
underlying records at read time (or cached with the source of truth
intact). No screen lets a user type over a computed total.

---

*Phase 0 status:* the base model keeps `created_by` / `updated_by` and
the audit service; masters (landlord, property, unit) use soft
deactivation (`status`) rather than deletion when referenced. The
financial tables arriving in Phases 2–4 must implement rules 1–9 from
their first migration.
