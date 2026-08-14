"""Phase 5 — Celery task tests.

TestingConfig sets CELERY_TASK_ALWAYS_EAGER, so task.delay() runs
inline and the JobRun rows show up immediately in the same DB session.
No broker required."""
import json
from datetime import date, timedelta

from app.extensions import db
from app.models import JobRun, PropertyAgreement, Landlord, Property
from app.tasks.expiry import daily_expiry_sweep
from app.tasks.reminders import recompute_reminder_summary


def _make_property_with_expiring_agreement(app, *, days_ago: int):
    """Mint the minimum graph needed to test the expiry sweep: a
    landlord -> property -> active agreement whose expiry_date is
    `days_ago` days in the past (positive number = expired)."""
    with app.app_context():
        ll = Landlord(code="LL-T-1", name="Sweep Landlord")
        db.session.add(ll)
        db.session.flush()
        prop = Property(code="PROP-T-1", name="Sweep Tower",
                        property_type="full_building", landlord_id=ll.id)
        db.session.add(prop)
        db.session.flush()
        a = PropertyAgreement(
            property_id=prop.id, landlord_id=ll.id,
            start_date=date.today() - timedelta(days=days_ago + 365),
            expiry_date=date.today() - timedelta(days=days_ago),
            renewal_status="pending",
        )
        db.session.add(a)
        db.session.commit()
        return a.id


# ---------------------------------------------------------------------------
# daily_expiry_sweep
# ---------------------------------------------------------------------------
def test_expiry_sweep_flips_expired_agreement(app):
    agreement_id = _make_property_with_expiring_agreement(app, days_ago=10)
    with app.app_context():
        result = daily_expiry_sweep.delay().get()
        assert result["expired_count"] == 1
        assert agreement_id in result["agreement_ids"]
        a = PropertyAgreement.query.get(agreement_id)
        assert a.renewal_status == "expired"


def test_expiry_sweep_is_idempotent(app):
    _make_property_with_expiring_agreement(app, days_ago=20)
    with app.app_context():
        first = daily_expiry_sweep.delay().get()
        second = daily_expiry_sweep.delay().get()
        assert first["expired_count"] == 1
        assert second["expired_count"] == 0  # already flipped


def test_expiry_sweep_writes_jobrun_row(app):
    _make_property_with_expiring_agreement(app, days_ago=5)
    with app.app_context():
        daily_expiry_sweep.delay().get()
        runs = JobRun.query.filter_by(task="daily_expiry_sweep").all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "ok"
        assert run.finished_at is not None
        result = json.loads(run.result)
        assert result["expired_count"] == 1


def test_expiry_sweep_no_op_with_no_data(app):
    with app.app_context():
        result = daily_expiry_sweep.delay().get()
        assert result["expired_count"] == 0
        runs = JobRun.query.filter_by(task="daily_expiry_sweep").all()
        assert len(runs) == 1
        assert runs[0].status == "ok"


# ---------------------------------------------------------------------------
# recompute_reminder_summary
# ---------------------------------------------------------------------------
def test_reminder_summary_returns_bucket_counts(app):
    with app.app_context():
        result = recompute_reminder_summary.delay().get()
        assert set(result.keys()) == {"expired", "7", "15", "30", "60", "90", "safe"}
        assert all(isinstance(v, int) for v in result.values())
        run = JobRun.query.filter_by(task="recompute_reminder_summary").first()
        assert run is not None
        assert run.status == "ok"
        assert json.loads(run.result) == result


# ---------------------------------------------------------------------------
# Task registry — confirms beat schedule and task names are discoverable
# ---------------------------------------------------------------------------
def test_celery_tasks_registered(app):
    from app.celery_app import celery
    registered = set(celery.tasks.keys())
    assert "app.tasks.expiry.daily_expiry_sweep" in registered
    assert "app.tasks.reminders.recompute_reminder_summary" in registered


def test_beat_schedule_configured(app):
    from app.celery_app import celery
    sched = celery.conf.beat_schedule
    assert "daily-expiry-sweep" in sched
    assert "daily-reminder-recompute" in sched
