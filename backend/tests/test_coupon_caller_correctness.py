"""Focused tests for TridentWear Phase C.6.6D.3B: Coupon Caller Correctness Fixes.

Covers:
1. create_payment_order_record: Stable order ID exists before coupon redemption.
2. create_payment_order_record: Redemption receives the correct order_id.
3. create_payment_order_record: Invalid discount does not raise UnboundLocalError and cleanly cleans up.
4. create_payment_order_record: Order creation failure releases only the current order's redemption.
5. create_payment_order_record: Repeated attempts do not double-increment usage.
6. create_payment_order_record: A redemption conflict does not silently retry without order_id.
7. process_create_order: Coupon redemption uses db.redeem_coupon() with the persisted order ID.
8. process_create_order: Direct usage_count increment is removed.
9. process_create_order: Failed order creation cleans up only the current order's redemption.
10. process_create_order: Usage-limit failures and invalid coupons reject safely.
11. process_create_order: Non-coupon orders retain existing behavior without coupon interaction.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.services.order_service as os_mod
import app.db.database as db_mod
from app.db.database import JsonDatabaseAdapter, CouponConflictError


@pytest.fixture
def clean_json_db(tmp_path, monkeypatch):
    """Provides an isolated JsonDatabaseAdapter in tmp_path."""
    monkeypatch.setattr(db_mod, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()
    monkeypatch.setattr(os_mod, "db", adapter)
    import app.services.product_service as prod_service
    monkeypatch.setattr(prod_service, "db", adapter)
    import app.services.payment_service as ps_mod
    monkeypatch.setattr(ps_mod, "db", adapter)
    return adapter, tmp_path


# --- create_payment_order_record Tests ---

def test_create_payment_order_record_stable_order_id_before_redemption(clean_json_db):
    """Verify that a stable order_id is generated and passed to redeem_coupon."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "SAVE10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg", "stock": 10}]

    captured_order_ids = []
    orig_redeem = adapter.redeem_coupon

    def spy_redeem(code, today_iso, order_id=None):
        captured_order_ids.append(order_id)
        return orig_redeem(code, today_iso, order_id=order_id)

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"), \
         patch.object(adapter, "redeem_coupon", side_effect=spy_redeem):

        order = os_mod.create_payment_order_record({
            "items": [{"id": 1, "qty": 1, "size": "M"}],
            "coupon_code": "SAVE10"
        })

    assert len(captured_order_ids) == 1
    assert captured_order_ids[0] is not None
    assert captured_order_ids[0] == order["order_id"]
    assert order["coupon_status"] == "redeemed"

    # Verify coupon record in DB contains this exact order_id
    coupon = adapter.read("coupons", {"code": "SAVE10"})[0]
    assert coupon["usage_count"] == 1
    assert order["order_id"] in coupon["redeemed_orders"]


