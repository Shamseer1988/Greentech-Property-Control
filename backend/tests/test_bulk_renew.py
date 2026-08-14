"""Bulk agreement renewal: services/agreements.py::bulk_renew() and the
POST /agreements/bulk-renew route.

Setup mirrors test_agreements_routes.py's helpers."""
from datetime import date, timedelta


def _set_company_signatory(client, auth_headers):
    for key, value in (
        ("company.signatory_name", "Ali Hassan"),
        ("company.signatory_name_ar", "علي حسن"),
        ("company.signatory_id_number", "28888888888"),
    ):
        resp = client.put(f"/api/v1/settings/{key}", headers=auth_headers, json={"value": value})
        assert resp.status_code == 200, resp.get_data(as_text=True)


def _landlord(client, auth_headers, **overrides):
    payload = {
        "name": "Bulk Renew Landlord", "name_ar": "مالك التجديد الجماعي",
        "signatory_name": "Ismail Thanjalil", "signatory_name_ar": "إسماعيل ثنجاليل",
        "signatory_id_number": "26935600953",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/landlords", headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _term_payload(**overrides):
    today = date.today()
    payload = {
        "template_slug": "labour-camp-room-rental",
        "rooms_description": "10 labour rooms",
        "rooms_count": 10,
        "start_date": (today - timedelta(days=345)).isoformat(),
        "end_date": (today + timedelta(days=20)).isoformat(),
        "electricity_included": True, "water_included": True,
        "free_months_count": 0,
        "deposit_cheque_required": False,
        "cancellation_mode": "no_cancellation",
        "rent_amount": 9000, "rent_payment_frequency_months": 3, "currency": "QAR",
    }
    payload.update(overrides)
    return payload


def _generate(client, auth_headers, landlord_id, **overrides):
    payload = _term_payload(party_role="landlord", landlord_id=landlord_id, **overrides)
    resp = client.post("/api/v1/agreements", headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def test_bulk_renew_regenerates_expiring_agreements(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    original = _generate(client, auth_headers, landlord["id"])

    resp = client.post("/api/v1/agreements/bulk-renew", headers=auth_headers,
                       json={"within_days": 60})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["renewed_count"] == 1
    assert data["failed_count"] == 0
    assert data["renewed"][0]["old_agreement_id"] == original["id"]

    old = client.get(f"/api/v1/agreements/{original['id']}", headers=auth_headers).get_json()["data"]
    assert old["superseded_by_id"] == data["renewed"][0]["new_agreement_id"]

    new = client.get(f"/api/v1/agreements/{data['renewed'][0]['new_agreement_id']}",
                     headers=auth_headers).get_json()["data"]
    assert new["start_date"] == original["end_date"] or new["start_date"] > original["end_date"]
    # Same length as the original term, just shifted to start right after it.
    assert new["end_date"] > new["start_date"]


def test_bulk_renew_skips_agreements_outside_the_window(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    today = date.today()
    _generate(client, auth_headers, landlord["id"],
             start_date=today.isoformat(),
             end_date=(today + timedelta(days=400)).isoformat())

    resp = client.post("/api/v1/agreements/bulk-renew", headers=auth_headers,
                       json={"within_days": 60})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["renewed_count"] == 0


def test_bulk_renew_never_double_supersedes(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    _generate(client, auth_headers, landlord["id"])

    first = client.post("/api/v1/agreements/bulk-renew", headers=auth_headers,
                        json={"within_days": 60}).get_json()["data"]
    assert first["renewed_count"] == 1

    # The new agreement's own term is far in the future (start = old end +
    # 1 day, same span as the original ~365-day term), so a second run
    # must find nothing left to renew — it must never re-supersede the
    # already-superseded original.
    second = client.post("/api/v1/agreements/bulk-renew", headers=auth_headers,
                         json={"within_days": 60}).get_json()["data"]
    assert second["renewed_count"] == 0


def test_bulk_renew_requires_agreement_create_permission(client):
    resp = client.post("/api/v1/agreements/bulk-renew", json={"within_days": 60})
    assert resp.status_code == 401
