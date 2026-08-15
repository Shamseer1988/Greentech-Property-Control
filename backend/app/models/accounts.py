"""Accounting scaffold — Account, JournalEntry, JournalLine, BankAccount, Supplier.

Tables created by running `flask --app wsgi init-db` after registering models.
Routes and posting hooks are added in the future accounting module phase.
The `accounting.enabled` system setting gates all posting hooks — when False
(the default) no JEs are created, so property management is not affected.
"""
from sqlalchemy import Column, String, Integer, Boolean, Numeric, Text, Date, DateTime, Index

from ..extensions import db
from .base import BaseModel


class Account(BaseModel):
    """Chart of Accounts entry."""
    __tablename__ = "accounts"

    code         = Column(String(20), unique=True, nullable=False)
    name         = Column(String(100), nullable=False)
    # asset | liability | equity | income | expense
    account_type = Column(String(20), nullable=False)
    parent_id    = Column(Integer, db.ForeignKey("accounts.id"), nullable=True)
    is_control   = Column(Boolean, default=False, nullable=False)
    is_bank      = Column(Boolean, default=False, nullable=False)
    is_active    = Column(Boolean, default=True, nullable=False)

    parent       = db.relationship("Account", remote_side="Account.id", backref="children")
    journal_lines = db.relationship("JournalLine", backref="account", lazy="dynamic")

    __table_args__ = (
        Index("ix_accounts_code", "code"),
        Index("ix_accounts_account_type", "account_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "account_type": self.account_type,
            "parent_id": self.parent_id,
            "is_control": self.is_control,
            "is_bank": self.is_bank,
            "is_active": self.is_active,
        }


class JournalEntry(BaseModel):
    """Header record for a double-entry voucher."""
    __tablename__ = "journal_entries"

    entry_number      = Column(String(20), nullable=False, unique=True)
    # rv | pv | sjv | pjv | jv
    voucher_type      = Column(String(10), nullable=False, index=True)
    date              = Column(Date, nullable=False, index=True)
    narration         = Column(Text)
    # Links back to the originating sub-ledger record (nullable for manual JVs)
    ref_type          = Column(String(50))
    ref_id            = Column(Integer)
    # draft | posted | void
    status            = Column(String(20), nullable=False, default="draft", index=True)
    posted_at         = Column(DateTime)
    posted_by         = Column(Integer, db.ForeignKey("users.id"), nullable=True)
    void_reason       = Column(Text)
    voided_at         = Column(DateTime)
    reversal_entry_id = Column(Integer, db.ForeignKey("journal_entries.id"), nullable=True)

    lines = db.relationship(
        "JournalLine", backref="entry", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        Index("ix_journal_entries_ref", "ref_type", "ref_id"),
    )

    def to_dict(self):
        from datetime import datetime, date
        def _ser(v):
            if isinstance(v, (datetime, date)):
                return v.isoformat()
            return v
        return {c.name: _ser(getattr(self, c.name)) for c in self.__table__.columns}


class JournalLine(BaseModel):
    """One debit or credit leg of a JournalEntry."""
    __tablename__ = "journal_lines"

    entry_id   = Column(Integer, db.ForeignKey("journal_entries.id"), nullable=False)
    line_no    = Column(Integer, nullable=False)
    account_id = Column(Integer, db.ForeignKey("accounts.id"), nullable=False)
    # landlord | client | supplier | null
    party_type = Column(String(20))
    party_id   = Column(Integer)
    debit      = Column(Numeric(15, 2), nullable=False, default=0)
    credit     = Column(Numeric(15, 2), nullable=False, default=0)
    narration  = Column(Text)

    __table_args__ = (
        Index("ix_journal_lines_entry_id", "entry_id"),
        Index("ix_journal_lines_account_id", "account_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "entry_id": self.entry_id,
            "line_no": self.line_no,
            "account_id": self.account_id,
            "party_type": self.party_type,
            "party_id": self.party_id,
            "debit": float(self.debit) if self.debit is not None else 0,
            "credit": float(self.credit) if self.credit is not None else 0,
            "narration": self.narration,
        }


class BankAccount(BaseModel):
    """Named bank / cash account used in payment and receipt vouchers."""
    __tablename__ = "bank_accounts"

    name           = Column(String(100), nullable=False)
    bank_name      = Column(String(100))
    account_number = Column(String(50))
    iban           = Column(String(34))
    account_id     = Column(Integer, db.ForeignKey("accounts.id"), nullable=True)
    is_default     = Column(Boolean, default=False, nullable=False)
    is_active      = Column(Boolean, default=True, nullable=False)

    gl_account = db.relationship("Account", foreign_keys=[account_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "bank_name": self.bank_name,
            "account_number": self.account_number,
            "iban": self.iban,
            "account_id": self.account_id,
            "is_default": self.is_default,
            "is_active": self.is_active,
        }


class Supplier(BaseModel):
    """Supplier / vendor master for non-landlord, non-client payees.

    Covers sewage authority, electricity provider, maintenance contractors,
    and any other third-party payee that is not a property landlord.
    """
    __tablename__ = "suppliers"

    code                   = Column(String(20), unique=True, index=True)
    name                   = Column(String(200), nullable=False)
    # sewage | electricity | maintenance | other
    category               = Column(String(50), index=True)
    contact_person         = Column(String(100))
    phone                  = Column(String(30))
    email                  = Column(String(200))
    vat_number             = Column(String(50))
    default_ap_account_id  = Column(Integer, db.ForeignKey("accounts.id"), nullable=True)
    payment_terms          = Column(Integer, default=30)
    is_active              = Column(Boolean, default=True, nullable=False)

    default_ap_account = db.relationship("Account", foreign_keys=[default_ap_account_id])

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "vat_number": self.vat_number,
            "default_ap_account_id": self.default_ap_account_id,
            "payment_terms": self.payment_terms,
            "is_active": self.is_active,
        }
