"""
TridentWear — Test Suite for Gate 2O.3.4:
Secure Backend FBT Offer & Order Qualification Implementation.

Tests cover:
1. Token structure, signature, claims, expiration, and tamper resistance.
2. Distinct item qualification rules (min 2 distinct products, qty/sizes don't count).
3. Authoritative line item math and exclusion of unrelated cart products.
4. Product API endpoint (/api/v1/products/{id}/fbt-offer).
5. Coupon apply endpoint (/api/v1/coupons/apply).
6. Direct order creation (COD) and replay protection across orders.
7. Online payment orders (pending vs finalized capture).
8. Failure compensation releasing coupon and offer.
9. SQL adapter unique offer_id enforcement and Alembic migration 0013.
"""

import sys
import time
import uuid
import copy
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest
import multiprocessing

def _worker_reserve_fbt_offer(db_dir_str, code, today_iso, order_id, offer_id, sync_event, queue):
    """Worker process function for genuine multi-process FBT offer contention test."""
    try:
        import sys
        from pathlib import Path
        b_dir = Path(__file__).resolve().parent.parent
        if str(b_dir) not in sys.path:
            sys.path.insert(0, str(b_dir))
        import app.db.database as db_m
        db_m.DB_DIR = Path(db_dir_str)
        w_adapter = db_m.JsonDatabaseAdapter()
        # Synchronize start to maximize contention
        sync_event.wait(timeout=5)
        res = w_adapter.reserve_coupon_offer(code, today_iso, order_id=order_id, offer_id=offer_id)
        queue.put(("SUCCESS", order_id, res))
    except db_m.CouponConflictError as cce:
        queue.put(("CONFLICT", order_id, str(cce)))
    except Exception as e:
        queue.put(("ERROR", order_id, str(e)))

import jwt
from fastapi import HTTPException
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_fbt_secret, FBT_OFFER_EXPIRATION_HOURS
import app.services.fbt_service as fbt_service
from app.services.fbt_service import (
    issue_fbt_offer,
    verify_fbt_token,
    validate_fbt_bundle_qualification,
    FBT_ISSUER,
    FBT_AUDIENCE,
    FBT_TOKEN_TYPE,
)
import app.db.database as db_module
from app.db.database import (
    JsonDatabaseAdapter,
    PostgresDatabaseAdapter,
    CouponConflictError,
)
from app.api.coupons import apply_coupon, ApplyCouponPayload
from app.api.products import get_product_fbt_offer
from app.services.order_service import (
    process_create_order,
    create_pending_payment_order,
    create_payment_order_record,
    cancel_order_logic,
)
from app.services.payment_service import (
    finalize_paid_order,
    process_webhook,
)
from app.db.models import metadata, coupons, coupon_redemptions
from sqlalchemy import create_engine, select, insert


SAMPLE_CATALOG = [
    {"id": 1, "name": "Classic Black Tee", "price": 799.0, "stock": 50, "category": "tshirt"},
    {"id": 2, "name": "White Minimal Tee", "price": 699.0, "stock": 40, "category": "tshirt"},
    {"id": 3, "name": "Navy Formal Shirt", "price": 1299.0, "stock": 30, "category": "shirt"},
    {"id": 4, "name": "Olive Casual Shirt", "price": 1099.0, "stock": 25, "category": "shirt"},
]


