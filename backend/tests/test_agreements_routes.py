"""Agreement routes: full round trip through the Flask test client —
preview, generate, list, void, regenerate — and the attachment/party
swap invariants."""
import io
import zipfile


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
        "name": "Paris Hypermarket LLC", "name_ar": "باريس هايبر ماركت ذ.م.م",
        "signatory_name": "Ismail Thanjalil", "signatory_name_ar": "إسماعيل ثنجاليل",
        "signatory_id_number": "26935600953",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/landlords", headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _client_party(client, auth_headers, **overrides):
    payload = {
        "name": "Porto Services LLC", "name_ar": "بورتو للخدمات ذ.م.م",
        "signatory_name": "Mohamed Tarek", "signatory_name_ar": "محمد طارق",
        "signatory_id_number": "26958602105",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/clients", headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _term_payload(**overrides):
    payload = {
        "template_slug": "labour-camp-room-rental",
        "rooms_description": "10 labour rooms in area 85, street 520, building no. 16",
        "rooms_count": 10,
        "start_date": "2026-09-01", "end_date": "2027-06-30",
        "electricity_included": True, "water_included": True,
        "free_months_count": 0,
        "deposit_cheque_required": True,
        "cancellation_mode": "notice_months", "cancellation_notice_months": 3,
        "rent_amount": 9000, "rent_payment_frequency_months": 3, "currency": "QAR",
    }
    payload.update(overrides)
    return payload


def test_list_agreement_templates(client, auth_headers):
    resp = client.get("/api/v1/agreement-templates", headers=auth_headers)
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.get_json()["data"]}
    assert "labour-camp-room-rental" in slugs


def test_preview_returns_clauses_without_persisting(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    payload = _term_payload(party_role="landlord", landlord_id=landlord["id"])
    resp = client.post("/api/v1/agreements/preview", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    clauses = resp.get_json()["data"]["clauses"]
    assert len(clauses) > 5

    listed = client.get(f"/api/v1/agreements?entity_type=landlord&entity_id={landlord['id']}",
                        headers=auth_headers).get_json()["data"]
    assert listed == [], "a preview must not create a row"


def test_generate_creates_agreement_and_docx_attachment(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    payload = _term_payload(party_role="landlord", landlord_id=landlord["id"])
    resp = client.post("/api/v1/agreements", headers=auth_headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    agreement = resp.get_json()["data"]
    assert agreement["agreement_number"].startswith("AGR-")
    assert agreement["attachment_id"] is not None

    dl = client.get(f"/api/v1/attachments/{agreement['attachment_id']}/download",
                    headers=auth_headers)
    assert dl.status_code == 200
    assert zipfile.is_zipfile(io.BytesIO(dl.data)), "a .docx is a zip container"

    docs = client.get(f"/api/v1/attachments?entity_type=landlord&entity_id={landlord['id']}",
                      headers=auth_headers).get_json()["data"]
    assert any(d["category"] == "agreement" for d in docs)


def test_generate_fails_cleanly_when_signatory_missing(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    bare = client.post("/api/v1/landlords", headers=auth_headers,
                       json={"name": "No Signatory Co"}).get_json()["data"]
    payload = _term_payload(party_role="landlord", landlord_id=bare["id"])
    resp = client.post("/api/v1/agreements", headers=auth_headers, json=payload)
    assert resp.status_code == 400
    assert "signatory" in resp.get_json()["message"].lower()


def test_client_agreement_swaps_party_roles(client, auth_headers):
    """party_role='client' means GreenTech is the Lessor and the client
    master is the Tenant — the reverse of a landlord agreement."""
    _set_company_signatory(client, auth_headers)
    party = _client_party(client, auth_headers)
    payload = _term_payload(party_role="client", client_id=party["id"])
    resp = client.post("/api/v1/agreements/preview", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    clauses = resp.get_json()["data"]["clauses"]
    early_vacate = next(c for c in clauses if c["heading_en"] and "Early Vacate" in c["heading_en"])
    # For a client agreement, our own company is the Lessor.
    assert "Lessor" in early_vacate["body_en"]


def test_void_agreement(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    payload = _term_payload(party_role="landlord", landlord_id=landlord["id"])
    agreement = client.post("/api/v1/agreements", headers=auth_headers,
                            json=payload).get_json()["data"]

    resp = client.post(f"/api/v1/agreements/{agreement['id']}/void", headers=auth_headers,
                       json={"reason": "typo in terms"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["status"] == "voided"


def test_regenerate_creates_a_new_row_and_links_supersession(client, auth_headers):
    _set_company_signatory(client, auth_headers)
    landlord = _landlord(client, auth_headers)
    payload = _term_payload(party_role="landlord", landlord_id=landlord["id"])
    original = client.post("/api/v1/agreements", headers=auth_headers,
                           json=payload).get_json()["data"]

    resp = client.post(f"/api/v1/agreements/{original['id']}/regenerate", headers=auth_headers,
                       json={"rent_amount": 9500})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    new_agreement = resp.get_json()["data"]
    assert new_agreement["id"] != original["id"]
    assert new_agreement["rent_amount"] == 9500.0

    original_detail = client.get(f"/api/v1/agreements/{original['id']}",
                                 headers=auth_headers).get_json()["data"]
    assert original_detail["superseded_by_id"] == new_agreement["id"]


def test_agreement_routes_require_auth(client):
    assert client.get("/api/v1/agreement-templates").status_code == 401
    assert client.get("/api/v1/agreements").status_code == 401
    assert client.post("/api/v1/agreements").status_code == 401
