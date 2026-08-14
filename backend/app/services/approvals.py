"""Approval workflow service.

Two shapes of approval share this queue.

**Write-then-finalise** (``renewal``): the transaction row is created up
front with ``status="pending_approval"`` and its side effects deferred.
Approving runs the module's ``finalize_*`` helper; rejecting marks the
transaction row ``rejected``.

**Defer-then-replay** (``contract_cancellation``, ``rent_reduction``,
``receipt_void``): nothing is written to the domain at all. The request
stores the call's arguments in ``payload`` and approving replays them
through the very same service function the un-gated path calls. Two
things fall out of that, both deliberate:

  * A pending request cannot leak into the numbers. There is no
    half-applied amendment for the rent engine or the ageing report to
    trip over, which matters because those read amendments unfiltered.
  * The action is validated against the state of the day it is
    *approved*, not the day it was requested. If the contract was
    cancelled in the meantime, approving a rent reduction on it fails
    loudly instead of writing a contradiction.

Rejecting a deferred request writes nothing anywhere; the request row
itself is the record that someone asked and was told no.
"""
from __future__ import annotations

from datetime import datetime

from ..extensions import db
from ..models import ApprovalRequest, ClientContract, LandlordRenewal, Receipt, User
from ..models.approval import APPROVAL_MODULES, MODULE_LABELS
from . import settings as settings_service


class ApprovalError(ValueError):
    pass


# ----------------------------------------------------------------------
# Transaction-number generator (APPR-YYYYMM-NNNN)
# ----------------------------------------------------------------------

