"""Phase 4 — OpenAPI spec exposure + Phase 4 schema validation."""
import json


def test_openapi_spec_is_served_in_test_env(client):
    """Dev / testing envs expose the spec at /openapi.json so the
    frontend's openapi-typescript codegen script can read it."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.get_json()
    assert spec["openapi"].startswith("3.")
    # Migrated paths are documented.
    paths = spec["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/landlords" in paths
    assert "/api/v1/landlords" in paths


def test_docs_ui_present(client):
    r = client.get("/docs")
    assert r.status_code == 200
    body = r.get_data(as_text=True).lower()
    assert "swagger" in body or "openapi" in body


def test_login_input_schema_in_spec(client):
    spec = client.get("/openapi.json").get_json()
    login_op = spec["paths"]["/api/v1/auth/login"]["post"]
    body_schema = login_op["requestBody"]["content"]["application/json"]["schema"]
    # The schema reference points at LoginIn — fetch it from components.
    assert "$ref" in body_schema or "properties" in body_schema


# ---------------------------------------------------------------------------
# 422 validation envelope
# ---------------------------------------------------------------------------
def test_login_missing_password_returns_422(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin"})
    assert r.status_code == 422
    body = r.get_json()
    assert body["success"] is False
    # details carries the marshmallow field-error map (or a stringified form).
    assert "password" in json.dumps(body.get("details", "")).lower()


def test_landlord_missing_name_returns_422(client, auth_headers):
    r = client.post("/api/v1/landlords", headers=auth_headers, json={"mobile": "555"})
    assert r.status_code == 422
    body = r.get_json()
    assert body["success"] is False
    assert "name" in json.dumps(body.get("details", "")).lower()


def test_landlord_create_then_get(client, auth_headers):
    """Smoke the full migrated CRUD pattern on landlords."""
    r = client.post(
        "/api/v1/landlords",
        headers=auth_headers,
        json={"name": "Schema Test Landlord", "qid_cr_number": "CR-9876"},
    )
    assert r.status_code == 201
    ll = r.get_json()["data"]
    g = client.get(f"/api/v1/landlords/{ll['id']}", headers=auth_headers).get_json()["data"]
    assert g["name"] == "Schema Test Landlord"
    assert g["qid_cr_number"] == "CR-9876"
