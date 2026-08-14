"""Notification rules, email, Telegram and AI.

Nothing here touches a real mail server, bot or model. `_send` and the
HTTP posts are stubbed, so the suite exercises composition, the advance
windows, the dedupe key and the enabled/disabled guards — which is
where the mistakes that would embarrass the company actually live.

The property under test throughout: **nothing leaves the building
unless it was explicitly switched on.**
"""
from datetime import date, timedelta

import pytest

from app.services import (
    ai as ai_service, email as email_service,
    notification_rules as rules_service, telegram as telegram_service,
)


@pytest.fixture()
def sent(monkeypatch):
    """Capture what would have gone to an SMTP server."""
    outbox = []
    monkeypatch.setattr(email_service, "_send",
                        lambda cfg, mime, to: outbox.append((to, mime["Subject"],
                                                             mime.get_content())))
    return outbox


@pytest.fixture()
def posted(monkeypatch):
    """Capture what would have gone to Telegram."""
    calls = []
    monkeypatch.setattr(telegram_service, "_post",
                        lambda token, method, payload: calls.append(payload) or {"ok": True})
    return calls


def _set(app, values: dict):
    from app.extensions import db
    from app.services import settings as settings_service
    with app.app_context():
        for key, value in values.items():
            settings_service.set_value(key, value, actor_id=1)
        db.session.commit()


def _smtp_ready(app, **extra):
    _set(app, {
        "email.smtp_host": "smtp.example.test",
        "email.from_address": "accounts@greentech.test",
        "email.from_name": "GreenTech",
        "email.enabled": True,
        **extra,
    })


@pytest.fixture()
def estate(client, auth_headers):
    """A tenant with an email address whose contract expires in 60 days."""
    today = date.today()
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "OWNER ONE",
                                 "email": "owner@example.test"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "ST-50", "property_type": "building_with_store",
        "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 3},
    }).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "TENANT ONE",
                               "email": "tenant@example.test"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]],
        "start_date": (today - timedelta(days=300)).isoformat(),
        "expiry_date": (today + timedelta(days=60)).isoformat(),
        "monthly_rent": 9000, "payment_mode": "cash",
    }).get_json()["data"]
    return {"landlord": landlord, "property": prop, "client": tenant,
            "contract": contract, "today": today}