def _next_request_number() -> str:
    today = datetime.utcnow().date()
    month_key = today.strftime("%Y%m")
    like = f"APPR-{month_key}-%"
    last = (
        db.session.query(ApprovalRequest.transaction_number)
        .filter(ApprovalRequest.transaction_number.like(like))
        .order_by(ApprovalRequest.transaction_number.desc())
        .limit(1)
        .scalar()
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    return f"APPR-{month_key}-{seq:04d}"


_ENTITY_TYPE_BY_MODULE = {
    "renewal": "landlord_renewal",
    "contract_cancellation": "client_contract",
    "rent_reduction": "client_contract",
    "receipt_void": "receipt",
}

_MODEL_BY_MODULE = {
    "renewal": LandlordRenewal,
    "contract_cancellation": ClientContract,
    "rent_reduction": ClientContract,
    "receipt_void": Receipt,
}

# Modules where the referenced record is the transaction itself, so a
# rejection has somewhere to land. For every other module the record is
# the untouched contract or receipt the request was *about* — writing
# "rejected" onto it would corrupt a live row.
_RECORD_IS_TRANSACTION = {"renewal"}

# The setting that gates each module. Absent from this map means the
# module is always gated (it is only ever reached deliberately).
_SETTING_BY_MODULE = {
    "renewal": "approval.renewal.required",
    "contract_cancellation": "approval.contract_cancellation.required",
    "rent_reduction": "approval.rent_reduction.required",
    "receipt_void": "approval.receipt_void.required",
}


def is_required(module: str) -> bool:
    """Whether `module` currently needs an approver. Read at request time
    so flipping the toggle never strands work already in the queue."""
    key = _SETTING_BY_MODULE.get(module)
    if key is None:
        return True
    return settings_service.get_bool(key, False)


def _actor(actor_id: int) -> User:
    user = User.query.get(actor_id)
    if user is None:
        raise ApprovalError("Approving user no longer exists")
    return user


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def create_request(*, module: str, entity, actor_id: int, summary: str | None = None,
                   payload: dict | None = None) -> ApprovalRequest:
    if module not in APPROVAL_MODULES:
        raise ApprovalError(f"Unsupported module: {module}")

    # One pending request per entity per module. Without this an operator
    # who clicks twice queues two cancellations of the same contract, and
    # the second one fails confusingly at approval time instead of now.
    existing = (
        ApprovalRequest.query
        .filter_by(module=module, entity_id=entity.id, status="pending")
        .first()
    )
    if existing is not None:
        raise ApprovalError(
            f"{MODULE_LABELS.get(module, module)} is already awaiting approval "
            f"({existing.transaction_number})"
        )

    req = ApprovalRequest(
        transaction_number=_next_request_number(),
        module=module,
        entity_type=_ENTITY_TYPE_BY_MODULE[module],
        entity_id=entity.id,
        entity_reference=(getattr(entity, "transaction_number", None)
                          or getattr(entity, "contract_number", None)
                          or getattr(entity, "receipt_number", None)),
        requested_by=actor_id,
        status="pending",
        summary=summary,
        payload=payload or None,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.session.add(req)
    db.session.flush()
    return req


def pending_for(*, module: str, entity_id: int) -> ApprovalRequest | None:
    return (
        ApprovalRequest.query
        .filter_by(module=module, entity_id=entity_id, status="pending")
        .first()
    )


def pending_for_contract(contract_id: int) -> list[ApprovalRequest]:
    """Everything queued against one contract, so the contract page can
    say "a rent reduction is waiting for approval" instead of silently
    showing the old rent."""
    return (
        ApprovalRequest.query
        .filter(ApprovalRequest.entity_type == "client_contract",
                ApprovalRequest.entity_id == contract_id,
                ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.id.desc())
        .all()
    )


def list_requests(*, status: str | None = None, module: str | None = None) -> list[ApprovalRequest]:
    q = ApprovalRequest.query
    if status:
        q = q.filter_by(status=status)
    if module:
        q = q.filter_by(module=module)
    return q.order_by(ApprovalRequest.id.desc()).limit(500).all()


def approve(*, request_id: int, actor_id: int, remarks: str | None = None) -> ApprovalRequest:
    req = ApprovalRequest.query.get(request_id)
    if req is None:
        raise ApprovalError("Approval request not found")
    if req.status != "pending":
        raise ApprovalError(f"Request is already {req.status}")

    model = _MODEL_BY_MODULE.get(req.module)
    if model is None:
        raise ApprovalError(f"Unsupported module: {req.module}")
    record = model.query.get(req.entity_id)
    if record is None:
        raise ApprovalError("Underlying record is missing")

    # Dispatch to the module-specific finalizer (imported lazily to avoid
    # circular imports between approvals.py and the transaction services).
    # Domain errors are re-raised as ApprovalError so the route answers
    # 400 with the real reason rather than a 500.
    args = req.payload or {}
    if req.module == "renewal":
        from . import renewals as svc
        svc.finalize_pending_renewal(record, actor_id=actor_id)
    elif req.module in ("contract_cancellation", "rent_reduction"):
        from . import contracts as svc
        fn = (svc.cancel_contract if req.module == "contract_cancellation"
              else svc.change_rent)
        try:
            fn(record, actor=_actor(actor_id), **args)
        except svc.ContractError as exc:
            raise ApprovalError(str(exc)) from exc
    elif req.module == "receipt_void":
        from . import receipts as svc
        try:
            svc.void_receipt(record, actor=_actor(actor_id), **args)
        except svc.ReceiptError as exc:
            raise ApprovalError(str(exc)) from exc

    req.status = "approved"
    req.decided_by = actor_id
    req.decided_at = datetime.utcnow()
    req.decision_remarks = remarks
    db.session.flush()
    return req


def reject(*, request_id: int, actor_id: int, remarks: str | None = None) -> ApprovalRequest:
    req = ApprovalRequest.query.get(request_id)
    if req is None:
        raise ApprovalError("Approval request not found")
    if req.status != "pending":
        raise ApprovalError(f"Request is already {req.status}")

    # Only write "rejected" onto the record when the record *is* the
    # transaction. For a deferred request the record is the live contract
    # or receipt the request was about, and nothing about it changes.
    if req.module in _RECORD_IS_TRANSACTION:
        model = _MODEL_BY_MODULE.get(req.module)
        record = model.query.get(req.entity_id) if model is not None else None
        if record is not None:
            record.status = "rejected"
            if hasattr(record, "updated_by"):
                record.updated_by = actor_id

    req.status = "rejected"
    req.decided_by = actor_id
    req.decided_at = datetime.utcnow()
    req.decision_remarks = remarks
    db.session.flush()
    return req


def pending_counts() -> dict:
    """Per-module counts of pending requests for dashboard/alert center."""
    from sqlalchemy import func as f
    rows = (
        db.session.query(ApprovalRequest.module, f.count(ApprovalRequest.id))
        .filter(ApprovalRequest.status == "pending")
        .group_by(ApprovalRequest.module)
        .all()
    )
    out = {m: 0 for m in APPROVAL_MODULES}
    out["total"] = 0
    for m, n in rows:
        out[m] = int(n)
        out["total"] += int(n)
    return out
