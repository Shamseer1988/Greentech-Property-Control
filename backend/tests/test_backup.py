"""Backup archives: what goes in, what comes back, and what is refused.

pg_dump and pg_restore need a real PostgreSQL, which the suite doesn't
have (it runs on SQLite), so those two calls are stubbed here and the
archive layer around them is tested for real. The genuine round trip
against Postgres is exercised by scripts/verify_phase5.py.
"""
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.services import backup as backup_service


@pytest.fixture()
def backup_env(app, tmp_path, monkeypatch):
    """Point the service at throwaway folders and stub out Postgres."""
    folder = tmp_path / "backups"
    folder.mkdir()
    uploads = Path(app.config["UPLOAD_FOLDER"])

    monkeypatch.setattr(backup_service, "backup_dir", lambda: folder)
    monkeypatch.setattr(backup_service, "_require_pg_dump", lambda: None)
    monkeypatch.setattr(backup_service, "_require_pg_restore", lambda: None)
    monkeypatch.setattr(
        backup_service, "_pg_dump_to",
        lambda target: Path(target).write_bytes(b"PGDMP-fake-dump"))

    restored: list[bytes] = []
    monkeypatch.setattr(
        backup_service, "_restore_database",
        lambda source: restored.append(Path(source).read_bytes()))

    return {"folder": folder, "uploads": uploads, "restored": restored}


def _put(uploads: Path, rel: str, body: bytes = b"x") -> Path:
    path = uploads / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


# ---------------------------------------------------------------- create

def test_backup_carries_the_database_and_every_uploaded_file(app, backup_env):
    _put(backup_env["uploads"], "landlord/1/agreement.pdf", b"the agreement")
    _put(backup_env["uploads"], "contract/9/cheque-copy.jpg", b"the cheque")

    with app.app_context():
        rec = backup_service.create_backup()

    assert rec.filename.endswith(".zip")
    assert rec.kind == "full"
    assert rec.attachments == 2

    with zipfile.ZipFile(backup_env["folder"] / rec.filename) as zf:
        names = set(zf.namelist())
        assert backup_service.DB_MEMBER in names
        assert "uploads/landlord/1/agreement.pdf" in names
        assert "uploads/contract/9/cheque-copy.jpg" in names
        assert zf.read("uploads/landlord/1/agreement.pdf") == b"the agreement"

        manifest = json.loads(zf.read(backup_service.MANIFEST_MEMBER))
        assert manifest["attachments"] == 2
        assert manifest["created_at"]


def test_backup_of_an_empty_portal_still_produces_a_restorable_archive(app, backup_env):
    with app.app_context():
        rec = backup_service.create_backup()
    assert rec.attachments == 0
    with zipfile.ZipFile(backup_env["folder"] / rec.filename) as zf:
        assert backup_service.DB_MEMBER in zf.namelist()


def test_history_reports_kind_and_attachment_count(app, backup_env):
    _put(backup_env["uploads"], "a.pdf")
    with app.app_context():
        backup_service.create_backup()
        # A bare pg_dump someone dropped in the folder by hand.
        (backup_env["folder"] / "manual.dump").write_bytes(b"PGDMP")
        rows = backup_service.list_backups()

    by_kind = {r.kind: r for r in rows}
    assert by_kind["full"].attachments == 1
    assert by_kind["database"].attachments is None
    assert by_kind["database"].to_dict()["size_human"]


# --------------------------------------------------------------- restore

def test_restoring_a_full_backup_brings_the_files_back(app, backup_env):
    uploads = backup_env["uploads"]
    _put(uploads, "landlord/1/agreement.pdf", b"the agreement")

    with app.app_context():
        rec = backup_service.create_backup()

        # Someone deletes the file after the backup was taken.
        (uploads / "landlord/1/agreement.pdf").unlink()
        _put(uploads, "stray.txt", b"written after the backup")

        result = backup_service.restore_backup(backup_env["folder"] / rec.filename)

    assert backup_env["restored"] == [b"PGDMP-fake-dump"]
    assert result["attachments"] == 1
    assert (uploads / "landlord/1/agreement.pdf").read_bytes() == b"the agreement"
    # The archive is authoritative: files added since are not carried over.
    assert not (uploads / "stray.txt").exists()


def test_the_replaced_uploads_folder_is_kept_not_deleted(app, backup_env):
    uploads = backup_env["uploads"]
    _put(uploads, "keep-me.pdf", b"precious")

    with app.app_context():
        rec = backup_service.create_backup()
        _put(uploads, "written-later.pdf", b"also precious")
        result = backup_service.restore_backup(backup_env["folder"] / rec.filename)

    aside = Path(result["uploads_backup"])
    assert aside.is_dir()
    assert (aside / "written-later.pdf").read_bytes() == b"also precious"


def test_a_bare_dump_restores_the_database_and_says_so(app, backup_env):
    source = backup_env["folder"] / "manual.dump"
    source.write_bytes(b"PGDMP-by-hand")

    with app.app_context():
        result = backup_service.restore_backup(source)

    assert backup_env["restored"] == [b"PGDMP-by-hand"]
    assert result["attachments"] is None
    assert result["uploads_backup"] is None


