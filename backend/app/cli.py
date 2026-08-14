import os
import click
from flask import Flask

from .extensions import db
from .models import User, Role, Permission
from .services.permissions import PERMISSION_CATALOG, ROLE_PRESETS, permission_code


def _seed_permissions() -> dict[str, Permission]:
    existing = {p.code: p for p in Permission.query.all()}
    for module, action, desc in PERMISSION_CATALOG:
        code = permission_code(module, action)
        if code in existing:
            p = existing[code]
            if p.description != desc:
                p.description = desc
            continue
        p = Permission(code=code, module=module, action=action, description=desc)
        db.session.add(p)
        existing[code] = p
    db.session.flush()
    return existing


def _seed_roles(perm_index: dict[str, Permission]) -> dict[str, Role]:
    existing = {r.code: r for r in Role.query.all()}
    all_perms = list(perm_index.values())
    for code, cfg in ROLE_PRESETS.items():
        role = existing.get(code)
        if role is None:
            role = Role(code=code, name=cfg["name"], description=cfg["description"],
                        is_system=True, is_active=True)
            db.session.add(role)
            existing[code] = role
        else:
            role.name = cfg["name"]
            role.description = cfg["description"]
            role.is_system = True
        codes = cfg["permissions"]
        if codes == ["*"]:
            role.permissions = all_perms
        else:
            role.permissions = [perm_index[c] for c in codes if c in perm_index]
    db.session.flush()
    return existing


def _seed_super_user(role_index: dict[str, Role]) -> User:
    username = (os.getenv("SUPERUSER_USERNAME") or "admin").lower()
    email = (os.getenv("SUPERUSER_EMAIL") or "admin@greentech.local").lower()
    password = os.getenv("SUPERUSER_PASSWORD") or "ChangeMe123!"

    user = User.query.filter(db.func.lower(User.username) == username).first()
    if user is None:
        user = User(
            username=username,
            email=email,
            full_name="System Administrator",
            is_active=True,
            is_super_user=True,
        )
        user.set_password(password)
        user.roles = [role_index["super_user"]] if "super_user" in role_index else []
        db.session.add(user)
        click.echo(f"  -> created super user '{username}' (password from SUPERUSER_PASSWORD or default 'ChangeMe123!')")
    else:
        user.is_super_user = True
        user.is_active = True
        click.echo(f"  -> super user '{username}' already exists; ensured flags")
    return user


# Categories named as the accounting software's P&L names them, so the
# first import maps almost everything without the operator typing.
EXPENSE_CATEGORIES: list[tuple[str, str, str, bool]] = [
    # (code, name, kind, is_property_wise)
    ("RENT_RECEIVED", "Rent Received", "income", False),
    ("OTHER_INCOME", "Other Income", "income", False),
    ("RENT_PAID", "Rent Paid", "direct", True),
    ("SEWAGE", "Sewage Removal and Cleaning", "direct", True),
    ("ELECTRICITY_CAMP", "Electricity and Water for Camp", "direct", True),
    ("GENERAL_CAMP", "General Expense for Camp", "direct", True),
    ("MAINT_CLEANING", "Maintenance and Cleaning", "direct", True),
    ("BANK_CHARGES", "Bank Charges", "indirect", False),
    ("REAL_ESTATE_COMMISSION", "Real Estate Commission", "indirect", False),
    ("ELECTRICITY_OFFICE", "Electricity and Water for Office", "indirect", False),
    ("FUEL", "Fuel Charges", "indirect", False),
    ("AUDIT", "Auditing Charges", "indirect", False),
    ("VEHICLE_HIRE", "Vehicle Hire Rent", "indirect", False),
    ("SALARY", "Salary and Allowances", "indirect", False),
    ("DISCOUNT_ALLOWED", "Discount Allowed", "indirect", False),
    ("SPONSOR_FEE", "Sponsor Fee", "indirect", False),
    ("COMMISSION", "Commission", "indirect", False),
    ("MESS_ACCOMMODATION", "Mess and Accommodation", "indirect", False),
    ("DEPRECIATION", "Depreciation", "indirect", False),
    ("VISA", "Emigration and Visa Charges", "indirect", False),
    ("LEAVE_SALARY", "Leave Salary", "indirect", False),
    ("GRATUITY", "Gratuity", "indirect", False),
    ("CORPORATE_OFFICE", "Corporate Office Expense", "indirect", False),
    ("VEHICLE_INSURANCE", "Vehicle Insurance and Maintenance", "indirect", False),
    ("AIR_FARE", "Air Fare Charges", "indirect", False),
    ("TELEPHONE", "Telephone Charges", "indirect", False),
    ("LEGAL", "Legal Charges", "indirect", False),
    ("TRAVELLING", "Travelling Expenses", "indirect", False),
    ("STAFF_RELATED", "Staff Related Expense", "indirect", False),
    ("BALADIYA_FINE", "Baladiya Fine and Other", "indirect", False),
    ("OTHER_ALLOWANCE", "Other Allowance", "indirect", False),
    ("PRINTING_STATIONERY", "Printing and Stationery", "indirect", False),
]

