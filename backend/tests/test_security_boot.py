"""Phase 2 — boot-time guardrail tests for ProductionConfig.validate."""
import pytest
from config import ProductionConfig, DEV_DEFAULT_SECRET, DEV_DEFAULT_JWT_SECRET


def _good_cfg(**overrides):
    cfg = {
        "SECRET_KEY": "x" * 64,
        "JWT_SECRET_KEY": "y" * 64,
        "CORS_ORIGINS": ["https://portal.example.com"],
    }
    cfg.update(overrides)
    return cfg


def test_validate_accepts_safe_prod_config():
    # Should not raise.
    ProductionConfig.validate(_good_cfg())


def test_validate_rejects_dev_secret_key():
    with pytest.raises(RuntimeError) as exc:
        ProductionConfig.validate(_good_cfg(SECRET_KEY=DEV_DEFAULT_SECRET))
    assert "SECRET_KEY" in str(exc.value)


def test_validate_rejects_dev_jwt_secret_key():
    with pytest.raises(RuntimeError) as exc:
        ProductionConfig.validate(_good_cfg(JWT_SECRET_KEY=DEV_DEFAULT_JWT_SECRET))
    assert "JWT_SECRET_KEY" in str(exc.value)


def test_validate_rejects_missing_secret_key():
    with pytest.raises(RuntimeError) as exc:
        ProductionConfig.validate(_good_cfg(SECRET_KEY=""))
    assert "SECRET_KEY" in str(exc.value)


def test_validate_rejects_short_secret():
    with pytest.raises(RuntimeError) as exc:
        ProductionConfig.validate(_good_cfg(SECRET_KEY="short"))
    assert "at least" in str(exc.value)


def test_validate_rejects_wildcard_cors():
    with pytest.raises(RuntimeError) as exc:
        ProductionConfig.validate(_good_cfg(CORS_ORIGINS=["*"]))
    assert "CORS_ORIGINS" in str(exc.value)


def test_validate_reports_all_problems_at_once():
    with pytest.raises(RuntimeError) as exc:
        ProductionConfig.validate({
            "SECRET_KEY": DEV_DEFAULT_SECRET,
            "JWT_SECRET_KEY": DEV_DEFAULT_JWT_SECRET,
            "CORS_ORIGINS": ["*"],
        })
    msg = str(exc.value)
    assert "SECRET_KEY" in msg
    assert "JWT_SECRET_KEY" in msg
    assert "CORS_ORIGINS" in msg
