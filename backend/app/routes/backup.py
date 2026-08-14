"""Backup management API.

Endpoints (all require `backup.manage`):

    GET    /api/v1/backups                       — list backup files on disk
    POST   /api/v1/backups                       — run a backup now (sync)
    GET    /api/v1/backups/<filename>/download   — download a backup file
    POST   /api/v1/backups/upload-restore        — upload a file and restore
    POST   /api/v1/backups/<filename>/restore    — restore an on-disk backup
    DELETE /api/v1/backups/<filename>            — delete a backup file
    GET    /api/v1/backups/info                  — folder path + free space

Backup *schedule* settings (cron / retention days) live in the existing
SystemSetting catalog under the "backup" category and are edited via the
normal Settings UI; the scheduled celery task in app.tasks.backup reads
them once per run.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from werkzeug.utils import secure_filename

from ..services import audit, backup
from ..utils.auth import require_permission, current_user
from ..utils.responses import success_response, error_response

backup_bp = Blueprint("backup", __name__)


def _restored_message(source: str, result: dict) -> str:
    """Say plainly what came back, and what didn't. A database-only
    restore leaves every attachment row pointing at a file that no
    longer exists — the operator needs to hear that now, not when they
    click an agreement next month."""
    parts = [f"Restored from {source}."]
    if result.get("attachments") is None:
        parts.append(
            "This was a database-only backup, so uploaded files "
            "(agreements, cheque copies, vouchers) were NOT restored."
        )
    else:
        parts.append(f"{result['attachments']} attachment file(s) restored.")
    if result.get("uploads_backup"):
        parts.append(f"The previous uploads folder was kept at {result['uploads_backup']}.")
    parts.append(
        "You may need to sign in again — the restored database may have "
        "different user records."
    )
    return " ".join(parts)


@backup_bp.get("")
@require_permission("backup.manage")
def list_backups():
    rows = backup.list_backups()
    return success_response(
        data=[r.to_dict() for r in rows],
        meta={"count": len(rows)},
    )


@backup_bp.get("/info")
@require_permission("backup.manage")
def info():
    """Report the folder the backup service is actually using right
    now — so the Settings UI can show whether the operator's configured
    path is reachable and how much space is left."""
    try:
        folder = str(backup.backup_dir())  # honours the setting + env
    except Exception:
        folder = os.getenv("BACKUP_FOLDER", os.path.join(os.path.dirname(__file__), "..", "..", "..", "backups"))
    try:
        usage = shutil.disk_usage(folder)
        space = {
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        }
    except OSError:
        space = {"free_bytes": None, "total_bytes": None}
    return success_response(
        data={
            "folder": folder,
            "writable": os.access(folder, os.W_OK),
            **space,
        }
    )


@backup_bp.post("")
@require_permission("backup.manage")
def create_now():
    actor = current_user()
    try:
        rec = backup.create_backup()
    except backup.BackupError as exc:
        return error_response(str(exc), 500)
    audit.record(
        user=actor,
        action="create",
        module="backup",
        entity_type="backup",
        entity_id=rec.filename,
        new_value=rec.to_dict(),
    )
    from ..extensions import db
    db.session.commit()
    return success_response(
        data=rec.to_dict(),
        message=f"Backup {rec.filename} created",
        status=201,
    )


@backup_bp.get("/<path:filename>/download")
@require_permission("backup.manage")
def download(filename: str):
    try:
        path = backup.path_for(filename)
    except backup.BackupError as exc:
        return error_response(str(exc), 404)
    return send_file(
        path,
        as_attachment=True,
        download_name=path.name,
        mimetype="application/octet-stream",
    )


@backup_bp.delete("/<path:filename>")
@require_permission("backup.manage")
def delete(filename: str):
    actor = current_user()
    try:
        backup.delete_backup(filename)
    except backup.BackupError as exc:
        return error_response(str(exc), 404)
    audit.record(
        user=actor,
        action="delete",
        module="backup",
        entity_type="backup",
        entity_id=filename,
    )
    from ..extensions import db
    db.session.commit()
    return success_response(message=f"Backup {filename} deleted")


@backup_bp.post("/<path:filename>/restore")
@require_permission("backup.manage")
def restore_existing(filename: str):
    # Snapshot operator identity BEFORE the restore — the SQLAlchemy
    # session is detached during the drop+recreate, so the `actor` ORM
    # object becomes unusable. We log to the application logger (visible
    # in the backend service log) instead of writing AuditLog — the
    # audit row would race against the just-restored DB and the
    # restoring user might not even exist there.
    actor = current_user()
    actor_id, actor_username = actor.id, actor.username
    try:
        path = backup.path_for(filename)
        result = backup.restore_backup(path)
    except backup.BackupError as exc:
        return error_response(str(exc), 400)

    current_app.logger.warning(
        "DB RESTORED from %s by user_id=%s username=%s",
        filename, actor_id, actor_username,
    )
    return success_response(data=result, message=_restored_message(filename, result))


@backup_bp.post("/upload-restore")
@require_permission("backup.manage")
def upload_restore():
    """Restore from a file the operator uploads (a backup taken on
    another machine). Streams to a temp file under BACKUP_FOLDER, runs
    pg_restore, then keeps the file in the folder list."""
    actor = current_user()
    f = request.files.get("file")
    if f is None or not f.filename:
        return error_response("file is required", 400)

    safe_name = secure_filename(f.filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in backup.BACKUP_SUFFIXES:
        return error_response(
            "Only .zip (full backup) or .dump (database only) files are accepted", 400)

    # Save into the same folder `list_backups` reads, so an uploaded
    # archive appears in the history alongside the local ones.
    folder = backup.backup_dir()
    target = folder / safe_name
    if target.exists():
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')
        target = folder / f"{target.stem}-{stamp}{suffix}"

    f.save(target)

    actor_id, actor_username = actor.id, actor.username
    try:
        result = backup.restore_backup(target)
    except backup.BackupError as exc:
        return error_response(str(exc), 400)

    current_app.logger.warning(
        "DB RESTORED from uploaded %s (saved as %s) by user_id=%s username=%s",
        f.filename, target.name, actor_id, actor_username,
    )
    return success_response(
        data={"filename": target.name, **result},
        message=_restored_message(f"uploaded {target.name}", result),
    )