def test_an_archive_without_a_database_member_is_refused(app, backup_env):
    bogus = backup_env["folder"] / "not-a-backup.zip"
    with zipfile.ZipFile(bogus, "w") as zf:
        zf.writestr("holiday-photo.jpg", b"nope")

    with app.app_context():
        with pytest.raises(backup_service.BackupError, match="database.dump"):
            backup_service.restore_backup(bogus)
    assert backup_env["restored"] == []


def test_a_zip_that_escapes_the_restore_folder_is_refused(app, backup_env):
    """Zip-slip. An operator can upload an archive from anywhere, so it
    is not trusted just because they hold backup.manage."""
    evil = backup_env["folder"] / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr(backup_service.DB_MEMBER, b"PGDMP")
        zf.writestr("../../pwned.txt", b"escaped")

    with app.app_context():
        with pytest.raises(backup_service.BackupError, match="outside"):
            backup_service.restore_backup(evil)
    assert backup_env["restored"] == []


def test_a_corrupt_archive_fails_before_touching_the_database(app, backup_env):
    junk = backup_env["folder"] / "truncated.zip"
    junk.write_bytes(b"not really a zip")

    with app.app_context():
        with pytest.raises(backup_service.BackupError):
            backup_service.restore_backup(junk)
    assert backup_env["restored"] == []


# -------------------------------------------------- restore is not destructive

def test_an_unreadable_dump_is_rejected_before_anything_is_dropped(app, monkeypatch, tmp_path):
    """The check that matters most: a bad archive must cost nothing.

    An earlier version dropped the database first and discovered
    problems afterwards, which is the one order that can lose data.
    """
    source = tmp_path / "truncated.dump"
    source.write_bytes(b"not a dump")

    calls: list[str] = []
    monkeypatch.setattr(backup_service, "_require_pg_restore", lambda: None)
    monkeypatch.setattr(backup_service, "_psql_on_target",
                        lambda sql, **kw: calls.append("psql"))
    monkeypatch.setattr(backup_service.subprocess, "run", _fake_run(calls))

    with app.app_context():
        with pytest.raises(backup_service.BackupError, match="not a readable database dump"):
            backup_service._restore_database(source)

    assert calls == ["pg_restore --list"], \
        "nothing may touch the live database before the dump is verified"


def test_restore_replaces_objects_in_place_and_never_drops_the_database(
        app, monkeypatch, tmp_path):
    """`DROP DATABASE` needs the CREATEDB attribute to undo, which a
    least-privilege app role hasn't got — so the restore must work
    inside the existing database."""
    source = tmp_path / "good.dump"
    source.write_bytes(b"PGDMP")

    statements: list[str] = []
    commands: list[list[str]] = []
    monkeypatch.setattr(backup_service, "_require_pg_restore", lambda: None)
    monkeypatch.setattr(backup_service, "_psql_on_target",
                        lambda sql, **kw: statements.append(sql))

    def run(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(backup_service.subprocess, "run", run)

    with app.app_context():
        backup_service._restore_database(source)

    joined = " ".join(statements).upper()
    assert "DROP DATABASE" not in joined
    assert "CREATE DATABASE" not in joined
    assert any("PG_TERMINATE_BACKEND" in s.upper() for s in statements), \
        "other sessions must be cleared or --clean will block on their locks"

    restore_cmd = commands[-1]
    assert "--clean" in restore_cmd and "--if-exists" in restore_cmd
    assert "--single-transaction" in restore_cmd, "a failed restore must roll back"


def _fake_run(calls: list[str]):
    def run(cmd, **kwargs):
        if "--list" in cmd:
            calls.append("pg_restore --list")
            return subprocess.CompletedProcess(cmd, 1, "", "unrecognised archive format")
        calls.append("pg_restore")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


# ------------------------------------------------------------- filenames

@pytest.mark.parametrize("name", [
    "../../etc/passwd", "back;rm -rf /.dump", "nope.txt", "", "a.dump.exe",
])
def test_unsafe_filenames_are_rejected(app, name):
    with app.app_context():
        with pytest.raises(backup_service.BackupError, match="Invalid backup filename"):
            backup_service._safe_filename(name)


@pytest.mark.parametrize("name", [
    "greentech-realestate-20260803-101500Z.zip",
    "greentech-realestate-20260803-101500Z.dump",
])
def test_our_own_filenames_are_accepted(app, name):
    with app.app_context():
        assert backup_service._safe_filename(name) == name


# ------------------------------------------------------------------ API

def test_backup_endpoints_need_the_permission(client):
    assert client.get("/api/v1/backups").status_code == 401


def test_upload_restore_rejects_a_file_that_is_not_a_backup(client, auth_headers):
    import io
    resp = client.post(
        "/api/v1/backups/upload-restore", headers=auth_headers,
        data={"file": (io.BytesIO(b"whatever"), "notes.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert ".zip" in resp.get_json()["message"]
