import os
import pytest

from app import create_app
from app.extensions import db
from app.cli import (
    _seed_permissions, _seed_roles, _seed_super_user, _seed_expense_categories,
    _seed_property_types, _seed_unit_types,
)
from app.services import notification_rules, settings as settings_service


# The seeder reads the super-user credentials from the environment, and
# backend/.env is loaded at import time — so without this the operator's
# real password would decide whether the suite passes. Pin them here so
# the tests are hermetic on any machine.
TEST_SUPERUSER_PASSWORD = "ChangeMe123!"
os.environ["SUPERUSER_USERNAME"] = "admin"
os.environ["SUPERUSER_EMAIL"] = "admin@test.local"
os.environ["SUPERUSER_PASSWORD"] = TEST_SUPERUSER_PASSWORD


@pytest.fixture()
def app(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    os.environ["UPLOAD_FOLDER"] = str(upload_dir)
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = str(upload_dir)
    with app.app_context():
        db.create_all()
        perm_index = _seed_permissions()
        role_index = _seed_roles(perm_index)
        _seed_super_user(role_index)
        # Mirrors `flask seed` — tests exercise the same starting data an
        # operator gets: the expense categories and ledger mappings the
        # P&L import relies on, and the notification rules (all disabled)
        # the messaging screens expect to find.
        _seed_expense_categories()
        _seed_property_types()
        _seed_unit_types()
        settings_service.seed_defaults()
        notification_rules.seed_defaults()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    # use_cookies=True is the default but spell it out — Phase 1's auth
    # depends entirely on the client cookie jar persisting JWT cookies
    # between requests.
    return app.test_client(use_cookies=True)


def _csrf_from(client):
    """Pluck the readable csrf_access_token cookie value from the client jar."""
    for c in client._cookies.values() if hasattr(client._cookies, "values") else client._cookies:
        # Werkzeug's test-client cookie jar is dict-like in recent versions
        # and a list in older ones; handle both.
        name = getattr(c, "key", None) or getattr(c, "name", None)
        if name == "csrf_access_token":
            return c.value
    return None


@pytest.fixture()
def admin_token(client):
    """Logs the test client in as admin. Cookies persist on the client jar;
    this fixture also returns the CSRF token value so callers can mint
    auth_headers for mutating requests (GETs need no header)."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": TEST_SUPERUSER_PASSWORD},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    csrf = _csrf_from(client)
    assert csrf, "csrf_access_token cookie missing after login"
    return csrf


@pytest.fixture()
def auth_headers(admin_token):
    # Cookies travel automatically on the test client; the only thing
    # callers need on top is the CSRF echo header for non-safe methods.
    return {"X-CSRF-TOKEN": admin_token}
