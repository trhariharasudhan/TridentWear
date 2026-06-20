# -*- coding: utf-8 -*-
"""
test_payment_security.py — Minimal security test for Razorpay signature verification.

Tests:
1. POST /api/v1/payments/verify with a missing signature -> must return 400
2. POST /api/v1/payments/verify with a fabricated/invalid signature -> must return 400
3. POST /api/v1/payments/verify with correct HMAC signature (test_mode=True) -> must return 200
4. POST /api/v1/payments/cod -> must still return 200 (COD unaffected)

Run with:
    python test_payment_security.py

Requires the server to be running on http://127.0.0.1:8010
"""

import hmac
import hashlib
import json
import sys
import urllib.request
import urllib.error

import os
BASE = os.getenv("TRIDENT_BASE_URL", "http://127.0.0.1:8020")

# ── Test Razorpay key secret (matches backend/.env test value) ────────────────
# Change this if your RAZORPAY_KEY_SECRET in backend/.env is different.
TEST_KEY_SECRET = "rzp_test_key_secret"

PASS = 0
FAIL = 0


def request(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=all_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(label: str, got_status: int, want_status: int, body: dict) -> None:
    global PASS, FAIL
    ok = got_status == want_status
    mark = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"         Expected HTTP {want_status}, got HTTP {got_status}")
        print(f"         Body: {body}")


def make_signature(order_id: str, payment_id: str, secret: str) -> str:
    msg = f"{order_id}|{payment_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


# ── Shared order payload ──────────────────────────────────────────────────────
ORDER_DATA = {
    "subtotal": 999.0,
    "customer": {"name": "Test User", "email": "test@example.com", "phone": "9999999999"},
    "shipping": {"address": "123 Test St", "city": "Mumbai", "pincode": "400001", "state": "MH"},
    "items": [{"product_id": 1, "name": "Test Tee", "qty": 1, "price": 999.0}],
    "test_mode": True,
}

ORDER_ID = "order_testorderid0001"
PAYMENT_ID = "pay_testpayid0001"


def test_missing_signature():
    """Missing razorpay_signature field should return 422 (validation error)."""
    body = {
        "razorpay_order_id": ORDER_ID,
        "razorpay_payment_id": PAYMENT_ID,
        # razorpay_signature intentionally omitted
        "order_data": ORDER_DATA,
    }
    # Pydantic will catch this before service layer
    status, resp = request("POST", "/api/v1/payments/verify", {
        "razorpay_order_id": ORDER_ID,
        "razorpay_payment_id": PAYMENT_ID,
        "razorpay_signature": "",   # empty string
        "order_data": ORDER_DATA,
    })
    check("Empty signature -> HTTP 400", status, 400, resp)


def test_invalid_signature():
    """Fabricated/wrong signature must be rejected with 400."""
    body = {
        "razorpay_order_id": ORDER_ID,
        "razorpay_payment_id": PAYMENT_ID,
        "razorpay_signature": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "order_data": ORDER_DATA,
    }
    status, resp = request("POST", "/api/v1/payments/verify", body)
    check("Invalid signature -> HTTP 400", status, 400, resp)


def test_valid_signature():
    """Correctly computed HMAC should be accepted (test_mode=True, dev env)."""
    sig = make_signature(ORDER_ID, PAYMENT_ID, TEST_KEY_SECRET)
    body = {
        "razorpay_order_id": ORDER_ID,
        "razorpay_payment_id": PAYMENT_ID,
        "razorpay_signature": sig,
        "order_data": ORDER_DATA,
    }
    status, resp = request("POST", "/api/v1/payments/verify", body)
    check("Valid HMAC signature -> HTTP 200", status, 200, resp)


def test_cod_unaffected():
    """COD flow must be completely unaffected by the Razorpay changes."""
    body = {
        "items": ORDER_DATA["items"],
        "subtotal": ORDER_DATA["subtotal"],
        "customer": ORDER_DATA["customer"],
        "shipping": ORDER_DATA["shipping"],
        "test_mode": True,
    }
    status, resp = request("POST", "/api/v1/payments/cod", body)
    check("COD order flow -> HTTP 200", status, 200, resp)



def test_webhook_missing_signature():
    """Webhook with missing signature header -> 400."""
    body = {"event": "payment.captured", "id": "evt_test0001", "payload": {}}
    status, resp = request("POST", "/api/v1/payments/webhook", body)
    check("Webhook missing signature -> HTTP 400", status, 400, resp)


def test_webhook_invalid_signature():
    """Webhook with invalid signature -> 400."""
    body = {"event": "payment.captured", "id": "evt_test0001", "payload": {}}
    headers = {"X-Razorpay-Signature": "wrongsignature"}
    status, resp = request("POST", "/api/v1/payments/webhook", body, headers=headers)
    check("Webhook invalid signature -> HTTP 400", status, 400, resp)


def test_webhook_valid_signature():
    """Webhook with valid signature -> 200."""
    body = {
        "event": "payment.captured",
        "id": f"evt_test_{uuid_hex()}",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test0001",
                    "order_id": "order_testorderid0001",
                    "status": "captured"
                }
            }
        }
    }
    raw_body = json.dumps(body).encode()
    webhook_secret = "rzp_webhook_secret"
    sig = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    headers = {"X-Razorpay-Signature": sig}
    status, resp = request("POST", "/api/v1/payments/webhook", body, headers=headers)
    check("Webhook valid signature -> HTTP 200", status, 200, resp)


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


# ── Run ───────────────────────────────────────────────────────────────────────
print("\nTridentWear — Payment Security Tests")
print("=" * 45)
print(f"Server: {BASE}")
print(f"Key secret under test: {TEST_KEY_SECRET[:8]}...")
print()

test_missing_signature()
test_invalid_signature()
test_valid_signature()
test_cod_unaffected()
test_webhook_missing_signature()
test_webhook_invalid_signature()
test_webhook_valid_signature()

print()
print("=" * 45)
print(f"Results: {PASS} passed, {FAIL} failed")

if FAIL:
    print("SECURITY ISSUE — one or more payment security checks failed!")
    sys.exit(1)
else:
    print("All payment security checks passed.")
    sys.exit(0)
