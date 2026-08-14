def test_catalog_groups_settings(client, auth_headers):
    resp = client.get("/api/v1/settings/catalog", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    categories = [s["category"] for s in data["sections"]]
    for required in [
        "company", "property", "numbering", "approval", "alerts",
        "email", "ui", "import", "security", "backup", "audit",
    ]:
        assert required in categories
    assert data["count"] > 20

    # Email password is secret and masked
    email = next(s for s in data["sections"] if s["category"] == "email")
    pwd = next(s for s in email["settings"] if s["key"] == "email.smtp_password")
    assert pwd["is_secret"] is True
    assert pwd["value"] is None


def test_public_settings_no_auth_needed(client):
    resp = client.get("/api/v1/settings/public")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    # Branding fields
    assert "company.name" in data
    assert "company.logo_url" in data
    # UI fields (Phase 13) used by the theme bridge
    for key in (
        "ui.accent_color", "ui.glassmorphism", "ui.compact_mode",
        "ui.sidebar_default_collapsed", "ui.table_density",
    ):
        assert key in data


def test_bulk_update_settings(client, auth_headers):
    resp = client.put(
        "/api/v1/settings", headers=auth_headers,
        json={"settings": {
            "company.name": "GreenTech Operations",
            "ui.accent_color": "violet",
            "import.max_rows": "2500",   # string should be coerced to int
            "alerts.email_enabled": "true",
        }},
    )
    assert resp.status_code == 200
    listed = client.get("/api/v1/settings", headers=auth_headers).get_json()["data"]
    by_key = {s["key"]: s for s in listed}
    assert by_key["company.name"]["value"] == "GreenTech Operations"
    assert by_key["ui.accent_color"]["value"] == "violet"
    assert by_key["import.max_rows"]["value"] == 2500
    assert by_key["alerts.email_enabled"]["value"] is True


def test_bulk_update_rejects_invalid_select(client, auth_headers):
    resp = client.put(
        "/api/v1/settings", headers=auth_headers,
        json={"settings": {"ui.accent_color": "neon-pink"}},
    )
    assert resp.status_code == 400
    assert "ui.accent_color" in resp.get_json()["message"]


def test_single_update_still_works(client, auth_headers):
    resp = client.put(
        "/api/v1/settings/approval.assignment.required",
        headers=auth_headers, json={"value": True},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["value"] is True


def test_secret_value_is_never_returned(client, auth_headers):
    client.put(
        "/api/v1/settings/email.smtp_password",
        headers=auth_headers, json={"value": "topsecret"},
    )
    listed = client.get("/api/v1/settings", headers=auth_headers).get_json()["data"]
    pwd = next(s for s in listed if s["key"] == "email.smtp_password")
    assert pwd["value"] is None
    assert pwd["is_set"] is True


def test_numbering_prefix_applies_to_new_property(client, auth_headers):
    client.put(
        "/api/v1/settings/numbering.property.prefix",
        headers=auth_headers, json={"value": "BLDG"},
    )
    resp = client.post(
        "/api/v1/properties", headers=auth_headers,
        json={"name": "Numbering Test", "property_type": "full_building"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["code"].startswith("BLDG-")


def test_settings_view_required(client):
    resp = client.get("/api/v1/settings")
    assert resp.status_code == 401