# The export spells some ledgers differently from the category name
# (and misspells a few). Pre-map them so month one is friction-free.
LEDGER_ALIASES: dict[str, str] = {
    "RENT RECEIVED": "RENT_RECEIVED",
    "OTHER INCOME": "OTHER_INCOME",
    "RENT PAID": "RENT_PAID",
    "SEAWAGE REMOVAL AND CLEANING": "SEWAGE",
    "ELECTRICITY AND WATER FOR CAMP": "ELECTRICITY_CAMP",
    "GENERAL EXPENCE FOR CAMP": "GENERAL_CAMP",
    "BANK CHARGES": "BANK_CHARGES",
    "REAL ESTATE COMMISSION": "REAL_ESTATE_COMMISSION",
    "ELECTRICITY AND WATER FOR OFFICE": "ELECTRICITY_OFFICE",
    "FUEL CHARGES": "FUEL",
    "AUDITING CHARGES": "AUDIT",
    "VEHICLE HIRE RENT": "VEHICLE_HIRE",
    "SALARY AND ALLOWANCES": "SALARY",
    "DISCOUNT ALLOWED": "DISCOUNT_ALLOWED",
    "SPONSER FEE": "SPONSOR_FEE",
    "COMMISSION": "COMMISSION",
    "MESS AND ACCOMMODATION": "MESS_ACCOMMODATION",
    "DEPRECIATION A/C": "DEPRECIATION",
    "EMIGRATION AND VISA CHARGE": "VISA",
    "LEAVE SALARY": "LEAVE_SALARY",
    "GRATUITY": "GRATUITY",
    "CORPORATE OFFICE EXPENCE": "CORPORATE_OFFICE",
    "VEHICLE INSURANCE AND MAINTANANCE": "VEHICLE_INSURANCE",
    "AIR FAIR CHARGES": "AIR_FARE",
    "TELEPHONE CHARGES": "TELEPHONE",
    "LEGAL CHARGES": "LEGAL",
    "TRAVELLING EXPENSES": "TRAVELLING",
    "STAFF RELATED EXPENSE": "STAFF_RELATED",
    "BALADIYA FINE AND OTHER": "BALADIYA_FINE",
    "OTHER ALLOWENCE": "OTHER_ALLOWANCE",
    "PRINTING  AND STATIONERY": "PRINTING_STATIONERY",
    "PRINTING AND STATIONERY": "PRINTING_STATIONERY",
}


def _seed_property_types() -> None:
    from .models import PropertyType
    from .routes.properties import DEFAULT_PROPERTY_TYPES

    by_code = {t.code: t for t in PropertyType.query.all()}
    for code, name in DEFAULT_PROPERTY_TYPES:
        if code not in by_code:
            db.session.add(PropertyType(code=code, name=name))
    db.session.flush()


def _seed_expense_categories() -> None:
    from .models import ExpenseCategory, LedgerMapping

    by_code = {c.code: c for c in ExpenseCategory.query.all()}
    for code, name, kind, property_wise in EXPENSE_CATEGORIES:
        row = by_code.get(code)
        if row is None:
            row = ExpenseCategory(code=code, name=name, kind=kind,
                                  is_property_wise=property_wise)
            db.session.add(row)
            by_code[code] = row
        else:
            row.name, row.kind, row.is_property_wise = name, kind, property_wise
    db.session.flush()

    existing = {m.ledger_name.upper() for m in LedgerMapping.query.all()}
    for ledger, code in LEDGER_ALIASES.items():
        if ledger in existing:
            continue
        category = by_code.get(code)
        if category is not None:
            db.session.add(LedgerMapping(ledger_name=ledger, category_id=category.id))
    db.session.flush()
    click.echo(f"  -> {len(by_code)} categories, {len(LEDGER_ALIASES)} ledger mappings")


