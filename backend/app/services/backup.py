"""Backup + restore service.

Wraps `pg_dump` / `pg_restore` so the operator can:
  * trigger an on-demand backup via the UI
  * download an existing backup as a single file
  * restore from a previously-downloaded backup (or one already on disk)
  * have backups run automatically on a schedule (see app.tasks.backup)

Storage:
  Backups live in BACKUP_FOLDER (defaults to ../backups, relative to
  the backend folder). Set the env var to point at a host-absolute
  path in production.

  A backup is a single zip named

      greentech-realestate-YYYYMMDD-HHMMSSZ.zip

  holding `database.dump` (custom pg_dump format — compact and friendly
  to pg_restore's selective options), every file under the uploads
  folder, and a `manifest.json`. Database and files travel together on
  purpose: attachment rows store a path relative to the uploads folder,
  so restoring one without the other yields a portal full of agreements
  and cheque copies that no longer open.

  A bare `.dump` is still accepted on restore — it is what you get from
  running pg_dump by hand — but it restores the database only, and the
  API says so in its response.

Security:
  * pg_dump / pg_restore are invoked with the DB password injected via
    the PGPASSWORD env var so it never appears in `ps`.
  * Filenames coming back in over the API are validated against
    SAFE_FILENAME_RE — no path traversal, no shell metacharacters.
  * Uploaded archives are extracted member by member and any path that
    escapes the destination is refused (zip-slip).
  * Restore is allowed only when the caller has `backup.manage`.
"""
from __future__ import annotations

import os
import re
import json
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from flask import current_app


SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.(zip|dump)$")
BACKUP_PREFIX = "greentech-realestate"
BACKUP_SUFFIXES = (".zip", ".dump")
PG_DUMP = "pg_dump"
PG_RESTORE = "pg_restore"
PSQL = "psql"

# Layout inside a .zip archive.
DB_MEMBER = "database.dump"
UPLOADS_MEMBER_PREFIX = "uploads/"
MANIFEST_MEMBER = "manifest.json"


class BackupError(RuntimeError):
    """Raised for any expected backup/restore failure that should
    surface as a clean 4xx/5xx instead of a stacktrace."""


@dataclass
class BackupFile:
    filename: str
    size_bytes: int
    created_at: datetime
    attachments: int | None = None

    @property
    def kind(self) -> str:
        """`full` carries the database and the uploaded files; `database`
        is a bare pg_dump, which restores the rows but leaves every
        attachment pointing at a file that isn't there."""
        return "full" if self.filename.endswith(".zip") else "database"

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "size_human": _human_bytes(self.size_bytes),
            "created_at": self.created_at.isoformat(),
            "kind": self.kind,
            "attachments": self.attachments,
        }


# The backend folder — the anchor for any relative path in config.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _anchored(folder: str | os.PathLike) -> Path:
    """Turn a configured folder into an absolute path.

    `BACKUP_FOLDER=../backups` has to mean the same directory to every
    caller. Left relative it does not: our own code resolves it against
    the process working directory, but Flask's send_file resolves a
    relative path against the *application* folder, so a download 500s
    on a file the listing had just shown. Anchor it once, here.
    """
    p = Path(folder).expanduser()
    return p if p.is_absolute() else (BACKEND_ROOT / p).resolve()


def backup_dir() -> Path:
    """Resolve the backup folder. Operator can override via the
    `backup.folder` setting in the Settings UI; falls back to the
    BACKUP_FOLDER env var, then to ../backups relative to the backend
    folder. Always `mkdir -p`s the resulting path so a fresh install
    just works."""
    from . import settings as settings_service
    try:
        configured = settings_service.get("backup.folder")
    except Exception:
        configured = None
    folder = (
        (configured or "").strip()
        or current_app.config.get("BACKUP_FOLDER")
        or os.getenv("BACKUP_FOLDER")
        or (BACKEND_ROOT.parent / "backups")
    )
    p = _anchored(folder)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _db_env() -> dict[str, str]:
    """Build a subprocess env with PG* vars wired from app config /
    POSTGRES_* env vars. Password goes through PGPASSWORD so it isn't
    visible in `ps`."""
    env = os.environ.copy()
    pw = os.getenv("POSTGRES_PASSWORD") or current_app.config.get("POSTGRES_PASSWORD")
    if pw:
        env["PGPASSWORD"] = pw
    return env


