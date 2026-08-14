"""Approval workflow.

Only landlord renewals route through approvals in Phase 0. The
contract-side modules (client contract cancellation, rent reduction,
receipt void, expense delete) register in Phases 2-4 and get their own
tests then.
"""
from datetime import date, timedelta


def _enable(app, key: str):
    """Flip a system setting on inside an app context."""
    from app.extensions import db
    from app.services import settings as settings_service
    with app.app_context():
        settings_service.set_value(key, True, actor_id=1)
        db.session.commit()


def _scaffold(client, auth_headers):
    prop = client.post("/api/v1/properties", headers=auth_headers,
                       json={"name": "P", "property_type": "full_building"}).get_json()["data"]
    ll = client.post("/api/v1/landlords", headers=auth_headers,
                     json={"name": "M"}).get_json()["data"]
    return prop, ll


def _with_agreement(client, auth_headers, prop, ll, days_to_expiry=30):
    today = date.today()
    client.post(f"/api/v1/properties/{prop['id']}/agreements", headers=auth_headers,
                json={"landlord_id": ll["id"],
                      "start_date": (today - timedelta(days=200)).isoformat(),
                      "expiry_date": (today + timedelta(days=days_to_expiry)).isoformat(),
                      "monthly_rent": 10000})


def _renew(client, auth_headers, prop, ll, rent=11000):
    today = date.today()
    return client.post("/api/v1/renewals", headers=auth_headers,
                       json={"property_id": prop["id"], "landlord_id": ll["id"],
                             "new_start_date": (today + timedelta(days=31)).isoformat(),
                             "new_expiry_date": (today + timedelta(days=395)).isoformat(),
                             "new_monthly_rent": rent})


# ---------- Settings ----------

def test_seed_defaults_present(client, auth_headers):
    from app.services import settings as s
    assert s.get_bool("approval.renewal.required") is False


# ---------- Renewal approval ----------

def test_renewal_with_approval_required_keeps_old_active(app, client, auth_headers):
    _enable(app, "approval.renewal.required")
    prop, ll = _scaffold(client, auth_headers)
    _with_agreement(client, auth_headers, prop, ll)

    resp = _renew(client, auth_headers, prop, ll)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["status"] == "pending_approval"

    agreements = client.get(f"/api/v1/properties/{prop['id']}/agreements",
                            headers=auth_headers).get_json()["data"]
    # The old agreement stays active and nothing is archived yet.
    assert sum(a["is_active"] for a in agreements) == 1
    assert sum(not a["is_active"] for a in agreements) == 0

    req = client.get("/api/v1/approvals?module=renewal", headers=auth_headers).get_json()["data"][0]
    assert req["entity_type"] == "landlord_renewal"
    ok = client.post(f"/api/v1/approvals/{req['id']}/approve", headers=auth_headers, json={})
    assert ok.status_code == 200
    assert ok.get_json()["data"]["status"] == "approved"

    after = client.get(f"/api/v1/properties/{prop['id']}/agreements",
                       headers=auth_headers).get_json()["data"]
    assert sum(a["is_active"] for a in after) == 1
    assert sum(not a["is_active"] for a in after) == 1
    new_active = next(a for a in after if a["is_active"])
    assert new_active["monthly_rent"] == 11000.0


def test_reject_renewal_leaves_old_agreement_untouched(app, client, auth_headers):
    _enable(app, "approval.renewal.required")
    prop, ll = _scaffold(client, auth_headers)
    _with_agreement(client, auth_headers, prop, ll)
    _renew(client, auth_headers, prop, ll)

    req = client.get("/api/v1/approvals?module=renewal", headers=auth_headers).get_json()["data"][0]
    resp = client.post(f"/api/v1/approvals/{req['id']}/reject",
                       headers=auth_headers, json={"remarks": "rent too high"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "rejected"

    after = client.get(f"/api/v1/properties/{prop['id']}/agreements",
                       headers=auth_headers).get_json()["data"]
    assert sum(a["is_active"] for a in after) == 1
    assert next(a for a in after if a["is_active"])["monthly_rent"] == 10000.0


def test_decided_request_cannot_be_decided_again(app, client, auth_headers):
    _enable(app, "approval.renewal.required")
    prop, ll = _scaffold(client, auth_headers)
    _with_agreement(client, auth_headers, prop, ll)
    _renew(client, auth_headers, prop, ll)

    req = client.get("/api/v1/approvals?module=renewal", headers=auth_headers).get_json()["data"][0]
    assert client.post(f"/api/v1/approvals/{req['id']}/approve",
                       headers=auth_headers, json={}).status_code == 200
    again = client.post(f"/api/v1/approvals/{req['id']}/approve", headers=auth_headers, json={})
    assert again.status_code == 400
    assert "approved" in again.get_json()["message"].lower()


def test_pending_counts(app, client, auth_headers):
    _enable(app, "approval.renewal.required")
    prop, ll = _scaffold(client, auth_headers)
    _with_agreement(client, auth_headers, prop, ll)
    _renew(client, auth_headers, prop, ll)

    counts = client.get("/api/v1/approvals/counts", headers=auth_headers).get_json()["data"]
    assert counts["renewal"] == 1
    assert counts["total"] == 1


def test_approvals_require_auth(client):
    resp = client.get("/api/v1/approvals")
    assert resp.status_code == 401


def test_synchronous_path_still_works_without_setting(client, auth_headers):
    """When the toggle is off (default) the renewal posts immediately."""
    prop, ll = _scaffold(client, auth_headers)
    _with_agreement(client, auth_headers, prop, ll)

    resp = _renew(client, auth_headers, prop, ll)
    assert resp.status_code == 201
    assert resp.get_json()["data"]["status"] == "completed"

    queue = client.get("/api/v1/approvals", headers=auth_headers).get_json()
    assert queue["meta"]["count"] == 0

    after = client.get(f"/api/v1/properties/{prop['id']}/agreements",
                       headers=auth_headers).get_json()["data"]
    assert sum(not a["is_active"] for a in after) == 1