class DummyRequest:
    def __init__(self, cookies=None, headers=None, session=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.session = session or {}


class MockPayload(BaseModel):
    items: list
    subtotal: float
    customer: dict
    shipping: dict
    payment_method: str = "cod"
    coupon_code: str = ""
    fbt_token: str = ""
    test_mode: bool = False


@pytest.fixture
def mock_db_dir(tmp_path, monkeypatch):
    """Provides isolated JSON database directory with fresh products and coupons."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    monkeypatch.setattr(db_module, "DB_DIR", db_dir)

    coupons_data = [
        {
            "id": 1,
            "code": "TRIDENTFIRST",
            "discount_pct": 20.0,
            "expires_at": "2027-12-31",
            "usage_limit": 1000,
            "usage_count": 0,
            "is_active": True,
        },
        {
            "id": 2,
            "code": "TRIDENT10",
            "discount_pct": 10.0,
            "expires_at": "2027-12-31",
            "usage_limit": 5000,
            "usage_count": 0,
            "is_active": True,
        },
        {
            "id": 4,
            "code": "BUNDLE10",
            "discount_pct": 10.0,
            "expires_at": "2027-12-31",
            "usage_limit": 5000,
            "usage_count": 0,
            "is_active": True,
            "redeemed_orders": {},
            "redeemed_offers": {},
        },
    ]

    import json
    with open(db_dir / "coupons.json", "w", encoding="utf-8") as f:
        json.dump(coupons_data, f, indent=2)

    with open(db_dir / "products.json", "w", encoding="utf-8") as f:
        json.dump(SAMPLE_CATALOG, f, indent=2)

    with open(db_dir / "orders.json", "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    monkeypatch.setattr("app.services.product_service.FRONTEND_PRODUCTS_PATH", tmp_path / "frontend_products.json")
    adapter = JsonDatabaseAdapter()
    monkeypatch.setattr("app.core.db_switch.db", adapter)
    monkeypatch.setattr("app.services.product_service.db", adapter)
    monkeypatch.setattr("app.services.order_service.db", adapter)
    monkeypatch.setattr("app.api.coupons.db", adapter)

    return adapter, db_dir


# ==============================================================================
# GROUP 1: Token Generation, Claims & Cryptographic Verification
# ==============================================================================

def test_issue_fbt_offer_claims():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    assert offer["primary_product_id"] == 1
    assert len(offer["suggested_product_ids"]) == 2
    assert offer["min_distinct_count"] == 2
    assert offer["discount_pct"] == 10.0
    assert len(offer["offer_id"]) >= 16

    decoded = jwt.decode(
        offer["token"],
        get_fbt_secret(),
        algorithms=["HS256"],
        audience=FBT_AUDIENCE,
        issuer=FBT_ISSUER,
    )
    assert decoded["iss"] == FBT_ISSUER
    assert decoded["aud"] == FBT_AUDIENCE
    assert decoded["typ"] == FBT_TOKEN_TYPE
    assert decoded["v"] == 1
    assert decoded["offer_id"] == offer["offer_id"]
    assert decoded["primary_product_id"] == 1
    assert set(decoded["qualifying_product_ids"]) == {1, offer["suggested_product_ids"][0], offer["suggested_product_ids"][1]}
    assert decoded["exp"] > decoded["iat"]


def test_issue_fbt_offer_primary_not_found():
    with pytest.raises(ValueError, match="not found in catalog"):
        issue_fbt_offer(999, SAMPLE_CATALOG)


def test_issue_fbt_offer_insufficient_products():
    single_catalog = [{"id": 1, "name": "Solo Product", "price": 500}]
    with pytest.raises(ValueError, match="Insufficient products"):
        issue_fbt_offer(1, single_catalog)


def test_verify_fbt_token_valid():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    claims = verify_fbt_token(offer["token"])
    assert claims["offer_id"] == offer["offer_id"]
    assert claims["primary_product_id"] == 1


def test_verify_fbt_token_expired():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG, expiration_hours=-1)
    with pytest.raises(ValueError, match="expired"):
        verify_fbt_token(offer["token"])


def test_verify_fbt_token_tampered_signature():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    parts = offer["token"].split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.tamperedSignature123"
    with pytest.raises(ValueError, match="Invalid FBT offer token"):
        verify_fbt_token(tampered_token)


def test_verify_fbt_token_wrong_secret():
    payload = {
        "iss": FBT_ISSUER,
        "aud": FBT_AUDIENCE,
        "typ": FBT_TOKEN_TYPE,
        "v": 1,
        "offer_id": "test_offer_123456789",
        "primary_product_id": 1,
        "qualifying_product_ids": [1, 2, 3],
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    wrong_token = jwt.encode(payload, "completely-wrong-secret", algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid FBT offer token"):
        verify_fbt_token(wrong_token)


def test_verify_fbt_token_tampered_payload():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    parts = offer["token"].split(".")
    # Modify header or payload base64 part
    tampered = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"
    with pytest.raises(ValueError, match="Invalid FBT offer token"):
        verify_fbt_token(tampered)


def test_verify_fbt_token_invalid_type():
    payload = {
        "iss": FBT_ISSUER,
        "aud": FBT_AUDIENCE,
        "typ": "session_auth",
        "v": 1,
        "offer_id": "test_offer_123456789",
        "qualifying_product_ids": [1, 2],
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, get_fbt_secret(), algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid token type"):
        verify_fbt_token(token)


def test_verify_fbt_token_missing_offer_id():
    payload = {
        "iss": FBT_ISSUER,
        "aud": FBT_AUDIENCE,
        "typ": FBT_TOKEN_TYPE,
        "v": 1,
        "qualifying_product_ids": [1, 2],
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, get_fbt_secret(), algorithm="HS256")
    with pytest.raises(ValueError, match="missing or has invalid offer_id"):
        verify_fbt_token(token)


def test_verify_fbt_token_missing_qualifying_ids():
    payload = {
        "iss": FBT_ISSUER,
        "aud": FBT_AUDIENCE,
        "typ": FBT_TOKEN_TYPE,
        "v": 1,
        "offer_id": "test_offer_123456789",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, get_fbt_secret(), algorithm="HS256")
    with pytest.raises(ValueError, match="qualifying_product_ids"):
        verify_fbt_token(token)


def test_verify_fbt_token_non_string():
    with pytest.raises(ValueError, match="must be a non-empty string"):
        verify_fbt_token("")
    with pytest.raises(ValueError, match="must be a non-empty string"):
        verify_fbt_token(None)


# ==============================================================================
# GROUP 2: Bundle Qualification Rules & Subtotal Calculations
# ==============================================================================

def test_validate_qualification_exact_2_distinct_items():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    items = [
        {"id": 1, "quantity": 1},
        {"id": offer["suggested_product_ids"][0], "quantity": 1},
    ]
    res = validate_fbt_bundle_qualification(offer["token"], items, prod_map)
    assert res["is_qualified"] is True
    assert len(res["qualifying_product_ids"]) == 2
    expected_subtotal = prod_map[1]["price"] + prod_map[offer["suggested_product_ids"][0]]["price"]
    assert res["qualifying_subtotal"] == expected_subtotal
    assert res["discount_amount"] == round(expected_subtotal * 0.10, 2)


def test_validate_qualification_all_3_bundle_items():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    items = [
        {"id": 1, "quantity": 1},
        {"id": offer["suggested_product_ids"][0], "quantity": 1},
        {"id": offer["suggested_product_ids"][1], "quantity": 1},
    ]
    res = validate_fbt_bundle_qualification(offer["token"], items, prod_map)
    assert res["is_qualified"] is True
    assert len(res["qualifying_product_ids"]) == 3


def test_validate_qualification_fails_single_distinct_item():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    items = [{"id": 1, "quantity": 1}]
    with pytest.raises(ValueError, match="requires at least 2 distinct products"):
        validate_fbt_bundle_qualification(offer["token"], items, prod_map)


def test_validate_qualification_fails_duplicate_quantities_single_item():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    items = [{"id": 1, "quantity": 3}]
    with pytest.raises(ValueError, match="requires at least 2 distinct products"):
        validate_fbt_bundle_qualification(offer["token"], items, prod_map)


def test_validate_qualification_fails_duplicate_sizes_single_item():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    items = [
        {"id": 1, "size": "M", "quantity": 1},
        {"id": 1, "size": "L", "quantity": 1},
    ]
    with pytest.raises(ValueError, match="requires at least 2 distinct products"):
        validate_fbt_bundle_qualification(offer["token"], items, prod_map)


def test_validate_qualification_fails_zero_qualifying_items():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    # Product 4 is not in the offer (which used 1, 2, 3)
    items = [{"id": 4, "quantity": 2}]
    with pytest.raises(ValueError, match="requires at least 2 distinct products"):
        validate_fbt_bundle_qualification(offer["token"], items, prod_map)


def test_validate_qualification_empty_cart_fails():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    with pytest.raises(ValueError, match="Cart items must be a non-empty list"):
        validate_fbt_bundle_qualification(offer["token"], [], prod_map)


def test_validate_qualification_unrelated_items_excluded_from_discount():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    # Offer has 1, 2, 3. Product 4 is unrelated.
    items = [
        {"id": 1, "quantity": 1},
        {"id": 2, "quantity": 1},
        {"id": 4, "quantity": 1},  # Unrelated ₹1099 item
    ]
    res = validate_fbt_bundle_qualification(offer["token"], items, prod_map)
    assert res["is_qualified"] is True
    # Qualifying items: 1 (799) + 2 (699) = 1498
    assert res["qualifying_subtotal"] == 1498.0
    # Discount must be 10% of 1498 = 149.80, NOT 10% of (1498 + 1099 = 2597)
    assert res["discount_amount"] == 149.80


def test_validate_qualification_authoritative_pricing_tamper():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    # Attacker tries to pass bogus price
    items = [
        {"id": 1, "price": 10.0, "quantity": 1},
        {"id": 2, "price": 10.0, "quantity": 1},
    ]
    res = validate_fbt_bundle_qualification(offer["token"], items, prod_map)
    # Must use authoritative catalog prices 799 and 699
    assert res["qualifying_subtotal"] == 1498.0
    assert res["discount_amount"] == 149.80


def test_validate_qualification_multiple_quantities_qualifying():
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}
    items = [
        {"id": 1, "quantity": 2},  # 2 * 799 = 1598
        {"id": 2, "quantity": 1},  # 1 * 699 = 699
    ]
    res = validate_fbt_bundle_qualification(offer["token"], items, prod_map)
    assert res["qualifying_subtotal"] == 2297.0
    assert res["discount_amount"] == 229.70


# ==============================================================================
# GROUP 3: Product API Endpoint (/api/v1/products/{id}/fbt-offer)
# ==============================================================================

def test_get_product_fbt_offer_endpoint(mock_db_dir):
    response = get_product_fbt_offer(1)
    assert response["success"] is True
    offer = response["offer"]
    assert offer["primary_product_id"] == 1
    assert "token" in offer
    claims = verify_fbt_token(offer["token"])
    assert claims["primary_product_id"] == 1


def test_get_product_fbt_offer_not_found(mock_db_dir):
    with pytest.raises(HTTPException) as exc:
        get_product_fbt_offer(9999)
    assert exc.value.status_code == 404


# ==============================================================================
# GROUP 4: Coupon Apply Endpoint (/api/v1/coupons/apply)
# ==============================================================================

def test_apply_bundle10_missing_fbt_token(mock_db_dir):
    payload = ApplyCouponPayload(code="BUNDLE10", subtotal=1500.0)
    with pytest.raises(HTTPException) as exc:
        apply_coupon(payload)
    assert exc.value.status_code == 400
    assert "requires a valid FBT offer token" in exc.value.detail


def test_apply_bundle10_missing_items(mock_db_dir):
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    payload = ApplyCouponPayload(code="BUNDLE10", subtotal=1500.0, fbt_token=offer["token"])
    with pytest.raises(HTTPException) as exc:
        apply_coupon(payload)
    assert exc.value.status_code == 400
    assert "requires cart items" in exc.value.detail


def test_apply_bundle10_unqualified_items(mock_db_dir):
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    payload = ApplyCouponPayload(
        code="BUNDLE10",
        subtotal=799.0,
        fbt_token=offer["token"],
        items=[{"id": 1, "quantity": 1}],
    )
    with pytest.raises(HTTPException) as exc:
        apply_coupon(payload)
    assert exc.value.status_code == 400
    assert "requires at least 2 distinct products" in exc.value.detail


def test_apply_bundle10_success_does_not_consume_offer(mock_db_dir):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    items = [{"id": 1, "quantity": 1}, {"id": 2, "quantity": 1}]
    payload = ApplyCouponPayload(
        code="BUNDLE10",
        subtotal=1498.0,
        fbt_token=offer["token"],
        items=items,
    )
    res = apply_coupon(payload)
    assert res["success"] is True
    assert res["code"] == "BUNDLE10"
    assert res["discount_amount"] == 149.80
    assert res["final_total"] == 1348.20
    assert res["offer_id"] == offer["offer_id"]

    # Verify coupon usage_count was NOT incremented and offer was NOT consumed
    coupon_in_db = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert coupon_in_db["usage_count"] == 0
    assert offer["offer_id"] not in coupon_in_db.get("redeemed_offers", {})


def test_apply_generic_coupon_backward_compat(mock_db_dir):
    payload = ApplyCouponPayload(code="TRIDENT10", subtotal=1000.0)
    res = apply_coupon(payload)
    assert res["success"] is True
    assert res["code"] == "TRIDENT10"
    assert res["discount_amount"] == 100.0
    assert res["final_total"] == 900.0


# ==============================================================================
# GROUP 5: Order Creation & Replay Protection (COD & Direct Flow)
# ==============================================================================

def test_order_creation_bundle10_success(mock_db_dir):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    items = [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}]

    payload = MockPayload(
        items=items,
        subtotal=1498.0,
        customer={"name": "Alice Tester", "email": "alice@example.com", "phone": "9876543210"},
        shipping={"address": "123 High Street", "city": "Bengaluru", "pincode": "560001"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token=offer["token"],
    )

    res = process_create_order(payload, DummyRequest())
    assert res["success"] is True
    assert res["order_id"].startswith("TRD-")

    # Verify durable persistence of offer_id and coupon details
    saved_order = adapter.read("orders", {"order_id": res["order_id"]})[0]
    assert saved_order["coupon_code"] == "BUNDLE10"
    assert saved_order["discount_amount"] == 149.80
    assert saved_order["total"] == 1348.20
    assert saved_order["fbt_offer_id"] == offer["offer_id"]

    # Verify coupon usage and redeemed_offers record
    coupon_in_db = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert coupon_in_db["usage_count"] == 1
    assert offer["offer_id"] in coupon_in_db["redeemed_offers"]


def test_order_creation_bundle10_missing_token_rejected(mock_db_dir):
    items = [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}]
    payload = MockPayload(
        items=items,
        subtotal=1498.0,
        customer={"name": "Alice Tester", "email": "alice@example.com", "phone": "9876543210"},
        shipping={"address": "123 High Street", "city": "Bengaluru", "pincode": "560001"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token="",
    )
    with pytest.raises(HTTPException) as exc:
        process_create_order(payload, DummyRequest())
    assert exc.value.status_code == 400
    assert "requires a valid FBT offer token" in exc.value.detail


def test_order_creation_bundle10_unqualified_rejected(mock_db_dir):
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    # Only single product
    items = [{"id": 1, "qty": 2}]
    payload = MockPayload(
        items=items,
        subtotal=1598.0,
        customer={"name": "Alice Tester", "email": "alice@example.com", "phone": "9876543210"},
        shipping={"address": "123 High Street", "city": "Bengaluru", "pincode": "560001"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token=offer["token"],
    )
    with pytest.raises(HTTPException) as exc:
        process_create_order(payload, DummyRequest())
    assert exc.value.status_code == 400
    assert "requires at least 2 distinct products" in exc.value.detail


def test_order_creation_bundle10_replay_rejected(mock_db_dir):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    items = [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}]

    # Order 1 consumes the offer
    payload1 = MockPayload(
        items=items,
        subtotal=1498.0,
        customer={"name": "Alice Tester", "email": "alice@example.com", "phone": "9876543210"},
        shipping={"address": "123 High Street", "city": "Bengaluru", "pincode": "560001"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token=offer["token"],
    )
    order1 = process_create_order(payload1, DummyRequest())
    assert order1["order_id"].startswith("TRD-")

    # Order 2 attempts to use the SAME offer
    payload2 = MockPayload(
        items=items,
        subtotal=1498.0,
        customer={"name": "Bob Replayer", "email": "bob@example.com", "phone": "9876543211"},
        shipping={"address": "456 Market Road", "city": "Mumbai", "pincode": "400001"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token=offer["token"],
    )
    with pytest.raises(HTTPException) as exc:
        process_create_order(payload2, DummyRequest())
    assert exc.value.status_code == 400
    assert "Coupon conflict" in exc.value.detail or "already been redeemed" in exc.value.detail

    # Coupon usage count must remain 1
    coupon_in_db = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert coupon_in_db["usage_count"] == 1


def test_order_creation_bundle10_idempotent_retry(mock_db_dir):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    today_iso = datetime.now(timezone.utc).date().isoformat()
    order_id = "TRD-IDEMPOTENT-001"

    # Direct adapter call simulating first redemption
    res1 = adapter.redeem_coupon("BUNDLE10", today_iso, order_id=order_id, offer_id=offer["offer_id"])
    assert res1 is not None
    assert res1["already_redeemed"] is False

    # Idempotent retry for the EXACT same order_id and offer_id
    res2 = adapter.redeem_coupon("BUNDLE10", today_iso, order_id=order_id, offer_id=offer["offer_id"])
    assert res2 is not None
    assert res2["already_redeemed"] is True

    # Usage count remains 1
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 1


# ==============================================================================
# GROUP 6: Online Payment Flow & Compensation
# ==============================================================================

def test_create_pending_payment_order_bundle10(mock_db_dir):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    order_data = {
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Charlie", "email": "charlie@example.com", "phone": "9876543210"},
        "shipping": {"address": "789 Park Street", "city": "Kolkata"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
    }
    pending = create_pending_payment_order(order_data)
    assert pending["order_id"].startswith("TRD-")
    assert pending["order"]["discount_amount"] == 149.80
    assert pending["order"]["total"] == 1348.20
    assert pending["amount_paise"] == 134820
    assert pending["order"]["fbt_offer_id"] == offer["offer_id"]

    # Preview does not consume coupon
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 0
    assert offer["offer_id"] not in c.get("redeemed_offers", {})


def test_create_payment_order_record_bundle10_flow(mock_db_dir):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    order_data = {
        "order_id": "TRD-PAYMENT-001",
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Charlie", "email": "charlie@example.com", "phone": "9876543210"},
        "shipping": {"address": "789 Park Street", "city": "Kolkata"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
        "payment_status": "paid",
        "razorpay_payment_id": "pay_test123456",
    }
    record = create_payment_order_record(order_data)
    assert record["order_id"] == "TRD-PAYMENT-001"
    assert record["discount_amount"] == 149.80
    assert record["fbt_offer_id"] == offer["offer_id"]

    # Offer is now consumed
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 1
    assert offer["offer_id"] in c["redeemed_offers"]

    # Second order attempting same offer is rejected with CouponConflictError or HTTPException
    order_data_2 = copy.deepcopy(order_data)
    order_data_2["order_id"] = "TRD-PAYMENT-002"
    order_data_2["razorpay_payment_id"] = "pay_test999999"
    with pytest.raises((CouponConflictError, HTTPException)) as exc:
        create_payment_order_record(order_data_2)


def test_order_insert_failure_releases_coupon_and_offer(mock_db_dir, monkeypatch):
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    items = [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}]

    # Force db.insert to fail
    def failing_insert(table, data):
        if table == "orders":
            raise RuntimeError("Simulated DB disk failure")
        return adapter.insert(table, data)

    monkeypatch.setattr(adapter, "insert", failing_insert)

    payload = MockPayload(
        items=items,
        subtotal=1498.0,
        customer={"name": "Alice Tester", "email": "alice@example.com", "phone": "9876543210"},
        shipping={"address": "123 High Street", "city": "Bengaluru", "pincode": "560001"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token=offer["token"],
    )

    with pytest.raises(HTTPException) as exc:
        process_create_order(payload, DummyRequest())
    assert exc.value.status_code == 500

    # Coupon must be released and offer_id cleared
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 0
    assert offer["offer_id"] not in c.get("redeemed_offers", {})


# ==============================================================================
# GROUP 7: SQL Adapter & Alembic Migration
# ==============================================================================

def test_sql_adapter_offer_id_redemption_and_replay(tmp_path):
    """Verifies PostgresDatabaseAdapter logic on a SQLite in-memory/temp database."""
    engine = create_engine(f"sqlite:///{tmp_path}/test_db.sqlite")
    metadata.create_all(engine)

    # Seed coupons
    with engine.begin() as conn:
        conn.execute(
            insert(coupons).values(
                code="BUNDLE10",
                discount_pct=10.0,
                expires_at="2027-12-31",
                usage_limit=5000,
                usage_count=0,
                is_active=True,
            )
        )

    dsn = f"sqlite:///{tmp_path}/test_db.sqlite"
    adapter = PostgresDatabaseAdapter(dsn)
    today_iso = "2026-11-09"
    offer_id = "test_offer_sql_unique_123"

    # 1. First redemption succeeds
    r1 = adapter.redeem_coupon("BUNDLE10", today_iso, order_id="TRD-SQL-001", offer_id=offer_id)
    assert r1 is not None
    assert r1["already_redeemed"] is False

    # 2. Idempotent retry for same order succeeds
    r2 = adapter.redeem_coupon("BUNDLE10", today_iso, order_id="TRD-SQL-001", offer_id=offer_id)
    assert r2 is not None
    assert r2["already_redeemed"] is True

    # 3. Different order with SAME offer_id fails with CouponConflictError
    with pytest.raises(CouponConflictError, match="already been redeemed"):
        adapter.redeem_coupon("BUNDLE10", today_iso, order_id="TRD-SQL-002", offer_id=offer_id)


def test_alembic_migration_0013_upgrade_downgrade(tmp_path, monkeypatch):
    """Verifies that migration 20261109_0013 adds offer_id only (not status) and removes it cleanly."""
    import importlib.util
    migration_path = BACKEND_DIR / "alembic" / "versions" / "20261109_0013_add_fbt_offer_id_to_coupon_redemptions.py"
    assert migration_path.exists()

    spec = importlib.util.spec_from_file_location("migration_0013", str(migration_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    engine = create_engine(f"sqlite:///{tmp_path}/migration_test_0013.sqlite")
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Column, Integer, String, Table, MetaData

    test_meta = MetaData()
    test_coupons = Table("coupons", test_meta, Column("code", String, primary_key=True))
    test_redemptions = Table(
        "coupon_redemptions",
        test_meta,
        Column("id", Integer, primary_key=True),
        Column("order_id", String, unique=True),
        Column("coupon_code", String),
    )
    test_meta.create_all(engine)

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)

        import alembic.op as alembic_op
        monkeypatch.setattr(alembic_op, "get_bind", lambda: conn)
        monkeypatch.setattr(alembic_op, "batch_alter_table", op.batch_alter_table)

        mod.upgrade()
        conn.commit()

        import sqlalchemy as sa
        insp = sa.inspect(conn)
        cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}
        assert "offer_id" in cols
        assert "status" not in cols  # 0013 must NOT contain status column!

        mod.downgrade()
        conn.commit()

        insp2 = sa.inspect(conn)
        cols_after = {c["name"] for c in insp2.get_columns("coupon_redemptions")}
        assert "offer_id" not in cols_after


def test_alembic_migration_0014_upgrade_downgrade(tmp_path, monkeypatch):
    """Verifies that migration 20261109_0014 adds status column and index cleanly, and rolls back safely."""
    import importlib.util
    migration_path = BACKEND_DIR / "alembic" / "versions" / "20261109_0014_add_status_to_coupon_redemptions.py"
    assert migration_path.exists()

    spec = importlib.util.spec_from_file_location("migration_0014", str(migration_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    engine = create_engine(f"sqlite:///{tmp_path}/migration_test_0014.sqlite")
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Column, Integer, String, Table, MetaData

    # Pre-0014 schema (has offer_id)
    test_meta = MetaData()
    test_coupons = Table("coupons", test_meta, Column("code", String, primary_key=True))
    test_redemptions = Table(
        "coupon_redemptions",
        test_meta,
        Column("id", Integer, primary_key=True),
        Column("order_id", String, unique=True),
        Column("coupon_code", String),
        Column("offer_id", String, unique=True),
    )
    test_meta.create_all(engine)

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)

        import alembic.op as alembic_op
        monkeypatch.setattr(alembic_op, "get_bind", lambda: conn)
        monkeypatch.setattr(alembic_op, "batch_alter_table", op.batch_alter_table)

        mod.upgrade()
        conn.commit()

        import sqlalchemy as sa
        insp = sa.inspect(conn)
        cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}
        indexes = {ix["name"] for ix in insp.get_indexes("coupon_redemptions")}
        assert "status" in cols
        assert "ix_coupon_redemptions_status" in indexes

        mod.downgrade()
        conn.commit()

        insp2 = sa.inspect(conn)
        cols_after = {c["name"] for c in insp2.get_columns("coupon_redemptions")}
        assert "status" not in cols_after
        assert "offer_id" in cols_after  # offer_id preserved!


# ==============================================================================
# GROUP 8: Gate 2O.3.6 Online Reservation, Stock Filtering & Lifecycle Parity
# ==============================================================================

def test_issue_fbt_offer_filters_out_of_stock_products():
    """Verifies that suggested bundle products strictly exclude out-of-stock items."""
    catalog_with_oos = [
        {"id": 1, "name": "Primary Tee", "price": 500.0, "stock": 10, "category": "tshirt"},
        {"id": 2, "name": "OOS Product A", "price": 300.0, "stock": 0, "category": "tshirt"},
        {"id": 3, "name": "In Stock Product B", "price": 400.0, "stock": 5, "category": "shirt"},
        {"id": 4, "name": "OOS Product C", "price": 600.0, "stock": 0, "category": "pants"},
        {"id": 5, "name": "In Stock Product D", "price": 700.0, "stock": 12, "category": "jacket"},
    ]
    offer = issue_fbt_offer(1, catalog_with_oos)
    # Suggestions must not include product 2 or 4
    for pid in offer["suggested_product_ids"]:
        assert pid in [3, 5]
        assert pid not in [2, 4]


def test_issue_fbt_offer_insufficient_stock_raises_error():
    """Verifies error when there are fewer than 1 in-stock suggestion candidates."""
    all_oos = [
        {"id": 1, "name": "Primary Tee", "price": 500.0, "stock": 10, "category": "tshirt"},
        {"id": 2, "name": "OOS 1", "price": 300.0, "stock": 0, "category": "tshirt"},
        {"id": 3, "name": "OOS 2", "price": 400.0, "stock": 0, "category": "shirt"},
    ]
    with pytest.raises(ValueError, match="Insufficient products"):
        issue_fbt_offer(1, all_oos)


def test_validate_qualification_rejects_malformed_items():
    """Verifies that validate_fbt_bundle_qualification rejects malformed cart items."""
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    token = offer["token"]
    prod_map = {p["id"]: p for p in SAMPLE_CATALOG}

    # 1. Non-dict item
    with pytest.raises(ValueError, match="must be a dictionary"):
        validate_fbt_bundle_qualification(token, ["not_a_dict"], prod_map)

    # 2. Missing product ID
    with pytest.raises(ValueError, match="missing product id"):
        validate_fbt_bundle_qualification(token, [{"qty": 1}], prod_map)

    # 3. Invalid product ID format
    with pytest.raises(ValueError, match="invalid product id"):
        validate_fbt_bundle_qualification(token, [{"id": "not_an_int", "qty": 1}], prod_map)

    # 4. Invalid quantity format
    with pytest.raises(ValueError, match="invalid quantity"):
        validate_fbt_bundle_qualification(token, [{"id": 1, "quantity": "invalid"}], prod_map)


def test_pending_payment_order_reserves_offer_and_locks_concurrent_orders(mock_db_dir):
    """Verifies that pending online payment reserves offer and blocks other orders."""
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    order_data_1 = {
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Alice Online", "email": "alice@example.com", "phone": "9876543210"},
        "shipping": {"address": "101 Cyber City", "city": "Gurugram"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
    }
    pending_1 = create_pending_payment_order(order_data_1)
    assert pending_1["order"]["coupon_status"] == "reserved"
    assert pending_1["order"]["fbt_offer_id"] == offer["offer_id"]

    # Verify usage_count is NOT incremented during reservation
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 0
    assert offer["offer_id"] in c.get("reserved_offers", {})
    assert c["reserved_offers"][offer["offer_id"]]["order_id"] == pending_1["order_id"]

    # Concurrent order 2 attempting to create pending order with same token is rejected
    order_data_2 = copy.deepcopy(order_data_1)
    order_data_2["customer"]["email"] = "bob@example.com"
    with pytest.raises(HTTPException) as exc2:
        create_pending_payment_order(order_data_2)
    assert exc2.value.status_code == 400
    assert "reservation conflict" in exc2.value.detail.lower()

    # Concurrent order 3 attempting direct COD with same token is rejected
    payload_3 = MockPayload(
        items=[{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        subtotal=1498.0,
        customer={"name": "Charlie COD", "email": "charlie@example.com", "phone": "9876543210"},
        shipping={"address": "102 Market St", "city": "Delhi"},
        payment_method="cod",
        coupon_code="BUNDLE10",
        fbt_token=offer["token"],
    )
    with pytest.raises(HTTPException) as exc3:
        process_create_order(payload_3, DummyRequest())
    assert exc3.value.status_code == 400
    assert "conflict" in exc3.value.detail.lower()


def test_finalize_paid_order_converts_reservation_to_redemption(mock_db_dir):
    """Verifies finalize_paid_order passes offer_id and finalizes reservation without double count."""
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    order_data = {
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Dave Capture", "email": "dave@example.com", "phone": "9876543210"},
        "shipping": {"address": "202 Tech Park", "city": "Hyderabad"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
        "test_mode": True,
    }
    pending = create_pending_payment_order(order_data)
    assert pending["order"]["coupon_status"] == "reserved"

    # Finalize payment
    finalized = finalize_paid_order(
        order=pending["order"],
        razorpay_payment_id="pay_capture_test_123",
        test_mode=True,
    )
    assert finalized["payment_status"] == "paid"
    updated_order = adapter.read("orders", {"order_id": pending["order_id"]})[0]
    assert updated_order["coupon_status"] == "redeemed"

    # DB coupon checks: usage_count incremented to 1, offer moved from reserved to redeemed
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 1
    assert offer["offer_id"] not in c.get("reserved_offers", {})
    assert offer["offer_id"] in c.get("redeemed_offers", {})
    assert c["redeemed_offers"][offer["offer_id"]]["order_id"] == pending["order_id"]

    # Idempotent second call with same payment ID does NOT increment usage_count
    finalized_retry = finalize_paid_order(
        order=updated_order,
        razorpay_payment_id="pay_capture_test_123",
        test_mode=True,
    )
    assert finalized_retry["payment_status"] == "paid"
    c_retry = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c_retry["usage_count"] == 1


def test_payment_failed_webhook_releases_reservation(mock_db_dir, monkeypatch):
    """Verifies payment.failed webhook releases reservation so another order can claim offer."""
    import json
    import hmac
    import hashlib
    import app.services.payment_service as ps_module

    monkeypatch.setattr(ps_module, "RAZORPAY_WEBHOOK_SECRET", "test_webhook_sec")
    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    order_data = {
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Eve Gateway", "email": "eve@example.com", "phone": "9876543210"},
        "shipping": {"address": "303 Marine Lines", "city": "Mumbai"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
        "test_mode": True,
    }
    pending = create_pending_payment_order(order_data)
    rzp_order_id = pending["razorpay_order_id"]

    # Simulate webhook payment.failed
    payload = {
        "id": "evt_fail_999",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_fail_001",
                    "order_id": rzp_order_id,
                    "status": "failed",
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(b"test_webhook_sec", raw_body, hashlib.sha256).hexdigest()

    resp = process_webhook(raw_body, sig)
    assert resp["success"] is True

    # Check order status is failed and coupon_status is released
    updated_order = adapter.read("orders", {"order_id": pending["order_id"]})[0]
    assert updated_order["payment_status"] == "failed"
    assert updated_order["coupon_status"] == "released"

    # Offer is no longer reserved in coupon
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert offer["offer_id"] not in c.get("reserved_offers", {})
    assert c["usage_count"] == 0

    # New order can now reserve this offer cleanly
    order_data_new = {
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Frank New", "email": "frank@example.com", "phone": "9876543210"},
        "shipping": {"address": "404 North Ave", "city": "Chennai"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
    }
    pending_new = create_pending_payment_order(order_data_new)
    assert pending_new["order"]["coupon_status"] == "reserved"


def test_user_cancellation_releases_reservation(mock_db_dir, monkeypatch):
    """Verifies user cancelling pending order releases reservation."""
    import app.services.order_service as os_module
    monkeypatch.setattr(os_module, "get_session_user", lambda req: {"id": 42, "email": "grace@example.com"})

    adapter, _ = mock_db_dir
    offer = issue_fbt_offer(1, SAMPLE_CATALOG)
    order_data = {
        "items": [{"id": 1, "qty": 1}, {"id": 2, "qty": 1}],
        "customer": {"name": "Grace User", "email": "grace@example.com", "phone": "9876543210", "user_id": 42},
        "shipping": {"address": "505 South Ext", "city": "Delhi"},
        "coupon_code": "BUNDLE10",
        "fbt_token": offer["token"],
    }
    pending = create_pending_payment_order(order_data)
    req = DummyRequest(session={"user": {"id": 42, "email": "grace@example.com"}})

    res = cancel_order_logic(pending["order_id"], req)
    assert res["success"] is True

    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert offer["offer_id"] not in c.get("reserved_offers", {})

    # Another order can now claim the offer
    pending_retry = create_pending_payment_order(order_data)
    assert pending_retry["order"]["coupon_status"] == "reserved"


def test_sql_adapter_reservation_lifecycle_parity(tmp_path):
    """Verifies PostgresDatabaseAdapter reservation, replay protection, and redemption transition."""
    engine = create_engine(f"sqlite:///{tmp_path}/test_sql_res.sqlite")
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            insert(coupons).values(
                code="BUNDLE10",
                discount_pct=10.0,
                expires_at="2027-12-31",
                usage_limit=10,
                usage_count=0,
                is_active=True,
            )
        )

    dsn = f"sqlite:///{tmp_path}/test_sql_res.sqlite"
    adapter = PostgresDatabaseAdapter(dsn)
    today_iso = "2026-11-09"
    offer_id = "test_sql_offer_lifecycle_999"

    # 1. Reserve offer for order TRD-RES-1
    res1 = adapter.reserve_coupon_offer("BUNDLE10", today_iso, order_id="TRD-RES-1", offer_id=offer_id)
    assert res1 is not None
    assert res1["already_reserved"] is False

    # Check DB state: status == 'reserved', coupon usage_count == 0
    with engine.connect() as conn:
        red_row = conn.execute(select(coupon_redemptions).where(coupon_redemptions.c.offer_id == offer_id)).first()
        assert red_row.status == "reserved"
        assert red_row.order_id == "TRD-RES-1"
        c_row = conn.execute(select(coupons).where(coupons.c.code == "BUNDLE10")).first()
        assert c_row.usage_count == 0

    # 2. Idempotent reservation for same order succeeds
    res_idem = adapter.reserve_coupon_offer("BUNDLE10", today_iso, order_id="TRD-RES-1", offer_id=offer_id)
    assert res_idem is not None
    assert res_idem["already_reserved"] is True

    # 3. Different order attempting to reserve same offer raises CouponConflictError
    with pytest.raises(CouponConflictError, match="already been reserved"):
        adapter.reserve_coupon_offer("BUNDLE10", today_iso, order_id="TRD-RES-2", offer_id=offer_id)

    # 4. Finalize redemption for TRD-RES-1
    red_final = adapter.redeem_coupon("BUNDLE10", today_iso, order_id="TRD-RES-1", offer_id=offer_id)
    assert red_final is not None
    assert red_final["already_redeemed"] is False

    # Check DB state: status == 'redeemed', coupon usage_count == 1
    with engine.connect() as conn:
        red_row2 = conn.execute(select(coupon_redemptions).where(coupon_redemptions.c.offer_id == offer_id)).first()
        assert red_row2.status == "redeemed"
        c_row2 = conn.execute(select(coupons).where(coupons.c.code == "BUNDLE10")).first()
        assert c_row2.usage_count == 1

    # 5. Idempotent redeem call for TRD-RES-1 returns already_redeemed=True, usage_count still 1
    red_idem = adapter.redeem_coupon("BUNDLE10", today_iso, order_id="TRD-RES-1", offer_id=offer_id)
    assert red_idem is not None
    assert red_idem["already_redeemed"] is True
    with engine.connect() as conn:
        c_row3 = conn.execute(select(coupons).where(coupons.c.code == "BUNDLE10")).first()
        assert c_row3.usage_count == 1

    # 6. Release coupon offer testing for a separate reservation
    offer_id_2 = "test_sql_offer_rel_888"
    adapter.reserve_coupon_offer("BUNDLE10", today_iso, order_id="TRD-RES-REL", offer_id=offer_id_2)
    rel_ok = adapter.release_coupon_offer("BUNDLE10", order_id="TRD-RES-REL", offer_id=offer_id_2)
    assert rel_ok is True

    # Verify reservation row is deleted and usage_count is unchanged (0 for offer 2)
    with engine.connect() as conn:
        deleted_row = conn.execute(select(coupon_redemptions).where(coupon_redemptions.c.offer_id == offer_id_2)).first()
        assert deleted_row is None


def test_multiprocessing_two_os_processes_competing_for_same_fbt_offer(tmp_path):
    """Genuine multiprocessing test: Two separate OS processes (not threads)
    compete to reserve the exact same FBT offer token simultaneously.
    Adapter: JsonDatabaseAdapter (cross-process file locking via CrossProcessLock).
    Execution Model: multiprocessing.Process with synchronized event start.

    Invariants:
    1. Exactly one OS process succeeds in claiming the reservation.
    2. Exactly one OS process is rejected with CouponConflictError.
    3. Persisted database records the winner's order_id under reserved_offers.
    4. usage_count remains 0 (not incremented during reservation).
    """
    db_module.DB_DIR = tmp_path
    adapter = JsonDatabaseAdapter()
    adapter.insert("coupons", {
        "id": 1,
        "code": "BUNDLE10",
        "discount_pct": 10.0,
        "expires_at": "2027-12-31",
        "usage_limit": 500,
        "usage_count": 0,
        "is_active": True,
    })

    offer_id = "test_fbt_multiprocess_contention_token_999"
    today_iso = "2026-11-09"

    queue = multiprocessing.Queue()
    sync_event = multiprocessing.Event()

    p1 = multiprocessing.Process(
        target=_worker_reserve_fbt_offer,
        args=(str(tmp_path), "BUNDLE10", today_iso, "TRD-MP-PROC-1", offer_id, sync_event, queue)
    )
    p2 = multiprocessing.Process(
        target=_worker_reserve_fbt_offer,
        args=(str(tmp_path), "BUNDLE10", today_iso, "TRD-MP-PROC-2", offer_id, sync_event, queue)
    )

    p1.start()
    p2.start()

    # Unblock both processes simultaneously to induce maximum lock contention
    sync_event.set()

    p1.join(timeout=10)
    p2.join(timeout=10)

    # Ensure termination
    if p1.is_alive():
        p1.terminate()
    if p2.is_alive():
        p2.terminate()

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == 2, f"Expected 2 worker results, got {len(results)}: {results}"
    outcomes = [r[0] for r in results]
    assert "SUCCESS" in outcomes, f"One process must succeed: {results}"
    assert "CONFLICT" in outcomes, f"One process must receive conflict: {results}"

    winner_order_id = next(r[1] for r in results if r[0] == "SUCCESS")

    # Verify persisted DB state
    c = adapter.read("coupons", {"code": "BUNDLE10"})[0]
    assert c["usage_count"] == 0
    assert offer_id in c.get("reserved_offers", {})
    assert c["reserved_offers"][offer_id]["order_id"] == winner_order_id