def test_create_payment_order_record_invalid_discount_no_unbound_local(clean_json_db):
    """Verify that an invalid discount percentage does not raise UnboundLocalError and cleans up."""
    adapter, _ = clean_json_db
    # Coupon with invalid discount (> 100%)
    adapter.insert("coupons", {
        "id": 1, "code": "BOGUS150", "discount_pct": 150.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg", "stock": 10}]

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"):
        order = os_mod.create_payment_order_record({
            "items": [{"id": 1, "qty": 1, "size": "M"}],
            "coupon_code": "BOGUS150"
        })

    # Total remains undiscounted, no UnboundLocalError
    assert order["discount_amount"] == 0.0
    assert order["total"] == 100.0
    assert order["coupon_status"] == "none"

    # Coupon usage was released and remains 0
    coupon = adapter.read("coupons", {"code": "BOGUS150"})[0]
    assert coupon["usage_count"] == 0
    assert order["order_id"] not in coupon.get("redeemed_orders", {})


def test_create_payment_order_record_insert_failure_releases_only_current_order(clean_json_db):
    """Verify that an order creation failure releases only this order's redemption and preserves prior orders."""
    adapter, _ = clean_json_db
    # Seed prior order's redemption
    adapter.insert("coupons", {
        "id": 1, "code": "LIMITED", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 10, "usage_count": 1, "is_active": True,
        "redeemed_orders": {"TRD-PRIOR": {"redeemed_at": "2026-10-28T00:00:00Z"}}
    })
    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg", "stock": 10}]

    def fail_insert(table, data):
        raise RuntimeError("Simulated DB disk failure")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"), \
         patch.object(adapter, "insert", side_effect=fail_insert):

        with pytest.raises(RuntimeError, match="Simulated DB disk failure"):
            os_mod.create_payment_order_record({
                "items": [{"id": 1, "qty": 1, "size": "M"}],
                "coupon_code": "LIMITED"
            })

    # Prior redemption must remain intact, usage_count must remain 1
    coupon = adapter.read("coupons", {"code": "LIMITED"})[0]
    assert coupon["usage_count"] == 1
    assert "TRD-PRIOR" in coupon["redeemed_orders"]


def test_create_payment_order_record_repeated_attempt_idempotency(clean_json_db):
    """Verify that repeated attempts for the same order_id do not double-increment usage."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "REPEAT10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 5, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg", "stock": 10}]

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"):
        order1 = os_mod.create_payment_order_record({
            "order_id": "TRD-STABLE-1",
            "items": [{"id": 1, "qty": 1, "size": "M"}],
            "coupon_code": "REPEAT10"
        })

    coupon = adapter.read("coupons", {"code": "REPEAT10"})[0]
    assert coupon["usage_count"] == 1

    # Simulate re-running with same order_id (e.g. retry before DB read check)
    today_iso = datetime.now(timezone.utc).date().isoformat()
    retry_res = adapter.redeem_coupon("REPEAT10", today_iso, order_id="TRD-STABLE-1")
    assert retry_res["already_redeemed"] is True
    assert retry_res["usage_count"] == 1

    coupon_after = adapter.read("coupons", {"code": "REPEAT10"})[0]
    assert coupon_after["usage_count"] == 1


def test_create_payment_order_record_conflict_does_not_retry_anonymously(clean_json_db):
    """Verify that if an order has redeemed a different coupon, it raises CouponConflictError and does not retry."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "COUPON_A", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 5, "usage_count": 1, "is_active": True,
        "redeemed_orders": {"TRD-CONFLICT-1": {"redeemed_at": "2026-10-28T00:00:00Z"}}
    })
    adapter.insert("coupons", {
        "id": 2, "code": "COUPON_B", "discount_pct": 20.0, "expires_at": "2029-12-31",
        "usage_limit": 5, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg", "stock": 10}]

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"):
        with pytest.raises(CouponConflictError) as exc:
            os_mod.create_payment_order_record({
                "order_id": "TRD-CONFLICT-1",
                "items": [{"id": 1, "qty": 1, "size": "M"}],
                "coupon_code": "COUPON_B"
            })
    assert "already redeemed coupon COUPON_A" in str(exc.value)

    # COUPON_B must not have been incremented
    coupon_b = adapter.read("coupons", {"code": "COUPON_B"})[0]
    assert coupon_b["usage_count"] == 0


# --- process_create_order Tests ---

class DummyRequest:
    session = {}
    headers = {}
    client = MagicMock(host="127.0.0.1")


class DummyPayload:
    def __init__(self, items, coupon_code="", customer=None, shipping=None, payment_method="cod"):
        self.items = items
        self.coupon_code = coupon_code
        self.customer = customer or {"name": "Test User", "email": "test@example.com", "phone": "9876543210"}
        self.shipping = shipping or {"address": "123 Main Street", "city": "Bengaluru", "pincode": "560001"}
        self.payment_method = payment_method
        self.test_mode = False


def test_process_create_order_uses_redeem_coupon_with_persisted_order_id(clean_json_db):
    """Verify process_create_order uses db.redeem_coupon and records the persisted order ID."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "COD10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Shirt", "price": 1000.0, "stock": 50, "image": "shirt.jpg"}]

    captured_order_ids = []
    orig_redeem = adapter.redeem_coupon

    def spy_redeem(code, today_iso, order_id=None):
        captured_order_ids.append(order_id)
        return orig_redeem(code, today_iso, order_id=order_id)

    payload = DummyPayload(items=[{"id": 1, "qty": 1, "size": "L"}], coupon_code="COD10")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"), \
         patch.object(adapter, "redeem_coupon", side_effect=spy_redeem), \
         patch.object(os_mod, "send_order_email"):

        res = os_mod.process_create_order(payload, DummyRequest())

    assert res["success"] is True
    persisted_order_id = res["order_id"]
    assert len(captured_order_ids) == 1
    assert captured_order_ids[0] == persisted_order_id

    # Check database state
    coupon = adapter.read("coupons", {"code": "COD10"})[0]
    assert coupon["usage_count"] == 1
    assert persisted_order_id in coupon["redeemed_orders"]

    order = adapter.read("orders", {"order_id": persisted_order_id})[0]
    assert order["discount_amount"] == 100.0
    assert order["total"] == 900.0
    assert order["coupon_status"] == "redeemed"


def test_process_create_order_direct_usage_count_increment_removed(clean_json_db):
    """Verify that process_create_order does not perform a direct db.update on coupons."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "DIRECT_CHECK", "discount_pct": 20.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Shirt", "price": 500.0, "stock": 50, "image": "shirt.jpg"}]

    update_tables = []
    orig_update = adapter.update

    def spy_update(table, filters, data):
        update_tables.append(table)
        return orig_update(table, filters, data)

    payload = DummyPayload(items=[{"id": 1, "qty": 1, "size": "M"}], coupon_code="DIRECT_CHECK")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"), \
         patch.object(adapter, "update", side_effect=spy_update), \
         patch.object(os_mod, "send_order_email"):

        res = os_mod.process_create_order(payload, DummyRequest())

    assert res["success"] is True
    # The 'coupons' table should NOT be updated via db.update directly; only via redeem_coupon
    assert "coupons" not in update_tables


