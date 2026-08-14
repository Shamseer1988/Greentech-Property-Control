def _cookies(client):
    """Return {name: value} for cookies currently on the test client jar.

    Works with both the dict-style jar shipped in Werkzeug 3 and the
    older list-style jar."""
    out = {}
    jar = client._cookies
    if hasattr(jar, "values"):
        items = list(jar.values())
    else:
        items = list(jar)
    for c in items:
        name = getattr(c, "key", None) or getattr(c, "name", None)
        out[name] = c.value
    return out


def test_login_success_sets_cookies(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "ChangeMe123!"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    # JWTs no longer travel in the body — only the user.
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert data["user"]["is_super_user"] is True
    cookies = _cookies(client)
    assert "access_token_cookie" in cookies
    assert "refresh_token_cookie" in cookies
    assert "csrf_access_token" in cookies  # readable by JS for X-CSRF-TOKEN echo


def test_login_bad_password(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_cookie(client, auth_headers):
    # GET routes need no CSRF echo; the cookie alone authenticates.
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["username"] == "admin"
    assert "*" in body["permissions"] or len(body["permissions"]) > 10


def test_users_list_requires_permission(client):
    resp = client.get("/api/v1/users")
    assert resp.status_code == 401


def test_users_list(client, auth_headers):
    resp = client.get("/api/v1/users", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["meta"]["count"] >= 1


def test_create_and_login_regular_user(app, client, auth_headers):
    roles = client.get("/api/v1/roles", headers=auth_headers).get_json()["data"]
    hr = next(r for r in roles if r["code"] == "accounts")

    resp = client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "username": "hr1",
            "email": "hr1@greentech.local",
            "full_name": "HR One",
            "password": "Password123",
            "role_ids": [hr["id"]],
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)

    # Second logical session: fresh client so its cookie jar is clean.
    hr_client = app.test_client(use_cookies=True)
    login = hr_client.post("/api/v1/auth/login", json={"username": "hr1", "password": "Password123"})
    assert login.status_code == 200
    csrf = _cookies(hr_client)["csrf_access_token"]
    hr_headers = {"X-CSRF-TOKEN": csrf}

    me = hr_client.get("/api/v1/auth/me").get_json()["data"]
    assert "property.view" in me["permissions"]
    assert "user.manage" not in me["permissions"]

    forbidden = hr_client.post(
        "/api/v1/users", headers=hr_headers,
        json={"username": "x", "email": "x@x.com", "full_name": "X", "password": "Password123"},
    )
    assert forbidden.status_code == 403


def test_role_permission_catalog(client, auth_headers):
    resp = client.get("/api/v1/roles/permissions/catalog", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "modules" in data
    assert data["count"] > 0


def test_audit_log_records_login(client, auth_headers):
    resp = client.get("/api/v1/audit?action=login", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.get_json()["data"]
    assert any(r["action"] == "login" for r in rows)
