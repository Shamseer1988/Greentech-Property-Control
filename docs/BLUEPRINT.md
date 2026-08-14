# GreenTech Real Estate Control Portal — System Blueprint

Property, contract and rent-control software for the **GreenTech Trading & Contracting** real-estate division (Qatar, QAR).

This document is the functional specification. The phase-by-phase build order lives in `DEVELOPMENT-PLAN.md`; the rules that govern anything touching money live in [`ACCOUNTING-RULES.md`](ACCOUNTING-RULES.md).

---

## 1. What the business does

GreenTech **rents property from landlords** and **sublets it to clients**.

- **From landlords:** whole buildings, buildings with a store, flat buildings (1BHK / 2BHK), villas, labour camps, standalone stores.
- **To clients:** a single room, two or three rooms, a whole floor, two floors, a partial building, a store, a cafeteria, a supermarket.

Money moves in three modes:

| Mode | How it works |
|---|---|
| **CASH** | Collected monthly. Some clients also pay a cash deposit. |
| **CHEQUE (PDC)** | A one-year agreement means **12 post-dated rent cheques + 1 security cheque** held on file. |
| **ONLINE** | Bank transfer, monthly. |

The margin on any property is: *rent received from clients* − *rent paid to the landlord* − *property-wise expenses* (sewage removal, electricity & water, maintenance, cleaning).

## 2. The problem this replaces

Two systems fail today:

1. **The master workbook** (`1-GreenTech Master File 2026.xlsm`) is the real system of record. Its "New-2026" sheet holds one block per property — client rows with expiry date, payment mode, room count, opening balance and a column per month; then Cash/Cheque totals, empty rooms, landlord rent paid, expenses, and a monthly Profit-or-Loss line. Companion sheets track landlords (with Arabic names and security cheques), month-wise ageing, statements of account and empty rooms. Everything is maintained by hand and nothing validates.

2. **The accounting software has no property-wise allocation.** It can tell you total rent paid, total rent received and total indirect expenses — but not what any single property earned. Per-property profitability is therefore invisible.

**The core value of this system: every rial of income and expense lands on a property, so per-property P&L is automatic.**

## 3. Domain model

### Masters
| Entity | Purpose |
|---|---|
| **Landlord** | The owner GreenTech rents *from*. English + Arabic name, contact, CR/QID with expiry, documents. Code `LL-0001`. |
| **Client** | The tenant GreenTech lets *to*. English + Arabic name, contact person, phone, CR/QID with expiry, documents. Code `CL-0001`. |
| **Property** | A building / camp / villa / store taken from a landlord. Code `PROP-0001`. |
| **Floor** | Belongs to a property — `G`, `1`, `2`, `M`. |
| **Unit** | **The atom of occupancy.** Every lettable thing and every facility: room, 1BHK/2BHK flat, whole floor, villa, store, shop, cafeteria, supermarket — plus kitchen, bathroom, play area and mess, each flagged **shared** (common to the property) or **dedicated** (attached to one client contract). Units carry a real unit number so a contract can name exactly which rooms it holds. |

### Contracts
| Entity | Purpose |
|---|---|
| **Landlord contract** | Property, start/expiry, monthly rent payable, security cheque, deposit, free-room clauses, documents. |
| **Client contract** | Client + the exact units allocated, start/expiry, monthly rent, mode, opening balance, cash deposit, documents. |
| **Contract amendment** | Dated, versioned changes: cancellation, rent reduction/increase, free months, **room-count reduction (naming which units are released)**, renewal. The original contract row is never rewritten. |
| **PDC register** | The 12 rent cheques + security cheque. Lifecycle: received → deposited → cleared / bounced → replaced. Cheque copy attached per cheque. |

### Money
| Entity | Purpose |
|---|---|
| **Rent schedule** | Auto-generated monthly charge per client contract, honouring free months, reductions, unit changes and cancellation date (pro-rata). |
| **Receipt** | Cash / cheque / online, allocated oldest-first, printable receipt voucher. |
| **Landlord payment** | Monthly rent paid, printable payment voucher. |
| **Expense** | Property-wise direct (sewage, electricity & water, maintenance, general) + company-level indirect (salary, fuel, telephone, bank charges…). Imported monthly from the accounting software's P&L export. |

