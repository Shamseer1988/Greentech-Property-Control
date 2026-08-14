"""Daily notification sweep.

Runs hourly and does nothing unless two conditions hold: the operator
has switched `notifications.enabled` on, and the current hour matches
`notifications.send_hour`. Checking the hour inside the task rather than
in the beat schedule means the operator can move the send time from the
Settings screen without touching a cron expression or restarting beat.
"""
import json
from datetime import date, datetime

from ..celery_app import celery
from ..extensions import db
from ..services import notification_rules as rules_service
from ..services import settings as settings_service
from . import jobrun


@celery.task(name="app.tasks.notifications.hourly_notification_sweep")
def hourly_notification_sweep(force: bool = False, today_iso: str | None = None):
    today = date.fromisoformat(today_iso) if today_iso else date.today()
    with jobrun("hourly_notification_sweep", {"today": today.isoformat()}) as run:
        if not force:
            if not settings_service.get_bool("notifications.enabled", False):
                result = {"skipped": "notifications are switched off"}
                run.result = json.dumps(result)
                return result
            send_hour = int(settings_service.get("notifications.send_hour") or 6)
            if datetime.utcnow().hour != send_hour:
                result = {"skipped": f"not the send hour (waiting for {send_hour:02d}:00 UTC)"}
                run.result = json.dumps(result)
                return result

        result = rules_service.run_sweep(today)
        db.session.commit()
        # The per-finding detail can be long; the JobRun keeps the shape.
        run.result = json.dumps({
            "date": result["date"],
            "rules_evaluated": result["rules_evaluated"],
            "findings": result["findings"],
            "by_event": {e["event"]: e["findings"] for e in result["events"]},
        })
        return result
