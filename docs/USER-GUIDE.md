# GreenTech Real Estate Portal — Step-by-Step User Guide

A screen-by-screen walkthrough of the portal, from the very first login to
running your monthly reports. Written for the person actually operating the
system day to day — property/landlord admins, collections staff, and
accounts.

For how to install and run the app itself, see [DEPLOYMENT.md](DEPLOYMENT.md).
For the accounting rules the money side of this app enforces (why some things
are "void + repost" instead of "edit"), see [ACCOUNTING-RULES.md](ACCOUNTING-RULES.md).

---

## Contents

1. [Signing in and the basics](#1-signing-in-and-the-basics)
2. [Recommended setup order](#2-recommended-setup-order-first-time-only)
3. [Settings](#3-settings)
4. [Users & Roles](#4-users--roles)
5. [Landlords](#5-landlords)
6. [Clients](#6-clients)
7. [Properties](#7-properties)
8. [Contracts](#8-contracts)
9. [Collections](#9-collections)
10. [Expenses](#10-expenses)
11. [Profit & Loss](#11-profit--loss)
12. [Approvals](#12-approvals)
13. [Reports](#13-reports)
14. [Alerts](#14-alerts)
15. [Messages](#15-messages)
16. [Audit Log](#16-audit-log)
17. [Migration (one-time workbook import)](#17-migration-one-time-workbook-import)
18. [Common patterns across every screen](#18-common-patterns-across-every-screen)
19. [Walkthrough: a new property from zero to first receipt](#19-walkthrough-a-new-property-from-zero-to-first-receipt)
20. [Troubleshooting](#20-troubleshooting)

---

## 1. Signing in and the basics

1. Open the portal in your browser and sign in with your username/email and
   password.
2. The **sidebar** on the left is how you get everywhere. It only shows the
   screens your role has permission for.
3. The **top bar** has:
   - A global **Search** box — type a property, unit, landlord, or client
     name and jump straight to it.
   - A **notifications bell** — in-app alerts (document expiring, approval
     needed, etc.).
   - A **theme toggle** (light/dark).
   - Your **profile menu** (top right) — change password, sign out.
4. Click the **collapse** button at the bottom of the sidebar to shrink it to
   icons-only if you want more screen space.

---

## 2. Recommended setup order (first time only)

The screens depend on each other, so set the portal up in this order the
first time:

1. **Settings** — company name/logo, numbering formats, approval rules.
2. **Users & Roles** — add your staff and decide who can do what.
3. **Landlords** — the property owners you deal with.
4. **Clients** — the tenants you'll let space to.
5. **Properties** — buildings/camps/villas, linked to a landlord, with their
   floors and units generated.
6. **Contracts** — tie a client to specific units in a property.
7. From here on it's day-to-day operation: **Collections**, **Expenses**,
   **Profit & Loss**, **Reports**.

If you're moving from an existing spreadsheet, see
[§17 Migration](#17-migration-one-time-workbook-import) instead of entering
everything by hand.

---

## 3. Settings

*Sidebar → Settings.* Organized into tabs down the left of the page:

| Tab | What you set |
|---|---|
| **Company** | Company name, logo (shown in the sidebar and on printed reports/emails). |
| **Property** | Defaults used when creating properties (unit numbering style, etc.). |
| **Numbering** | The prefix/format for auto-generated codes — property codes, contract numbers, receipt/voucher numbers. |
| **Approval** | Which actions require a second person's sign-off before they take effect (contract cancellation, rent reduction, receipt void) — see [§12 Approvals](#12-approvals). |
| **Alerts** | How many days before expiry a document/agreement counts as "expiring soon" for the Alerts screen and dashboard. |
| **Email** | SMTP server details so the portal can send emails (statements, reminders). Use **Test connection** before saving. |
| **UI** | Glassmorphism on/off, compact density, table row density — cosmetic, per-install not per-user. |
| **Import** | Defaults for the P&L import wizard (ledger-to-category mapping is remembered automatically after the first import, see [§10](#10-expenses)). |
| **Security** | Password policy, session behaviour. |
| **Backup** | Trigger a backup on demand, download a previous backup, or restore from one. A backup bundles the database *and* every uploaded document into a single `.zip`. **Restore is destructive** — it replaces everything currently in the database with what's in the backup file, so use it deliberately. |
| **Audit** | Retention settings for the audit log. |
| **Notifications** | The rules engine — which events (contract expiring, cheque due, document expiring…) send a reminder, how many days in advance, and to whom. Rules are created disabled; turn on only the ones you want live. |
| **Telegram** | Connect a Telegram bot so staff-group alerts can go out there instead of/as well as email. |
| **AI** | Optional: connect Gemini/Azure OpenAI/a local model so the portal can draft reminder emails and a monthly summary for you. Entirely optional — the app works fully without it. |

Each tab has its own **Save** — changes to one tab don't touch another.

---

## 4. Users & Roles

*Sidebar → Users & Roles.*

### Add a user
1. **New user** → fill in username, email, full name, password.
2. Assign one or more **roles** (Admin, Accounts, Property Manager, etc. —
   whatever roles exist in your install).
2. Save.

### Roles & Permissions
Click **Roles & Permissions** (top right) to see/edit what each role can do —
every screen and every action (view/create/edit/deactivate/approve/export)
is a separate permission you can grant per role.

### Deactivating a user
Users are **never deleted** — click the deactivate icon on their row instead.
A deactivated user can't log in but their history (audit trail, things they
created) stays intact. By default the list only shows active users; tick
**Show deactivated** at the top of the list to see everyone.

---

## 5. Landlords

*Sidebar → Landlords.* The property owners you rent from.

### Create a landlord
1. **New landlord** → name (English, and Arabic if you have it), QID/CR
   number and expiry, mobile, email, address, contact person.
2. Save. A code (e.g. `LL-0001`) is generated automatically.

### Find a landlord
The search box filters as you type — no need to press Search. Combine with
the **status** filter and the **agreement expiry** filter (Expired / within
1, 3, or 6 months) to narrow the list. Inactive landlords are hidden by
default — tick **Show deactivated** to include them.

### A landlord's page has three tabs:
- **Overview** — their live agreements, this month's per-property P&L for
  buildings they own, and recent rent-paid vouchers.
- **Properties** — every property currently linked to this landlord, each
  a click-through to its own page.
- **Documents** — CR/QID copies, agreements, anything else on file. See
  [§18](#18-common-patterns-across-every-screen) for how uploads work,
  including tagging a document to a property at the same time.

### Editing / deactivating
Click the pencil icon on a landlord's row to edit their details. There's no
delete — set their **Status** to Inactive instead if they're no longer
active; their history (properties, agreements, payments) stays exactly as
it was.

> **Note:** a landlord's own `monthly_rent`/agreement dates fields are
> legacy — the real, current source of truth for what you owe a landlord is
> the **agreement on each property** (§7). Manage rent and dates there.

---

## 6. Clients

*Sidebar → Clients.* The tenants/companies you let space to.

### Create a client
1. **New client** → name (English/Arabic), type (Company/Individual),
   contact person, mobile, alternate mobile, email, address, CR/QID number
   and expiry.
2. Save. A code (e.g. `CL-0001`) is generated automatically.

### Find a client
Same pattern as Landlords: type-ahead search, a **status** filter
(Active/Inactive/**Blacklisted**), and **Show deactivated** (default off) to
reveal inactive/blacklisted clients.

### A client's page
- **Overview** — their contracts, balance, statement.
- **Documents** — CR/QID copies etc. (the paperclip icon on the list also
  opens this without leaving the list page).

Blacklisting a client (set status = Blacklisted) doesn't touch their
existing contracts or history — it just flags them so new contracts get a
visible warning.

---

## 7. Properties

*Sidebar → Properties.* Buildings, camps, villas, and stores.

### Create a property
1. **New property** → **Step 1: Details** — name, landlord, type (full
   building / building with store / flat building / villa / labour camp /
   store / mixed use / **compound**), address fields, ownership type,
   managed-by, remarks. Continue.
2. **Step 2: Structure** — choose whether to generate the floor/unit layout
   now (recommended):
   - **One building** — number of floors, rooms per floor, whether to
     include a ground floor ("G"), floor/unit number prefixes, default unit
     type. The preview line shows exactly how many floors/units it will
     create and what the first unit number will look like.
   - **Compound** — for a plot with two or more separate buildings sharing
     it. Add a building block per building, each with its own floor count,
     rooms per floor, and store count. Buildings get lettered automatically
     (A, B, C…) if you don't give them a code.
3. **Create**. You land straight on the new property's Units tab.

### A property's page has six tabs:
- **Overview** — address, type, ownership, the active agreement summary,
  live occupancy snapshot (occupied/empty/maintenance/blocked).
- **Rent & costs** — this property's month-by-month P&L (rent charged vs.
  collected, rent paid to the landlord, direct running costs, margin).
- **Agreement** — the landlord agreement(s) on this property. See below.
- **Floors** — add/rename/remove floors.
- **Units** — add/edit/remove individual units (type, whether it has a
  bathroom/AC, whether it's a shared facility, base rent).
- **Attachments** — documents for this property (agreements, photos,
  government paperwork). A document uploaded here that was *also* uploaded
  from a linked landlord shows an "Also on: LL-xxxx" note — it's the same
  file, not a duplicate.

### Editing the property's own details
Click **Edit** (top of the property page) for a form covering name, type,
ownership, address fields, managed-by, remarks. This is separate from the
agreement (below) and from status.

### Changing status
Click **Change status** to move a property between Active / On hold /
Maintenance / Inactive. Moving it away from Active needs a reason, and the
portal blocks the change if the property still has occupied units (it'll
tell you which ones).

### Agreements — create, renew, and amend
The **Agreement** tab keeps every agreement this property has ever had, not
just the current one:
- **New / renew** — a blank form: landlord, agreement number, start/expiry
  dates, monthly rent, deposit, payment terms, notice period, reminder
  window. Posting it automatically archives whatever agreement was active
  before (marked "Archived", not deleted — the full history stays visible
  in the table).
- **Amend agreement** (shown whenever there's an active agreement) — the
  same form, but **pre-filled with the current agreement's values**. Use
  this when you need to fix or update the rent, a date, or any other term
  on the existing deal: change only what's different and post. Behind the
  scenes this is the same "new + archive the old one" mechanism — nothing
  is silently overwritten, so you can always see what the rent used to be
  and when it changed.

### Floors & Units
Add floors/units individually from their tabs, or bulk-generate more of the
same pattern used at creation time. Each unit tracks its own type, rent,
and occupancy status (derived automatically from active contracts — you
don't set "occupied" by hand).

### Floor plan view
**Floor plan →** (top of the property page) gives a printable, visual
floor-by-floor layout of every unit and its occupancy — useful for a wall
chart or a printed handout.

---

## 8. Contracts

*Sidebar → Contracts.* Ties one client to specific units in one property,
for a dated period, at an agreed rent.

### Create a contract
1. **New contract** → pick the client, then the property, then the exact
   unit(s) from that property's live floor plan (occupied units are
   greyed out).
2. Set start date, expiry date, monthly rent, payment mode (Cash / Cheque /
   Online), security deposit, opening balance if migrating a mid-tenancy.
3. If the mode is **Cheque**, add the post-dated cheques (PDCs) covering the
   term right there in the same wizard.
4. Save. A contract number (e.g. `CON-202608-0001`) is generated.

### Find a contract
Type-ahead search matches the contract number, client name, *or* property
name. Filter by status (Active/Cancelled/Expired/Renewed), payment mode, and
expiry window (Expired / within 1, 3, or 6 months).

### A contract's page has five tabs:
- **Overview** — client, property, units held, rent, dates, pending
  approvals if any.
- **Units** — the exact units allocated, with their date ranges.
- **Cheques** — the PDC book for this contract: received → deposited →
  cleared/bounced/replaced, each a dated event.
- **History** *(amendments)* — every change to the contract's terms
  (rent change, free months, unit swaps) as a **dated amendment** — nothing
  is edited in place. This is the same principle as the property agreement
  amend flow (§7): if the rent changes partway through the term, you record
  it as an amendment with an effective date, so every past month's rent
  charge stays correct and explainable.
- **Attachments** — the signed agreement, ID copies, etc.

### Cancelling or reducing rent
Cancelling a contract or reducing its rent goes through the **Approvals**
queue if your install requires sign-off for those actions (§3 Settings →
Approval, §12). Until approved, the contract keeps working as before.

---

## 9. Collections

*Sidebar → Collections.* What clients owe, and the money coming in.

### The main list
Every client with an outstanding balance, oldest-due date, and days
overdue. **Generate rent** (top right) raises this month's rent charges for
every active contract that hasn't been charged yet — run it once at the
start of each month (or whenever you add a contract mid-month).

### Receiving a payment
Click the receipt icon on a client's row to open **Receive payment**: enter
the amount, date, mode (cash/cheque/online/adjustment), and reference. The
portal allocates it to the client's **oldest open charge first**
automatically — you can override which months it settles if needed.
Anything paid beyond what's owed sits as a credit on the client's account.

### Correcting a receipt
Receipts are never edited after posting — click **Void** with a reason, and
enter a fresh, correct receipt. The voided one stays visible (struck
through) so the trail is never broken.

### Cash due booking
*Collections → Cash due booking.* A dedicated worklist for cash-paying
tenants: this month's charge for every cash-mode contract, grouped by
property, with a banner showing whether you're inside the property's usual
5th–15th collection window. Click **Receive** on any row to post that
tenant's cash payment on the spot — it's the same receipt flow as above,
just pre-scoped to the day's collection run.

### Ageing report
*Collections → Ageing report.* Outstanding balances bucketed by how overdue
they are (current / 30 / 60 / 90+ days), per client and totalled. Exportable.

### Statement of account
Click through to any client from the main list to see their full statement:
every charge and every receipt, running balance, in date order — handy to
send a tenant directly (see [§15 Messages](#15-messages)).

---

## 10. Expenses

*Sidebar → Expenses.* Running costs and what you pay landlords. Three tabs:

### Expenses tab
- **Record expense** → category (Property cost = feeds a property's P&L, or
  Company overhead = stays at company level), property (required for
  property costs), month, amount, reference, remarks.
- **Manage categories** → the full list of expense categories. **New
  category** to add one; click a name to rename it inline; the **Active**
  pill toggles a category on/off. Categories are never deleted, only
  deactivated — a deactivated category can't be picked for a new expense
  but its history stays intact. Deactivated categories are hidden by
  default; tick **Show deactivated** to see them.
- Unallocated direct costs (property-type costs with no property attached
  yet, usually from an import) are flagged — click the link icon to assign
  one to a property.
- **Void** a posted expense with a reason if it was entered wrong; it stays
  visible struck-through and drops out of P&L totals. Correct it by posting
  a fresh one. Voided expenses are hidden by default — tick **Show voided**
  to see them.

### Landlord payments tab
- **Pay landlord** → landlord, property, rent month, payment date, amount,
  mode, reference. Generates a voucher number automatically.
- Same void-and-repost rule as expenses/receipts for corrections.

### Imports tab
Every P&L file you've imported from your accounting software, with the
period it covered and whether the file's own totals matched what got
posted. See below.

### Importing a monthly P&L file
Use this to bring in the accounting software's month-end export (typically
your *indirect/overhead* costs — salary, fuel, telephone, etc. — since
direct/property costs are usually entered per-property as above):
1. **Import P&L** → upload the file.
2. The wizard shows every ledger line it found and **checks the file's own
   printed totals against the sum of its lines** — it refuses to post if
   they don't match, so a torn or partial export can't silently under-load
   a month.
3. Map any ledger name that hasn't been seen before to a category (mappings
   are remembered, so next month's import is a two-click job).
4. Post. Everything lands as expenses for that month, each keeping the
   original ledger name as a pointer back to the source file.

---

## 11. Profit & Loss

*Sidebar → Profit & Loss.*

- **Property P&L** — for a chosen month (and optionally one property): rent
  charged, rent collected, rent paid to the landlord, every direct expense
  category as its own column, total costs, and margin — laid out exactly
  like the workbook block this replaced.
- **Company P&L** — the whole company for the month: rental income, direct
  costs, indirect/overhead costs by category, net profit.

Both are also available under **Reports** (§13) with the full export/print
toolkit.

---

## 12. Approvals

*Sidebar → Approvals.* A queue of actions that are staged but not yet in
effect, for actions your install has marked as needing a second person's
sign-off (Settings → Approval decides which ones — typically contract
cancellation, rent reduction, and receipt voids).

- Each row shows what's being requested, by whom, and why.
- **Approve** applies the change immediately. **Reject** discards the
  request — nothing changes.
- The sidebar badge shows how many are waiting.

If approvals aren't turned on for a given action type, that action just
takes effect immediately when requested — the queue only holds what's been
configured to need sign-off.

---

## 13. Reports

*Sidebar → Reports.* Every report is filterable, sortable, paginated,
printable, and exports to Excel or PDF. Grouped by category:

**Occupancy**
- *Property Occupancy Report* — every property's unit count, occupied/
  empty/maintenance/blocked breakdown, occupancy %.
- *Empty Units Report* — every currently-vacant unit, property and floor.
- *Empty Units Trend* — the same, but **as a month-by-month chart** (bar
  chart, occupied vs. empty), camp-wise or totalled, derived from contract
  history rather than a live snapshot — use this to see vacancy trending up
  or down over time, not just right now.

**Contracts**
- *Landlord Agreement Expiry Report* — every agreement, bucketed by how
  soon it expires (7/15/30/60/90 days or already expired).
- *Document Expiry Report* — CR/QID/other tracked documents nearing expiry.
- *Contract Expiry Control* — client contracts approaching their expiry.

**Money**
- *Rent Collection Report* — charges for a month, paid/unpaid, per client.
- *Ageing Report* — the same ageing buckets as Collections, as a
  standalone exportable report.
- *PDC Register* — every post-dated cheque and its current status.
- *Property Profit & Loss* / *Company Profit & Loss* — see §11.

**Control**
- *Audit Report* — a filterable export of the audit log (§16).

### Using any report
1. Open it from the Reports list.
2. Set filters at the top (month, property, status, expiry window,
   depending on the report) and **Run report**.
3. Sort by clicking a column header. Change how many rows show per page,
   or page through with the arrows at the bottom.
4. **Columns** lets you hide ones you don't need for this view.
5. **PDF** / **Excel** to export exactly what's on screen (respecting your
   filters); **Print** for a clean printed layout.

---

## 14. Alerts

*Sidebar → Alerts.* A live feed of what needs attention soon: agreements
and documents approaching expiry, and anything under active maintenance.
How far in advance something counts as "soon" is set in Settings → Alerts.
This is a read-only heads-up screen — act on what it shows from the
relevant screen (Properties, Landlords, etc.).

---

## 15. Messages

*Sidebar → Messages.* Every reminder and email the portal has sent (or
would have sent, if a rule fired but a channel wasn't configured) — a full
outbound log, so you can always answer "did the tenant get their expiry
notice?"

You can also **compose a message manually** from here — pick a client or
landlord, attach their statement of account automatically, and send.

---

## 16. Audit Log

*Sidebar → Audit Log.* Every create, edit, void, approval, and status
change across the whole portal — who did it, when, and (for edits) the
before/after values side by side. Filterable by module, action, user, and
date range. This is the ultimate answer to "who changed this and when" —
nothing in the app bypasses it.

---

## 17. Migration (one-time workbook import)

*Sidebar → Migration.* For bringing your existing tracking spreadsheet in
wholesale instead of typing everything by hand — a one-time, guided
operation restricted to whoever manages Settings.

1. **Parse** — upload the workbook. The portal reads it and reports exactly
   what it understood: landlords, properties, tenants, rent history — and
   flags anything it couldn't confidently match (a fuzzy landlord-name
   match, an unusual date) for you to look at before anything is written.
2. **Plan** — apply any corrections and see the *exact* set of records that
   would be created, still without writing anything.
3. **Commit** — writes it all in one transaction: either the whole import
   lands, or none of it does. Re-running against a database that already
   has data from a previous import reuses what matches (by name) and adds
   only what's new, so a partial or corrected re-run is safe.
4. **Reconcile** — after committing, run this to compare the app's own
   monthly figures against the workbook's, month by month, to confirm
   nothing was lost or miscalculated in translation.

This is meant to be run once (or re-run to correct/extend a first pass) —
day-to-day data entry after that goes through the normal screens above.

---

## 18. Common patterns across every screen

A few conventions repeat everywhere in the portal, so once you know them
you know most of the app:

- **Search boxes filter as you type** (a short pause after you stop typing)
  on every list — Landlords, Clients, Properties, Contracts. Press Enter or
  click Search for an instant refresh.
- **Nothing is ever hard-deleted.** Master data (landlords, clients,
  properties, expense categories, users) is **deactivated**, not removed —
  its history stays intact and nothing that references it breaks. Every
  such list hides deactivated rows by default; tick **Show deactivated** to
  see them. Explicit status filters (e.g. picking "Inactive" specifically)
  always work regardless of that checkbox.
- **Financial records are corrected by void + repost, not editing.**
  Receipts, landlord payments, and expenses can't have their amount, date,
  or party changed after posting — you void the wrong one (with a reason,
  it stays visible struck-through) and post a correct one. This keeps the
  books always reconstructable. See [ACCOUNTING-RULES.md](ACCOUNTING-RULES.md).
- **Terms that change over time (agreements, contract rent) are corrected
  by amendment, not editing.** A new dated record is created and the old
  one is archived — you always keep the answer to "what was the rent last
  March." The property Agreement tab and a contract's History tab both work
  this way; look for an **Amend** button pre-filled with the current values.
- **Attachments can be shared.** A document uploaded on a landlord can be
  tagged to also show up on one of their properties (an "Also show on
  property" option in the upload dialog) — one upload, no duplicate file.
  Click the eye icon to preview an image or PDF inline; the download icon
  always saves a copy.
- **Tables paginate and sort.** Click a column header to sort; use the
  rows-per-page control and prev/next buttons at the bottom of any table.
- **Everything you can see is scoped by your role's permissions** — if a
  button or a whole sidebar item is missing, your role doesn't have that
  permission (an admin can grant it under Users & Roles → Roles &
  Permissions).

---

## 19. Walkthrough: a new property from zero to first receipt

Putting the whole flow together, start to finish:

1. **Landlords** → New landlord → enter the owner's details → Save.
2. **Properties** → New property → Details (pick that landlord, fill
   address) → Continue → Structure (choose One building or Compound, set
   floors/rooms) → Create. The floors and units are generated for you.
3. On the new property's **Agreement** tab → New / renew → set the rent
   you've agreed to pay the landlord, the term, and the deposit → Post.
4. **Clients** → New client → enter the tenant's details → Save.
5. **Contracts** → New contract → pick the client and this property → pick
   the exact unit(s) from the live floor plan → set rent, dates, payment
   mode (add PDCs now if Cheque) → Save.
6. **Collections** → **Generate rent** to raise this month's charge for the
   new contract.
7. When the tenant pays, find them in **Collections** (or **Cash due
   booking** if they pay cash) → **Receive payment** → enter the amount →
   Post. Their balance updates immediately, allocated oldest-charge-first.
8. Check **Rent & costs** on the property page, or **Reports → Property
   Profit & Loss**, to see the month's numbers for this property alongside
   everything else.

---

## 20. Troubleshooting

- **A button/page I expect isn't there.** Your role likely doesn't have
  that permission — ask an admin to grant it under Users & Roles → Roles &
  Permissions.
- **I made a mistake on a receipt/payment/expense.** Void it (with a
  reason) and post a correct one — see §18. There is no edit for posted
  financial records, by design.
- **I need to fix an agreement's rent or dates.** Use **Amend agreement**
  on the property's Agreement tab (§7), not a raw edit — it keeps the old
  terms on record.
- **A landlord/client/category I need is missing from a picker.** It may be
  deactivated. Reactivate it from its list page (tick **Show deactivated**
  to find it, then flip its status back).
- **Something looks wrong across the whole month.** Check **Audit Log**
  (§16) filtered to that date range — every change that could explain it is
  there with a before/after.
- **I need to undo something bigger than one record.** Settings → Backup
  lets you restore a previous backup — this replaces the *entire* database,
  so use it only as a last resort and only if you're sure.
