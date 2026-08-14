"""Permission catalog and role presets for the system.

Permission codes use dotted notation: "<module>.<action>".
Modules align with the application sidebar / blueprint modules.

Contract / rent / expense permissions are added here in Phases 2-4 so
the catalog stays the single source of truth.
"""

PERMISSION_CATALOG: list[tuple[str, str, str]] = [
    # (module, action, description)
    ("dashboard", "view", "View dashboard"),
    # Master setup
    ("property", "view", "View properties"),
    ("property", "create", "Create properties"),
    ("property", "edit", "Edit properties"),
    ("property", "deactivate", "Deactivate properties"),
    ("property", "amend", "Amend landlord contracts (rent, free months, units, deposit)"),
    ("property", "cancel", "Cancel landlord contracts"),
    ("landlord", "view", "View landlords"),
    ("landlord", "create", "Create landlords"),
    ("landlord", "edit", "Edit landlords"),
    ("client", "view", "View clients"),
    ("client", "create", "Create clients"),
    ("client", "edit", "Edit clients"),
    ("contract", "view", "View client contracts"),
    ("contract", "create", "Create / renew client contracts"),
    ("contract", "amend", "Amend contracts (rent, free months, units)"),
    ("contract", "cancel", "Cancel client contracts"),
    ("agreement", "view", "View generated rental agreements"),
    ("agreement", "create", "Generate rental agreement documents"),
    ("agreement", "void", "Void a generated rental agreement"),
    ("cheque", "manage", "Register PDC cheques and record their lifecycle"),
    ("rent", "view", "View rent charges, ageing and statements"),
    ("rent", "generate", "Generate the monthly rent schedule"),
    ("receipt", "view", "View receipts"),
    ("receipt", "create", "Post receipts"),
    ("receipt", "void", "Void a posted receipt"),
    ("expense", "view", "View expenses, landlord payments and property P&L"),
    ("expense", "manage", "Record expenses and landlord payments"),
    ("expense", "import", "Import the accounting software P&L export"),
    ("floor", "manage", "Manage floors"),
    ("unit", "view", "View units"),
    ("unit", "manage", "Create / edit / deactivate units"),
    # Transactions
    ("renewal", "create", "Renew landlord agreement"),
    ("maintenance", "manage", "Manage maintenance records"),
    ("approval", "approve", "Approve transactions"),
    ("approval", "reject", "Reject transactions"),
    # Reports / export
    ("report", "view", "View reports"),
    ("report", "export", "Export reports to Excel / PDF"),
    # Attachments
    ("attachment", "upload", "Upload attachments"),
    ("attachment", "view", "View attachments"),
    # Administration
    ("user", "view", "View users"),
    ("user", "manage", "Manage users"),
    ("role", "view", "View roles"),
    ("role", "manage", "Manage roles and permissions"),
    ("audit", "view", "View audit log"),
    ("settings", "view", "View system settings"),
    ("settings", "manage", "Manage system settings"),
    ("backup", "manage", "Run, restore, and schedule database backups"),
    # Notifications / outbound messages. `send` is separate from
    # `manage` on purpose: configuring a reminder rule and actually
    # mailing a tenant are different levels of trust.
    ("notification", "manage", "Configure notification rules and templates"),
    ("notification", "send", "Send email / Telegram messages and run the sweep"),
    ("notification", "view", "View the sent-message log"),
]


def permission_code(module: str, action: str) -> str:
    return f"{module}.{action}"


def all_permission_codes() -> list[str]:
    return [permission_code(m, a) for m, a, _ in PERMISSION_CATALOG]


# Role -> list of permission codes ("*" means all).
ROLE_PRESETS: dict[str, dict] = {
    "super_user": {
        "name": "Super User",
        "description": "Full unrestricted access (managed via is_super_user flag).",
        "permissions": ["*"],
    },
    "admin": {
        "name": "Admin",
        "description": "System administrator with full operational access.",
        "permissions": all_permission_codes(),
    },
    "accounts": {
        "name": "Accounts",
        "description": "Accounts team: contracts, rent, receipts, expenses, reports.",
        "permissions": [
            "dashboard.view",
            "property.view", "property.create", "property.edit",
            "property.amend", "property.cancel",
            "landlord.view", "landlord.create", "landlord.edit",
            "client.view", "client.create", "client.edit",
            "contract.view", "contract.create", "contract.amend", "contract.cancel",
            "agreement.view", "agreement.create", "agreement.void",
            "cheque.manage",
            "rent.view", "rent.generate",
            "receipt.view", "receipt.create", "receipt.void",
            "expense.view", "expense.manage", "expense.import",
            "floor.manage", "unit.view", "unit.manage",
            "renewal.create", "maintenance.manage",
            "report.view", "report.export",
            "attachment.upload", "attachment.view",
            "notification.view", "notification.send",
        ],
    },
    "data_entry": {
        "name": "Data Entry",
        "description": "Enter masters and day-to-day records; no approvals or admin.",
        "permissions": [
            "dashboard.view",
            "property.view", "landlord.view", "unit.view",
            "client.view", "client.create", "client.edit",
            "contract.view", "agreement.view", "agreement.create",
            "rent.view", "receipt.view", "receipt.create",
            "expense.view", "expense.manage",
            "maintenance.manage",
            "attachment.upload", "attachment.view",
            "report.view",
        ],
    },
    "viewer": {
        "name": "Viewer",
        "description": "Read-only access to dashboards and reports.",
        "permissions": [
            "dashboard.view",
            "property.view", "landlord.view", "unit.view", "client.view",
            "contract.view", "agreement.view", "rent.view", "receipt.view", "expense.view",
            "report.view",
            "attachment.view",
        ],
    },
    "auditor": {
        "name": "Auditor",
        "description": "Read everything plus audit trail access.",
        "permissions": all_permission_codes(),
    },
}
