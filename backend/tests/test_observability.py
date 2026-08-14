"""Phase 6 — JSON logging + request-id + Prometheus tests."""
import json
import pytest

from app import create_app
from app.extensions import db
from app.cli import _seed_permissions, _seed_roles, _seed_super_user
from app.services import settings as settings_service


@pytest.fixture()
def json_log_app(tmp_path, monkeypatch):
    """Spin up a fresh app with LOG_JSON=True. structlog's default
    PrintLogger writes to sys.stdout; tests use pytest's capsys to read
    those lines back. Config attrs are read at import time so we poke
    the class directly."""
    from config import TestingConfig
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setenv("UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(TestingConfig, "LOG_JSON", True, raising=False)
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(upload_dir)
    with app.app_context():
        db.create_all()
        pi = _seed_permissions()
        ri = _seed_roles(pi)
        _seed_super_user(ri)
        settings_service.seed_defaults()
        db.session.commit()
        try:
            yield app
        finally:
            db.session.remove()
            db.drop_all()


def _json_lines(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------
# request-id propagation
# ---------------------------------------------------------------------------
def test_request_id_echoed_in_response_header(json_log_app):
    c = json_log_app.test_client()
    r = c.get("/api/v1/health", headers={"X-Request-ID": "test-abc-123"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "test-abc-123"


def test_request_id_minted_when_absent(json_log_app):
    c = json_log_app.test_client()
    r = c.get("/api/v1/health")
    rid = r.headers.get("X-Request-ID")
    assert rid and len(rid) >= 16  # uuid4 hex is 32 chars


def test_request_id_appears_in_access_log_line(json_log_app, capsys):
    c = json_log_app.test_client()
    capsys.readouterr()  # discard setup chatter
    c.get("/api/v1/health", headers={"X-Request-ID": "find-me-in-logs"})

    captured = capsys.readouterr()
    lines = _json_lines(captured.out)
    matching = [l for l in lines if l.get("request_id") == "find-me-in-logs"]
    assert matching, f"no log line carried the request_id; saw: {lines}"
    access = next((l for l in matching if l.get("event") == "request"), None)
    assert access is not None, f"no 'request' event in: {matching}"
    assert access["method"] == "GET"
    assert access["path"] == "/api/v1/health"
    assert access["status"] == 200


def test_cf_ray_used_as_fallback(json_log_app):
    c = json_log_app.test_client()
    r = c.get("/api/v1/health", headers={"CF-Ray": "abcd1234-DFW"})
    assert r.headers.get("X-Request-ID") == "abcd1234-DFW"


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------
def test_metrics_open_when_no_token_configured(client):
    # Default TestingConfig leaves METRICS_TOKEN unset → /metrics
    # serves without auth (private-network deployments).
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "# HELP" in body  # Prometheus exposition format
    assert "greentech_app_info" in body


def test_metrics_requires_token_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    app = create_app("testing")
    app.config["METRICS_TOKEN"] = "secret-scraper-token"
    with app.app_context():
        db.create_all()
        try:
            c = app.test_client()
            assert c.get("/metrics").status_code == 401
            ok = c.get("/metrics", headers={"X-Metrics-Token": "secret-scraper-token"})
            assert ok.status_code == 200
            assert c.get("/metrics", headers={"X-Metrics-Token": "wrong"}).status_code == 401
        finally:
            db.session.remove()
            db.drop_all()
