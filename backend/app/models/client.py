from sqlalchemy import Column, String, Text, Date, Index

from .base import BaseModel


CLIENT_TYPES = {"company", "individual"}
CLIENT_STATUSES = {"active", "inactive", "blacklisted"}


class Client(BaseModel):
    """A tenant GreenTech lets units to.

    Clients rent rooms, floors, flats, stores, cafeterias and
    supermarkets. Their contracts (with unit allocation, rent, mode and
    PDC cheques) arrive in Phase 2 and reference this master.
    """

    __tablename__ = "clients"

    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(160), nullable=False, index=True)
    # Arabic legal name — printed on contracts and official notices.
    name_ar = Column(String(160), nullable=True)

    client_type = Column(String(16), default="company", nullable=False)

    contact_person = Column(String(120), nullable=True)
    mobile = Column(String(32), nullable=True, index=True)
    alt_mobile = Column(String(32), nullable=True)
    email = Column(String(120), nullable=True)
    address = Column(Text, nullable=True)

    # Commercial registration (company) or QID (individual), with the
    # expiry the document-expiry alerts watch.
    qid_cr_number = Column(String(64), nullable=True, index=True)
    qid_cr_expiry_date = Column(Date, nullable=True, index=True)

    # The named individual who signs on the client's behalf — distinct
    # from qid_cr_number, which is the *company's* CR/QID. Required
    # before a rental agreement can be generated for this client.
    signatory_name = Column(String(160), nullable=True)
    signatory_name_ar = Column(String(160), nullable=True)
    signatory_id_number = Column(String(64), nullable=True)
    signatory_title = Column(String(80), nullable=True)
    signatory_mobile = Column(String(32), nullable=True)

    status = Column(String(16), default="active", nullable=False, index=True)
    remarks = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_clients_status_name", "status", "name"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        if data.get("qid_cr_expiry_date") and not isinstance(data["qid_cr_expiry_date"], str):
            data["qid_cr_expiry_date"] = data["qid_cr_expiry_date"].isoformat()
        return data
