"""Gapless document numbering: seeding from legacy rows, and collision-
free allocation across many receipts posted in one batch — the exact
shape of what the bulk entry screen (Phase 5) does."""


def _client_with_charges(client, auth_headers, *, months_upto="2026-06-01"):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Num LL"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Num Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "Num Client"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": "2026-01-01",
        "expiry_date": "2026-12-31", "monthly_rent": 1000, "payment_mode": "cash",
    }).get_json()["data"]
    client.post("/api/v1/rent/generate", headers=auth_headers,
               json={"contract_id": contract["id"], "upto": months_upto})
    return tenant, contract


def test_receipt_numbers_are_sequential_and_unique_across_a_batch(client, auth_headers):
    """What a bulk-entry post loop does: many receipts, one after
    another, inside requests that could interleave in production."""
    tenant, _ = _client_with_charges(client, auth_headers)

    numbers = []
    for _ in range(15):
        resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
            "client_id": tenant["id"], "amount": 50, "receipt_date": "2026-01-05",
            "mode": "cash",
        })
        assert resp.status_code == 201, resp.get_data(as_text=True)
        numbers.append(resp.get_json()["data"]["receipt_number"])

    assert len(set(numbers)) == 15, f"duplicate receipt numbers: {numbers}"
    seqs = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
    assert seqs == list(range(seqs[0], seqs[0] + 15)), "must be gapless and contiguous"


def test_voucher_numbers_are_sequential_and_unique_across_a_batch(client, auth_headers):
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "Num Voucher LL"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "Num Voucher Tower", "property_type": "full_building",
        "landlord_id": landlord["id"], "layout": {"floors": 1, "units_per_floor": 4},
    }).get_json()["data"]

    numbers = []
    for i in range(15):
        resp = client.post("/api/v1/expenses/landlord-payments", headers=auth_headers, json={
            "landlord_id": landlord["id"], "property_id": prop["id"],
            "period_month": "2026-01-01", "amount": 100 + i, "mode": "cash",
        })
        assert resp.status_code == 201, resp.get_data(as_text=True)
        numbers.append(resp.get_json()["data"]["voucher_number"])

    assert len(set(numbers)) == 15
    seqs = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
    assert seqs == list(range(seqs[0], seqs[0] + 15))


def test_numbering_seeds_from_pre_existing_legacy_numbers(app, client, auth_headers):
    """A receipt created before this fix existed (no NumberSequence row
    yet) must not have its number reused — the first allocation after
    such a row seeds from the current max, not from zero."""
    from datetime import date, datetime
    from app.extensions import db
    from app.models import Receipt

    month_key = datetime.utcnow().strftime("%Y%m")
    tenant, _ = _client_with_charges(client, auth_headers)
    with app.app_context():
        legacy = Receipt(
            receipt_number=f"RV-{month_key}-0007", client_id=tenant["id"],
            receipt_date=date(2026, 1, 1), amount=1, mode="cash", status="posted",
            created_by=1, updated_by=1,
        )
        db.session.add(legacy)
        db.session.commit()

    resp = client.post("/api/v1/rent/receipts", headers=auth_headers, json={
        "client_id": tenant["id"], "amount": 50, "receipt_date": "2026-01-05",
        "mode": "cash",
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    new_number = resp.get_json()["data"]["receipt_number"]
    assert new_number.startswith(f"RV-{month_key}-")
    assert int(new_number.rsplit("-", 1)[1]) > 7, "must continue past the legacy number"