def register_commands(app: Flask) -> None:
    @app.cli.command("wait-for-db")
    @click.option("--timeout", default=60, show_default=True,
                  help="Seconds to keep retrying before giving up.")
    def wait_for_db(timeout):
        """Block until the database accepts a connection.

        Postgres may finish starting a few seconds after its service
        manager marks it Started. Calling SELECT 1 in a polling loop
        avoids the backend crash-looping on a transient connection
        refused while the DB is still warming up.
        """
        import time
        from sqlalchemy import text

        deadline = time.time() + timeout
        attempt = 0
        while True:
            attempt += 1
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                click.echo(f"Database reachable (attempt {attempt}).")
                return
            except Exception as exc:  # noqa: BLE001 — any driver/DNS error retries
                if time.time() >= deadline:
                    click.echo(f"Database not reachable after {timeout}s: {exc}")
                    raise SystemExit(1)
                click.echo(f"  waiting for database (attempt {attempt})...")
                time.sleep(2)

    @app.cli.command("init-db")
    def init_db():
        """Create all tables from the SQLAlchemy models.

        Use this for fresh deployments (first-time install, CI tests) where
        no Alembic migration history exists. The command is idempotent: if
        a table is already present, SQLAlchemy leaves it alone. After
        running, switch to `flask db upgrade` for subsequent schema changes
        once you've initialised migrations.
        """
        click.echo("Creating any missing tables from models...")
        db.create_all()
        click.echo("Done. Run `flask --app wsgi seed` next.")

    @app.cli.command("run-job")
    @click.argument("name")
    def run_job(name: str):
        """Synchronously run a registered Celery task by short name
        (no broker required). Lets operators verify a task's logic
        without spinning up a worker. Examples:
            flask run-job daily_expiry_sweep
            flask run-job recompute_reminder_summary
        """
        from .celery_app import celery
        # Match either the bare function name or the full dotted task name.
        candidates = [t for tname, t in celery.tasks.items()
                      if tname.endswith("." + name) or tname == name]
        if not candidates:
            click.echo(f"Unknown task '{name}'. Available:")
            for tname in sorted(celery.tasks):
                if tname.startswith("app."):
                    click.echo(f"  {tname}")
            raise SystemExit(1)
        result = candidates[0].apply().get()
        click.echo(f"ok: {result}")

    @app.cli.command("dump-openapi")
    @click.option("--output", "-o", default="-",
                  help="Output file path; '-' (default) prints to stdout.")
    def dump_openapi(output: str):
        """Emit the OpenAPI 3 spec as JSON.

        Used by the frontend codegen script (`npm run gen-api-types`)
        to drive openapi-typescript without booting a full HTTP server.
        """
        import json
        spec = app.spec
        # apiflask.app.spec is already a dict in 2.x; older versions
        # returned a Spec object. Handle both defensively.
        if hasattr(spec, "to_dict"):
            spec = spec.to_dict()
        payload = json.dumps(spec, indent=2, sort_keys=True, default=str)
        if output == "-":
            click.echo(payload)
        else:
            with open(output, "w") as fh:
                fh.write(payload)
            click.echo(f"wrote {output}")

    @app.cli.command("migrate-all")
    def migrate_all():
        """Run every schema delta in order, idempotently.

        Safe to invoke on every boot — each delta checks the live schema
        first, so a fresh install (already at head via `init-db`) sees
        every check pass, and an older install catches up.

        Append new deltas at the BOTTOM as later phases land.
        """
        click.echo("Running all phase migrations idempotently...")
        bind = db.engine
        from sqlalchemy import inspect, text

        with bind.begin() as conn:
            insp = inspect(bind)

            # --- Phase 0.5: the occupancy atom was renamed Room -> Unit.
            # Installs created before the rename carry a `rooms` table with
            # room_* columns; move them across rather than dropping data.
            if insp.has_table("rooms") and not insp.has_table("units"):
                conn.execute(text("ALTER TABLE rooms RENAME TO units"))
                for old, new in (
                    ("room_number", "unit_number"),
                    ("room_name", "unit_name"),
                    ("room_type", "unit_type"),
                ):
                    cols = {c["name"] for c in inspect(conn).get_columns("units")}
                    if old in cols and new not in cols:
                        conn.execute(text(f"ALTER TABLE units RENAME COLUMN {old} TO {new}"))
                click.echo("  ~ rooms -> units (table + columns)")

            # Maintenance records referenced the old entity type name.
            if insp.has_table("maintenance_records"):
                conn.execute(text(
                    "UPDATE maintenance_records SET entity_type = 'unit' "
                    "WHERE entity_type = 'room'"
                ))

            # --- Phase 1: Arabic names + document expiry on the masters.
            if insp.has_table("landlords"):
                cols = {c["name"] for c in insp.get_columns("landlords")}
                if "name_ar" not in cols:
                    conn.execute(text("ALTER TABLE landlords ADD COLUMN name_ar VARCHAR(160)"))
                    click.echo("  + landlords.name_ar")
                if "qid_cr_expiry_date" not in cols:
                    conn.execute(text("ALTER TABLE landlords ADD COLUMN qid_cr_expiry_date DATE"))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_landlords_qid_cr_expiry_date "
                        "ON landlords (qid_cr_expiry_date)"
                    ))
                    click.echo("  + landlords.qid_cr_expiry_date")

            # --- Phase 1: the Client master (tenants we let units to).
            if not insp.has_table("clients"):
                from .models import Client
                Client.__table__.create(bind=conn)
                click.echo("  + clients")

            # --- Phase 2: contracts, dated unit allocation, amendments, PDC.
            for model_name, table in (
                ("ClientContract", "client_contracts"),
                ("ContractUnit", "contract_units"),
                ("ContractAmendment", "contract_amendments"),
                ("Cheque", "cheques"),
                ("ChequeEvent", "cheque_events"),
            ):
                if not insp.has_table(table):
                    from . import models as _models
                    getattr(_models, model_name).__table__.create(bind=conn)
                    click.echo(f"  + {table}")

            # --- Phase 3: rent charges and receipts.
            for model_name, table in (
                ("RentCharge", "rent_charges"),
                ("Receipt", "receipts"),
                ("ReceiptAllocation", "receipt_allocations"),
            ):
                if not insp.has_table(table):
                    from . import models as _models
                    getattr(_models, model_name).__table__.create(bind=conn)
                    click.echo(f"  + {table}")

            # --- Phase 4: expenses, landlord payments, P&L import.
            for model_name, table in (
                ("ExpenseCategory", "expense_categories"),
                ("LedgerMapping", "ledger_mappings"),
                ("ExpenseImportBatch", "expense_import_batches"),
                ("Expense", "expenses"),
                ("LandlordPayment", "landlord_payments"),
            ):
                if not insp.has_table(table):
                    from . import models as _models
                    getattr(_models, model_name).__table__.create(bind=conn)
                    click.echo(f"  + {table}")

            # --- Phase 1: document identity + expiry on attachments.
            if insp.has_table("attachments"):
                cols = {c["name"] for c in insp.get_columns("attachments")}
                if "doc_number" not in cols:
                    conn.execute(text("ALTER TABLE attachments ADD COLUMN doc_number VARCHAR(64)"))
                    click.echo("  + attachments.doc_number")
                if "issue_date" not in cols:
                    conn.execute(text("ALTER TABLE attachments ADD COLUMN issue_date DATE"))
                    click.echo("  + attachments.issue_date")
                if "expiry_date" not in cols:
                    conn.execute(text("ALTER TABLE attachments ADD COLUMN expiry_date DATE"))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_attachments_expiry_date "
                        "ON attachments (expiry_date)"
                    ))
                    click.echo("  + attachments.expiry_date")

            # --- Phase 5: deferred approvals carry the arguments of the
            # action they are holding, replayed when an approver says yes.
            if insp.has_table("approval_requests"):
                cols = {c["name"] for c in insp.get_columns("approval_requests")}
                if "payload" not in cols:
                    conn.execute(text("ALTER TABLE approval_requests ADD COLUMN payload JSONB"))
                    click.echo("  + approval_requests.payload")

            # --- Phase 7: notification rules and the outbound log.
            for model_name, table in (
                ("NotificationRule", "notification_rules"),
                ("OutboundMessage", "outbound_messages"),
            ):
                if not insp.has_table(table):
                    from . import models as _models
                    getattr(_models, model_name).__table__.create(bind=conn)
                    click.echo(f"  + {table}")

            # --- Search/attachments/expenses pass: an attachment uploaded
            # on one entity can also be tagged onto another (e.g. a
            # landlord doc that also belongs to one of their properties)
            # without a second upload.
            if not insp.has_table("attachment_links"):
                from . import models as _models
                _models.AttachmentLink.__table__.create(bind=conn)
                click.echo("  + attachment_links")

            # --- Expense void support, mirroring LandlordPayment so a
            # posted expense is corrected by void + repost, never edited.
            if insp.has_table("expenses"):
                cols = {c["name"] for c in insp.get_columns("expenses")}
                if "status" not in cols:
                    conn.execute(text(
                        "ALTER TABLE expenses ADD COLUMN status VARCHAR(12) "
                        "NOT NULL DEFAULT 'posted'"))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_expenses_status "
                        "ON expenses (status)"))
                    click.echo("  + expenses.status")
                if "void_reason" not in cols:
                    conn.execute(text("ALTER TABLE expenses ADD COLUMN void_reason VARCHAR(160)"))
                    click.echo("  + expenses.void_reason")
                if "voided_at" not in cols:
                    conn.execute(text("ALTER TABLE expenses ADD COLUMN voided_at DATE"))
                    click.echo("  + expenses.voided_at")
                if "voided_by" not in cols:
                    conn.execute(text("ALTER TABLE expenses ADD COLUMN voided_by INTEGER"))
                    click.echo("  + expenses.voided_by")

            # --- Unit size (free text: room dimensions like "4/4", or a
            # store/shop's floor area like "450 Sqm").
            if insp.has_table("units"):
                cols = {c["name"] for c in insp.get_columns("units")}
                if "size" not in cols:
                    conn.execute(text("ALTER TABLE units ADD COLUMN size VARCHAR(32)"))
                    click.echo("  + units.size")

            # --- Contract dates-correction amendment payload.
            if insp.has_table("contract_amendments"):
                cols = {c["name"] for c in insp.get_columns("contract_amendments")}
                for col in ("old_start_date", "new_start_date", "old_expiry_date", "new_expiry_date"):
                    if col not in cols:
                        conn.execute(text(f"ALTER TABLE contract_amendments ADD COLUMN {col} DATE"))
                        click.echo(f"  + contract_amendments.{col}")

            # --- Property Types master (replaces the hardcoded set that
            # used to live in routes/properties.py). Seeded by `flask seed`.
            if not insp.has_table("property_types"):
                from . import models as _models
                _models.PropertyType.__table__.create(bind=conn)
                click.echo("  + property_types")

            # --- Landlord contracts get client-contract parity: per-unit
            # allocation, amendments, a proper status. `property_agreements`
            # already had `is_active`; it becomes a generated column below
            # so it can never drift from the new `status`.
            if insp.has_table("property_agreements"):
                cols = {c["name"] for c in insp.get_columns("property_agreements")}
                if "status" not in cols:
                    conn.execute(text(
                        "ALTER TABLE property_agreements "
                        "ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"))
                    # Preserve today's is_active meaning exactly: the nightly
                    # sweep (tasks/expiry.py) only ever flips renewal_status,
                    # never is_active, so a lapsed-but-unrenewed agreement
                    # has always stayed "current". Map that history in.
                    conn.execute(text("""
                        UPDATE property_agreements SET status = CASE
                          WHEN is_active AND expiry_date < CURRENT_DATE THEN 'expired'
                          WHEN is_active                                THEN 'active'
                          ELSE 'renewed'
                        END"""))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_property_agreements_status_expiry "
                        "ON property_agreements (status, expiry_date)"))
                    click.echo("  + property_agreements.status (backfilled from is_active)")

                for col, ddl in (
                    ("contract_number",     "VARCHAR(40)"),
                    ("cancellation_date",   "DATE"),
                    ("cancellation_reason", "VARCHAR(160)"),
                    ("renewed_to_id",       "INTEGER REFERENCES property_agreements(id) ON DELETE SET NULL"),
                    ("payment_mode",        "VARCHAR(8) NOT NULL DEFAULT 'cheque'"),
                    ("opening_balance",     "NUMERIC(12,2) NOT NULL DEFAULT 0"),
                ):
                    if col not in cols:
                        conn.execute(text(f"ALTER TABLE property_agreements ADD COLUMN {col} {ddl}"))
                        click.echo(f"  + property_agreements.{col}")

                # Deterministic + idempotent (id-derived), so a re-run is a
                # no-op once every row has one.
                conn.execute(text(
                    "UPDATE property_agreements "
                    "SET contract_number = 'LCON-' || LPAD(id::text, 6, '0') "
                    "WHERE contract_number IS NULL"))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_property_agreements_contract_number "
                    "ON property_agreements (contract_number)"))

                # is_active -> generated column (Postgres 12+). Drop +
                # re-add is the only way to add GENERATED ALWAYS AS to an
                # existing column; safe here because the whole delta runs
                # inside one transaction (bind.begin()) and status is
                # already backfilled above. Guarded by reflecting whether
                # it's already generated, so a re-run is a no-op.
                pgver = int(conn.execute(text("SHOW server_version_num")).scalar())
                live_cols = {c["name"]: c for c in inspect(conn).get_columns("property_agreements")}
                already_generated = bool(live_cols.get("is_active", {}).get("computed"))
                if pgver >= 120000 and "is_active" in live_cols and not already_generated:
                    conn.execute(text("ALTER TABLE property_agreements DROP COLUMN is_active"))
                    conn.execute(text(
                        "ALTER TABLE property_agreements ADD COLUMN is_active BOOLEAN "
                        "GENERATED ALWAYS AS (status IN ('active', 'expired')) STORED"))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_property_agreements_active_expiry "
                        "ON property_agreements (is_active, expiry_date)"))
                    click.echo("  ~ property_agreements.is_active is now derived from status")
                elif pgver < 120000:
                    click.echo("  ! PG<12: is_active stays a plain column, kept in sync by the service layer")

            for model_name, table in (
                ("LandlordContractUnit",      "landlord_contract_units"),
                ("LandlordContractAmendment", "landlord_contract_amendments"),
            ):
                if not insp.has_table(table):
                    from . import models as _models
                    getattr(_models, model_name).__table__.create(bind=conn)
                    click.echo(f"  + {table}")

            if insp.has_table("property_agreements"):
                dup = conn.execute(text(
                    "SELECT count(*) FROM (SELECT property_id FROM property_agreements "
                    "WHERE status='active' GROUP BY property_id HAVING count(*)>1) x")).scalar()
                norent = conn.execute(text(
                    "SELECT count(*) FROM property_agreements "
                    "WHERE status IN ('active','expired') AND monthly_rent IS NULL")).scalar()
                if dup:
                    click.echo(f"  ! {dup} propert(ies) have more than one active landlord contract")
                if norent:
                    click.echo(f"  ! {norent} live landlord contract(s) have no monthly_rent — dues will skip them")

            # --- Landlord dues ledger: what's owed to a landlord per
            # property per month, mirroring rent_charges/receipt_allocations
            # on the client side. `landlord_payments.contract_id` is added
            # first so the new tables' FKs have somewhere to point.
            if insp.has_table("landlord_payments"):
                cols = {c["name"] for c in insp.get_columns("landlord_payments")}
                if "contract_id" not in cols:
                    conn.execute(text(
                        "ALTER TABLE landlord_payments ADD COLUMN contract_id INTEGER "
                        "REFERENCES property_agreements(id) ON DELETE SET NULL"))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_landlord_payments_contract_id "
                        "ON landlord_payments (contract_id)"))
                    click.echo("  + landlord_payments.contract_id")

            for model_name, table in (
                ("LandlordCharge",            "landlord_charges"),
                ("LandlordPaymentAllocation", "landlord_payment_allocations"),
            ):
                if not insp.has_table(table):
                    from . import models as _models
                    getattr(_models, model_name).__table__.create(bind=conn)
                    click.echo(f"  + {table}")

            # --- Race-safe document numbering (services/numbering.py),
            # needed before the bulk entry screen can batch-post many
            # receipts/vouchers in one transaction without colliding.
            if not insp.has_table("number_sequences"):
                from . import models as _models
                _models.NumberSequence.__table__.create(bind=conn)
                click.echo("  + number_sequences")

            # --- Bilingual agreement generation: signatory fields on the
            # landlord/client masters (the named individual who signs, with
            # their own personal ID — distinct from qid_cr_number, the
            # company's CR/QID), and the generated_agreements table itself,
            # a dated, immutable drafting snapshot mirroring how
            # ContractAmendment/LandlordContractAmendment are never edited
            # in place.
            for table_name in ("landlords", "clients"):
                if insp.has_table(table_name):
                    cols = {c["name"] for c in insp.get_columns(table_name)}
                    for col, ddl in (
                        ("signatory_name",      "VARCHAR(160)"),
                        ("signatory_name_ar",   "VARCHAR(160)"),
                        ("signatory_id_number", "VARCHAR(64)"),
                        ("signatory_title",     "VARCHAR(80)"),
                        ("signatory_mobile",    "VARCHAR(32)"),
                    ):
                        if col not in cols:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col} {ddl}"))
                            click.echo(f"  + {table_name}.{col}")

            if not insp.has_table("generated_agreements"):
                from . import models as _models
                _models.GeneratedAgreement.__table__.create(bind=conn)
                click.echo("  + generated_agreements")

        click.echo("Done.")

    @app.cli.group("landlord-dues")
    def landlord_dues_group():
        """Landlord dues ledger: generate monthly charges, reconcile
        already-posted payments against them."""

    def _system_actor():
        actor = User.query.filter_by(is_super_user=True).order_by(User.id).first()
        if actor is None:
            click.echo("No super user found to attribute this run to. Run `flask seed` first.")
            raise SystemExit(1)
        return actor

    @landlord_dues_group.command("generate")
    @click.option("--upto", default=None, help="YYYY-MM-DD, default today.")
    @click.option("--property-id", type=int, default=None)
    @click.option("--commit", is_flag=True, default=False,
                  help="Write the generated charges. Without this, it's a dry run.")
    def landlord_dues_generate(upto, property_id, commit):
        """Generate this month's (and every unbooked past month's) charge
        for every live landlord contract. Idempotent — never touches a
        month that already has money against it. Contracts with no rent
        figure are skipped, not raised."""
        import json
        from datetime import date
        from .services import landlord_rent as lr_service

        actor = _system_actor()
        upto_date = date.fromisoformat(upto) if upto else date.today()
        counts = lr_service.generate_all(upto=upto_date, actor=actor, property_id=property_id)
        if commit:
            db.session.commit()
        else:
            db.session.rollback()
        click.echo(json.dumps(counts, indent=2))
        click.echo("(dry run — nothing written; pass --commit to write)" if not commit else "Committed.")

    @landlord_dues_group.command("reconcile")
    @click.option("--upto", default=None, help="YYYY-MM-DD, default today.")
    @click.option("--commit", is_flag=True, default=False,
                  help="Write the allocations. Without this, it's a dry run.")
    def landlord_dues_reconcile(upto, commit):
        """Match already-posted landlord payments against open charges
        within (landlord_id, property_id) so one building's cheque never
        settles another building's arrear.

        Each payment already carries the `period_month` it was recorded
        for (from the original import or manual entry), so that month's
        charge is matched first — a payment tagged "March" settles March,
        not whatever month happens to be oldest. Only a payment's
        leftover, if any, falls through to the oldest still-open charge.
        Without this same-month pass, a contract with any older backlog
        (rent charges now exist for its full history back to its start
        date, not just recent months) would pull every payment backward
        to pay off the oldest debt first, making recent months look
        unpaid even though the payment recorded for that month exists.

        Existing allocations are left alone; only a payment's unallocated
        balance is matched. Prints a per-property-per-month due/paid/
        variance table. Requires --commit to actually write anything."""
        from datetime import date
        from .models import LandlordCharge, LandlordPayment, Property
        from .services import landlord_rent as lr_service
        from .services.expenses import _apply_to_landlord_charge

        actor = _system_actor()
        upto_date = date.fromisoformat(upto) if upto else date.today()

        pairs = (
            db.session.query(LandlordPayment.landlord_id, LandlordPayment.property_id)
            .filter(LandlordPayment.status == "posted")
            .distinct().all()
        )
        matched = 0
        for landlord_id, property_id in pairs:
            payments = (
                LandlordPayment.query
                .filter_by(landlord_id=landlord_id, property_id=property_id, status="posted")
                .order_by(LandlordPayment.payment_date.asc(), LandlordPayment.id.asc())
                .all()
            )
            for payment in payments:
                remaining = payment.unallocated()
                if remaining <= 0:
                    continue
                already = {a.charge_id for a in (payment.allocations or [])}

                same_month = (
                    LandlordCharge.query
                    .filter_by(landlord_id=landlord_id, property_id=property_id,
                              period_month=lr_service.month_start(payment.period_month))
                    .filter(LandlordCharge.status.in_(("open", "part_paid")))
                    .first()
                )
                if same_month is not None and same_month.id not in already:
                    applied = _apply_to_landlord_charge(payment, same_month, remaining,
                                                        manual=True, actor=actor)
                    if applied > 0:
                        matched += 1
                    remaining = round(remaining - applied, 2)
                    already.add(same_month.id)

                for charge in lr_service.open_charges_for(landlord_id, property_id, upto=upto_date):
                    if remaining <= 0:
                        break
                    if charge.id in already:
                        continue
                    applied = _apply_to_landlord_charge(payment, charge, remaining,
                                                        manual=False, actor=actor)
                    if applied > 0:
                        matched += 1
                    remaining = round(remaining - applied, 2)

        # Report due | paid | variance per property per month, reflecting
        # the allocation just simulated above (visible in-session either way).
        rows = (
            db.session.query(LandlordCharge.property_id, LandlordCharge.period_month,
                             db.func.sum(LandlordCharge.amount),
                             db.func.sum(LandlordCharge.allocated))
            .filter(LandlordCharge.period_month <= lr_service.month_start(upto_date))
            .group_by(LandlordCharge.property_id, LandlordCharge.period_month)
            .order_by(LandlordCharge.property_id, LandlordCharge.period_month)
            .all()
        )
        prop_codes = {p.id: p.code for p in Property.query.all()}
        click.echo(f"{'property':<10} {'month':<10} {'due':>12} {'paid':>12} {'variance':>12}")
        for pid, month, due, paid in rows:
            due, paid = float(due or 0), float(paid or 0)
            click.echo(f"{prop_codes.get(pid, pid):<10} {month.isoformat():<10} "
                      f"{due:>12.2f} {paid:>12.2f} {due - paid:>12.2f}")
        click.echo(f"\n{matched} allocation(s) matched across {len(pairs)} landlord/property pair(s).")

        if commit:
            db.session.commit()
            click.echo("Committed.")
        else:
            db.session.rollback()
            click.echo("(dry run — nothing written; pass --commit to write)")

    @app.cli.command("seed")
    def seed():
        """Seed permissions, roles, and the default super user."""
        click.echo("Seeding permissions...")
        perm_index = _seed_permissions()
        click.echo(f"  -> {len(perm_index)} permissions present")

        click.echo("Seeding roles...")
        role_index = _seed_roles(perm_index)
        click.echo(f"  -> {len(role_index)} roles present")

        click.echo("Seeding super user...")
        _seed_super_user(role_index)

        click.echo("Seeding expense categories...")
        _seed_expense_categories()

        click.echo("Seeding property types...")
        _seed_property_types()

        click.echo("Seeding system settings...")
        from .services import settings as settings_service
        settings_service.seed_defaults()

        click.echo("Seeding notification rules...")
        from .services import notification_rules as rules_service
        created = rules_service.seed_defaults()
        click.echo(f"  -> {created} rule(s) added (all disabled until you enable them)")

        db.session.commit()
        click.echo("Done.")
