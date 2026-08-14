"""System-settings service. Backed by the ``system_settings`` table.

Each entry in ``DEFAULTS`` describes one setting:
  - key, category, label, description, type
  - value: the default value used when seeding
  - options: list of {value, label} for ``select`` types
  - is_secret: don't return the value over the API, only "set"/"not set"
  - help: longer help text rendered under the field
"""
from __future__ import annotations

from typing import Any

from ..extensions import db
from ..models import SystemSetting
from .cache import cache_get, cache_set, cache_delete

_CACHE_TTL = 30  # seconds — short enough that a stale read self-heals fast


# Category ordering controls how tabs are sorted in the UI.
CATEGORY_ORDER = [
    "company", "property", "expense", "numbering", "approval", "alerts",
    "email", "ui", "import", "security", "backup", "audit",
]

CATEGORY_LABEL = {
    "company": "Company",
    "property": "Property",
    "expense": "Expense categories",
    "numbering": "Numbering",
    "approval": "Approval workflow",
    "alerts": "Alerts & reminders",
    "email": "Email",
    "ui": "UI / Theme",
    "import": "Import / Export",
    "security": "Security",
    "backup": "Backup",
    "audit": "Audit",
    "notifications": "Notification rules",
    "telegram": "Telegram",
    "ai": "AI assistant",
}


