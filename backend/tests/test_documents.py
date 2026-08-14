"""Document identity + expiry on attachments, and the alerts they feed."""
import io
from datetime import date, timedelta


def _upload(client, auth_headers, *, entity_type="landlord", entity_id=1,
            category="govt_doc", name="qid.pdf", **fields):
    data = {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "category": category,
        "file": (io.BytesIO(b"%PDF-1.4 doc"), name),
    }
    data.update({k: v for k, v in fields.items() if v is not None})
    return client.post("/api/v1/attachments", headers=auth_headers,
                       data=data, content_type="multipart/form-data")


def _landlord(client, auth_headers, name="Doc LL"):
    return client.post("/api/v1/landlords", headers=auth_headers,
                       json={"name": name}).get_json()["data"]


def _property(client, auth_headers, landlord_id, name="Doc Property"):
    return client.post("/api/v1/properties", headers=auth_headers, json={
        "name": name, "property_type": "store", "landlord_id": landlord_id,
        "layout": {"floors": 1, "units_per_floor": 2},
    }).get_json()["data"]


def _client_contract(client, auth_headers):
    ll = _landlord(client, auth_headers, "Contract LL")
    prop = _property(client, auth_headers, ll["id"], "Contract Property")
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Doc Tenant"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": 1000, "payment_mode": "cash",
    }).get_json()["data"]
    return tenant, contract


def test_upload_stores_document_fields(client, auth_headers):
    ll = _landlord(client, auth_headers)
    expiry = (date.today() + timedelta(days=45)).isoformat()
    resp = _upload(client, auth_headers, entity_id=ll["id"],
                   doc_number="QID-28899", issue_date="2024-01-15", expiry_date=expiry)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    att = resp.get_json()["data"]
    assert att["doc_number"] == "QID-28899"
    assert att["issue_date"] == "2024-01-15"
    assert att["expiry_date"] == expiry

    listed = client.get(
        f"/api/v1/attachments?entity_type=landlord&entity_id={ll['id']}",
        headers=auth_headers,
    ).get_json()
    assert listed["data"][0]["doc_number"] == "QID-28899"


def test_upload_without_document_fields_still_works(client, auth_headers):
    ll = _landlord(client, auth_headers, "Plain LL")
    resp = _upload(client, auth_headers, entity_id=ll["id"], category="agreement")
    assert resp.status_code == 201
    att = resp.get_json()["data"]
    assert att["doc_number"] is None
    assert att["expiry_date"] is None


def test_upload_rejects_bad_dates_and_category(client, auth_headers):
    ll = _landlord(client, auth_headers, "Bad LL")

    bad_date = _upload(client, auth_headers, entity_id=ll["id"], expiry_date="15-01-2024")
    assert bad_date.status_code == 400
    assert "YYYY-MM-DD" in bad_date.get_json()["message"]

    inverted = _upload(client, auth_headers, entity_id=ll["id"],
                       issue_date="2025-01-01", expiry_date="2024-01-01")
    assert inverted.status_code == 400

    bad_cat = _upload(client, auth_headers, entity_id=ll["id"], category="mixtape")
    assert bad_cat.status_code == 400


def test_expiring_documents_service_buckets_and_labels(app, client, auth_headers):
    ll = _landlord(client, auth_headers, "Expiring LL")
    today = date.today()
    _upload(client, auth_headers, entity_id=ll["id"], category="govt_doc",
            doc_number="EXPIRED-1", expiry_date=(today - timedelta(days=3)).isoformat())
    _upload(client, auth_headers, entity_id=ll["id"], category="company_doc",
            name="cr.pdf", doc_number="SOON-1",
            expiry_date=(today + timedelta(days=10)).isoformat())
    # Far future — outside the 90-day window.
    _upload(client, auth_headers, entity_id=ll["id"], category="company_doc",
            name="far.pdf", doc_number="FAR-1",
            expiry_date=(today + timedelta(days=400)).isoformat())
    # An agreement is tracked by the contract, not the document alerts.
    _upload(client, auth_headers, entity_id=ll["id"], category="agreement",
            name="ag.pdf", expiry_date=(today + timedelta(days=5)).isoformat())

    with app.app_context():
        from app.services.documents import expiring_documents
        rows = expiring_documents(within_days=90)

    numbers = [r["doc_number"] for r in rows]
    assert numbers == ["EXPIRED-1", "SOON-1"], "sorted soonest-first, agreement excluded"
    assert rows[0]["bucket"] == "expired"
    assert rows[0]["days_left"] < 0
    assert rows[0]["entity_name"] == "Expiring LL", "entity label resolved"
    assert rows[1]["days_left"] == 10


