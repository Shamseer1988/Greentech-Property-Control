from datetime import datetime, timezone
from flask import Blueprint

from ..extensions import db
from ..utils.responses import success_response, error_response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    return success_response(
        data={
            "status": "healthy",
            "service": "greentech-realestate-api",
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )


@health_bp.get("/health/db")
def health_db():
    try:
        db.session.execute(db.text("SELECT 1"))
        return success_response(data={"database": "connected"})
    except Exception as exc:
        return error_response("Database unreachable", 503, str(exc))