DEFAULTS: list[dict] = [
    # ---------- Company ----------
    {"key": "company.name", "category": "company", "type": "string",
     "label": "Company name", "value": "GreenTech Real Estate",
     "description": "Displayed in the topbar and on every report header."},
    {"key": "company.legal_name", "category": "company", "type": "string",
     "label": "Legal name", "value": "",
     "description": "Full registered legal name used on contracts and PDFs."},
    {"key": "company.address", "category": "company", "type": "textarea",
     "label": "Head office address", "value": "",
     "description": "Address printed on official documents."},
    {"key": "company.contact_email", "category": "company", "type": "string",
     "label": "Contact email", "value": ""},
    {"key": "company.contact_phone", "category": "company", "type": "string",
     "label": "Contact phone", "value": ""},
    {"key": "company.logo_url", "category": "company", "type": "string",
     "label": "Logo URL", "value": "",
     "description": "Public URL to a square logo image; shown in the topbar."},
    {"key": "company.currency", "category": "company", "type": "select",
     "label": "Currency", "value": "QAR",
     "options": [
         {"value": "QAR", "label": "Qatari Riyal (QAR)"},
         {"value": "AED", "label": "UAE Dirham (AED)"},
         {"value": "SAR", "label": "Saudi Riyal (SAR)"},
         {"value": "USD", "label": "US Dollar (USD)"},
     ],
     "description": "Currency code used across amounts, vouchers and reports."},
    {"key": "company.fiscal_year_start_month", "category": "company", "type": "int",
     "label": "Fiscal year start month", "value": 1,
     "description": "1 = January. Used by yearly reports and period locking."},
    {"key": "company.name_ar", "category": "company", "type": "string",
     "label": "Company name (Arabic)", "value": "",
     "description": "Arabic legal name — printed on the Arabic side of generated agreements."},
    {"key": "company.cr_number", "category": "company", "type": "string",
     "label": "Commercial registration no.", "value": "",
     "description": "The company's own CR/establishment registration number."},
    {"key": "company.signatory_name", "category": "company", "type": "string",
     "label": "Signatory name", "value": "",
     "description": "Person authorized to sign agreements on the company's behalf."},
    {"key": "company.signatory_name_ar", "category": "company", "type": "string",
     "label": "Signatory name (Arabic)", "value": ""},
    {"key": "company.signatory_id_number", "category": "company", "type": "string",
     "label": "Signatory ID number", "value": "",
     "description": "The signatory's personal QID — distinct from the company's CR number."},
    {"key": "company.signatory_title", "category": "company", "type": "string",
     "label": "Signatory title", "value": "",
     "description": "e.g. General Manager."},

    # ---------- Property defaults ----------
    {"key": "property.default_ownership", "category": "property", "type": "select",
     "label": "Default ownership type", "value": "rented",
     "options": [
         {"value": "rented", "label": "Rented"},
         {"value": "company_owned", "label": "Company owned"},
         {"value": "temporary", "label": "Temporary"},
     ]},
    # ---------- Numbering ----------
    {"key": "numbering.property.prefix", "category": "numbering", "type": "string",
     "label": "Property code prefix", "value": "PROP",
     "help": "Used for auto-generated property codes such as PROP-0001."},
    {"key": "numbering.landlord.prefix", "category": "numbering", "type": "string",
     "label": "Landlord code prefix", "value": "LL"},
    {"key": "numbering.client.prefix", "category": "numbering", "type": "string",
     "label": "Client code prefix", "value": "CL"},
    {"key": "contract.default_cheque_count", "category": "property", "type": "int",
     "label": "Cheques per annual contract", "value": 12,
     "description": "How many rent cheques the PDC grid pre-fills for a one-year agreement."},

    # ---------- Expense categories ----------
    {"key": "numbering.expense_category.prefix", "category": "expense", "type": "string",
     "label": "Expense category code prefix", "value": "EX",
     "help": "Used for auto-generated expense category codes such as EX-0001. "
             "Existing categories keep their current code either way."},

    # ---------- Approval workflow ----------
    # Each toggle gates one action. When it is on the action is queued
    # instead of applied, and replayed on approval — see
    # services/approvals.py.
    {"key": "approval.renewal.required", "category": "approval", "type": "bool",
     "label": "Require approval — landlord renewals", "value": False,
     "description": "Landlord renewals are held until approved; old agreement is not archived early."},
    {"key": "approval.contract_cancellation.required", "category": "approval", "type": "bool",
     "label": "Require approval — contract cancellation", "value": False,
     "description": "Cancelling a client contract waits for an approver before units are released."},
    {"key": "approval.rent_reduction.required", "category": "approval", "type": "bool",
     "label": "Require approval — rent reduction", "value": False,
     "description": "Lowering a contract's rent waits for an approver. Rent increases are not gated."},
    {"key": "approval.receipt_void.required", "category": "approval", "type": "bool",
     "label": "Require approval — receipt void", "value": False,
     "description": "Voiding a collection receipt waits for an approver; the receipt stays posted until then."},

    # ---------- Alerts ----------
    {"key": "alerts.reminder_days", "category": "alerts", "type": "string",
     "label": "Agreement-expiry reminder buckets", "value": "90,60,30,15,7",
     "description": "Comma-separated days before expiry to show reminders."},
    {"key": "alerts.email_enabled", "category": "alerts", "type": "bool",
     "label": "Email alerts enabled", "value": False,
     "description": "Send alert emails in addition to the dashboard notifications."},
    {"key": "alerts.dashboard_enabled", "category": "alerts", "type": "bool",
     "label": "Dashboard alerts enabled", "value": True},
    {"key": "alerts.daily_digest_enabled", "category": "alerts", "type": "bool",
     "label": "Daily digest email", "value": False},
    {"key": "alerts.escalation_users", "category": "alerts", "type": "string",
     "label": "Escalation users", "value": "",
     "description": "Comma-separated email addresses to copy on critical alerts."},

    # ---------- Email ----------
    {"key": "email.smtp_host", "category": "email", "type": "string",
     "label": "SMTP host", "value": ""},
    {"key": "email.smtp_port", "category": "email", "type": "int",
     "label": "SMTP port", "value": 587},
    {"key": "email.smtp_username", "category": "email", "type": "string",
     "label": "SMTP username", "value": ""},
    {"key": "email.smtp_password", "category": "email", "type": "password",
     "label": "SMTP password", "value": "", "is_secret": True,
     "description": "Stored encrypted at rest; never returned by the API."},
    {"key": "email.from_address", "category": "email", "type": "string",
     "label": "From address", "value": ""},
    {"key": "email.from_name", "category": "email", "type": "string",
     "label": "From name", "value": "GreenTech Real Estate"},
    {"key": "email.tls_enabled", "category": "email", "type": "bool",
     "label": "Use TLS", "value": True},
    # The master tap. Off by default and deliberately separate from
    # having valid SMTP details: configuring a mail server should never
    # be the same act as starting to mail clients.
    {"key": "email.enabled", "category": "email", "type": "bool",
     "label": "Send email", "value": False,
     "description": "Off: messages are still composed and logged, but nothing leaves the building. "
                    "Turn on only when the templates and recipients have been checked."},
    {"key": "email.redirect_to", "category": "email", "type": "string",
     "label": "Redirect all mail to", "value": "",
     "description": "Safety net for trials — when set, every message goes here instead of the "
                    "real recipient, with the intended address noted in the body."},

    # ---------- Notifications ----------
    {"key": "notifications.enabled", "category": "notifications", "type": "bool",
     "label": "Run the notification sweep", "value": False,
     "description": "The daily job that evaluates the rules below. Off until you are ready."},
    {"key": "notifications.send_hour", "category": "notifications", "type": "int",
     "label": "Daily send hour (UTC)", "value": 6,
     "description": "Qatar is UTC+3, so 6 here is 9am local."},
    {"key": "notifications.digest_emails", "category": "notifications", "type": "string",
     "label": "Staff digest recipients", "value": "",
     "description": "Comma-separated addresses that receive the internal summary of each sweep."},

    # ---------- Telegram ----------
    {"key": "telegram.enabled", "category": "telegram", "type": "bool",
     "label": "Send Telegram messages", "value": False},
    {"key": "telegram.bot_token", "category": "telegram", "type": "password",
     "label": "Bot token", "value": "", "is_secret": True,
     "description": "From @BotFather. Stored encrypted; never returned by the API."},
    {"key": "telegram.chat_id", "category": "telegram", "type": "string",
     "label": "Chat ID", "value": "",
     "description": "The staff group or channel id, e.g. -1001234567890."},

    # ---------- AI ----------
    {"key": "ai.enabled", "category": "ai", "type": "bool",
     "label": "Enable AI features", "value": False,
     "description": "Drafting and the monthly summary. Drafts are always reviewed before sending."},
    {"key": "ai.provider", "category": "ai", "type": "select",
     "label": "Provider", "value": "gemini",
     "options": [
         {"value": "gemini", "label": "Google Gemini"},
         {"value": "azure", "label": "Azure OpenAI"},
         {"value": "local", "label": "Local (OpenAI-compatible)"},
     ]},
    {"key": "ai.api_key", "category": "ai", "type": "password",
     "label": "API key", "value": "", "is_secret": True},
    {"key": "ai.endpoint", "category": "ai", "type": "string",
     "label": "Endpoint", "value": "",
     "description": "Azure resource URL, or the base URL of your local server "
                    "(e.g. http://localhost:11434/v1). Leave blank for Gemini."},
    {"key": "ai.model", "category": "ai", "type": "string",
     "label": "Model", "value": "gemini-2.0-flash",
     "description": "Gemini model name, Azure deployment name, or local model id."},
    {"key": "ai.timeout_seconds", "category": "ai", "type": "int",
     "label": "Request timeout (seconds)", "value": 30},

    # ---------- UI / Theme ----------
    {"key": "ui.accent_color", "category": "ui", "type": "select",
     "label": "Accent color", "value": "blue",
     "options": [
         {"value": "blue", "label": "Blue"},
         {"value": "emerald", "label": "Emerald"},
         {"value": "violet", "label": "Violet"},
         {"value": "amber", "label": "Amber"},
         {"value": "rose", "label": "Rose"},
     ]},
    {"key": "ui.glassmorphism", "category": "ui", "type": "bool",
     "label": "Enable glassmorphism", "value": True,
     "description": "Frosted-glass card style. Disable for higher contrast."},
    {"key": "ui.compact_mode", "category": "ui", "type": "bool",
     "label": "Compact mode", "value": False,
     "description": "Tighter padding across the app."},
    {"key": "ui.sidebar_default_collapsed", "category": "ui", "type": "bool",
     "label": "Sidebar collapsed by default", "value": False},
    {"key": "ui.table_density", "category": "ui", "type": "select",
     "label": "Table density", "value": "comfortable",
     "options": [
         {"value": "compact", "label": "Compact"},
         {"value": "comfortable", "label": "Comfortable"},
         {"value": "spacious", "label": "Spacious"},
     ]},

    # ---------- Import / Export ----------
    {"key": "import.max_rows", "category": "import", "type": "int",
     "label": "Max rows per Excel import", "value": 5000},
    {"key": "import.allow_partial_commit", "category": "import", "type": "bool",
     "label": "Allow partial import commit", "value": False,
     "description": "When OFF (default) any row error rejects the whole import."},
    {"key": "export.default_format", "category": "import", "type": "select",
     "label": "Default report export format", "value": "xlsx",
     "options": [
         {"value": "xlsx", "label": "Excel (.xlsx)"},
         {"value": "csv", "label": "CSV"},
     ]},

    # ---------- Security ----------
    {"key": "security.password_min_length", "category": "security", "type": "int",
     "label": "Minimum password length", "value": 8},
    {"key": "security.session_timeout_minutes", "category": "security", "type": "int",
     "label": "Session timeout (minutes)", "value": 480,
     "description": "How long an access token stays valid before requiring re-login."},
    {"key": "security.lockout_attempts", "category": "security", "type": "int",
     "label": "Failed login lockout threshold", "value": 5},
    {"key": "security.require_2fa", "category": "security", "type": "bool",
     "label": "Require 2FA", "value": False,
     "description": "Placeholder — 2FA enrolment is on the roadmap."},

    # ---------- Backup ----------
    {"key": "backup.folder", "category": "backup", "type": "string",
     "label": "Backup folder path", "value": "",
     "description": "Absolute path on the host where pg_dump .dump files are written. "
                    "Leave empty to use BACKUP_FOLDER env var, which itself defaults to "
                    "a `backups/` folder next to the repo root. The path must exist and "
                    "be writable by the user running the backend process.",
     "help": "e.g. C:\\Apps\\greentech-backups   or   /var/lib/greentech/backups"},
    {"key": "backup.schedule", "category": "backup", "type": "select",
     "label": "Automatic backup schedule", "value": "daily",
     "options": [
         {"value": "disabled", "label": "Disabled"},
         {"value": "daily", "label": "Daily"},
         {"value": "weekly", "label": "Weekly"},
         {"value": "monthly", "label": "Monthly"},
     ]},
    {"key": "backup.retention_days", "category": "backup", "type": "int",
     "label": "Retain backups for (days)", "value": 30},

    # ---------- Audit ----------
    {"key": "audit.retention_days", "category": "audit", "type": "int",
     "label": "Audit log retention (days)", "value": 365,
     "description": "How long audit rows are kept before pruning."},
    {"key": "audit.log_read_actions", "category": "audit", "type": "bool",
     "label": "Log read actions", "value": False,
     "description": "Capture GET requests in the audit log too. Verbose; off by default."},
]


