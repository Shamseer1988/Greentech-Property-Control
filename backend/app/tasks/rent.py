"""Month-start rent generation.

Runs on the 1st so every live contract has its charge raised without
anyone remembering to press a button. Idempotent — a re-run on the same
day changes nothing.
"""
import json

from ..celery_app import celery
from ..extensions import db
from ..models import User
from ..services import rent as rent_service
from . import jobrun


@celery.task(name="app.tasks.rent.generate_monthly_rent")
def generate_monthly_rent(upto_iso: str | None = None):
    with jobrun("generate_monthly_rent", {"upto": upto_iso}) as run:
        # Scheduled work is attributed to the system super user so the
        # audit trail still names an actor.
        actor = User.query.filter_by(is_super_user=True).order_by(User.id).first()
        if actor is None:
            raise RuntimeError("No super user to attribute generated rent to")

        from datetime import date
        upto = date.fromisoformat(upto_iso) if upto_iso else date.today()
        counts = rent_service.generate_all(upto=upto, actor=actor)
        db.session.commit()
        run.result = json.dumps(counts)
        return counts
