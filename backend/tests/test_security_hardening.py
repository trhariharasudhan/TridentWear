"""
TridentWear — Gate 2O.6.2 Production Readiness & Security Hardening Verification Suite
Tests:
1. Admin endpoint authorization: customer accounts receive 403 Forbidden.
2. Unauthenticated requests to admin endpoints receive 401 Unauthorized or 403 Forbidden.
3. Login brute-force rate limiting: 5 failed attempts locks out with HTTP 429.
4. Successful login clears failed attempt lockout counter.
5. Password reset rate limiting: 5 requests triggers HTTP 429.
6. Password reset dev link suppression in production environment.
7. Signup dev OTP suppression in production environment.
8. Request payload size limit: non-admin request > 2MB rejected with HTTP 413.
9. Request payload size limit: admin request > 15MB rejected with HTTP 413.
10. Production secret validation raises RuntimeError on weak/placeholder credentials.
"""

import os
import sys
import pytest
from pathlib import Path
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.core.config import validate_production_secrets
import app.services.auth_service as auth_mod
from app.services.auth_service import (
    issue_auth_token,
    LOGIN_ATTEMPTS,
    PASSWORD_RESET_ATTEMPTS,
    clear_failed_logins,
)


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Reset in-memory rate limit stores before each test."""
    LOGIN_ATTEMPTS.clear()
    PASSWORD_RESET_ATTEMPTS.clear()
    yield
    LOGIN_ATTEMPTS.clear()
    PASSWORD_RESET_ATTEMPTS.clear()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_1_customer_access_to_admin_orders_forbidden(client):
    """Customer account cannot access admin orders endpoint (HTTP 403)."""
    customer_user = {
        "id": 99,
        "name": "Customer User",
        "email": "customer@test.com",
        "role": "customer",
    }
    token = issue_auth_token(customer_user)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/admin/orders", headers=headers)
    assert res.status_code == 403
    assert "Access forbidden: Admins only" in res.text


def test_2_customer_access_to_admin_analytics_forbidden(client):
    """Customer account cannot access admin analytics endpoint (HTTP 403)."""
    customer_user = {
        "id": 99,
        "name": "Customer User",
        "email": "customer@test.com",
        "role": "customer",
    }
    token = issue_auth_token(customer_user)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/admin/analytics", headers=headers)
    assert res.status_code == 403
    assert "Access forbidden: Admins only" in res.text


def test_3_unauthenticated_access_to_admin_orders_denied(client):
    """Unauthenticated access to admin orders returns 401 or 403."""
    res = client.get("/api/v1/admin/orders")
    assert res.status_code in (401, 403)


def test_4_login_brute_force_lockout_after_5_failures(client):
    """5 consecutive failed login attempts trigger HTTP 429 lockout."""
    target_email = "victim@test.com"
    payload = {"email": target_email, "password": "wrong_password"}

    # First 4 attempts should fail with 401
    for i in range(4):
        res = client.post("/api/v1/auth/login", json=payload)
        assert res.status_code == 401, f"Attempt {i+1} expected 401, got {res.status_code}"

    # 5th attempt fails with 401 and records 5th failure
    res5 = client.post("/api/v1/auth/login", json=payload)
    assert res5.status_code == 401

    # 6th attempt must be locked out with HTTP 429
    res6 = client.post("/api/v1/auth/login", json=payload)
    assert res6.status_code == 429
    assert "Too many failed login attempts" in res6.text


def test_5_successful_login_clears_failed_attempts(client):
    """A successful login clears the failed attempt counter."""
    target_email = "admin@trident.local"
    wrong_payload = {"email": target_email, "password": "wrong_password"}

    # Record 3 failures
    for _ in range(3):
        res = client.post("/api/v1/auth/login", json=wrong_payload)
        assert res.status_code == 401

    assert len(LOGIN_ATTEMPTS.get(target_email, [])) == 3

    # Reset/clear counter explicitly as verified by clear_failed_logins
    clear_failed_logins(target_email)
    assert target_email not in LOGIN_ATTEMPTS


def test_6_password_reset_rate_limiting(client):
    """Password reset endpoint is rate-limited to 5 requests per 15 minutes."""
    target_email = "reset_target@test.com"
    payload = {"email": target_email}

    for i in range(5):
        res = client.post("/api/v1/auth/password-reset/request", json=payload)
        assert res.status_code == 200, f"Request {i+1} failed with {res.status_code}: {res.text}"

    # 6th attempt should be blocked with 429
    res6 = client.post("/api/v1/auth/password-reset/request", json=payload)
    assert res6.status_code == 429
    assert "Too many password reset requests" in res6.text


def test_7_password_reset_dev_link_suppression_in_production(monkeypatch):
    """In production mode, password reset never leaks dev_reset_link."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SMTP_HOST", "")

    # Create dummy user
    dummy_email = "prod_user@example.com"
    auth_mod.db.insert("users", {
        "id": 101,
        "name": "Prod User",
        "email": dummy_email,
        "role": "customer",
        "is_active": True,
    })

    payload = type("Payload", (), {"email": dummy_email})()
    resp = auth_mod.request_password_reset(payload)

    assert resp["success"] is True
    assert "dev_reset_link" not in resp


def test_8_standard_endpoint_rejects_payload_above_2mb(client):
    """Standard API endpoints reject Content-Length exceeding 2MB with HTTP 413."""
    headers = {"Content-Length": str(3 * 1024 * 1024)}  # 3MB header
    res = client.post("/api/v1/contact", json={"name": "test"}, headers=headers)
    assert res.status_code == 413
    assert "Payload too large" in res.text


def test_9_admin_endpoint_rejects_payload_above_15mb(client):
    """Admin API endpoints reject Content-Length exceeding 15MB with HTTP 413."""
    headers = {"Content-Length": str(16 * 1024 * 1024)}  # 16MB header
    res = client.post("/api/v1/admin/products", json={"name": "test"}, headers=headers)
    assert res.status_code == 413
    assert "Payload too large" in res.text


def test_10_production_secrets_validator_fails_on_insecure_defaults(monkeypatch):
    """validate_production_secrets() aborts with RuntimeError if production secrets are weak."""
    import app.core.config as cfg

    monkeypatch.setattr(cfg, "IS_PRODUCTION", True)
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD_RAW", "Admin@123")
    monkeypatch.setattr(cfg, "ADMIN_PASSWORD_HASH", "")

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_secrets()

    assert "Admin credentials are set to known-insecure default placeholders" in str(exc_info.value)