def test_process_create_order_failure_releases_only_current_redemption(clean_json_db):
    """Verify that failure during process_create_order releases only its own coupon redemption."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "COMP_TEST", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 5, "usage_count": 1, "is_active": True,
        "redeemed_orders": {"TRD-OTHER": {"redeemed_at": "2026-10-28T00:00:00Z"}}
    })
    dummy_products = [{"id": 1, "name": "Shirt", "price": 500.0, "stock": 50, "image": "shirt.jpg"}]

    def fail_insert(table, data):
        raise RuntimeError("Order table write error")

    payload = DummyPayload(items=[{"id": 1, "qty": 1, "size": "M"}], coupon_code="COMP_TEST")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"), \
         patch.object(adapter, "insert", side_effect=fail_insert):
        with pytest.raises(HTTPException) as exc:
            os_mod.process_create_order(payload, DummyRequest())
        assert exc.value.status_code == 500

    # Coupon usage must remain 1, other order must remain
    coupon = adapter.read("coupons", {"code": "COMP_TEST"})[0]
    assert coupon["usage_count"] == 1
    assert "TRD-OTHER" in coupon["redeemed_orders"]


def test_process_create_order_usage_limit_rejection(clean_json_db):
    """Verify that a coupon at its usage limit is rejected before order creation."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "EXHAUSTED", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 1, "usage_count": 1, "is_active": True,
        "redeemed_orders": {"TRD-FIRST": {"redeemed_at": "2026-10-28T00:00:00Z"}}
    })
    dummy_products = [{"id": 1, "name": "Shirt", "price": 500.0, "stock": 50, "image": "shirt.jpg"}]

    payload = DummyPayload(items=[{"id": 1, "qty": 1, "size": "M"}], coupon_code="EXHAUSTED")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"):
        with pytest.raises(HTTPException) as exc:
            os_mod.process_create_order(payload, DummyRequest())
        assert exc.value.status_code == 400
        assert "usage limit reached" in exc.value.detail.lower()

    # No order should have been created
    orders = adapter.read("orders", {})
    assert len(orders) == 0