def _rules(client, auth_headers):
    resp = client.get("/api/v1/messaging/rules", headers=auth_headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return {r["event"]: r for r in resp.get_json()["data"]}


def _configure(client, auth_headers, event, **fields):
    rule = _rules(client, auth_headers)[event]
    resp = client.put(f"/api/v1/messaging/rules/{rule['id']}",
                      headers=auth_headers, json=fields)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _sweep(client, auth_headers, **body):
    resp = client.post("/api/v1/messaging/sweep", headers=auth_headers, json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _messages(client, auth_headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/v1/messaging/messages?{query}",
                      headers=auth_headers).get_json()["data"]


# ------------------------------------------------------------- the rules

def test_seeded_rules_all_start_disabled(client, auth_headers):
    """Nobody gets mailed because someone installed the software."""
    rules = _rules(client, auth_headers)
    assert len(rules) == 7
    assert all(r["is_enabled"] is False for r in rules.values())


def test_rule_rejects_an_unknown_channel(client, auth_headers):
    rule = _rules(client, auth_headers)["contract_expiry"]
    resp = client.put(f"/api/v1/messaging/rules/{rule['id']}",
                      headers=auth_headers, json={"channels": ["carrier_pigeon"]})
    assert resp.status_code == 400
    assert "carrier_pigeon" in resp.get_json()["message"]


def test_advance_days_are_normalised(client, auth_headers):
    rule = _configure(client, auth_headers, "contract_expiry",
                      advance_days=[30, 60, 30, 7])
    assert rule["advance_days"] == [60, 30, 7]


# ------------------------------------------------- the exit criterion

def test_contract_expiring_in_two_months_emails_the_tenant_and_tells_the_group(
        app, client, auth_headers, estate, sent, posted):
    """Phase 7's exit criterion, in one test."""
    _smtp_ready(app)
    _set(app, {"telegram.enabled": True, "telegram.bot_token": "test-token",
               "telegram.chat_id": "-100999"})
    _configure(client, auth_headers, "contract_expiry",
               is_enabled=True, advance_days=[60],
               channels=["email", "telegram", "inapp"], audiences=["client"])

    result = _sweep(client, auth_headers)
    assert result["findings"] == 1, result

    assert len(sent) == 1, "the tenant was not emailed"
    to, subject, body = sent[0]
    assert to == "tenant@example.test"
    assert estate["contract"]["contract_number"] in subject
    assert "TENANT ONE" in body
    assert "60 day(s)" in body

    assert len(posted) == 1, "the staff group was not told"
    assert estate["contract"]["contract_number"] in posted[0]["text"]
    assert posted[0]["chat_id"] == "-100999"

    log = _messages(client, auth_headers)
    assert {m["channel"] for m in log} == {"email", "telegram"}
    assert all(m["status"] == "sent" for m in log)


def test_the_same_reminder_is_not_sent_twice(app, client, auth_headers, estate, sent):
    """The sweep runs daily; the 60-day boundary is crossed once."""
    _smtp_ready(app)
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email"], audiences=["client"])

    first = _sweep(client, auth_headers)
    second = _sweep(client, auth_headers)

    assert first["findings"] == 1 and second["findings"] == 1, \
        "the finding is still found — it is the delivery that must not repeat"
    assert len(sent) == 1, "the tenant was emailed twice"
    assert len(_messages(client, auth_headers, channel="email")) == 1


def test_a_contract_a_day_outside_the_window_is_silent(
        app, client, auth_headers, estate, sent):
    _smtp_ready(app)
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[59], channels=["email"], audiences=["client"])
    result = _sweep(client, auth_headers)
    assert result["findings"] == 0
    assert sent == []


def test_a_disabled_rule_finds_nothing(app, client, auth_headers, estate, sent):
    _smtp_ready(app)
    _configure(client, auth_headers, "contract_expiry", is_enabled=False,
               advance_days=[60], channels=["email"], audiences=["client"])
    assert _sweep(client, auth_headers)["findings"] == 0
    assert sent == []


# ----------------------------------------------- nothing leaves by accident

def test_with_email_switched_off_the_message_is_composed_but_not_sent(
        app, client, auth_headers, estate, sent):
    """The default posture: you can read what would go out first."""
    _set(app, {"email.smtp_host": "smtp.example.test",
               "email.from_address": "accounts@greentech.test",
               "email.enabled": False})
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email"], audiences=["client"])

    assert _sweep(client, auth_headers)["findings"] == 1
    assert sent == [], "email went out while sending was switched off"

    log = _messages(client, auth_headers, channel="email")
    assert len(log) == 1
    assert log[0]["status"] == "skipped"
    assert "switched off" in log[0]["error"]
    assert log[0]["to_address"] == "tenant@example.test"
    assert "TENANT ONE" in log[0]["body"], "the draft is still readable"


def test_redirect_sends_everything_to_one_address_for_a_rehearsal(
        app, client, auth_headers, estate, sent):
    _smtp_ready(app, **{"email.redirect_to": "rehearsal@greentech.test"})
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email"], audiences=["client"])
    _sweep(client, auth_headers)

    assert len(sent) == 1
    to, _, body = sent[0]
    assert to == "rehearsal@greentech.test"
    assert "tenant@example.test" in body, "the intended recipient must be stated"


def test_a_preview_writes_nothing(app, client, auth_headers, estate, sent):
    _smtp_ready(app)
    rule = _configure(client, auth_headers, "contract_expiry", is_enabled=True,
                      advance_days=[60], channels=["email"], audiences=["client"])

    resp = client.post(f"/api/v1/messaging/rules/{rule['id']}/preview",
                       headers=auth_headers, json={})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["findings"] == 1
    assert data["results"][0]["deliveries"][0]["to"] == "tenant@example.test"

    assert sent == [], "a preview sent a real email"
    assert _messages(client, auth_headers) == [], "a preview wrote to the log"


def test_a_client_with_no_email_is_skipped_not_guessed(
        app, client, auth_headers, sent):
    today = date.today()
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "OWNER TWO"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "ST-51", "property_type": "villa", "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 1}}).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "NO EMAIL TENANT"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": (today - timedelta(days=10)).isoformat(),
        "expiry_date": (today + timedelta(days=60)).isoformat(),
        "monthly_rent": 5000, "payment_mode": "cash"})

    _smtp_ready(app)
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email"], audiences=["client"])
    assert _sweep(client, auth_headers)["findings"] == 1
    assert sent == [], "mailed a client with no address on file"


def test_extra_emails_reach_the_office_even_without_a_party(
        app, client, auth_headers, estate, sent):
    _smtp_ready(app)
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email"], audiences=[],
               extra_emails="accounts@greentech.test, not-an-address")
    _sweep(client, auth_headers)
    assert [to for to, _, _ in sent] == ["accounts@greentech.test"], \
        "the malformed address should have been dropped, the good one kept"


# ------------------------------------------------------------- templates

def test_a_custom_template_is_used_and_placeholders_filled(
        app, client, auth_headers, estate, sent):
    _smtp_ready(app)
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email"], audiences=["client"],
               subject_template="Renewal due: {contract_number}",
               body_template="Dear {client_name}, {days} days left on {property_name}.")
    _sweep(client, auth_headers)

    _, subject, body = sent[0]
    assert subject == f"Renewal due: {estate['contract']['contract_number']}"
    assert body.startswith("Dear TENANT ONE, 60 days left on ST-50.")


