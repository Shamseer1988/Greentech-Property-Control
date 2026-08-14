"""Phase 9 — consolidated security regression suite.

Many of these scenarios are covered in earlier files; this module
consolidates the security contract into one readable place that's the
first thing to fail if a future change loosens a guard. Adds the one
case not covered elsewhere: an expired access token must be rejected
even though its signature is still valid."""
import io
from datetime import timedelta
import pytest

from app import create_app
from app.extensions import db, limiter
from app.cli import _seed_permissions, _seed_roles, _seed_super_user
from app.services import settings as settings_service
from config import TestingConfig


def _cookies(client):
    out = {}
    jar = client._cookies
    items = list(jar.values()) if hasattr(jar, "values") else list(jar)
    for c in items:
        name = getattr(c, "key", None) or getattr(c, "name", None)
        out[name] = c.value
    return out


def _login(app, username="admin", password="ChangeMe123!"):
    c = app.test_client(use_cookies=True)
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    return c, _cookies(c).get("csrf_access_token")


# ---------------------------------------------------------------------------
# 1. Expired access token is rejected. We force-expire by minting an app
# instance whose JWT_ACCESS_TOKEN_EXPIRES is 1 second, then sleep.
# ---------------------------------------------------------------------------
@pytest.fixture()
def short_jwt_app(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(TestingConfig, "JWT_ACCESS_TOKEN_EXPIRES",
                        timedelta(seconds=1), raising=False)
    app = create_app("testing")
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


def test_expired_access_token_is_rejected(short_jwt_app):
    import time
    c, _csrf = _login(short_jwt_app)
    # First call works.
    assert c.get("/api/v1/auth/me").status_code == 200
    # Wait past the 1-second expiry.
    time.sleep(1.5)
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 2. Revoked token (logout-jti blocklist) is rejected on replay.
# ---------------------------------------------------------------------------
def test_revoked_token_rejected_after_logout(app):
    c, csrf = _login(app)
    cookies_before = _cookies(c)
    r = c.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    assert r.status_code == 200

    replay = app.test_client(use_cookies=True)
    replay.set_cookie("access_token_cookie",
                      cookies_before["access_token_cookie"], path="/api/v1")
    assert replay.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# 3. CSRF enforced on mutating cookie-auth calls.
# ---------------------------------------------------------------------------
def test_mutating_call_without_csrf_is_401(app):
    c, _csrf = _login(app)
    r = c.post("/api/v1/landlords", json={"name": "no-csrf"})
    assert r.status_code == 401


def test_mutating_call_with_csrf_succeeds(app):
    c, csrf = _login(app)
    r = c.post("/api/v1/landlords", json={"name": "with-csrf"},
               headers={"X-CSRF-TOKEN": csrf})
    assert r.status_code in (200, 201)


# ---------------------------------------------------------------------------
# 4. Permission-bypass attempt denied. A non-super-user without
# user.manage cannot create users.
# ---------------------------------------------------------------------------
def test_permission_bypass_denied_for_low_perm_user(client, app, auth_headers):
    # Admin (cookie) creates a HR Executive (no user.manage).
    roles = client.get("/api/v1/roles").get_json()["data"]
    hr = next(r for r in roles if r["code"] == "accounts")
    client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={"username": "low1", "email": "low1@x.com", "full_name": "Low",
              "password": "Password123", "role_ids": [hr["id"]]},
    )

    low = app.test_client(use_cookies=True)
    login = low.post("/api/v1/auth/login",
                     json={"username": "low1", "password": "Password123"})
    assert login.status_code == 200
    low_csrf = _cookies(low)["csrf_access_token"]

    # Attempt to create another user → 403, not 200.
    r = low.post(
        "/api/v1/users",
        headers={"X-CSRF-TOKEN": low_csrf},
        json={"username": "x", "email": "x@x.com",
              "full_name": "X", "password": "Password123"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 5. Rate-limit returns 429 (consolidated reference; full test lives in
# test_rate_limit.py).
# ---------------------------------------------------------------------------
def test_login_rate_limit_returns_429(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True, raising=False)
    app = create_app("testing")
    try:
        limiter.reset()
    except Exception:
        pass
    with app.app_context():
        db.create_all()
        pi = _seed_permissions()
        _seed_roles(pi)
        settings_service.seed_defaults()
        db.session.commit()
        c = app.test_client()
        statuses = [
            c.post("/api/v1/auth/login",
                   json={"username": "x", "password": "x"}).status_code
            for _ in range(11)
        ]
        db.session.remove()
        db.drop_all()
    assert statuses[10] == 429, statuses


# ---------------------------------------------------------------------------
# 6. Upload content-sniff rejection (consolidated reference; full
# coverage lives in test_attachments.py).
# ---------------------------------------------------------------------------
def test_upload_content_sniff_rejects_mime_mismatch(client, auth_headers):
    ll = client.post("/api/v1/landlords", headers=auth_headers,
                     json={"name": "Sec LL"}).get_json()["data"]
    prop = client.post(
        "/api/v1/properties", headers=auth_headers,
        json={"name": "Sec Tower", "property_type": "full_building",
              "city": "Doha", "landlord_id": ll["id"]},
    ).get_json()["data"]
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    r = client.post(
        "/api/v1/attachments",
        headers=auth_headers,
        data={
            "entity_type": "property", "entity_id": str(prop["id"]),
            "file": (io.BytesIO(pdf_bytes), "evil.png", "image/png"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 7. /metrics requires the token when one is configured (bonus on
# Phase 6's observability).
# ---------------------------------------------------------------------------
def test_metrics_endpoint_token_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    app = create_app("testing")
    app.config["METRICS_TOKEN"] = "scraper-token"
    with app.app_context():
        db.create_all()
        try:
            c = app.test_client()
            assert c.get("/metrics").status_code == 401
            assert c.get("/metrics", headers={"X-Metrics-Token": "scraper-token"}).status_code == 200
        finally:
            db.session.remove()
            db.drop_all()
