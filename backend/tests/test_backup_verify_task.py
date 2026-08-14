"""verify_backup_contents() and the weekly verify_latest_backup task.

Same stubbing approach as test_backup.py: no real Postgres in the
suite, so pg_restore --list is monkeypatched to return a controlled
table-of-contents rather than actually reading an archive.
"""
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.services import backup as backup_service
from app.tasks import backup as backup_task


FULL_TOC = "\n".join(
    f"123; 1259 16000 TABLE public {t} greentech"
    for t in backup_service.CORE_TABLES_TO_VERIFY
)


def _fake_run(returncode: int, stdout: str = "", stderr: str = ""):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return run


@pytest.fixture()
def verify_env(app, tmp_path, monkeypatch):
    folder = tmp_path / "backups"
    folder.mkdir()
    monkeypatch.setattr(backup_service, "backup_dir", lambda: folder)
    monkeypatch.setattr(backup_service, "_require_pg_dump", lambda: None)
    monkeypatch.setattr(backup_service, "_require_pg_restore", lambda: None)
    return folder


def _make_zip(folder: Path, name: str, *, attachments: int) -> Path:
    path = folder / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(backup_service.DB_MEMBER, b"PGDMP-fake-dump")
        zf.writestr(backup_service.MANIFEST_MEMBER, json.dumps({
            "created_at": "2026-01-01T00:00:00+00:00",
            "database": "greentech_realestate",
            "attachments": attachments,
        }))
    return path


def test_ok_when_toc_has_every_core_table_and_counts_match(app, verify_env, monkeypatch):
    _make_zip(verify_env, "backup1.zip", attachments=2)
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout=FULL_TOC))
    with app.app_context():
        from app.models import Attachment  # noqa: F401 — just confirming importable
        result = backup_service.verify_backup_contents("backup1.zip")
    assert result["ok"] is True
    assert result["missing_tables"] == []
    assert result["attachment_mismatch"] is None


def test_missing_table_in_toc_is_reported(app, verify_env, monkeypatch):
    _make_zip(verify_env, "backup2.zip", attachments=0)
    partial_toc = "123; 1259 16000 TABLE public landlords greentech"
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout=partial_toc))
    with app.app_context():
        result = backup_service.verify_backup_contents("backup2.zip")
    assert result["ok"] is False
    assert "clients" in result["missing_tables"]
    assert "generated_agreements" in result["missing_tables"]


def test_wild_attachment_mismatch_is_reported(app, verify_env, monkeypatch):
    # Manifest claims 400 attachments; the live table (empty in this test
    # DB) holds 0 — an order-of-magnitude gap, not ordinary drift.
    _make_zip(verify_env, "backup3.zip", attachments=400)
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout=FULL_TOC))
    with app.app_context():
        result = backup_service.verify_backup_contents("backup3.zip")
    assert result["ok"] is False
    assert result["attachment_mismatch"] == {"manifest": 400, "live": 0}


def test_unreadable_dump_raises_before_any_toc_check(app, verify_env, monkeypatch):
    _make_zip(verify_env, "backup4.zip", attachments=0)
    monkeypatch.setattr(subprocess, "run", _fake_run(1, stderr="pg_restore: error: input file does not appear to be a valid archive"))
    with app.app_context():
        with pytest.raises(backup_service.BackupError):
            backup_service.verify_backup_contents("backup4.zip")


def test_task_skips_cleanly_when_no_backups_exist(app, verify_env):
    with app.app_context():
        result = backup_task.verify_latest_backup.run()
    assert result["status"] == "skipped"


def test_task_alerts_on_problems_found(app, verify_env, monkeypatch):
    _make_zip(verify_env, "backup5.zip", attachments=0)
    partial_toc = "123; 1259 16000 TABLE public landlords greentech"
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout=partial_toc))

    from app.services import telegram as telegram_service
    calls = []
    monkeypatch.setattr(
        telegram_service, "send_now",
        lambda **kwargs: calls.append(kwargs) or None)

    with app.app_context():
        result = backup_task.verify_latest_backup.run()

    assert result["status"] == "problems_found"
    assert len(calls) == 1
    assert "backup5.zip" in calls[0]["text"]