def test_an_unknown_placeholder_survives_as_visible_text(app):
    with app.app_context():
        out = email_service.render("Hello {client_name}, ref {nonsense}",
                                   {"client_name": "ACME"})
    assert out == "Hello ACME, ref {nonsense}", \
        "a bad template should be visibly wrong, not raise in a nightly job"


# ---------------------------------------------------------------- other events

def test_rent_due_chases_the_unpaid_charge(app, client, auth_headers, estate, sent):
    today = date.today()
    client.post("/api/v1/rent/generate", headers=auth_headers,
                json={"contract_id": estate["contract"]["id"],
                      "upto": today.replace(day=1).isoformat()})
    _smtp_ready(app)
    # Offset 0 means "the day the month starts"; use today's actual offset.
    offset = (today - today.replace(day=1)).days
    _configure(client, auth_headers, "rent_due", is_enabled=True,
               advance_days=[offset], channels=["email"], audiences=["client"])

    result = _sweep(client, auth_headers)
    assert result["findings"] >= 1
    assert any("tenant@example.test" == to for to, _, _ in sent)
    assert any("outstanding" in body.lower() for _, _, body in sent)


def test_bounced_cheque_reaches_the_staff_group(app, client, auth_headers, posted):
    today = date.today()
    landlord = client.post("/api/v1/landlords", headers=auth_headers,
                           json={"name": "OWNER THREE"}).get_json()["data"]
    prop = client.post("/api/v1/properties", headers=auth_headers, json={
        "name": "ST-52", "property_type": "villa", "landlord_id": landlord["id"],
        "layout": {"floors": 1, "units_per_floor": 1}}).get_json()["data"]
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "BOUNCER"}).get_json()["data"]
    units = client.get(f"/api/v1/properties/{prop['id']}/units",
                       headers=auth_headers).get_json()["data"]
    contract = client.post("/api/v1/contracts", headers=auth_headers, json={
        "client_id": tenant["id"], "property_id": prop["id"],
        "unit_ids": [units[0]["id"]], "start_date": today.isoformat(),
        "expiry_date": (today + timedelta(days=300)).isoformat(),
        "monthly_rent": 4000, "payment_mode": "cheque"}).get_json()["data"]
    cheques = client.post(f"/api/v1/contracts/{contract['id']}/cheques",
                          headers=auth_headers,
                          json={"cheques": [{"cheque_number": "B-1",
                                             "cheque_date": today.isoformat(),
                                             "amount": 4000}]}).get_json()["data"]
    client.post(f"/api/v1/contracts/cheques/{cheques[0]['id']}/deposit",
                headers=auth_headers, json={})
    client.post(f"/api/v1/contracts/cheques/{cheques[0]['id']}/bounce",
                headers=auth_headers, json={"reason": "insufficient funds"})

    _set(app, {"telegram.enabled": True, "telegram.bot_token": "t",
               "telegram.chat_id": "-100777"})
    _configure(client, auth_headers, "cheque_bounced", is_enabled=True,
               channels=["telegram"], audiences=["staff"])

    assert _sweep(client, auth_headers)["findings"] == 1
    assert len(posted) == 1
    assert "B-1" in posted[0]["text"]
    assert "returned unpaid" in posted[0]["text"].lower()


def test_telegram_off_logs_but_does_not_post(app, client, auth_headers, estate, posted):
    _set(app, {"telegram.enabled": False, "telegram.bot_token": "t",
               "telegram.chat_id": "-1"})
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["telegram"], audiences=["staff"])
    _sweep(client, auth_headers)

    assert posted == []
    log = _messages(client, auth_headers, channel="telegram")
    assert len(log) == 1 and log[0]["status"] == "skipped"


# ------------------------------------------------------------ manual send

