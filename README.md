# GreenTech Real Estate Control Portal

Property, contract and rent control for the **GreenTech Trading & Contracting** real-estate division. Replaces the `1-GreenTech Master File 2026.xlsm` workbook: landlords, properties, units, contracts, PDC cheques, rent collection, ageing, property-wise expenses and P&L — with expiry control, reminders and dashboards on top.

The core gap it closes: the company's accounting software has **no property-wise allocation**. Here every rial of income and expense lands on a property, so per-property profit & loss is automatic.

> Functional spec: [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md). Build order: `DEVELOPMENT-PLAN.md` (parent folder).
> **Current status: Phase 7 — notifications, email, Telegram and AI complete.** The whole master workbook is replaced: masters, contracts with exact unit numbers, the PDC register, the rent engine, collections with ageing and statements, landlord payment vouchers, property expenses, and a month-end import of the accounting software's P&L export that reconciles against the file's own totals. **Per-property profit and loss — the number the accounting software cannot produce — is automatic.** Sensitive actions can be put behind an approver; every change is searchable in the audit log with before/after values; the database and all uploaded documents back up to one downloadable zip that restores from the browser. Four dashboards and eight reports — each exportable to Excel and PDF — put every figure the workbook held on screen. Reminders now go out on their own: configurable rules warn about expiring contracts and agreements, unpaid rent, cheques due and bounced, and expiring documents, by email, Telegram and in-app — with an AI assistant that drafts messages for review. **Nothing is sent until you switch it on.** Data migration and go-live follow in Phase 8.

---

## Stack

- **Backend** — Python Flask · App Factory + Blueprints · SQLAlchemy · Flask-Migrate (Alembic) · Flask-JWT-Extended · Flask-CORS · Marshmallow · openpyxl/pandas · Celery (needed only for scheduled reminders and backups)
- **Database** — PostgreSQL 14+ (developed against 18)
- **Frontend** — Next.js 14 (App Router) · TypeScript · React 18 · Tailwind CSS · Framer Motion · Lucide icons · Recharts · TanStack Table · React Hook Form · Zod · next-themes
- **Deploy target** — Windows host (PostgreSQL + waitress + Next.js) behind nginx. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Domain model

| Entity | Notes |
|---|---|
| **Landlord** | The owner you rent *from*. English + Arabic name, CR/QID with expiry. Code `LL-0001`. |
| **Client** | The tenant you let *to* — company or individual. English + Arabic name, CR/QID with expiry. Code `CL-0001`. |
| **Property** | A building / camp / villa / store taken from a landlord. Code `PROP-0001`. Types: full building, building with store, flat building, villa, labour camp, store, mixed use. |
| **Floor** | Belongs to a property — `G`, `1`, `2`… |
| **Unit** (table `units`) | The atom of occupancy: room, 1BHK/2BHK flat, whole floor, villa, store, shop, cafeteria, supermarket — plus facilities (kitchen, bathroom, play area, mess) flagged **shared** or **dedicated**. |
| **Property agreement** | The landlord contract: start, expiry, monthly rent, security deposit, reminder days. |
| **Attachment** | Central document store, usable from every module (agreements, company/govt docs, cheque copies, vouchers). Documents carry a number, issue date and expiry — company and government documents feed the renewal alerts. |
| **Client contract** | A tenancy: client + the exact units held, term, rent, payment mode (cash / cheque / online), deposit and opening balance. Code `CON-YYYYMM-NNNN`. |
| **Contract amendment** | Every post-signing change, dated and versioned: rent change, free months, units added or released, cancellation, renewal. The contract row is never rewritten. |
| **Cheque** | A post-dated cheque against a contract — 12 rent cheques + a security cheque for an annual agreement. Lifecycle: received → deposited → cleared / bounced → replaced, each transition an append-only event. Clearing a rent cheque posts its receipt. |
| **Rent charge** | What a client owes for one month on one contract, derived from the contract plus its amendments. Regenerating a month is safe and never disturbs one that has money against it. |
| **Receipt** | Money received, numbered `RV-YYYYMM-NNNN`. Settles the oldest open charge first unless directed otherwise; anything spare is held as an advance. Voided with a reason, never deleted. |
| **Landlord payment** | Rent paid out for a property, numbered `PV-YYYYMM-NNNN` — property-wise by construction, which is what makes the "Rent Paid" line attributable. |
| **Expense** | A cost for one month, either against a property (direct) or company-level (overhead). Entered by hand or imported. |
| **Import batch** | One accounting-software P&L file, imported once. Keyed by file hash so a re-import is caught, and it records the totals the file declared so the reconciliation is visible after the fact. |
| **Notification rule** | One per event (contract expiry, rent due, cheque bounced…): how far ahead to warn, down which channels, to whom. Ships disabled. |
| **Outbound message** | One row per delivery attempt on any channel — the record of what was said on the company's behalf, kept whether it sent, was skipped or failed. |