### Cross-cutting
- **Attachments** — a central document store used by every module: agreements, company docs (CR, computer card), government docs (QID, title deed, Baladiya), cheque copies, payment/receipt vouchers. Documents carry an expiry date that feeds the alert engine.
- **Audit log** — every create / edit / void / approval with user, timestamp and before/after values, filterable by module, action, user and date.
- **Approvals** — per-action toggles in **Settings → Approval**, currently covering landlord renewal, contract cancellation, rent reduction and receipt void. A rent *increase* is not gated; only reductions are. When a toggle is on the action is queued instead of applied: the rent, the unit allocation and the receipt all keep reading exactly as they did before the request, and the change is applied only on approval — re-validated then against the state of that day, so a request that has since become impossible fails on the approver's screen instead of writing a contradiction. Rejecting writes nothing anywhere; the request row is the record that someone asked and was told no.
- **Backup** — one zip holding the database and every uploaded document, taken, downloaded and restored from Settings.
- **Notifications** — one rule per event in **Settings → Notification rules**: expiring client contracts and landlord agreements, unpaid rent, cheques due to bank, bounced cheques, expiring documents, waiting approvals. Each rule carries its own advance days (60, 30, 7 — "two months before" is just `60`), channels (in-app, email, Telegram), audience (the tenant, the landlord, our staff) and an optional template. A daily sweep asks only *what is exactly N days away today*, so a reminder fires once as each threshold is crossed and a re-run changes nothing — every delivery carries a unique key.

  Three things stand between a template and a tenant's inbox, because a wrong mass-mailing cannot be recalled: **sending is off by default** (messages are still composed and logged, so you can read what *would* have gone out); **Preview** on any rule lists the exact recipients without contacting them; and **redirect-all** sends a whole run to one address so a month-end can be rehearsed. Every attempt — sent, skipped or failed — is kept in **Messages**.

- **AI assistant** — Gemini, Azure OpenAI or a local OpenAI-compatible server, configured in Settings. It drafts reminder and chase emails and writes the monthly management summary. It is handed the figures rather than trusted to recall them, and **a draft is never a send**: every AI-written message is reviewed and dispatched by a person.

## 4. What the system must produce

Reports that replace the workbook, each exportable to Excel:

| Report | Replaces |
|---|---|
| Property P&L (New-2026 layout) | The per-property block, including the monthly Profit-or-Loss line |
| Rent collection | Cash/Cheque totals per month |
| Client ageing | The "Ageing" sheet, month-wise buckets |
| Statement of account | The "Soa" sheet |
| Empty units | The "Empty Rooms" sheet, at unit-number precision |
| Expiry control | Landlord + client contract expiry with reminder buckets |
| PDC register | Cheques on hand, due for deposit, bounced |
| Company P&L | Reconciles against the accounting software |
| Audit report | Nothing in the workbook — who changed what, when |

All of these are live at **Reports**, each exportable to `.xlsx` and `.pdf`. A report never re-derives a figure that a page already shows: the ageing report *is* `services/ageing.ageing()`, the property P&L *is* `services/expenses.property_pnl()`. That is what makes a printed report and the screen it came from incapable of disagreeing.

Four dashboards read from the same services: **main** (rent charged and collected with collection %, arrears, month net profit, expiring contracts, PDCs due, bounced cheques, approvals waiting), **property** (occupancy, who is in the building, the month's block and a 12-month margin trend), **client** (contracts and units held, ageing, receipts, cheques on hand), and **landlord** (agreements, monthly commitment, what we have paid, and how their buildings performed).

## 5. Control and automation

- **Expiry control** — landlord and client contracts, with configurable advance warning (e.g. two months before expiry) and multiple triggers (90/60/30/7 days).
- **Rent due and overdue reminders** — configurable day of month, with escalation.
- **Cheque alerts** — due for deposit, and returned/bounced.
- **Document expiry** — CR / QID approaching expiry.
- **Channels** — in-app notification centre, email, Telegram, browser push. Each event type configures its own advance period, channels and recipients.
- **AI (optional)** — provider configurable (Google Gemini / Azure OpenAI / local). Drafts reminder and notice emails from live contract data, and writes a monthly management summary. The system is fully functional with no AI configured.

## 6. Non-negotiables

1. **History is never overwritten.** Rent changes, cancellations, free months and unit changes are dated amendments; any past month can be reproduced exactly.
2. **Occupancy is computed, never typed.** Empty units derive from active contract allocations, always live and unit-number precise.
3. **Import over manual entry.** Month-end expenses come from the accounting software export; the ledger-name mapping is saved once and reused.
4. **Attachments are first-class.** No contract, cheque or voucher exists without a place for its paper.
5. **Accounting discipline governs money.** See [`ACCOUNTING-RULES.md`](ACCOUNTING-RULES.md) — no hard deletes, immutable posted transactions, gapless voucher numbering, period lock, full audit trail.

## 7. Technology

- **Backend** — Python Flask (app factory + blueprints), SQLAlchemy, Flask-Migrate, Flask-JWT-Extended (cookie auth + CSRF), Marshmallow/apiflask schemas, openpyxl/pandas for import-export, Celery for scheduled jobs.
- **Database** — PostgreSQL.
- **Frontend** — Next.js 14 App Router, TypeScript, React 18, Tailwind CSS, TanStack Query/Table, Recharts, Framer Motion, next-themes (light/dark).
- **Auth** — JWT in HTTP-only cookies, CSRF echo header on mutations, role-based permissions as dotted `module.action` codes.
