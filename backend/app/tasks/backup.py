"""Scheduled database backups.

The beat schedule runs `scheduled_backup` daily (see app.celery_app
beat_schedule). The task itself reads `backup.schedule` from
SystemSetting and skips when:
  * schedule == "disabled"
  * schedule == "weekly" and today is not Monday
  * schedule == "monthly" and today is not the 1st

After a successful backup the task prunes anything older than
`backup.retention_days`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import jobrun
from ..celery_app import celery
from ..services import backup as backup_service
from ..services import settings as settings_service
from ..services import telegram as telegram_service


def _should_run_today(schedule: str, today: datetime) -> bool:
    s = (schedule or "").strip().lower()
    if s == "daily":
        return True
    if s == "weekly":
        return today.weekday() == 0  # Monday
    if s == "monthly":
        return today.day == 1
    return False  # "disabled" or unknown


@celery.task(name="app.tasks.backup.scheduled_backup")
def scheduled_backup() -> dict:
    """Daily entrypoint. Honors the operator's schedule setting."""
    schedule = (settings_service.get("backup.schedule") or "daily")
    today = datetime.now(timezone.utc)
    if not _should_run_today(str(schedule), today):
        return {"status": "skipped", "schedule": str(schedule)}

    try:
        rec = backup_service.create_backup()
    except backup_service.BackupError as exc:
        return {"status": "failed", "error": str(exc)}

    retention_raw = settings_service.get("backup.retention_days") or 30
    try:
        retention = int(retention_raw)
    except (TypeError, ValueError):
        retention = 30
    removed = backup_service.prune_old(retention)

    return {
        "status": "ok",
        "filename": rec.filename,
        "size_bytes": rec.size_bytes,
        "pruned": removed,
    }


@celery.task(name="app.tasks.backup.verify_latest_backup")
def verify_latest_backup() -> dict:
    """Weekly structural check on the most recent backup — see
    services/backup.py::verify_backup_contents() for what "structural"
    means here and why this stops short of a full restore drill. On
    failure, alerts via Telegram so a bad backup is caught long before
    the day it's actually needed."""
    with jobrun("verify_latest_backup") as run:
        backups = backup_service.list_backups()
        if not backups:
            run.result = "no backups to verify"
            return {"status": "skipped", "reason": "no backups exist yet"}

        latest = backups[0]
        try:
            result = backup_service.verify_backup_contents(latest.filename)
        except backup_service.BackupError as exc:
            telegram_service.send_now(
                text=f"⚠ Backup verification failed for {latest.filename}: {exc}",
                event="backup_verify_failed",
                is_manual=True,
                dedupe_key=f"backup-verify:{latest.filename}",
            )
            run.result = f"failed: {exc}"
            return {"status": "failed", "filename": latest.filename, "error": str(exc)}

        if not result["ok"]:
            parts = []
            if result["missing_tables"]:
                parts.append(f"missing tables: {', '.join(result['missing_tables'])}")
            if result["attachment_mismatch"]:
                m = result["attachment_mismatch"]
                parts.append(f"attachment count mismatch (manifest {m['manifest']} vs live {m['live']})")
            telegram_service.send_now(
                text=f"⚠ Backup verification found problems in {latest.filename}: {'; '.join(parts)}",
                event="backup_verify_failed",
                is_manual=True,
                dedupe_key=f"backup-verify:{latest.filename}",
            )

        return {"status": "ok" if result["ok"] else "problems_found",
                "filename": latest.filename, **result}