# In-memory metadata indexed by key, for quick masking / typing checks.
META_BY_KEY: dict[str, dict] = {d["key"]: d for d in DEFAULTS}


def _metadata_for(key: str) -> dict:
    return META_BY_KEY.get(key, {})


def is_secret(key: str) -> bool:
    return bool(_metadata_for(key).get("is_secret"))


def seed_defaults() -> None:
    """Insert any missing settings rows; never overwrite existing values.

    Description / category are refreshed from the catalog so docstring edits
    in code take effect on the next seed run.
    """
    existing = {s.key: s for s in SystemSetting.query.all()}
    for d in DEFAULTS:
        row = existing.get(d["key"])
        if row is None:
            db.session.add(SystemSetting(
                key=d["key"], value=d.get("value"), category=d["category"],
                description=d.get("description"),
            ))
        else:
            # Keep value, refresh metadata
            row.category = d["category"]
            if d.get("description") is not None:
                row.description = d["description"]
    db.session.flush()


def _coerce_value(key: str, value: Any) -> Any:
    """Coerce incoming values to the type declared in the catalog."""
    meta = _metadata_for(key)
    typ = meta.get("type", "string")
    if value is None or value == "":
        if typ in ("bool",):
            return False
        if typ in ("int",):
            return None
        return ""
    if typ == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "y", "on")
    if typ == "int":
        return int(value)
    if typ == "select":
        allowed = {o["value"] for o in meta.get("options", [])}
        if allowed and str(value) not in allowed:
            raise ValueError(f"{key} must be one of {sorted(allowed)}")
        return str(value)
    return value


