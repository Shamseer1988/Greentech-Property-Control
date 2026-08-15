import os
from apiflask import APIFlask
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_map, ProductionConfig
from .extensions import db, migrate, jwt, limiter
from .utils.responses import error_response


def _docs_enabled(env: str) -> bool:
    """OpenAPI docs (Swagger UI + /openapi.json) are on in dev/testing
    and off in production unless ENABLE_API_DOCS is explicitly truthy.
    The spec leaks field-level structure to anyone who can hit the URL,
    so prod stays closed by default."""
    if env != "production":
        return True
    flag = (os.getenv("ENABLE_API_DOCS") or "").lower()
    return flag in ("1", "true", "yes", "on")


def create_app(config_name: str | None = None) -> APIFlask:
    env = config_name or os.getenv("FLASK_ENV", "development")
    docs_on = _docs_enabled(env)
    app = APIFlask(
        __name__,
        title="GreenTech Real Estate API",
        version="1.0.0",
        docs_path="/docs" if docs_on else None,
        spec_path="/openapi.json" if docs_on else None,
    )
    # apiflask's own request/response tagging is documentation-only —
    # we still return success_response / error_response from views.
    app.config["AUTO_TAGS"] = False
    app.config.from_object(config_map.get(env, config_map["default"]))

    # Boot-time guardrail: production refuses to start with dev secrets
    # or wildcard CORS. Raises RuntimeError before the app serves traffic.
    if env == "production":
        ProductionConfig.validate(app.config)

    @app.error_processor
    def _envelope_errors(err):
        """Funnel apiflask validation / HTTP errors through our
        existing {success, message, details} envelope so clients never
        see two different error shapes."""
        body = error_response(
            err.message or "Request failed",
            err.status_code,
            err.detail or None,
        )
        # error_response returns (jsonify, status); apiflask wants
        # (body, status, headers). Unpack into the right tuple.
        json_resp, status = body
        return json_resp, status, err.headers or {}

    # ProxyFix so that get_remote_address() (rate-limit key), audit logs,
    # and request.scheme honour exactly one upstream proxy (nginx). If a
    # second proxy is ever inserted (e.g. Cloudflare in front of nginx),
    # bump x_for to 2.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    # Import models so Alembic autogenerate sees them
    from . import models  # noqa: F401
    migrate.init_app(app, db)
    jwt.init_app(app)
    _register_jwt_callbacks()
    limiter.init_app(app)
    # CORS: if any allowed origin is "*", broadcast that to flask-cors as a
    # single wildcard (the list form would attempt strict matching against
    # the literal string "*"). Same-origin requests through nginx don't
    # trigger CORS at all; this only matters for cross-origin dev setups.
    _cors_origins = app.config["CORS_ORIGINS"]
    if "*" in _cors_origins:
        _cors_origins = "*"
    CORS(app, resources={r"/api/*": {"origins": _cors_origins}}, supports_credentials=("*" not in _cors_origins))

    from .routes.health import health_bp
    from .routes.auth import auth_bp
    from .routes.users import users_bp
    from .routes.roles import roles_bp
    from .routes.audit import audit_bp
    from .routes.landlords import landlords_bp
    from .routes.clients import clients_bp
    from .routes.contracts import contracts_bp
    from .routes.rent import rent_bp
    from .routes.expenses import expenses_bp
    from .routes.properties import properties_bp
    from .routes.landlord_contracts import landlord_contracts_bp
    from .routes.agreements import agreements_bp
    from .routes.attachments import attachments_bp
    from .routes.floors import floors_bp
    from .routes.units import units_bp
    from .routes.renewals import renewals_bp
    from .routes.maintenance import maintenance_bp
    from .routes.search import search_bp
    from .routes.notifications import notifications_bp
    from .routes.events import events_bp
    from .routes.dashboard import dashboard_bp
    from .routes.reports import reports_bp
    from .routes.approvals import approvals_bp
    from .routes.settings import settings_bp
    from .routes.backup import backup_bp
    from .routes.messaging import messaging_bp
    from .routes.migration import migration_bp

    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")
    app.register_blueprint(roles_bp, url_prefix="/api/v1/roles")
    app.register_blueprint(audit_bp, url_prefix="/api/v1/audit")
    app.register_blueprint(landlords_bp, url_prefix="/api/v1/landlords")
    app.register_blueprint(clients_bp, url_prefix="/api/v1/clients")
    app.register_blueprint(contracts_bp, url_prefix="/api/v1/contracts")
    app.register_blueprint(rent_bp, url_prefix="/api/v1/rent")
    app.register_blueprint(expenses_bp, url_prefix="/api/v1/expenses")
    app.register_blueprint(properties_bp, url_prefix="/api/v1/properties")
    app.register_blueprint(landlord_contracts_bp, url_prefix="/api/v1/landlord-contracts")
    app.register_blueprint(agreements_bp, url_prefix="/api/v1")
    app.register_blueprint(attachments_bp, url_prefix="/api/v1/attachments")
    app.register_blueprint(floors_bp, url_prefix="/api/v1")
    app.register_blueprint(units_bp, url_prefix="/api/v1")
    app.register_blueprint(renewals_bp, url_prefix="/api/v1")
    app.register_blueprint(maintenance_bp, url_prefix="/api/v1")
    app.register_blueprint(search_bp, url_prefix="/api/v1")
    app.register_blueprint(notifications_bp, url_prefix="/api/v1/notifications")
    app.register_blueprint(events_bp, url_prefix="/api/v1/events")
    app.register_blueprint(dashboard_bp, url_prefix="/api/v1/dashboard")
    app.register_blueprint(reports_bp, url_prefix="/api/v1/reports")
    app.register_blueprint(approvals_bp, url_prefix="/api/v1/approvals")
    app.register_blueprint(settings_bp, url_prefix="/api/v1/settings")
    app.register_blueprint(backup_bp, url_prefix="/api/v1/backups")
    app.register_blueprint(messaging_bp, url_prefix="/api/v1/messaging")
    app.register_blueprint(migration_bp, url_prefix="/api/v1/migration")

    # Celery (Phase 5). Initialized after blueprints so task imports
    # see the fully-configured app.
    from .celery_app import init_celery
    init_celery(app)

    # Observability (Phase 6). init_logging plants the request-id hook
    # before any route registration so every log line emitted by a
    # handler is bound to its request.
    from .observability import init_logging, init_sentry, init_metrics
    init_logging(app)
    init_sentry(app)
    init_metrics(app)

    register_error_handlers(app)
    register_security_headers(app)
    register_cli(app)

    @app.route("/")
    def index():
        return jsonify({"service": "GreenTech Real Estate API", "status": "ok"})

    return app


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(err):
        return error_response("Bad request", 400, str(getattr(err, "description", "")))

    @app.errorhandler(401)
    def unauthorized(err):
        return error_response("Unauthorized", 401)

    @app.errorhandler(403)
    def forbidden(err):
        return error_response("Forbidden", 403)

    @app.errorhandler(404)
    def not_found(err):
        return error_response("Not found", 404)

    @app.errorhandler(429)
    def rate_limited(err):
        # Flask-Limiter raises a 429 with the per-route limit string in
        # `err.description`. Surface it so clients can show "try again in N".
        return error_response("Too many requests", 429, str(getattr(err, "description", "")))

    @app.errorhandler(422)
    def unprocessable(err):
        return error_response("Request validation failed", 422, str(getattr(err, "description", "")))

    @app.errorhandler(500)
    def server_error(err):
        return error_response("Internal server error", 500)