def test_manual_send_resolves_the_address_from_the_party(
        app, client, auth_headers, estate, sent):
    _smtp_ready(app)
    resp = client.post("/api/v1/messaging/send", headers=auth_headers, json={
        "party_type": "client", "party_id": estate["client"]["id"],
        "subject": "Your statement", "body": "Please find your statement attached.",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert [to for to, _, _ in sent] == ["tenant@example.test"]
    assert resp.get_json()["data"]["is_manual"] is True


def test_manual_send_refuses_a_party_with_no_address(app, client, auth_headers):
    _smtp_ready(app)
    tenant = client.post("/api/v1/clients", headers=auth_headers,
                         json={"name": "SILENT"}).get_json()["data"]
    resp = client.post("/api/v1/messaging/send", headers=auth_headers, json={
        "party_type": "client", "party_id": tenant["id"],
        "subject": "Hello", "body": "Hello",
    })
    assert resp.status_code == 400
    assert "no usable email" in resp.get_json()["message"]


def test_manual_send_needs_a_subject_and_body(app, client, auth_headers, estate):
    resp = client.post("/api/v1/messaging/send", headers=auth_headers, json={
        "party_type": "client", "party_id": estate["client"]["id"], "subject": "  ",
    })
    assert resp.status_code == 400


# -------------------------------------------------------------------- AI

def test_ai_is_off_until_configured(app, client, auth_headers):
    resp = client.post("/api/v1/messaging/ai/draft", headers=auth_headers,
                       json={"purpose": "remind about rent"})
    assert resp.status_code == 400
    assert "switched off" in resp.get_json()["message"]


def test_ai_draft_is_given_the_contract_facts(app, client, auth_headers, estate, monkeypatch):
    seen = {}

    def fake_complete(prompt, system=None, max_tokens=800):
        seen["prompt"] = prompt
        seen["system"] = system
        return "Dear TENANT ONE, your tenancy expires shortly."

    monkeypatch.setattr(ai_service, "complete", fake_complete)
    _set(app, {"ai.enabled": True, "ai.provider": "local",
               "ai.endpoint": "http://localhost:1234/v1", "ai.model": "test"})

    resp = client.post("/api/v1/messaging/ai/draft", headers=auth_headers, json={
        "purpose": "invite the tenant to renew",
        "contract_id": estate["contract"]["id"],
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["draft"].startswith("Dear TENANT ONE")
    # The model must be handed the real figures rather than inventing them.
    assert "TENANT ONE" in seen["prompt"]
    assert "9,000.00 QAR" in seen["prompt"]
    assert data["facts"]["contract_number"] == estate["contract"]["contract_number"]


def test_ai_drafting_never_sends(app, client, auth_headers, estate, sent, monkeypatch):
    monkeypatch.setattr(ai_service, "complete", lambda *a, **k: "A draft.")
    _set(app, {"ai.enabled": True, "ai.provider": "local",
               "ai.endpoint": "http://x/v1", "ai.model": "m"})
    _smtp_ready(app)
    client.post("/api/v1/messaging/ai/draft", headers=auth_headers,
                json={"purpose": "chase rent", "contract_id": estate["contract"]["id"]})
    assert sent == []
    assert _messages(client, auth_headers) == []


def test_ai_monthly_summary_is_fed_the_real_figures(
        app, client, auth_headers, estate, monkeypatch):
    captured = {}

    def fake_summary(figures):
        captured.update(figures)
        return "Collections held up; arrears concentrated in one tenant."

    monkeypatch.setattr(ai_service, "monthly_summary", fake_summary)
    _set(app, {"ai.enabled": True, "ai.provider": "local",
               "ai.endpoint": "http://x/v1", "ai.model": "m"})

    resp = client.post("/api/v1/messaging/ai/monthly-summary",
                       headers=auth_headers, json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert "arrears" in resp.get_json()["data"]["summary"]
    for key in ("rent_charged", "collection_percent", "net_profit", "occupancy_percent"):
        assert key in captured


def test_a_provider_failure_is_reported_not_swallowed(app, client, auth_headers, monkeypatch):
    def boom(*args, **kwargs):
        raise ai_service.AIError("The AI provider returned 401: bad key")

    monkeypatch.setattr(ai_service, "draft_message", boom)
    _set(app, {"ai.enabled": True, "ai.provider": "gemini",
               "ai.api_key": "x", "ai.model": "m"})
    resp = client.post("/api/v1/messaging/ai/draft", headers=auth_headers,
                       json={"purpose": "test"})
    assert resp.status_code == 400
    assert "401" in resp.get_json()["message"]


# ---------------------------------------------------------------- access

def test_messaging_endpoints_need_authentication(client):
    for path in ("/api/v1/messaging/rules", "/api/v1/messaging/messages"):
        assert client.get(path).status_code == 401
    assert client.post("/api/v1/messaging/send", json={}).status_code == 401


def test_the_log_can_be_filtered_by_channel_and_status(
        app, client, auth_headers, estate, sent, posted):
    _smtp_ready(app)
    _set(app, {"telegram.enabled": True, "telegram.bot_token": "t",
               "telegram.chat_id": "-1"})
    _configure(client, auth_headers, "contract_expiry", is_enabled=True,
               advance_days=[60], channels=["email", "telegram"], audiences=["client"])
    _sweep(client, auth_headers)

    assert len(_messages(client, auth_headers, channel="email")) == 1
    assert len(_messages(client, auth_headers, channel="telegram")) == 1
    assert len(_messages(client, auth_headers, status="sent")) == 2
    assert _messages(client, auth_headers, status="failed") == []
