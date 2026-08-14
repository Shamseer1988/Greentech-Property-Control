"""Document-expiry tracking.

Attachments in the expiring categories (company CR, government QID)
carry an ``expiry_date``. This module surfaces the ones coming due so
the alert centre and the reports page can show the same numbers.
"""
from datetime import date, timedelta

from ..models import Attachment, Landlord, Client, Property
from ..models.attachment import EXPIRING_CATEGORIES


# Human labels for the entity a document hangs off, resolved in one
# query per type rather than per row.
_LABELLERS = {
    "landlord": (Landlord, lambda r: r.name),
    "client": (Client, lambda r: r.name),
    "property": (Property, lambda r: r.name),
}


def _labels_for(entity_type: str, ids: set[str]) -> dict[str, str]:
    spec = _LABELLERS.get(entity_type)
    if spec is None or not ids:
        return {}
    model, label = spec
    numeric = [int(i) for i in ids if str(i).isdigit()]
    if not numeric:
        return {}
    rows = model.query.filter(model.id.in_(numeric)).all()
    return {str(r.id): label(r) for r in rows}


def expiring_documents(within_days: int = 90, today: date | None = None) -> list[dict]:
    """Documents already expired or expiring within `within_days`.

    Sorted soonest-first so the caller can slice a "top N" without
    re-sorting."""
    today = today or date.today()
    cutoff = today + timedelta(days=within_days)
    rows = (
        Attachment.query
        .filter(Attachment.expiry_date.isnot(None))
        .filter(Attachment.expiry_date <= cutoff)
        .filter(Attachment.category.in_(sorted(EXPIRING_CATEGORIES)))
        .order_by(Attachment.expiry_date.asc())
        .all()
    )

    by_type: dict[str, set[str]] = {}
    for a in rows:
        by_type.setdefault(a.entity_type, set()).add(a.entity_id)
    labels = {t: _labels_for(t, ids) for t, ids in by_type.items()}

    out = []
    for a in rows:
        days_left = (a.expiry_date - today).days
        out.append({
            "attachment_id": a.id,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "entity_name": labels.get(a.entity_type, {}).get(str(a.entity_id)),
            "category": a.category,
            "doc_number": a.doc_number,
            "original_name": a.original_name,
            "expiry_date": a.expiry_date.isoformat(),
            "days_left": days_left,
            "bucket": "expired" if days_left < 0 else str(days_left),
        })
    return out