The one-time migration off the workbook lands in Phase 8.

**Anything touching money must follow [`docs/ACCOUNTING-RULES.md`](docs/ACCOUNTING-RULES.md)** — no hard deletes, immutable posted transactions, dated amendments, gapless voucher numbers, period lock, full audit trail.

---

## Repository layout

```
backend/                 Flask API
  app/
    __init__.py          App factory + blueprint registration
    extensions.py        db, migrate, jwt, limiter singletons
    models/              SQLAlchemy models
    routes/              HTTP layer (one blueprint per module)
    services/            Business logic (audit, permissions, layout, reports…)
    tasks/               Celery tasks (expiry sweep, rent, notifications, backup)
    utils/               Auth decorators + response helpers
  config.py              Dev / Testing / Production configs
  wsgi.py                Entry point (waitress-serve target)
  tests/                 pytest suite
  .env.example
frontend/                Next.js TypeScript app
  src/app/(app)/         Authenticated shell: dashboard, properties, landlords,
                         approvals, reports, alerts, users, audit, settings
  src/components/        UI primitives, layout, attachments, search
  src/lib/               api client, auth store, query keys
docs/                    BLUEPRINT.md · ACCOUNTING-RULES.md · DEPLOYMENT.md
scripts/                 install / bootstrap-db / start-all / stop-all
uploads/                 Runtime attachments (gitignored)
backups/                 DB / file backups (gitignored)
```

---

## Quick start (Windows)

```powershell
.\scripts\install-windows.ps1   # venv + npm install + frontend build
.\scripts\bootstrap-db.ps1      # create tables, seed roles/permissions/admin
.\scripts\start-all.ps1         # backend + frontend windows
```

Open **http://localhost:3000** and sign in as `admin` with the `SUPERUSER_PASSWORD` from `backend\.env`.

Redis is **optional**: without `REDIS_URL` the rate limiter uses an in-memory store and the Celery windows are skipped. Everything works by hand — you can run the notification sweep and take a backup from the UI. Install Memurai and set `REDIS_URL` when you want reminders and backups to run on their own overnight.

See [DEV.md](DEV.md) for the day-to-day workflow and [DEPLOY.md](DEPLOY.md) for production.

---

## Roles

| Role | Intent |
|---|---|
| `super_user` | Unrestricted (the seeded `admin`). |
| `admin` | Full operational access including users, settings, backups. |
| `accounts` | Masters (landlords, clients, properties), contracts, rent, receipts, expenses, reports. |
| `data_entry` | Day-to-day entry; no approvals, no admin. |
| `viewer` | Read-only dashboards and reports. |
| `auditor` | Read everything plus the audit trail. |

Permissions are dotted `module.action` codes defined in `backend/app/services/permissions.py` — the single source of truth, seeded by `flask seed`.

---

## Tests

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest -q     # 330 tests
cd frontend; npx vitest run                             # 15 tests
cd frontend; npm run build                              # type-check + production build
```
