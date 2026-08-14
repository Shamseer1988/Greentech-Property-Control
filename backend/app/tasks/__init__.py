"""Background tasks. Importing this package triggers @celery.task
registration on each submodule so the worker has a complete task list."""
import json
import logging
from contextlib import contextmanager
from datetime import datetime

from ..extensions import db
from ..models import JobRun

log = logging.getLogger("greentech.tasks")


@contextmanager
def jobrun(task_name: str, payload: dict | None = None):
    """Wrap a task body so its start/end/result/error are recorded.

    Usage:
        @celery.task(name="...")
        def my_task(arg):
            with jobrun("my_task", {"arg": arg}) as run:
                result = ...do work...
                run.result = json.dumps(result)
                return result
    """
    run = JobRun(
        task=task_name,
        status="running",
        payload=json.dumps(payload) if payload is not None else None,
    )
    db.session.add(run)
    db.session.commit()
    log.info("task %s started run=%s", task_name, run.id)
    try:
        yield run
        run.status = "ok"
        run.finished_at = datetime.utcnow()
        db.session.commit()
        log.info("task %s ok run=%s", task_name, run.id)
    except Exception as exc:
        run.status = "error"
        run.error = repr(exc)[:4000]
        run.finished_at = datetime.utcnow()
        db.session.commit()
        log.exception("task %s failed run=%s", task_name, run.id)
        raise


# Importing submodules at package load wires the Celery registry.
from . import backup  # noqa: E402,F401
from . import reminders  # noqa: E402,F401
from . import expiry  # noqa: E402,F401
from . import rent  # noqa: E402,F401
from . import notifications  # noqa: E402,F401
from . import sentry_alerts  # noqa: E402,F401