def test_process_create_order_non_coupon_order_untouched(clean_json_db):
    """Verify non-coupon orders execute without calling coupon methods."""
    adapter, _ = clean_json_db
    dummy_products = [{"id": 1, "name": "Pants", "price": 800.0, "stock": 20, "image": "pants.jpg"}]

    captured_redeems = []
    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock"), \
         patch.object(adapter, "redeem_coupon", side_effect=lambda *args, **kwargs: captured_redeems.append(1)), \
         patch.object(os_mod, "send_order_email"):

        payload = DummyPayload(items=[{"id": 1, "qty": 2, "size": "32"}], coupon_code="")
        res = os_mod.process_create_order(payload, DummyRequest())

    assert res["success"] is True
    assert len(captured_redeems) == 0

    order = adapter.read("orders", {"order_id": res["order_id"]})[0]
    assert order["total"] == 1600.0
    assert order["discount_amount"] == 0.0
    assert order["coupon_code"] is None
    assert order["coupon_status"] == "none"


# --- F-01 & F-02 Regression Tests (Phase C.6.6D.3D) ---

from app.db.database import InsufficientStockError
import app.services.payment_service as ps_mod


def test_process_create_order_stock_failure_does_not_release_coupon(clean_json_db):
    """F-01: When stock deduction fails after order is saved, coupon is NOT released."""
    adapter, _ = clean_json_db
    adapter.insert("coupons", {
        "id": 1, "code": "STOCK_FAIL_KEEP", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 5, "usage_count": 0, "is_active": True
    })
    dummy_products = [{"id": 1, "name": "Shirt", "price": 500.0, "stock": 50, "image": "shirt.jpg"}]

    def mock_stock_shortage(items, order_id=None):
        raise InsufficientStockError("Item shortage at deduction boundary")

    payload = DummyPayload(items=[{"id": 1, "qty": 1, "size": "M"}], coupon_code="STOCK_FAIL_KEEP")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod, "deduct_stock", side_effect=mock_stock_shortage), \
         patch.object(os_mod, "send_order_email"):

        res = os_mod.process_create_order(payload, DummyRequest())

    assert res["success"] is True
    persisted_order_id = res["order_id"]

    # Verify coupon was NOT released: usage_count remains 1, order remains recorded
    coupon = adapter.read("coupons", {"code": "STOCK_FAIL_KEEP"})[0]
    assert coupon["usage_count"] == 1
    assert persisted_order_id in coupon["redeemed_orders"]

    # Verify persisted order reflects stock failure and manual review status
    order = adapter.read("orders", {"order_id": persisted_order_id})[0]
    assert order["coupon_status"] == "redeemed"
    assert order["stock_status"] == "failed_insufficient_stock"
    assert order["fulfillment_status"] == "manual_review_required"


