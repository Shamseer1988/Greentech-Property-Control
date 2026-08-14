from sqlalchemy import Column, String, Integer, Text, Date, ForeignKey, Index

from .base import BaseModel


# Document categories the UI offers. `agreement` and `cheque_copy` are
# the ones that must never be missing; the rest are supporting paper.
ATTACHMENT_CATEGORIES = {
    "agreement", "company_doc", "govt_doc", "cheque_copy",
    "receipt_voucher", "payment_voucher", "photo", "other",
}

# Categories whose expiry the alert engine watches. A tenancy agreement
# expiring is tracked by the contract itself, not here.
EXPIRING_CATEGORIES = {"company_doc", "govt_doc"}


class Attachment(BaseModel):
    __tablename__ = "attachments"

    entity_type = Column(String(48), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    category = Column(String(48), nullable=True)  # one of ATTACHMENT_CATEGORIES
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    path = Column(Text, nullable=False)

    # Document identity + validity. expiry_date drives the
    # document-expiry alerts (CR / QID renewals).
    doc_number = Column(String(64), nullable=True)
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)

    remarks = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_attachments_entity", "entity_type", "entity_id"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("issue_date", "expiry_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        return data


class AttachmentLink(BaseModel):
    """A second (or third) place an attachment also shows up.

    The attachment keeps exactly one owner (`entity_type`/`entity_id`
    above) — this table only adds extra places it's *visible*, so a
    document uploaded once on a landlord can also appear on one of their
    properties without a second upload or a second copy on disk.
    """

    __tablename__ = "attachment_links"

    attachment_id = Column(Integer, ForeignKey("attachments.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    entity_type = Column(String(48), nullable=False)
    entity_id = Column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_attachment_links_entity", "entity_type", "entity_id"),
    )