def get(key: str, default: Any = None) -> Any:
    cache_key = f"settings:{key}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached["value"] if cached["found"] else default

    row = SystemSetting.query.filter_by(key=key).first()
    if row is None:
        cache_set(cache_key, {"found": False, "value": None}, _CACHE_TTL)
        return default
    cache_set(cache_key, {"found": True, "value": row.value}, _CACHE_TTL)
    return row.value


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "y", "on")
    return bool(val)


def set_value(key: str, value: Any, *, actor_id: int | None = None,
              category: str | None = None, description: str | None = None) -> SystemSetting:
    coerced = _coerce_value(key, value)
    row = SystemSetting.query.filter_by(key=key).first()
    if row is None:
        meta = _metadata_for(key)
        row = SystemSetting(
            key=key,
            value=coerced,
            category=category or meta.get("category"),
            description=description or meta.get("description"),
            created_by=actor_id, updated_by=actor_id,
        )
        db.session.add(row)
    else:
        row.value = coerced
        if category is not None:
            row.category = category
        if description is not None:
            row.description = description
        row.updated_by = actor_id
    db.session.flush()
    cache_delete(f"settings:{key}")
    return row


def set_many(updates: dict, *, actor_id: int | None = None) -> list[SystemSetting]:
    rows = []
    for key, value in updates.items():
        rows.append(set_value(key, value, actor_id=actor_id))
    return rows