def test_finalize_paid_order_coupon_conflict_requires_manual_review_fulfillment_false(clean_json_db):
    """F-02: Stock and email complete, but coupon conflict flags manual review -> fulfillment_complete is False."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 201,
        "order_id": "ORD-CONF-FULFILL",
        "razorpay_order_id": "rzp_order_conf",
        "razorpay_payment_id": "pay_conf_1",
        "coupon_code": "WRONG_COUPON",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": True,
    }
    adapter.insert("orders", order_record)

    def mock_conflict_redeem(code, today_iso, order_id=None):
        raise CouponConflictError("Order already bound to a different coupon")

    with patch.object(adapter, "redeem_coupon", side_effect=mock_conflict_redeem), \
         patch.object(ps_mod, "send_order_email"):

        res = ps_mod.finalize_paid_order(dict(order_record), "pay_conf_1")

    assert res["success"] is True
    assert res["payment_status"] == "paid"
    # Even though stock and email completed, manual review makes fulfillment_complete False
    assert res["fulfillment_complete"] is False
    assert res["fulfillment_status"] == "manual_review_required"

    # Verify order in DB has manual_review_required
    db_order = adapter.read("orders", {"order_id": "ORD-CONF-FULFILL"})[0]
    assert db_order["fulfillment_status"] == "manual_review_required"
    assert db_order["coupon_status"] == "conflict_post_capture"


def test_finalize_paid_order_stock_incomplete_fulfillment_false(clean_json_db):
    """F-02: When stock deduction is pending (e.g. transient error), fulfillment_complete is False."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 202,
        "order_id": "ORD-STOCK-PENDING",
        "razorpay_order_id": "rzp_order_pend",
        "razorpay_payment_id": "pay_pend_1",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": False,
    }
    adapter.insert("orders", order_record)

    def mock_stock_transient_error(items, order_id=None):
        raise RuntimeError("Transient DB lock timeout on stock deduction")

    with patch.object(ps_mod, "deduct_stock", side_effect=mock_stock_transient_error), \
         patch.object(ps_mod, "send_order_email"):

        res = ps_mod.finalize_paid_order(dict(order_record), "pay_pend_1")

    assert res["success"] is True
    assert res["stock_status"] == "pending"
    assert res["fulfillment_complete"] is False
    db_order = adapter.read("orders", {"id": 202})[0]
    assert db_order.get("fulfillment_status") != "fulfilled"


def test_finalize_paid_order_email_incomplete_fulfillment_false(clean_json_db):
    """F-02: When email dispatch fails, fulfillment_complete is False."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 203,
        "order_id": "ORD-EMAIL-FAIL",
        "razorpay_order_id": "rzp_order_email",
        "razorpay_payment_id": "pay_email_1",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": True,
    }
    adapter.insert("orders", order_record)

    def mock_email_fail(order):
        raise RuntimeError("SMTP connection timeout")

    with patch.object(ps_mod, "send_order_email", side_effect=mock_email_fail):
        res = ps_mod.finalize_paid_order(dict(order_record), "pay_email_1")

    assert res["success"] is True
    assert res["email_status"] == "failed"
    assert res["fulfillment_complete"] is False
    db_order = adapter.read("orders", {"id": 203})[0]
    assert db_order.get("fulfillment_status") != "fulfilled"


def test_finalize_paid_order_normal_successful_fulfillment_true(clean_json_db):
    """F-02: Normal order with stock and email completed -> fulfillment_complete is True."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 204,
        "order_id": "ORD-NORM-SUCCESS",
        "razorpay_order_id": "rzp_order_norm",
        "razorpay_payment_id": "pay_norm_1",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": True,
    }
    adapter.insert("orders", order_record)

    with patch.object(ps_mod, "send_order_email"):
        res = ps_mod.finalize_paid_order(dict(order_record), "pay_norm_1")

    assert res["success"] is True
    assert res["stock_status"] == "deducted"
    assert res["email_status"] == "sent"
    assert res["fulfillment_complete"] is True
    assert res["fulfillment_status"] == "fulfilled"
    db_order = adapter.read("orders", {"id": 204})[0]
    assert db_order.get("fulfillment_status") == "fulfilled"