def _conn_args() -> list[str]:
    """Common -h / -U / -d / -p arguments for pg_dump and pg_restore."""
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "greentech")
    db = os.getenv("POSTGRES_DB", "greentech_realestate")
    return ["-h", host, "-p", str(port), "-U", user, "-d", db]


def _safe_filename(name: str) -> str:
    """Validate that a caller-supplied filename is safe to join against
    BACKUP_FOLDER. Rejects path traversal, shell metacharacters, and
    anything that isn't a .zip or .dump."""
    name = (name or "").strip()
    if not SAFE_FILENAME_RE.fullmatch(name):
        raise BackupError("Invalid backup filename")
    return name


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _manifest_of(path: Path) -> dict | None:
    """Read a full backup's manifest without unpacking it. Returns None
    for a bare .dump or an archive we can't read."""
    if path.suffix.lower() != ".zip":
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read(MANIFEST_MEMBER))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        return None


def list_backups() -> list[BackupFile]:
    """Every backup file currently in BACKUP_FOLDER, newest first."""
    out: list[BackupFile] = []
    for p in backup_dir().iterdir():
        if not p.is_file() or p.suffix.lower() not in BACKUP_SUFFIXES:
            continue
        stat = p.stat()
        manifest = _manifest_of(p)
        out.append(
            BackupFile(
                filename=p.name,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                attachments=(manifest or {}).get("attachments"),
            )
        )
    out.sort(key=lambda b: b.created_at, reverse=True)
    return out


def path_for(filename: str) -> Path:
    name = _safe_filename(filename)
    path = backup_dir() / name
    if not path.exists():
        raise BackupError("Backup file not found")
    return path


def delete_backup(filename: str) -> None:
    path_for(filename).unlink()


_TOOLS_HINT = (
    "Add the PostgreSQL bin folder (e.g. C:\\Program Files\\PostgreSQL\\18\\bin) "
    "to the system PATH and restart the backend service."
)


def _require_pg_dump() -> None:
    if shutil.which(PG_DUMP) is None:
        raise BackupError(f"pg_dump was not found on PATH. {_TOOLS_HINT}")


def _require_pg_restore() -> None:
    missing = [t for t in (PG_RESTORE, PSQL) if shutil.which(t) is None]
    if missing:
        raise BackupError(
            f"{' and '.join(missing)} {'was' if len(missing) == 1 else 'were'} "
            f"not found on PATH. {_TOOLS_HINT}"
        )


def _uploads_dir() -> Path:
    """Where attachment files live. Attachment rows store a path relative
    to this folder, so the two only make sense restored together."""
    folder = current_app.config.get("UPLOAD_FOLDER") or os.getenv("UPLOAD_FOLDER", "uploads")
    return _anchored(folder)


