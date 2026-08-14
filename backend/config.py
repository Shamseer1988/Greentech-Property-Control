import os
from dotenv import load_dotenv

# Load backend/.env. override=False so a value the operator deliberately
# exported in their shell (or supplied via a service-manager environment
# block) always wins over a stale entry in the file.
load_dotenv(override=False)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


# Defaults a developer might forget to override — fail loud in production.
DEV_DEFAULT_SECRET = "dev-secret"
DEV_DEFAULT_JWT_SECRET = "dev-jwt-secret"
MIN_SECRET_BYTES = 32


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _database_uri() -> str:
    """Resolve the SQLAlchemy URI.

    Priority:
      1. DATABASE_URL — explicit, wins if set (back-compat / native dev).
      2. Assembled from POSTGRES_* — the backend reads POSTGRES_USER /
         POSTGRES_PASSWORD / POSTGRES_DB / POSTGRES_HOST / POSTGRES_PORT
         from backend/.env (or the operator's shell environment).
      3. A localhost default for first-boot before .env exists.
    """
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "greentech_realestate")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", DEV_DEFAULT_SECRET)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEV_DEFAULT_JWT_SECRET)

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]

    UPLOAD_FOLDER = os.path.abspath(os.path.join(BASE_DIR, os.getenv("UPLOAD_FOLDER", "../uploads")))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "25")) * 1024 * 1024

    JWT_ACCESS_TOKEN_EXPIRES = 60 * 60 * 8  # 8 hours
    JWT_REFRESH_TOKEN_EXPIRES = 60 * 60 * 24 * 14  # 14 days

    # JWT lives in httpOnly cookies (Phase 1). Header auth is intentionally
    # disabled so XSS cannot exfiltrate a bearer token.
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_ACCESS_COOKIE_PATH = "/api/v1"
    JWT_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
    # Cookie flags are env-driven so the same image serves both flavours:
    #   LOCAL (plain HTTP):  JWT_COOKIE_SECURE=false  → browser keeps cookie
    #   LIVE  (HTTPS/CF):    JWT_COOKIE_SECURE=true   → cookie HTTPS-only
    # Defaults below are the safe DEV defaults; ProductionConfig flips the
    # baseline to secure so a prod boot without the env var is still safe.
    JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "Lax")
    JWT_COOKIE_SECURE = _env_bool("JWT_COOKIE_SECURE", False)

    # --- Phase 2: rate limiting ------------------------------------------
    # If REDIS_URL is set the limiter and (later) Celery share it. Without
    # it, Flask-Limiter falls back to its in-memory store — fine for dev
    # but per-process, so multi-worker prod must set REDIS_URL.
    REDIS_URL = os.getenv("REDIS_URL")
    RATELIMIT_STORAGE_URI = REDIS_URL or "memory://"
    RATELIMIT_DEFAULT = "300 per minute"
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_ENABLED = True

    # --- Phase 6: observability -----------------------------------------
    # Sentry DSN — when unset, init_sentry() is a no-op (safe in dev/CI).
    SENTRY_DSN = os.getenv("SENTRY_DSN") or None
    # Shared secret a Prometheus scraper must echo as X-Metrics-Token to
    # read /metrics. Leaving this empty disables the auth check (fine if
    # the scraper is on a private network and nginx already blocks public
    # access).
    METRICS_TOKEN = os.getenv("METRICS_TOKEN") or None
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    # JSON logs default on in production, off elsewhere — dev console
    # output stays human-readable.
    LOG_JSON = (os.getenv("LOG_JSON", "").lower() in ("1", "true", "yes"))


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = "development"


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    ENV = "testing"
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )
    # Disabled by default so test_auth.py etc. don't trip the bucket.
    # The dedicated rate-limit test re-enables it on its own app instance.
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = "memory://"
    # Celery tasks run inline in tests — no broker needed.
    CELERY_TASK_ALWAYS_EAGER = True


class ProductionConfig(Config):
    DEBUG = False
    ENV = "production"
    # Secure baseline for prod: HTTPS-only cookies. Still env-overridable
    # (e.g. a staging box behind plain HTTP) but defaults to safe.
    JWT_COOKIE_SECURE = _env_bool("JWT_COOKIE_SECURE", True)
    JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "Lax")
    LOG_JSON = True

    @classmethod
    def validate(cls, cfg) -> None:
        """Fail loud at boot if required prod secrets / CORS aren't safe.

        Called from create_app when FLASK_ENV=production. Raising here
        keeps a misconfigured deployment from ever serving traffic."""
        problems: list[str] = []

        for key, bad_default in (
            ("SECRET_KEY", DEV_DEFAULT_SECRET),
            ("JWT_SECRET_KEY", DEV_DEFAULT_JWT_SECRET),
        ):
            value = cfg.get(key)
            if not value:
                problems.append(f"{key} is not set")
                continue
            if value == bad_default:
                problems.append(f"{key} is still the dev default ('{bad_default}')")
                continue
            if len(str(value)) < MIN_SECRET_BYTES:
                problems.append(f"{key} must be at least {MIN_SECRET_BYTES} characters")

        origins = cfg.get("CORS_ORIGINS") or []
        if "*" in origins:
            problems.append(
                "CORS_ORIGINS contains '*' — production must list explicit origins"
            )

        if problems:
            raise RuntimeError(
                "Insecure production configuration:\n  - " + "\n  - ".join(problems)
            )


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