def test_finalize_paid_order_retry_after_manual_review_remains_false(clean_json_db):
    """F-02: Retrying an order already marked manual_review_required preserves fulfillment_complete=False."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 205,
        "order_id": "ORD-RETRY-MANUAL",
        "razorpay_order_id": "rzp_order_rev",
        "razorpay_payment_id": "pay_rev_1",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "sent",
        "fulfillment_status": "manual_review_required",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": True,
    }
    adapter.insert("orders", order_record)

    res = ps_mod.finalize_paid_order(dict(order_record), "pay_rev_1")

    assert res["success"] is True
    assert res["fulfillment_complete"] is False
    assert res["fulfillment_status"] == "manual_review_required"



def test_finalize_paid_order_status_update_failure_does_not_claim_completion(clean_json_db):
    """DISC-01: If persisting fulfillment_status='fulfilled' fails, fulfillment_complete is False."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 206,
        "order_id": "ORD-STATUS-FAIL",
        "razorpay_order_id": "rzp_order_fail",
        "razorpay_payment_id": "pay_fail_1",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": True,
    }
    adapter.insert("orders", order_record)

    original_update = adapter.update

    def mock_update_fail_on_fulfilled(table, filters, data):
        if table == "orders" and data.get("fulfillment_status") == "fulfilled":
            raise IOError("Simulated disk full while writing fulfillment status")
        return original_update(table, filters, data)

    with patch.object(adapter, "update", side_effect=mock_update_fail_on_fulfilled), \
         patch.object(ps_mod, "send_order_email"):
        res = ps_mod.finalize_paid_order(dict(order_record), "pay_fail_1")

    assert res["success"] is True
    assert res["fulfillment_complete"] is False
    assert res["fulfillment_status"] != "fulfilled"
    db_order = adapter.read("orders", {"id": 206})[0]
    assert db_order.get("fulfillment_status") != "fulfilled"
    # Payment, stock, and email side effects remain safe and intact
    assert db_order["payment_status"] == "paid"
    assert db_order["stock_status"] == "deducted"
    assert db_order["email_status"] == "sent"


def test_finalize_paid_order_retry_after_transient_status_update_failure_converges(clean_json_db):
    """DISC-01: A retry after status-update failure converges to fulfilled without duplicating stock or email."""
    adapter, _ = clean_json_db
    order_record = {
        "id": 207,
        "order_id": "ORD-STATUS-RETRY",
        "razorpay_order_id": "rzp_order_retry",
        "razorpay_payment_id": "pay_retry_1",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 1, "price": 100.0}],
        "test_mode": False,
    }
    adapter.insert("orders", order_record)

    original_update = adapter.update
    fail_status_update = True
    email_calls = []
    stock_calls = []

    def mock_update(table, filters, data):
        if table == "orders" and data.get("fulfillment_status") == "fulfilled" and fail_status_update:
            return []  # simulate zero rows updated
        return original_update(table, filters, data)

    def mock_email(order):
        email_calls.append(order["order_id"])

    def mock_stock(items, order_id=None):
        stock_calls.append(order_id)
        return True

    with patch.object(adapter, "update", side_effect=mock_update), \
         patch.object(ps_mod, "send_order_email", side_effect=mock_email), \
         patch.object(ps_mod, "deduct_stock", side_effect=mock_stock):

        # First call: status update returns empty list (failure to persist)
        res1 = ps_mod.finalize_paid_order(dict(order_record), "pay_retry_1")
        assert res1["success"] is True
        assert res1["fulfillment_complete"] is False
        assert len(stock_calls) == 1
        assert len(email_calls) == 1

        # DB record has stock deducted and email sent, but fulfillment_status not fulfilled
        mid_order = adapter.read("orders", {"id": 207})[0]
        assert mid_order["stock_status"] == "deducted"
        assert mid_order["email_status"] == "sent"
        assert mid_order.get("fulfillment_status") != "fulfilled"

        # Second call (retry): transient DB failure resolved
        fail_status_update = False
        res2 = ps_mod.finalize_paid_order(dict(mid_order), "pay_retry_1")

        # Stock and email MUST NOT be repeated
        assert len(stock_calls) == 1
        assert len(email_calls) == 1

        # Fulfillment converges to durable completion
        assert res2["success"] is True
        assert res2["fulfillment_complete"] is True
        assert res2["fulfillment_status"] == "fulfilled"

        final_order = adapter.read("orders", {"id": 207})[0]
        assert final_order["fulfillment_status"] == "fulfilled"
