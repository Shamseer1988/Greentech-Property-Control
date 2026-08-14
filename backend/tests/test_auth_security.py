"""Phase 1 — cookie-auth security regression suite."""


def _cookies(client):
    out = {}
    jar = client._cookies
    items = list(jar.values()) if hasattr(jar, "values") else list(jar)
    for c in items:
        name = getattr(c, "key", None) or getattr(c, "name", None)
        out[name] = c.value
    return out


def _login(app, username="admin", password="ChangeMe123!"):
    """Spin up an isolated test client + sign in. Returns (client, csrf)."""
    c = app.test_client(use_cookies=True)
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    return c, _cookies(c)["csrf_access_token"]


# ---------------------------------------------------------------------------
# 1. login plants cookies and hides JWTs
# ---------------------------------------------------------------------------
def test_login_body_has_no_tokens(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "ChangeMe123!"})
    assert r.status_code == 200
    body = r.get_json()["data"]
    assert "access_token" not in body
    assert "refresh_token" not in body
    cookies = _cookies(client)
    assert cookies.get("access_token_cookie")
    assert cookies.get("refresh_token_cookie")
    assert cookies.get("csrf_access_token")
    assert cookies.get("csrf_refresh_token")


# ---------------------------------------------------------------------------
# 2. GETs work via cookie alone; mutating calls require CSRF echo
# ---------------------------------------------------------------------------
def test_get_works_with_cookie_only(app):
    c, _csrf = _login(app)
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200


def test_mutating_call_without_csrf_is_rejected(app):
    c, _csrf = _login(app)
    # No X-CSRF-TOKEN echoed → Flask-JWT-Extended rejects.
    r = c.post("/api/v1/landlords", json={"name": "X"})
    assert r.status_code == 401


def test_mutating_call_with_csrf_succeeds(app):
    c, csrf = _login(app)
    r = c.post("/api/v1/landlords", json={"name": "CSRF OK"},
               headers={"X-CSRF-TOKEN": csrf})
    assert r.status_code in (200, 201), r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 3. logout revokes the jti — old cookies stop working
# ---------------------------------------------------------------------------
def test_logout_revokes_token(app):
    c, csrf = _login(app)
    # Snapshot cookies before logout so we can re-attach them afterwards.
    cookies_before = _cookies(c)
    r = c.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    assert r.status_code == 200

    # Replay the original access cookie against a fresh client.
    replay = app.test_client(use_cookies=True)
    replay.set_cookie("access_token_cookie", cookies_before["access_token_cookie"],
                      path="/api/v1")
    r2 = replay.get("/api/v1/auth/me")
    assert r2.status_code == 401, "blocklist should reject revoked jti"


# ---------------------------------------------------------------------------
# 4. change-password bumps token_version → ALL outstanding sessions die
# ---------------------------------------------------------------------------
def test_change_password_invalidates_other_sessions(app, client):
    # Make a regular user to mutate without nuking the admin fixture.
    admin = client
    admin.post("/api/v1/auth/login", json={"username": "admin", "password": "ChangeMe123!"})
    admin_csrf = _cookies(admin)["csrf_access_token"]
    roles = admin.get("/api/v1/roles").get_json()["data"]
    hr = next(r for r in roles if r["code"] == "accounts")
    r = admin.post(
        "/api/v1/users",
        headers={"X-CSRF-TOKEN": admin_csrf},
        json={"username": "victim", "email": "v@v.com", "full_name": "V",
              "password": "Password123", "role_ids": [hr["id"]]},
    )
    assert r.status_code == 201

    # Two simultaneous victim sessions.
    s1, csrf1 = _login(app, "victim", "Password123")
    s2, csrf2 = _login(app, "victim", "Password123")
    assert s1.get("/api/v1/auth/me").status_code == 200
    assert s2.get("/api/v1/auth/me").status_code == 200

    # Session 1 changes its password.
    r = s1.post(
        "/api/v1/auth/change-password",
        headers={"X-CSRF-TOKEN": csrf1},
        json={"old_password": "Password123", "new_password": "NewPassword456"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    # Session 2's cookies are now stale: token_version mismatch → 401.
    assert s2.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# 5. me requires auth
# ---------------------------------------------------------------------------
def test_me_unauthenticated_is_401(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