def test_document_expiry_surfaces_in_alerts(client, auth_headers):
    ll = _landlord(client, auth_headers, "Alert LL")
    today = date.today()
    _upload(client, auth_headers, entity_id=ll["id"], category="govt_doc",
            doc_number="GONE", expiry_date=(today - timedelta(days=1)).isoformat())
    _upload(client, auth_headers, entity_id=ll["id"], category="company_doc",
            name="cr.pdf", doc_number="SOON",
            expiry_date=(today + timedelta(days=20)).isoformat())

    body = client.get("/api/v1/dashboard/alerts", headers=auth_headers).get_json()["data"]
    assert len(body["critical"]["expired_documents"]) == 1
    assert len(body["warning"]["documents_expiring_within_30_days"]) == 1
    assert body["counts"]["critical"] >= 1
    assert body["counts"]["warning"] >= 1


def test_document_expiry_report(client, auth_headers):
    ll = _landlord(client, auth_headers, "Report LL")
    _upload(client, auth_headers, entity_id=ll["id"], category="govt_doc",
            doc_number="RPT-1",
            expiry_date=(date.today() + timedelta(days=15)).isoformat())

    catalog = client.get("/api/v1/reports", headers=auth_headers).get_json()["data"]
    assert "document-expiry" in {r["slug"] for r in catalog}

    resp = client.get("/api/v1/reports/document-expiry", headers=auth_headers)
    assert resp.status_code == 200
    payload = resp.get_json()["data"]
    assert payload["meta"]["count"] == 1
    row = payload["rows"][0]
    assert row["doc_number"] == "RPT-1"
    assert row["entity_name"] == "Report LL"
    assert row["days_left"] == 15


def test_document_expiry_report_filters_by_entity_type(client, auth_headers):
    ll = _landlord(client, auth_headers, "Filter LL")
    cl = client.post("/api/v1/clients", headers=auth_headers,
                     json={"name": "Filter Client"}).get_json()["data"]
    soon = (date.today() + timedelta(days=10)).isoformat()
    _upload(client, auth_headers, entity_type="landlord", entity_id=ll["id"],
            category="govt_doc", doc_number="LL-DOC", expiry_date=soon)
    _upload(client, auth_headers, entity_type="client", entity_id=cl["id"],
            category="company_doc", name="cr.pdf", doc_number="CL-DOC", expiry_date=soon)

    only_clients = client.get("/api/v1/reports/document-expiry?entity_type=client",
                              headers=auth_headers).get_json()["data"]
    assert only_clients["meta"]["count"] == 1
    assert only_clients["rows"][0]["doc_number"] == "CL-DOC"
    assert only_clients["rows"][0]["entity_name"] == "Filter Client"


# --------------------------------------------------------- also-tagging

def test_upload_can_also_tag_to_a_property(client, auth_headers):
    ll = _landlord(client, auth_headers, "Tag LL")
    prop = _property(client, auth_headers, ll["id"], "Tag Property")

    resp = _upload(client, auth_headers, entity_id=ll["id"], category="agreement",
                   link_entity_type="property", link_entity_id=str(prop["id"]))
    assert resp.status_code == 201, resp.get_data(as_text=True)

    on_property = client.get(
        f"/api/v1/attachments?entity_type=property&entity_id={prop['id']}",
        headers=auth_headers).get_json()["data"]
    assert len(on_property) == 1
    also_on = on_property[0]["also_on"]
    assert also_on == [], "the property's own view shouldn't list itself as an 'also on'"

    on_landlord = client.get(
        f"/api/v1/attachments?entity_type=landlord&entity_id={ll['id']}",
        headers=auth_headers).get_json()["data"]
    assert on_landlord[0]["also_on"] == [{"entity_type": "property", "code": prop["code"], "name": prop["name"]}]


def test_upload_can_also_tag_to_a_client_contract(client, auth_headers):
    tenant, contract = _client_contract(client, auth_headers)

    resp = _upload(client, auth_headers, entity_type="client", entity_id=tenant["id"],
                   category="agreement", link_entity_type="client_contract",
                   link_entity_id=str(contract["id"]))
    assert resp.status_code == 201, resp.get_data(as_text=True)

    on_contract = client.get(
        f"/api/v1/attachments?entity_type=client_contract&entity_id={contract['id']}",
        headers=auth_headers).get_json()["data"]
    assert len(on_contract) == 1
    assert on_contract[0]["also_on"] == []

    on_client = client.get(
        f"/api/v1/attachments?entity_type=client&entity_id={tenant['id']}",
        headers=auth_headers).get_json()["data"]
    assert on_client[0]["also_on"] == [
        {"entity_type": "client_contract", "code": contract["contract_number"], "name": tenant["name"]}
    ]


def test_upload_rejects_unsupported_link_entity_type(client, auth_headers):
    ll = _landlord(client, auth_headers, "Bad Link LL")
    resp = _upload(client, auth_headers, entity_id=ll["id"],
                   link_entity_type="cheque", link_entity_id="1")
    assert resp.status_code == 400
    assert "Cannot also-tag" in resp.get_json()["message"]


def test_upload_rejects_link_to_missing_entity(client, auth_headers):
    ll = _landlord(client, auth_headers, "Missing Link LL")
    resp = _upload(client, auth_headers, entity_id=ll["id"],
                   link_entity_type="property", link_entity_id="999999")
    assert resp.status_code == 400
    assert "does not exist" in resp.get_json()["message"]
