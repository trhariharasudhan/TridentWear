import os
import time
import pytest
from app.core.redis_client import check_rate_limit, get_redis_health, get_redis_client
import app.core.redis_client as rc_module

def test_redis_unconfigured_defaults_to_in_memory_fallback():
    """When REDIS_URL is unset, rate limiting safely operates in memory."""
    store = {}
    allowed1, count1 = check_rate_limit("user_test_1", max_requests=3, window_seconds=10, in_memory_store=store)
    allowed2, count2 = check_rate_limit("user_test_1", max_requests=3, window_seconds=10, in_memory_store=store)
    allowed3, count3 = check_rate_limit("user_test_1", max_requests=3, window_seconds=10, in_memory_store=store)
    allowed4, count4 = check_rate_limit("user_test_1", max_requests=3, window_seconds=10, in_memory_store=store)

    assert allowed1 is True and count1 == 1
    assert allowed2 is True and count2 == 2
    assert allowed3 is True and count3 == 3
    assert allowed4 is False and count4 == 3


def test_rate_limit_sliding_window_expiration():
    """Stale requests outside window_seconds expire and allow new requests."""
    store = {}
    now = time.time()
    # Populate with entries from 100 seconds ago
    store["user_stale"] = [now - 100, now - 90, now - 80]

    allowed, count = check_rate_limit("user_stale", max_requests=2, window_seconds=60, in_memory_store=store)
    assert allowed is True
    assert count == 1  # 3 expired, 1 added


def test_redis_connection_failure_falls_back_safely(monkeypatch):
    """When REDIS_URL is configured to an unreachable host, fallback operates safely."""
    monkeypatch.setenv("REDIS_URL", "redis://nonexistent-host:9999/0")
    # Reset singleton state
    rc_module._redis_initialized = False
    rc_module._redis_client = None

    health = get_redis_health()
    assert health["status"] in ("unavailable", "driver_missing", "unconfigured")

    store = {}
    allowed, count = check_rate_limit("user_failover", max_requests=5, window_seconds=60, in_memory_store=store)
    assert allowed is True
    assert count == 1


def test_redis_health_status_structure():
    """Health check dictionary provides predictable fields."""
    health = get_redis_health()
    assert "status" in health