def _pg_dump_to(target: Path) -> None:
    _require_pg_dump()
    cmd = [PG_DUMP, *_conn_args(), "-Fc", "--no-owner", "--no-privileges", "-f", str(target)]
    try:
        proc = subprocess.run(
            cmd,
            env=_db_env(),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        target.unlink(missing_ok=True)
        raise BackupError("pg_dump timed out after 10 minutes")

    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        # stderr from pg_dump tends to contain the actual reason on one
        # line — strip to keep the API response tidy.
        msg = (proc.stderr or "pg_dump failed").strip().splitlines()[-1]
        raise BackupError(f"pg_dump failed: {msg}")


def create_backup() -> BackupFile:
    """Take a full backup: the database *and* the uploaded files, in one
    zip the operator can download and keep off-site.

    Both halves have to travel together. Attachment rows hold a relative
    path into the uploads folder, so a database-only restore would bring
    back every agreement, cheque copy and voucher as a broken link —
    which is exactly the evidence you most want after a disaster.

    Synchronous — for a small/medium DB this finishes in seconds. If you
    need it async, queue this through celery (see app.tasks.backup)."""
    _require_pg_dump()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    filename = f"{BACKUP_PREFIX}-{ts}.zip"
    target = backup_dir() / filename

    uploads = _uploads_dir()
    attachments = 0

    with tempfile.TemporaryDirectory() as tmp:
        dump_path = Path(tmp) / DB_MEMBER
        _pg_dump_to(dump_path)

        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(dump_path, DB_MEMBER)

                if uploads.is_dir():
                    for path in sorted(uploads.rglob("*")):
                        if not path.is_file():
                            continue
                        rel = path.relative_to(uploads).as_posix()
                        zf.writestr(
                            zipfile.ZipInfo(UPLOADS_MEMBER_PREFIX + rel),
                            path.read_bytes(),
                        )
                        attachments += 1

                zf.writestr(MANIFEST_MEMBER, json.dumps({
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "database": os.getenv("POSTGRES_DB", "greentech_realestate"),
                    "attachments": attachments,
                    "uploads_folder": str(uploads),
                }, indent=2))
        except OSError as exc:
            target.unlink(missing_ok=True)
            raise BackupError(f"Could not write the backup archive: {exc}") from exc

    stat = target.stat()
    return BackupFile(
        filename=filename,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        attachments=attachments,
    )


def _psql_on_target(sql: str, *, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess:
    """Run a single SQL statement against the application's own database.

    Everything the restore needs happens *inside* the database, so there
    is no reason to connect to the `postgres` admin database — and no
    reason to require any privilege beyond the ones the app role already
    holds over its own objects.
    """
    _require_pg_restore()
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "greentech")
    db_name = os.getenv("POSTGRES_DB", "greentech_realestate")
    cmd = [PSQL, "-h", host, "-p", str(port), "-U", user, "-d", db_name,
           "-v", "ON_ERROR_STOP=1", "-c", sql]
    proc = subprocess.run(
        cmd, env=_db_env(), capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if check and proc.returncode != 0:
        msg = (proc.stderr or "psql failed").strip().splitlines()[-1]
        raise BackupError(f"psql failed ({sql[:60]}…): {msg}")
    return proc


def restore_backup(source: Path) -> dict:
    """Restore a backup, database and uploaded files both.

    A `.zip` is a full backup — the database is restored first, then the
    uploads folder is replaced so the attachment rows and the files they
    point at come back in step. A bare `.dump` restores the database
    only; the caller is told so it can warn that attachments will be
    missing.

    The previous uploads folder is never deleted, only moved aside to a
    timestamped sibling. Restoring the wrong archive is a bad afternoon;
    it should not also be an unrecoverable one.
    """
    if not source.exists():
        raise BackupError("Backup file not found")

    if source.suffix.lower() != ".zip":
        _restore_database(source)
        return {"database": True, "attachments": None, "uploads_backup": None}

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        try:
            with zipfile.ZipFile(source) as zf:
                names = set(zf.namelist())
                if DB_MEMBER not in names:
                    raise BackupError(
                        f"{source.name} is not a portal backup — it has no {DB_MEMBER}")
                _extract_safely(zf, staged)
        except zipfile.BadZipFile as exc:
            raise BackupError(f"{source.name} is not a readable zip archive") from exc

        # Database first: if it fails, the files on disk are untouched.
        _restore_database(staged / DB_MEMBER)
        moved_to, count = _restore_uploads(staged / "uploads")

    return {"database": True, "attachments": count, "uploads_backup": moved_to}


def _extract_safely(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract every member, refusing any that would escape `dest`.

    A crafted archive can carry `../../etc/passwd` or an absolute path;
    Python's own extractall has historically been permissive about it.
    Backups can be uploaded by an operator from anywhere, so the archive
    is not trusted just because someone with backup.manage sent it.
    """
    dest = dest.resolve()
    for member in zf.infolist():
        if member.is_dir():
            continue
        target = (dest / member.filename).resolve()
        if not target.is_relative_to(dest):
            raise BackupError(
                f"Refusing to extract {member.filename!r} — it points outside "
                "the restore folder")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def _restore_uploads(staged_uploads: Path) -> tuple[str | None, int]:
    """Swap the live uploads folder for the one in the archive, keeping
    the old one aside. Returns (where the old folder went, file count)."""
    live = _uploads_dir()
    count = sum(1 for p in staged_uploads.rglob("*") if p.is_file()) \
        if staged_uploads.is_dir() else 0

    moved_to: str | None = None
    if live.exists() and any(live.iterdir()):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        aside = live.parent / f"{live.name}.pre-restore-{ts}"
        shutil.move(str(live), str(aside))
        moved_to = str(aside)

    live.mkdir(parents=True, exist_ok=True)
    if staged_uploads.is_dir():
        for path in staged_uploads.rglob("*"):
            if not path.is_file():
                continue
            target = live / path.relative_to(staged_uploads)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return moved_to, count


def _verify_dump(source: Path) -> None:
    """Read the dump's table of contents before anything is destroyed.

    `pg_restore --list` parses the archive header without touching the
    server, so a truncated download or a file that isn't a custom-format
    dump is caught while the live data is still intact.
    """
    try:
        proc = subprocess.run(
            [PG_RESTORE, "--list", str(source)],
            env=_db_env(), capture_output=True, text=True, timeout=120, check=False,
        )
    except subprocess.TimeoutExpired:
        raise BackupError("Could not read the backup file (timed out)")
    if proc.returncode != 0:
        msg = (proc.stderr or "unreadable").strip().splitlines()[-1]
        raise BackupError(f"{source.name} is not a readable database dump: {msg}")


def _restore_database(source: Path) -> None:
    """Restore the database from a custom-format pg_dump file.

    Strategy: `pg_restore --clean --if-exists` into the *existing*
    database, inside a single transaction.

    An earlier version dropped the whole database and recreated it. That
    was wrong in a way worth recording, because it failed destructively:
    the application role owns its database, so the DROP succeeded, but
    creating a database needs the CREATEDB attribute, which a
    least-privilege app role does not have. The restore therefore
    deleted everything and then stopped — the one operation where that
    outcome is least acceptable. Replacing objects inside the database
    needs no special privilege, and the database never stops existing.

    `--clean` was originally avoided because its per-object DROPs
    deadlocked against sibling waitress threads and celery workers
    holding open sessions. That is handled here by disposing our own
    pool and terminating every other backend on the database first, so
    nothing is left holding a lock.

    After the restore SQLAlchemy's engine pool is disposed; the next
    request will reconnect. The route layer tells the operator their
    session may need a refresh.
    """
    _require_pg_restore()
    if not source.exists():
        raise BackupError("Backup file not found")

    # Prove the archive is readable BEFORE dropping a single object.
    _verify_dump(source)

    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "greentech")
    db_name = os.getenv("POSTGRES_DB", "greentech_realestate")
    env = _db_env()

    # 1. Release THIS worker's pooled connections so the DROPs below
    #    don't have to fight us. dispose() flushes the pool; next
    #    session access creates a fresh connection.
    try:
        from ..extensions import db as _db
        _db.session.remove()
        _db.engine.dispose()
    except Exception:
        # If we somehow can't import the app db (unit test, CLI), keep
        # going — pg_terminate_backend below catches sibling workers.
        pass

    # 2. Kill every other connection to the target DB so --clean's DROPs
    #    don't block on their locks. check=False because
    #    pg_terminate_backend occasionally returns false for a pid that
    #    has already exited.
    _psql_on_target(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        timeout=30,
        check=False,
    )

    # 3. Restore in place. --clean --if-exists drops each object it is
    #    about to recreate; --single-transaction makes the whole thing
    #    atomic, so a failure rolls back to the pre-restore state rather
    #    than leaving a half-built schema.
    cmd = [
        PG_RESTORE,
        "-h", host, "-p", str(port), "-U", user, "-d", db_name,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--single-transaction",
        "--exit-on-error",
        str(source),
    ]
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            timeout=900, check=False,
        )
    except subprocess.TimeoutExpired:
        raise BackupError("pg_restore timed out after 15 minutes")

    if proc.returncode != 0:
        msg = (proc.stderr or "pg_restore failed").strip().splitlines()[-1]
        raise BackupError(f"pg_restore failed: {msg}")


# Tables whose absence from a dump's table of contents means pg_dump
# silently skipped something — a failure mode `_verify_dump()`'s
# readability check alone would not catch, since a truncated-but-valid
# dump still parses fine.
CORE_TABLES_TO_VERIFY = ("landlords", "clients", "generated_agreements", "client_contracts")


def verify_backup_contents(filename: str) -> dict:
    """A deeper structural check than `_verify_dump()`'s readability-only
    pass, run on an existing backup file without touching the live
    database at all — no restore, no scratch database (the app role has
    no CREATEDB, and a genuine restore-into-scratch-DB drill would need
    either that privilege or a second Postgres instance, both out of
    scope for an automated task; see the restore-drill note in the repo's
    planning notes for why).

    Two checks: (1) the dump's table of contents actually lists the core
    tables — catches a pg_dump that silently dropped one; (2) the
    manifest's attachment count isn't wildly off from what the live
    Attachment table holds — catches a zip that lost the uploads folder.
    Returns {"ok", "missing_tables", "attachment_mismatch"}."""
    path = path_for(filename)
    _require_pg_restore()

    with tempfile.TemporaryDirectory() as tmp:
        dump_source = path
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                if DB_MEMBER not in zf.namelist():
                    raise BackupError(
                        f"{path.name} is not a portal backup — it has no {DB_MEMBER}")
                zf.extract(DB_MEMBER, tmp)
            dump_source = Path(tmp) / DB_MEMBER

        try:
            proc = subprocess.run(
                [PG_RESTORE, "--list", str(dump_source)],
                env=_db_env(), capture_output=True, text=True, timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            raise BackupError("Could not read the backup file (timed out)")
        if proc.returncode != 0:
            msg = (proc.stderr or "unreadable").strip().splitlines()[-1]
            raise BackupError(f"{path.name} is not a readable database dump: {msg}")

        toc = proc.stdout or ""
        missing = [t for t in CORE_TABLES_TO_VERIFY if f"TABLE public {t} " not in toc]

    manifest = _manifest_of(path) or {}
    attachment_mismatch = None
    manifest_count = manifest.get("attachments")
    if manifest_count is not None:
        from ..models import Attachment
        live_count = Attachment.query.count()
        # Some drift between backup time and verification time is
        # expected — a handful of attachments added or removed since the
        # backup was taken is normal, not a sign the uploads folder was
        # lost. Only alarm once the larger side is big enough that "a few
        # files changed" stops being a plausible explanation, and the
        # smaller side is either zero or under half of it.
        larger = max(manifest_count, live_count)
        smaller = min(manifest_count, live_count)
        if larger >= 5 and (smaller == 0 or smaller / larger < 0.5):
            attachment_mismatch = {"manifest": manifest_count, "live": live_count}

    return {
        "ok": not missing and attachment_mismatch is None,
        "missing_tables": missing,
        "attachment_mismatch": attachment_mismatch,
    }


def prune_old(retention_days: int) -> int:
    """Delete backup files older than `retention_days`. Returns the
    number of files removed. Called from the scheduled task."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 86400)
    removed = 0
    for p in backup_dir().iterdir():
        if not p.is_file() or p.suffix.lower() not in BACKUP_SUFFIXES:
            continue
        if p.stat().st_mtime < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
