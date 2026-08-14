"""services/cache.py — the Redis-backed cache with in-process fallback.

These tests deliberately flip app.config["TESTING"] off inside their own
app-context block to exercise the real caching path; every other test in
the suite relies on TESTING staying on so caching stays inert and the
process-global fallback dict never leaks a value across tests."""
import time

from app.services import cache as cache_service


def test_disabled_under_testing_config(app):
    with app.app_context():
        cache_service.cache_set("k1", {"a": 1}, 30)
        assert cache_service.cache_get("k1") is None


def test_get_set_round_trip_when_enabled(app):
    with app.app_context():
        app.config["TESTING"] = False
        try:
            cache_service.cache_set("k2", {"a": 1, "b": [1, 2, 3]}, 30)
            assert cache_service.cache_get("k2") == {"a": 1, "b": [1, 2, 3]}
        finally:
            app.config["TESTING"] = True
            cache_service.cache_delete("k2")


def test_miss_returns_none(app):
    with app.app_context():
        app.config["TESTING"] = False
        try:
            assert cache_service.cache_get("does-not-exist") is None
        finally:
            app.config["TESTING"] = True


def test_expiry_honoured(app):
    with app.app_context():
        app.config["TESTING"] = False
        try:
            cache_service.cache_set("k3", "value", 0)
            time.sleep(0.05)
            assert cache_service.cache_get("k3") is None
        finally:
            app.config["TESTING"] = True


def test_delete_removes_value(app):
    with app.app_context():
        app.config["TESTING"] = False
        try:
            cache_service.cache_set("k4", "value", 30)
            cache_service.cache_delete("k4")
            assert cache_service.cache_get("k4") is None
        finally:
            app.config["TESTING"] = True
            cache_service.cache_delete("k4")


def test_falls_back_to_local_store_when_redis_unset(app):
    # REDIS_URL is unset in the test config (confirmed via conftest), so
    # this exercises the exact fallback path production would use if a
    # broker went down mid-request.
    with app.app_context():
        assert app.config.get("REDIS_URL") is None
        app.config["TESTING"] = False
        try:
            cache_service.cache_set("k5", "fallback-value", 30)
            assert cache_service.cache_get("k5") == "fallback-value"
        finally:
            app.config["TESTING"] = True
            cache_service.cache_delete("k5")