def all_by_category() -> dict[str, list[SystemSetting]]:
    out: dict[str, list[SystemSetting]] = {}
    for s in SystemSetting.query.order_by(SystemSetting.category, SystemSetting.key).all():
        out.setdefault(s.category or "general", []).append(s)
    return out


def catalog() -> dict:
    """Catalog of all known settings grouped by category, with metadata.

    Secret values are masked to a boolean ``"is_set"`` flag.
    """
    by_key = {s.key: s for s in SystemSetting.query.all()}
    sections: list[dict] = []
    grouped: dict[str, list[dict]] = {}

    for d in DEFAULTS:
        row = by_key.get(d["key"])
        value: Any = row.value if row is not None else d.get("value")
        entry = {
            "key": d["key"],
            "label": d.get("label", d["key"]),
            "type": d.get("type", "string"),
            "description": d.get("description"),
            "help": d.get("help"),
            "options": d.get("options"),
            "is_secret": bool(d.get("is_secret")),
        }
        if entry["is_secret"]:
            entry["value"] = None
            entry["is_set"] = bool(value)
        else:
            entry["value"] = value
        grouped.setdefault(d["category"], []).append(entry)

    for category in CATEGORY_ORDER:
        if category not in grouped:
            continue
        sections.append({
            "category": category,
            "label": CATEGORY_LABEL.get(category, category.title()),
            "settings": grouped[category],
        })
    # Catch any orphan categories (e.g. legacy)
    for category, items in grouped.items():
        if category in CATEGORY_ORDER:
            continue
        sections.append({
            "category": category,
            "label": CATEGORY_LABEL.get(category, category.title()),
            "settings": items,
        })

    return {"sections": sections, "count": len(DEFAULTS)}
