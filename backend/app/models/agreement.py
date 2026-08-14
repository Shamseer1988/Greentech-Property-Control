"""A generated rental-agreement document — a dated, immutable drafting
snapshot, never edited in place (mirrors `ContractAmendment`/
`LandlordContractAmendment`). The wizard that creates one picks a
landlord or client from the master directly, not an existing contract
row, since a labour-camp room deal like the reference sample often has
no corresponding `ClientContract`/`LandlordContract` at all — the
optional `landlord_contract_id`/`client_contract_id` links are for
traceability only, never required.

`snapshot_json` freezes the company + party names/QID/signatory details
at generation time. A signed legal document must never silently change
if someone edits the landlord's name next year.
"""
from sqlalchemy import (
    Column, String, Integer, Date, Numeric, Text, Boolean, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..extensions import db
from .base import BaseModel


AGREEMENT_PARTY_ROLES = {"landlord", "client"}
AGREEMENT_STATUSES = {"generated", "voided"}
FREE_MONTHS_MODES = {"start", "end", "specific"}
CANCELLATION_MODES = {"no_cancellation", "notice_months"}


class GeneratedAgreement(BaseModel):
    __tablename__ = "generated_agreements"

    agreement_number = Column(String(40), unique=True, nullable=False, index=True)
    template_slug = Column(String(64), nullable=False, index=True)
    party_role = Column(String(8), nullable=False, index=True)  # AGREEMENT_PARTY_ROLES

    landlord_id = Column(Integer, ForeignKey("landlords.id", ondelete="RESTRICT"),
                         nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"),
                       nullable=True, index=True)
    landlord_contract_id = Column(Integer, ForeignKey("property_agreements.id", ondelete="SET NULL"),
                                  nullable=True, index=True)
    client_contract_id = Column(Integer, ForeignKey("client_contracts.id", ondelete="SET NULL"),
                                nullable=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="SET NULL"),
                         nullable=True, index=True)

    unit_ids = Column(Text, nullable=True)  # comma-separated, same convention as ContractAmendment
    rooms_count = Column(Integer, nullable=True)
    rooms_description = Column(Text, nullable=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    contract_period_months = Column(Integer, nullable=True)

    electricity_included = Column(Boolean, default=False, nullable=False)
    water_included = Column(Boolean, default=False, nullable=False)

    free_months_count = Column(Integer, nullable=True)
    free_months_mode = Column(String(16), nullable=True)      # FREE_MONTHS_MODES
    free_months_specific = Column(Text, nullable=True)        # comma-separated month-start dates

    deposit_cheque_required = Column(Boolean, default=False, nullable=False)

    cancellation_mode = Column(String(16), default="no_cancellation", nullable=False)  # CANCELLATION_MODES
    cancellation_notice_months = Column(Integer, nullable=True)

    rent_amount = Column(Numeric(12, 2), nullable=True)
    rent_payment_frequency_months = Column(Integer, nullable=True)
    currency = Column(String(8), default="QAR", nullable=False)

    snapshot_json = Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=True)

    status = Column(String(16), default="generated", nullable=False, index=True)
    superseded_by_id = Column(Integer, ForeignKey("generated_agreements.id", ondelete="SET NULL"),
                              nullable=True)
    attachment_id = Column(Integer, ForeignKey("attachments.id", ondelete="SET NULL"),
                           nullable=True)

    remarks = Column(Text, nullable=True)

    landlord = relationship("Landlord", lazy="joined")
    client = relationship("Client", lazy="joined")
    property = relationship("Property", lazy="joined")

    __table_args__ = (
        Index("ix_generated_agreements_party", "party_role", "landlord_id", "client_id"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("start_date", "end_date"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        if data.get("rent_amount") is not None:
            data["rent_amount"] = float(data["rent_amount"])
        data["unit_ids"] = (
            [int(x) for x in self.unit_ids.split(",") if x] if self.unit_ids else []
        )
        data["free_months_specific"] = (
            self.free_months_specific.split(",") if self.free_months_specific else []
        )
        if self.landlord is not None:
            data["landlord"] = {"id": self.landlord.id, "code": self.landlord.code,
                                "name": self.landlord.name}
        if self.client is not None:
            data["client"] = {"id": self.client.id, "code": self.client.code,
                              "name": self.client.name}
        if self.property is not None:
            data["property"] = {"id": self.property.id, "code": self.property.code,
                                "name": self.property.name}
        return data
