from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB

from ..extensions import db
from .base import BaseModel


APPROVAL_STATUSES = {"pending", "approved", "rejected"}

# Modules that participate in the approval workflow.
#
# Two shapes live here. For `renewal` the underlying record *is* the
# transaction: it is written up front carrying its own
# `status="pending_approval"`, and approving finalises it. For the
# money-critical actions below nothing is written until approval — the
# request stores the arguments in `payload` and the same service function
# the synchronous path calls is replayed on approval, so the action is
# re-validated against the state of the day it is approved rather than
# the day it was asked for.
APPROVAL_MODULES = {
    "renewal",
    "contract_cancellation",
    "rent_reduction",
    "receipt_void",
}

# Human-readable labels, used in the queue and in alert text.
MODULE_LABELS = {
    "renewal": "Landlord agreement renewal",
    "contract_cancellation": "Contract cancellation",
    "rent_reduction": "Rent reduction",
    "receipt_void": "Receipt void",
}


class ApprovalRequest(BaseModel):
    __tablename__ = "approval_requests"

    transaction_number = Column(String(40), unique=True, nullable=False, index=True)

    module = Column(String(24), nullable=False, index=True)  # one of APPROVAL_MODULES
    entity_type = Column(String(48), nullable=False)         # landlord_renewal, …
    entity_id = Column(Integer, nullable=False, index=True)
    entity_reference = Column(String(40), nullable=True)     # the txn number of the underlying record

    requested_by = Column(Integer, nullable=True)
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    status = Column(String(16), default="pending", nullable=False, index=True)
    decided_by = Column(Integer, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_remarks = Column(Text, nullable=True)

    summary = Column(Text, nullable=True)  # human-readable description
    remarks = Column(Text, nullable=True)

    # The arguments of the deferred action, replayed verbatim on approval.
    # Empty for `renewal`, whose record already holds its own state.
    payload = Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=True)

    __table_args__ = (
        Index("ix_approval_requests_module_status", "module", "status"),
        Index("ix_approval_requests_entity", "entity_type", "entity_id"),
    )

    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        for k in ("requested_at", "decided_at"):
            if data.get(k) and not isinstance(data[k], str):
                data[k] = data[k].isoformat()
        data["module_label"] = MODULE_LABELS.get(self.module, self.module)
        return data