def register_security_headers(app: Flask) -> None:
    """Defense-in-depth headers on every response. Uses setdefault so
    specific routes (e.g. file downloads that need a particular
    Content-Type) can override individual headers."""
    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), interest-cohort=()",
        )
        # Prevent aggressive caching of API responses by browsers and CDNs (e.g., Cloudflare)
        resp.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        resp.headers.setdefault("Pragma", "no-cache")
        return resp


def register_cli(app: Flask) -> None:
    from .cli import register_commands
    register_commands(app)


def _register_jwt_callbacks() -> None:
    """JWT lifecycle hooks: per-token-version invalidation + revocation list.

    Idempotent — safe to call once per create_app(). Imports are local so
    test environments that don't load every blueprint still work."""
    from .models import User, JWTBlocklist

    @jwt.additional_claims_loader
    def _claims(identity):
        user = User.query.get(int(identity)) if identity else None
        if user is None:
            return {}
        return {
            "username": user.username,
            "is_super_user": user.is_super_user,
            "tv": user.token_version,
        }

    @jwt.user_lookup_loader
    def _user_lookup(_jwt_header, jwt_data):
        user = User.query.get(int(jwt_data["sub"]))
        if user is None or not user.is_active:
            return None
        # Token version mismatch == issued before the last change-password
        # (or other forced invalidation). Treat as revoked.
        if int(jwt_data.get("tv", 0)) != int(user.token_version or 0):
            return None
        return user

    @jwt.token_in_blocklist_loader
    def _is_revoked(_jwt_header, jwt_data) -> bool:
        return JWTBlocklist.query.filter_by(jti=jwt_data["jti"]).first() is not None
