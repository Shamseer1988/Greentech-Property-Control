"""Agreement generation service: signatory validation, gapless
per-month numbering, and the snapshot claim — a generated agreement
must never change if the master record it was drawn from is edited
later."""
from app.extensions import db
from app.models import Landlord, User
from app.services import agreements as agreements_service
from app.services import settings as settings_service


def _actor(app):
    with app.app_context():
        return User.query.filter_by(is_super_user=True).first()


def _company_signatory(app):
    with app.app_context():
        settings_service.set_value("company.signatory_name", "Ali Hassan", actor_id=None)
        settings_service.set_value("company.signatory_name_ar", "علي حسن", actor_id=None)
        settings_service.set_value("company.signatory_id_number", "28888888888", actor_id=None)
        db.session.commit()


def _landlord_with_signatory(app, **overrides):
    with app.app_context():
        defaults = dict(
            code="LL-SVC", name="Paris Hypermarket LLC", name_ar="باريس هايبر ماركت ذ.م.م",
            signatory_name="Ismail Thanjalil", signatory_name_ar="إسماعيل ثنجاليل",
            signatory_id_number="26935600953",
        )
        defaults.update(overrides)
        landlord = Landlord(**defaults)
        db.session.add(landlord)
        db.session.commit()
        return landlord.id


def _generate(app, landlord_id, actor):
    with app.app_context():
        landlord = Landlord.query.get(landlord_id)
        agreement = agreements_service.generate(
            template_slug="labour-camp-room-rental", party_role="landlord",
            landlord_id=landlord.id, client_id=None,
            rooms_description="10 rooms in area 85", rooms_count=10,
            start_date="2026-09-01", end_date="2027-06-30",
            electricity_included=True, water_included=True,
            free_months_count=0, free_months_mode=None, free_months_specific=None,
            deposit_cheque_required=True,
            cancellation_mode="notice_months", cancellation_notice_months=3,
            rent_amount=9000, rent_payment_frequency_months=3, currency="QAR",
            actor=actor,
        )
        db.session.commit()
        return agreement.id


def test_generate_raises_when_landlord_has_no_signatory(app):
    with app.app_context():
        landlord = Landlord(code="LL-BARE", name="No Signatory Co")
        db.session.add(landlord)
        db.session.commit()
        actor = User.query.filter_by(is_super_user=True).first()
        try:
            agreements_service.generate(
                template_slug="labour-camp-room-rental", party_role="landlord",
                landlord_id=landlord.id, client_id=None,
                rooms_description="x", rooms_count=1,
                start_date="2026-01-01", end_date="2026-12-31",
                electricity_included=False, water_included=False,
                free_months_count=0, free_months_mode=None, free_months_specific=None,
                deposit_cheque_required=False,
                cancellation_mode="no_cancellation", cancellation_notice_months=None,
                rent_amount=1000, rent_payment_frequency_months=1, currency="QAR",
                actor=actor,
            )
            assert False, "should have raised AgreementError"
        except agreements_service.AgreementError as exc:
            assert "signatory" in str(exc).lower()


def test_generate_raises_when_company_signatory_missing(app):
    with app.app_context():
        landlord_id = _landlord_with_signatory(app)
    landlord = None
    with app.app_context():
        landlord = Landlord.query.get(landlord_id)
        actor = User.query.filter_by(is_super_user=True).first()
        # Company signatory settings were never set in this test's app instance.
        try:
            agreements_service.generate(
                template_slug="labour-camp-room-rental", party_role="landlord",
                landlord_id=landlord.id, client_id=None,
                rooms_description="x", rooms_count=1,
                start_date="2026-01-01", end_date="2026-12-31",
                electricity_included=False, water_included=False,
                free_months_count=0, free_months_mode=None, free_months_specific=None,
                deposit_cheque_required=False,
                cancellation_mode="no_cancellation", cancellation_notice_months=None,
                rent_amount=1000, rent_payment_frequency_months=1, currency="QAR",
                actor=actor,
            )
            assert False, "should have raised AgreementError"
        except agreements_service.AgreementError as exc:
            assert "company signatory" in str(exc).lower()


def test_agreement_number_is_gapless_per_month(app):
    _company_signatory(app)
    landlord_id = _landlord_with_signatory(app, code="LL-SEQ")
    with app.app_context():
        actor = User.query.filter_by(is_super_user=True).first()
        landlord = Landlord.query.get(landlord_id)
        first = agreements_service.generate(
            template_slug="labour-camp-room-rental", party_role="landlord",
            landlord_id=landlord.id, client_id=None,
            rooms_description="x", rooms_count=1,
            start_date="2026-01-01", end_date="2026-12-31",
            electricity_included=False, water_included=False,
            free_months_count=0, free_months_mode=None, free_months_specific=None,
            deposit_cheque_required=False,
            cancellation_mode="no_cancellation", cancellation_notice_months=None,
            rent_amount=1000, rent_payment_frequency_months=1, currency="QAR",
            actor=actor,
        )
        db.session.commit()
        second = agreements_service.generate(
            template_slug="labour-camp-room-rental", party_role="landlord",
            landlord_id=landlord.id, client_id=None,
            rooms_description="y", rooms_count=1,
            start_date="2026-01-01", end_date="2026-12-31",
            electricity_included=False, water_included=False,
            free_months_count=0, free_months_mode=None, free_months_specific=None,
            deposit_cheque_required=False,
            cancellation_mode="no_cancellation", cancellation_notice_months=None,
            rent_amount=1000, rent_payment_frequency_months=1, currency="QAR",
            actor=actor,
        )
        db.session.commit()
        first_seq = int(first.agreement_number.rsplit("-", 1)[1])
        second_seq = int(second.agreement_number.rsplit("-", 1)[1])
        assert second_seq == first_seq + 1
        assert first.agreement_number.startswith("AGR-")


def test_snapshot_survives_a_later_master_edit(app):
    _company_signatory(app)
    landlord_id = _landlord_with_signatory(app, code="LL-SNAP")
    actor = _actor(app)
    agreement_id = _generate(app, landlord_id, actor)

    with app.app_context():
        landlord = Landlord.query.get(landlord_id)
        landlord.name = "Renamed Later LLC"
        landlord.name_ar = "اسم آخر لاحقاً"
        db.session.commit()

    with app.app_context():
        from app.models import GeneratedAgreement
        agreement = GeneratedAgreement.query.get(agreement_id)
        assert agreement.snapshot_json["lessor"]["name"] == "Paris Hypermarket LLC"
        assert agreement.snapshot_json["lessor"]["name_ar"] == "باريس هايبر ماركت ذ.م.م"


def test_generate_saves_a_docx_attachment_on_the_landlord(app):
    _company_signatory(app)
    landlord_id = _landlord_with_signatory(app, code="LL-ATT")
    actor = _actor(app)
    agreement_id = _generate(app, landlord_id, actor)

    with app.app_context():
        from app.models import Attachment, GeneratedAgreement
        agreement = GeneratedAgreement.query.get(agreement_id)
        assert agreement.attachment_id is not None
        att = Attachment.query.get(agreement.attachment_id)
        assert att.entity_type == "landlord"
        assert att.entity_id == str(landlord_id)
        assert att.category == "agreement"
        assert att.original_name.endswith(".docx")
