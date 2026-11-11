"""
Focused unit tests for TridentWear Phase C.6.2: Secure Razorpay Payment Binding.
Tests all 12 required security invariants in Section 6.
"""
import sys
import hmac
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import app.services.payment_service as ps_mod
import app.services.order_service as os_mod
from app.db.database import PostgresDatabaseAdapter
from sqlalchemy import create_engine


TEST_SECRET = "test_razorpay_secret_12345"
TEST_KEY_ID = "rzp_test_key_abc"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setattr(ps_mod, "RAZORPAY_KEY_ID", TEST_KEY_ID)
    monkeypatch.setattr(ps_mod, "RAZORPAY_KEY_SECRET", TEST_SECRET)
    monkeypatch.setattr(ps_mod, "IS_PRODUCTION", False)
    monkeypatch.setattr(ps_mod, "create_gateway_order", lambda amount, currency, receipt, test_mode=False: f"order_{receipt.lower()}")


def compute_signature(order_id: str, payment_id: str, secret: str = TEST_SECRET) -> str:
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


class DummyRequest:
    def __init__(self, session=None, client_host="127.0.0.1"):
        self.session = session or {}
        self.client = type("Client", (), {"host": client_host})()
        self.headers = {}


@pytest.fixture
def mock_catalog():
    return [
        {"id": 1, "name": "Classic Crewneck", "price": 999.0, "stock": 10},
        {"id": 2, "name": "Graphic Tee", "price": 499.0, "stock": 5},
    ]


def test_1_valid_payment_matching_persisted_order_proceeds(mock_catalog):
    """1. A valid payment matching the persisted order amount and currency can proceed."""
    db_store = {"orders": [], "coupons": [], "products": mock_catalog}

    def mock_read(table, filters):
        return [row for row in db_store.get(table, []) if all(row.get(k) == v for k, v in filters.items())]

    def mock_insert(table, data):
        data_copy = dict(data, id=len(db_store[table]) + 1)
        db_store.setdefault(table, []).append(data_copy)
        return data_copy

    def mock_update(table, filters, updates):
        matched = []
        for row in db_store.get(table, []):
            if all(row.get(k) == v for k, v in filters.items()):
                row.update(updates)
                matched.append(dict(row))
        return matched

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert), \
         patch.object(os_mod.db, "read", side_effect=mock_read), \
         patch.object(os_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "insert", side_effect=mock_insert), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "deduct_stock") as mock_stock, \
         patch.object(ps_mod, "send_order_email") as mock_email:

        # Step 1: Client calls create-order
        create_res = ps_mod.process_razorpay_create(
            amount=99900,
            currency="INR",
            order_data={
                "items": [{"id": 1, "qty": 1}],
                "customer": {"name": "John Doe", "email": "john@example.com", "phone": "9876543210"},
                "shipping": {"address": "123 Main Street", "city": "Bengaluru", "postal_code": "560001"},
            }
        )
        assert create_res["success"] is True
        rz_order_id = create_res["razorpay_order_id"]
        assert create_res["amount"] == 99900

        # Step 2: Payment Gateway verifies and captures payment
        payment_id = "pay_valid_123"
        sig = compute_signature(rz_order_id, payment_id)

        # Mock gateway returning identical amount & currency
        mock_gateway = {
            "id": payment_id,
            "order_id": rz_order_id,
            "amount": 99900,
            "currency": "INR",
            "status": "captured",
        }

        with patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway):
            verify_res = ps_mod.process_razorpay_verify(
                razorpay_order_id=rz_order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=sig,
            )

        assert verify_res["success"] is True
        # Verify order in DB transitioned to paid
        saved = [o for o in db_store["orders"] if o["razorpay_order_id"] == rz_order_id][0]
        assert saved["payment_status"] == "paid"
        assert saved["status"] == "placed"
        assert saved["razorpay_payment_id"] == payment_id
        assert mock_stock.called
        assert mock_email.called


def test_2_underpaid_gateway_order_rejected(mock_catalog):
    """2. A ₹1 gateway order cannot verify against a ₹1,000 persisted order (Finding F1)."""
    db_store = {"orders": [], "coupons": [], "products": mock_catalog}

    def mock_read(table, filters):
        return [row for row in db_store.get(table, []) if all(row.get(k) == v for k, v in filters.items())]

    def mock_insert(table, data):
        data_copy = dict(data, id=len(db_store[table]) + 1)
        db_store.setdefault(table, []).append(data_copy)
        return data_copy

    def mock_update(table, filters, updates):
        matched = []
        for row in db_store.get(table, []):
            if all(row.get(k) == v for k, v in filters.items()):
                row.update(updates)
                matched.append(dict(row))
        return matched

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert), \
         patch.object(os_mod.db, "read", side_effect=mock_read), \
         patch.object(os_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update):

        # Persist pending order for ₹999.00 (99900 paise)
        create_res = ps_mod.process_razorpay_create(
            order_data={
                "items": [{"id": 1, "qty": 1}],
                "customer": {"name": "Attacker", "email": "att@example.com", "phone": "9876543210"},
                "shipping": {"address": "123 Main Street", "city": "Bengaluru"},
            }
        )
        rz_order_id = create_res["razorpay_order_id"]
        assert create_res["amount"] == 99900

        # Attacker paid ₹1.00 (100 paise) on Razorpay
        payment_id = "pay_underpaid_1"
        sig = compute_signature(rz_order_id, payment_id)

        mock_gateway = {
            "id": payment_id,
            "order_id": rz_order_id,
            "amount": 100,  # 100 paise = 1 INR
            "currency": "INR",
            "status": "captured",
        }

        with patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway):
            with pytest.raises(HTTPException) as exc:
                ps_mod.process_razorpay_verify(
                    razorpay_order_id=rz_order_id,
                    razorpay_payment_id=payment_id,
                    razorpay_signature=sig,
                )
            assert exc.value.status_code == 400
            assert "Payment amount mismatch" in exc.value.detail


def test_3_client_tampered_total_cannot_alter_server_calculated_amount(mock_catalog):
    """3. A modified client-side total cannot change the server-calculated payable amount."""
    db_store = {"orders": [], "coupons": [], "products": mock_catalog}

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=lambda t, d: dict(d, id=1)):

        # Client submits a fake subtotal of ₹5.00 for a ₹999 item
        create_res = ps_mod.process_razorpay_create(
            amount=500, # Client claims 500 paise (5 INR)
            currency="INR",
            order_data={
                "items": [{"id": 1, "qty": 1, "price": 5.0}], # Tampered item price
                "subtotal": 5.0, # Tampered subtotal
                "total": 5.0, # Tampered total
                "customer": {"name": "John Doe", "email": "john@example.com", "phone": "9876543210"},
                "shipping": {"address": "123 Main Street", "city": "Bengaluru"},
            }
        )
        # Server must enforce catalog price (999.0 * 1 = 999.00 -> 99900 paise)
        assert create_res["amount"] == 99900


def test_4_invalid_signature_rejected(mock_catalog):
    """4. Invalid signature is rejected (HTTP 400)."""
    with pytest.raises(HTTPException) as exc:
        ps_mod.process_razorpay_verify(
            razorpay_order_id="order_123",
            razorpay_payment_id="pay_123",
            razorpay_signature="invalid_tampered_signature_hex",
        )
    assert exc.value.status_code == 400
    assert "Invalid payment signature" in exc.value.detail


def test_5_unknown_or_mismatched_razorpay_order_id_rejected():
    """5. Unknown or mismatched Razorpay order ID is rejected."""
    payment_id = "pay_unknown_order"
    rz_order_id = "order_does_not_exist"
    sig = compute_signature(rz_order_id, payment_id)

    with patch.object(ps_mod.db, "read", return_value=[]):
        with pytest.raises(HTTPException) as exc:
            ps_mod.process_razorpay_verify(
                razorpay_order_id=rz_order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=sig,
            )
        assert exc.value.status_code == 404
        assert "No pending order found" in exc.value.detail


def test_6_payment_id_already_bound_rejected():
    """6. A payment ID already bound to another order is rejected."""
    payment_id = "pay_already_bound"
    rz_order_id = "order_intent_2"
    sig = compute_signature(rz_order_id, payment_id)

    # Order intent exists for order_intent_2 (TRD-NEW)
    def mock_read(table, filters):
        if filters.get("razorpay_order_id") == rz_order_id:
            return [{"id": 2, "order_id": "TRD-NEW", "razorpay_order_id": rz_order_id, "payment_status": "pending", "total": 999.0}]
        if filters.get("razorpay_payment_id") == payment_id:
            return [{"id": 1, "order_id": "TRD-PREVIOUS", "razorpay_payment_id": payment_id}]
        return []

    with patch.object(ps_mod.db, "read", side_effect=mock_read):
        with pytest.raises(HTTPException) as exc:
            ps_mod.process_razorpay_verify(
                razorpay_order_id=rz_order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=sig,
            )
        assert exc.value.status_code == 400
        assert "already been used for another order" in exc.value.detail


def test_7_wrong_currency_rejected():
    """7. Wrong currency is rejected."""
    # Test rejection on initiation
    with pytest.raises(HTTPException) as exc:
        ps_mod.process_razorpay_create(
            currency="USD",
            order_data={"items": [{"id": 1, "qty": 1}]}
        )
    assert exc.value.status_code == 400
    assert "Only INR currency is supported" in exc.value.detail

    # Test rejection on gateway verification
    payment_id = "pay_usd_curr"
    rz_order_id = "order_curr_check"
    sig = compute_signature(rz_order_id, payment_id)

    mock_order = [{"id": 1, "order_id": "TRD-1", "razorpay_order_id": rz_order_id, "payment_status": "pending", "total": 999.0}]
    mock_gateway = {
        "id": payment_id,
        "order_id": rz_order_id,
        "amount": 99900,
        "currency": "EUR",
        "status": "captured",
    }

    with patch.object(ps_mod.db, "read", return_value=mock_order), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway):
        with pytest.raises(HTTPException) as exc:
            ps_mod.process_razorpay_verify(
                razorpay_order_id=rz_order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=sig,
            )
        assert exc.value.status_code == 400
        assert "Invalid payment currency" in exc.value.detail


def test_8_uncaptured_or_failed_payment_cannot_become_paid():
    """8. An uncaptured/failed/authorized payment cannot become paid (F-02)."""
    payment_id = "pay_failed_gateway"
    rz_order_id = "order_intent_failed"
    sig = compute_signature(rz_order_id, payment_id)

    mock_order = [{"id": 1, "order_id": "TRD-1", "razorpay_order_id": rz_order_id, "payment_status": "pending", "total": 999.0}]

    # Case A: status == 'failed'
    mock_gateway_failed = {
        "id": payment_id,
        "order_id": rz_order_id,
        "amount": 99900,
        "currency": "INR",
        "status": "failed",
    }
    with patch.object(ps_mod.db, "read", return_value=mock_order), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway_failed):
        with pytest.raises(HTTPException) as exc:
            ps_mod.process_razorpay_verify(
                razorpay_order_id=rz_order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=sig,
            )
        assert exc.value.status_code == 400
        assert "not captured" in exc.value.detail

    # Case B: status == 'authorized' (F-02: authorized is NOT captured)
    mock_gateway_auth = {
        "id": payment_id,
        "order_id": rz_order_id,
        "amount": 99900,
        "currency": "INR",
        "status": "authorized",
    }
    with patch.object(ps_mod.db, "read", return_value=mock_order), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway_auth):
        with pytest.raises(HTTPException) as exc:
            ps_mod.process_razorpay_verify(
                razorpay_order_id=rz_order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=sig,
            )
        assert exc.value.status_code == 400
        assert "not captured" in exc.value.detail


def test_9_repeated_verification_idempotency():
    """9. Repeated verification does not duplicate the order, stock deduction, coupon redemption, or confirmation email."""
    payment_id = "pay_idemp_1"
    rz_order_id = "order_idemp_1"
    sig = compute_signature(rz_order_id, payment_id)

    # Order is already finalized as 'paid'
    already_paid_order = {
        "id": 1,
        "order_id": "TRD-ALREADYPAID",
        "razorpay_order_id": rz_order_id,
        "razorpay_payment_id": payment_id,
        "payment_status": "paid",
        "status": "placed",
        "total": 999.0,
    }

    with patch.object(ps_mod.db, "read", return_value=[already_paid_order]), \
         patch.object(ps_mod.db, "update") as mock_update, \
         patch.object(ps_mod, "deduct_stock") as mock_stock, \
         patch.object(ps_mod, "send_order_email") as mock_email:

        res = ps_mod.process_razorpay_verify(
            razorpay_order_id=rz_order_id,
            razorpay_payment_id=payment_id,
            razorpay_signature=sig,
        )

        assert res["success"] is True
        assert res["order_id"] == "TRD-ALREADYPAID"
        # No duplicate DB updates, stock deduction, or email
        assert not mock_update.called
        assert not mock_stock.called
        assert not mock_email.called


def test_10_concurrent_verification_cannot_finalize_twice():
    """10. Two concurrent verification attempts cannot finalize the same payment twice (F-01, F-03)."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    payment_id = "pay_concurrent_1"
    rz_order_id = "order_concurrent_1"
    sig = compute_signature(rz_order_id, payment_id)

    lock = threading.Lock()
    order_state = {
        "id": 1,
        "order_id": "TRD-RACE",
        "razorpay_order_id": rz_order_id,
        "status": "initiated",
        "payment_status": "pending",
        "total": 999.0,
        "coupon_code": "SAVE10",
        "coupon_status": "none",
        "items": [{"id": 1, "qty": 1}],
        "test_mode": False,
    }
    stock_deductions = []
    coupons_redeemed = []
    emails_sent = []

    def mock_read(table, filters):
        with lock:
            if table == "orders":
                if filters.get("id") == 1 or filters.get("razorpay_order_id") == rz_order_id:
                    return [dict(order_state)]
                if filters.get("razorpay_payment_id") == payment_id:
                    if order_state.get("razorpay_payment_id") == payment_id:
                        return [dict(order_state)]
            return []

    def mock_update(table, filters, updates):
        with lock:
            if table == "orders":
                for k, v in filters.items():
                    if order_state.get(k) != v:
                        return []  # Filter condition did not match!
                order_state.update(updates)
                return [dict(order_state)]
            return []

    def mock_deduct(items):
        with lock:
            stock_deductions.append(1)

    def mock_redeem(code, date_str, *args, **kwargs):
        with lock:
            coupons_redeemed.append(code)
        return {"code": code, "discount_pct": 10.0}

    def mock_email(order):
        with lock:
            emails_sent.append(order["order_id"])

    mock_gateway = {
        "id": payment_id,
        "order_id": rz_order_id,
        "amount": 99900,
        "currency": "INR",
        "status": "captured",
    }

    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        return ps_mod.process_razorpay_verify(rz_order_id, payment_id, sig)

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=mock_redeem), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", side_effect=mock_deduct), \
         patch.object(ps_mod, "send_order_email", side_effect=mock_email):

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker)
            f2 = executor.submit(worker)
            res1 = f1.result()
            res2 = f2.result()

    assert res1["success"] is True
    assert res2["success"] is True
    assert order_state["payment_status"] == "paid"
    assert order_state["coupon_status"] == "redeemed"
    assert len(stock_deductions) == 1, f"Stock deducted {len(stock_deductions)} times instead of 1"
    assert len(coupons_redeemed) == 1, f"Coupon redeemed {len(coupons_redeemed)} times instead of 1"
    assert len(emails_sent) == 1, f"Email sent {len(emails_sent)} times instead of 1"


def test_11_initiation_failure_does_not_leave_dangling_order_or_coupon(mock_catalog):
    """11. Failure during payment initiation does not leave a misleading usable payment intent or silently inconsistent coupon state."""
    db_store = {"orders": []}

    def mock_insert(table, data):
        data_copy = dict(data, id=1)
        db_store.setdefault(table, []).append(data_copy)
        return data_copy

    def mock_delete(table, filters):
        db_store[table] = [row for row in db_store.get(table, []) if not all(row.get(k) == v for k, v in filters.items())]
        return 1

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert), \
         patch.object(ps_mod.db, "delete", side_effect=mock_delete), \
         patch.object(ps_mod, "create_gateway_order", side_effect=RuntimeError("Razorpay API Timeout")):

        with pytest.raises(HTTPException) as exc:
            ps_mod.process_razorpay_create(
                order_data={
                    "items": [{"id": 1, "qty": 1}],
                    "customer": {"name": "Test", "email": "test@example.com", "phone": "9876543210"},
                    "shipping": {"address": "123 Main Street", "city": "Bengaluru"},
                    "test_mode": False
                }
            )
        assert exc.value.status_code == 502
        # Verify pending order was cleaned up
        assert len(db_store["orders"]) == 0


def test_12_cod_flow_compatibility(mock_catalog):
    """12. Existing COD and relevant payment tests remain compatible."""
    db_store = {"orders": [], "products": mock_catalog}

    def mock_insert(table, data):
        data_copy = dict(data, id=len(db_store[table]) + 1)
        db_store.setdefault(table, []).append(data_copy)
        return data_copy

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert), \
         patch.object(os_mod.db, "read", return_value=[]), \
         patch.object(os_mod, "deduct_stock") as mock_stock, \
         patch.object(os_mod, "send_order_email") as mock_email:

        cod_res = ps_mod.process_cod_order(
            subtotal=999.0,
            customer={"name": "COD Customer", "email": "cod@example.com", "phone": "9876543210"},
            shipping={"address": "123 Main Street", "city": "Bengaluru"},
            items=[{"id": 1, "qty": 1}],
            coupon_code=None,
            test_mode=False,
        )
        assert cod_res["success"] is True
        assert "order_id" in cod_res
        assert mock_stock.called
        assert mock_email.called
        assert db_store["orders"][0]["payment_status"] == "cod_pending"
        assert db_store["orders"][0]["payment_method"] == "cod"



def test_13_duplicate_product_ids_aggregate_stock_validation(mock_catalog):
    """13. Aggregate stock validation rejects carts with duplicate product IDs exceeding stock (F-04)."""
    # Product 2 has stock = 5 in mock_catalog
    # Cart has product 2 with qty 3 and qty 3 (total 6 > 5)
    with patch.object(os_mod, "load_products", return_value=mock_catalog):
        with pytest.raises(HTTPException) as exc:
            os_mod.create_pending_payment_order({
                "items": [
                    {"id": 2, "qty": 3, "size": "M"},
                    {"id": 2, "qty": 3, "size": "L"},
                ],
                "customer": {"name": "Test Customer", "email": "test@example.com", "phone": "9876543210"},
                "shipping": {"address": "123 Street", "city": "Bengaluru"},
            })
        assert exc.value.status_code == 400
        assert "Insufficient aggregate stock" in exc.value.detail

    # Within stock (3 + 2 = 5 <= 5) succeeds
    db_store = {"orders": []}
    def mock_insert(table, data):
        data_copy = dict(data, id=1)
        db_store.setdefault(table, []).append(data_copy)
        return data_copy

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert):
        res = os_mod.create_pending_payment_order({
            "items": [
                {"id": 2, "qty": 3, "size": "M"},
                {"id": 2, "qty": 2, "size": "L"},
            ],
            "customer": {"name": "Test Customer", "email": "test@example.com", "phone": "9876543210"},
            "shipping": {"address": "123 Street", "city": "Bengaluru"},
        })
        assert res["amount_paise"] == int((499.0 * 5) * 100)


def test_14_webhook_and_browser_verification_convergence():
    """14. Webhook capture and browser verification race cleanly with exact-once side effects (F-05)."""
    import json
    import threading
    from concurrent.futures import ThreadPoolExecutor

    payment_id = "pay_race_converge_1"
    rz_order_id = "order_race_converge_1"
    sig = compute_signature(rz_order_id, payment_id)

    lock = threading.Lock()
    order_state = {
        "id": 1,
        "order_id": "TRD-CONVERGE",
        "razorpay_order_id": rz_order_id,
        "status": "initiated",
        "payment_status": "pending",
        "total": 999.0,
        "coupon_code": "CONVERGE10",
        "coupon_status": "none",
        "items": [{"id": 1, "qty": 1}],
        "test_mode": False,
    }
    stock_deductions = []
    coupons_redeemed = []
    emails_sent = []
    events_store = []

    def mock_read(table, filters):
        with lock:
            if table == "orders":
                if filters.get("id") == 1 or filters.get("razorpay_order_id") == rz_order_id:
                    return [dict(order_state)]
                if filters.get("razorpay_payment_id") == payment_id:
                    if order_state.get("razorpay_payment_id") == payment_id:
                        return [dict(order_state)]
            elif table == "payment_events":
                return [dict(e) for e in events_store if all(e.get(k) == v for k, v in filters.items())]
            return []

    def mock_insert(table, data):
        with lock:
            if table == "payment_events":
                events_store.append(dict(data))
                return dict(data)
            return dict(data)

    def mock_update(table, filters, updates):
        with lock:
            if table == "orders":
                for k, v in filters.items():
                    if order_state.get(k) != v:
                        return []
                order_state.update(updates)
                return [dict(order_state)]
            return []

    def mock_deduct(items):
        with lock:
            stock_deductions.append(1)

    def mock_redeem(code, date_str, *args, **kwargs):
        with lock:
            coupons_redeemed.append(code)
        return {"code": code, "discount_pct": 10.0}

    def mock_email(order):
        with lock:
            emails_sent.append(order["order_id"])

    mock_gateway = {
        "id": payment_id,
        "order_id": rz_order_id,
        "amount": 99900,
        "currency": "INR",
        "status": "captured",
    }

    webhook_payload = json.dumps({
        "id": "evt_converge_test",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": rz_order_id,
                    "amount": 99900,
                    "currency": "INR",
                    "status": "captured"
                }
            }
        }
    }).encode("utf-8")
    webhook_sig = hmac.new(b"webhook_test_secret", webhook_payload, hashlib.sha256).hexdigest()

    barrier = threading.Barrier(2)

    def run_browser():
        barrier.wait()
        return ps_mod.process_razorpay_verify(rz_order_id, payment_id, sig)

    def run_webhook():
        barrier.wait()
        return ps_mod.process_webhook(webhook_payload, webhook_sig)

    with patch.object(ps_mod, "RAZORPAY_WEBHOOK_SECRET", "webhook_test_secret"), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "insert", side_effect=mock_insert), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=mock_redeem), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", side_effect=mock_deduct), \
         patch.object(ps_mod, "send_order_email", side_effect=mock_email):

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_browser = executor.submit(run_browser)
            f_webhook = executor.submit(run_webhook)
            res_browser = f_browser.result()
            res_webhook = f_webhook.result()

    assert res_browser["success"] is True
    assert res_webhook["success"] is True
    assert order_state["payment_status"] == "paid"
    assert order_state["coupon_status"] == "redeemed"
    assert len(stock_deductions) == 1
    assert len(coupons_redeemed) == 1
    assert len(emails_sent) == 1


# ==============================================================================
# Gate 2O.3.8: Payment Lifecycle Race & Callback State Invariant Tests
# ==============================================================================

def test_15_paid_order_late_failure_webhook_cannot_overwrite_paid():
    """Verify that a late payment.failed webhook does NOT overwrite a paid order
    and does NOT release the already redeemed coupon/offer.
    """
    import hmac
    import hashlib
    import json
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    order_state = {
        "id": 101,
        "order_id": "TRD-PAID-001",
        "razorpay_order_id": "order_paid_late_fail",
        "payment_status": "paid",
        "coupon_status": "redeemed",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_late_fail_123",
        "discount_amount": 100.0,
    }
    released_coupons = []

    def mock_read(table, filters):
        if table == "orders" and filters.get("razorpay_order_id") == "order_paid_late_fail":
            return [dict(order_state)]
        return []

    def mock_update(table, filters, updates):
        if table == "orders":
            order_state.update(updates)
            return [dict(order_state)]
        return []

    def mock_release(*args, **kwargs):
        released_coupons.append(args)
        return True

    webhook_payload = json.dumps({
        "id": "evt_late_fail_001",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_late_fail",
                    "order_id": "order_paid_late_fail",
                    "status": "failed",
                }
            }
        }
    }).encode("utf-8")
    webhook_sig = hmac.new(b"webhook_test_secret", webhook_payload, hashlib.sha256).hexdigest()

    with patch.object(ps_mod, "RAZORPAY_WEBHOOK_SECRET", "webhook_test_secret"), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "release_coupon", side_effect=mock_release), \
         patch.object(ps_mod.db, "release_coupon_offer", side_effect=mock_release):

        resp = ps_mod.process_webhook(webhook_payload, webhook_sig)
        assert resp["success"] is True

    # Invariant: order remains paid, coupon remains redeemed, no release called
    assert order_state["payment_status"] == "paid"
    assert order_state["coupon_status"] == "redeemed"
    assert len(released_coupons) == 0


def test_16_cancelled_order_late_payment_capture_flags_manual_review_no_fulfillment():
    """Verify that a late capture on a cancelled order preserves cancelled status,
    records payment_status='paid', sets fulfillment_status='manual_review_required',
    and does NOT deduct stock or redeem coupon.
    """
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    order_state = {
        "id": 102,
        "order_id": "TRD-CANCEL-001",
        "razorpay_order_id": "order_cancelled_late_cap",
        "status": "cancelled",
        "payment_status": "pending",
        "stock_status": "pending",
        "coupon_status": "released",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_cancel_123",
        "total": 500.0,
    }
    stock_deductions = []
    coupon_redemptions = []

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_state)]
        return []

    def mock_update(table, filters, updates):
        if table == "orders":
            order_state.update(updates)
            return [dict(order_state)]
        return []

    mock_gateway = {
        "id": "pay_late_cap_999",
        "order_id": "order_cancelled_late_cap",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
    }

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", side_effect=lambda *a, **k: stock_deductions.append(1)), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=lambda *a, **k: coupon_redemptions.append(1)):

        res = ps_mod.finalize_paid_order(
            order=order_state,
            razorpay_payment_id="pay_late_cap_999",
            test_mode=True,
        )

    # Invariants:
    assert res["success"] is True
    assert res["payment_status"] == "paid"
    assert res["fulfillment_status"] == "manual_review_required"
    assert res["fulfillment_complete"] is False
    assert order_state["status"] == "cancelled"  # Not revived to placed!
    assert order_state["payment_status"] == "paid"
    assert order_state["fulfillment_status"] == "manual_review_required"
    assert len(stock_deductions) == 0  # No stock deduction
    assert len(coupon_redemptions) == 0  # No coupon redemption


def test_17_concurrent_success_and_failure_race_cannot_break_paid_state():
    """Demonstrate that concurrent success and failure callbacks cannot leave
    a captured order in 'failed' status.
    """
    import hmac
    import hashlib
    import json
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    lock = threading.Lock()
    order_state = {
        "id": 103,
        "order_id": "TRD-RACE-001",
        "razorpay_order_id": "order_race_sf_1",
        "status": "initiated",
        "payment_status": "pending",
        "coupon_status": "reserved",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_race_123",
        "total": 999.0,
    }

    def mock_read(table, filters):
        with lock:
            if table == "orders":
                return [dict(order_state)]
            elif table == "payment_events":
                return []
            return []

    def mock_update(table, filters, updates):
        with lock:
            if table == "orders":
                # Conditional atomic check on payment_status if supplied
                if "payment_status" in filters and order_state.get("payment_status") != filters["payment_status"]:
                    return []
                order_state.update(updates)
                return [dict(order_state)]
            return []

    mock_gateway = {
        "id": "pay_race_win",
        "order_id": "order_race_sf_1",
        "amount": 99900,
        "currency": "INR",
        "status": "captured",
    }

    webhook_payload = json.dumps({
        "id": "evt_race_fail_1",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_race_failed_attempt",
                    "order_id": "order_race_sf_1",
                    "status": "failed",
                }
            }
        }
    }).encode("utf-8")
    webhook_sig = hmac.new(b"webhook_test_secret", webhook_payload, hashlib.sha256).hexdigest()

    barrier = threading.Barrier(2)

    def run_success():
        barrier.wait()
        return ps_mod.finalize_paid_order(
            order=dict(order_state),
            razorpay_payment_id="pay_race_win",
            test_mode=True,
        )

    def run_failure():
        barrier.wait()
        return ps_mod.process_webhook(webhook_payload, webhook_sig)

    with patch.object(ps_mod, "RAZORPAY_WEBHOOK_SECRET", "webhook_test_secret"), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "insert", return_value={"id": 1}), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "redeem_coupon", return_value={"code": "BUNDLE10"}), \
         patch.object(ps_mod.db, "release_coupon", return_value=True), \
         patch.object(ps_mod.db, "release_coupon_offer", return_value=True), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", return_value=True), \
         patch.object(ps_mod, "send_order_email", return_value=True):

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_succ = executor.submit(run_success)
            f_fail = executor.submit(run_failure)
            res_succ = f_succ.result()
            res_fail = f_fail.result()

    # The order must either remain paid (if success won or converged)
    # Crucially, payment_status CANNOT be 'failed' while payment was verified as paid!
    assert order_state["payment_status"] == "paid"
    assert order_state["coupon_status"] == "redeemed"


def test_18_stale_payment_finalization_cas_fails_when_order_cancelled_mid_flight():
    """Verify that a cancellation occurring between the initial read and conditional update (CAS)
    causes the payment finalization CAS to fail.
    Proves:
    1. A cancelled order cannot be changed to placed by a stale payment finalization attempt.
    2. Cancellation is preserved.
    3. Confirmed gateway capture records payment_status='paid' with fulfillment_status='manual_review_required'.
    4. No stock deduction or coupon redemption occurs.
    """
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    order_state = {
        "id": 104,
        "order_id": "TRD-STALE-CANCEL-001",
        "razorpay_order_id": "order_stale_cancel_1",
        "status": "initiated",
        "payment_status": "pending",
        "stock_status": "pending",
        "coupon_status": "reserved",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_stale_cancel_999",
        "total": 750.0,
    }
    stock_deductions = []
    coupon_redemptions = []
    cancellation_occurred = False

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_state)]
        return []

    def mock_update(table, filters, updates):
        nonlocal cancellation_occurred
        if table == "orders":
            # Simulate race: right as finalize_paid_order checks the CAS update,
            # an out-of-band cancellation commits first to order_state!
            if not cancellation_occurred and filters.get("status") == "initiated":
                # Interleaved cancellation commits before CAS checks match
                order_state["status"] = "cancelled"
                order_state["coupon_status"] = "released"
                cancellation_occurred = True

            # Standard atomic filter matching (mimics JsonDatabaseAdapter / PostgresDatabaseAdapter)
            for k, v in filters.items():
                if order_state.get(k) != v:
                    return []  # Filter condition failed due to concurrent cancellation!

            order_state.update(updates)
            return [dict(order_state)]
        return []

    mock_gateway = {
        "id": "pay_stale_cancel_win",
        "order_id": "order_stale_cancel_1",
        "amount": 75000,
        "currency": "INR",
        "status": "captured",
    }

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", side_effect=lambda *a, **k: stock_deductions.append(1)), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=lambda *a, **k: coupon_redemptions.append(1)):

        # finalize_paid_order is called with order data where status was 'initiated'
        initial_order_copy = dict(order_state)
        res = ps_mod.finalize_paid_order(
            order=initial_order_copy,
            razorpay_payment_id="pay_stale_cancel_win",
            test_mode=True,
        )

    # Invariants verification:
    assert cancellation_occurred is True, "Interleaved cancellation must have occurred"
    assert res["success"] is True
    assert res["payment_status"] == "paid"
    assert res["fulfillment_status"] == "manual_review_required"
    assert res["fulfillment_complete"] is False
    assert "flagged for manual review/refund" in res["message"]

    # Critical security invariant: Order status MUST remain 'cancelled', NEVER revived to 'placed'!
    assert order_state["status"] == "cancelled"
    assert order_state["payment_status"] == "paid"
    assert order_state["fulfillment_status"] == "manual_review_required"

    # Critical side-effect invariants: Zero stock deduction, zero coupon redemption!
    assert len(stock_deductions) == 0, f"Stock must NOT be deducted on cancelled order, but got {len(stock_deductions)}"
    assert len(coupon_redemptions) == 0, f"Coupon must NOT be redeemed on cancelled order, but got {len(coupon_redemptions)}"


def test_19_concurrent_cancellation_and_capture_thread_race():
    """True multi-thread concurrency test: Two threads simultaneously attempt
    to cancel the order (via real cancel_order_logic) and finalize payment capture
    (via real finalize_paid_order).
    Execution Model: ThreadPoolExecutor with threading.Barrier synchronization.
    Under atomic CAS, order MUST end in either:
    - (A) placed / paid with full fulfillment (capture won first; cancellation rejected)
    - (B) cancelled / paid with manual_review_required and zero fulfillment (cancellation won first; capture records paid + manual review)
    Never cancelled / placed or placed without payment.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from fastapi import HTTPException
    from unittest.mock import patch
    import app.services.payment_service as ps_mod
    from app.services.order_service import cancel_order_logic

    lock = threading.Lock()
    order_state = {
        "id": 105,
        "order_id": "TRD-RACE-THREAD-001",
        "razorpay_order_id": "order_race_thread_1",
        "user_id": 105,
        "customer": {"user_id": 105, "name": "Racer", "email": "racer@example.com"},
        "status": "initiated",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "coupon_status": "reserved",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_race_thread_105",
        "total": 1200.0,
    }
    stock_deductions = []
    coupon_redemptions = []
    released_offers = []

    def mock_read(table, filters):
        with lock:
            if table == "orders":
                return [dict(order_state)]
            return []

    def mock_update(table, filters, updates):
        with lock:
            if table == "orders":
                for k, v in filters.items():
                    if order_state.get(k) != v:
                        return []
                order_state.update(updates)
                return [dict(order_state)]
            return []

    barrier = threading.Barrier(2)
    dummy_req = DummyRequest(session={"user": {"id": 105, "email": "racer@example.com"}})

    def run_capture():
        barrier.wait()
        return ps_mod.finalize_paid_order(
            order=dict(order_state),
            razorpay_payment_id="pay_race_thread_win",
            test_mode=False,
        )

    def run_cancel():
        barrier.wait()
        try:
            return cancel_order_logic(order_state["order_id"], dummy_req)
        except Exception as exc:
            return exc

    mock_gateway = {
        "id": "pay_race_thread_win",
        "order_id": "order_race_thread_1",
        "amount": 120000,
        "currency": "INR",
        "status": "captured",
    }

    with patch("app.services.order_service.get_session_user", return_value={"id": 105, "email": "racer@example.com"}), \
         patch("app.services.payment_service.db.read", side_effect=mock_read), \
         patch("app.services.payment_service.db.update", side_effect=mock_update), \
         patch("app.services.order_service.db.read", side_effect=mock_read), \
         patch("app.services.order_service.db.update", side_effect=mock_update), \
         patch("app.services.order_service.db.release_coupon_offer", side_effect=lambda *a, **k: released_offers.append(1)), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", side_effect=lambda *a, **k: stock_deductions.append(1)), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=lambda *a, **k: coupon_redemptions.append(1)), \
         patch.object(ps_mod, "send_order_email", return_value=True):

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_cap = executor.submit(run_capture)
            f_can = executor.submit(run_cancel)
            res_cap = f_cap.result()
            res_can = f_can.result()

    # Verify that the final state is strictly consistent with either Case A or Case B
    with lock:
        final_status = order_state["status"]
        final_pay_status = order_state["payment_status"]
        final_ful_status = order_state.get("fulfillment_status")

    assert final_pay_status == "paid"

    if final_status == "cancelled":
        # Case B: Cancellation won the race first
        assert final_ful_status == "manual_review_required"
        assert res_can["success"] is True
        assert len(stock_deductions) == 0, "No stock deduction allowed on cancelled order"
        assert len(coupon_redemptions) == 0, "No coupon redemption allowed on cancelled order"
    elif final_status == "placed":
        # Case A: Capture won the race first; cancellation rejected because order is already paid
        assert final_ful_status == "fulfilled"
        assert isinstance(res_can, HTTPException)
        assert res_can.status_code == 400
        assert "paid" in res_can.detail
        assert len(stock_deductions) == 1
        assert len(coupon_redemptions) == 1
    else:
        pytest.fail(f"Invalid order status after concurrent race: {final_status}")


def test_20_normal_pending_order_payment_finalization_completes_successfully():
    """Verify that a normal non-cancelled pending order completes successfully
    through the CAS update and executes all fulfillment side effects.
    """
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    order_state = {
        "id": 106,
        "order_id": "TRD-NORMAL-001",
        "razorpay_order_id": "order_normal_1",
        "status": "initiated",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "coupon_status": "reserved",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_normal_106",
        "total": 999.0,
    }
    stock_deductions = []
    coupons_redeemed = []
    emails_sent = []

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_state)]
        return []

    def mock_update(table, filters, updates):
        if table == "orders":
            for k, v in filters.items():
                if order_state.get(k) != v:
                    return []
            order_state.update(updates)
            return [dict(order_state)]
        return []

    mock_gateway = {
        "id": "pay_normal_999",
        "order_id": "order_normal_1",
        "amount": 99900,
        "currency": "INR",
        "status": "captured",
    }

    def mock_redeem(*args, **kwargs):
        coupons_redeemed.append(order_state["coupon_code"])
        return {"code": order_state["coupon_code"], "status": "redeemed"}

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "fetch_gateway_payment", return_value=mock_gateway), \
         patch.object(ps_mod, "deduct_stock", side_effect=lambda *a, **k: stock_deductions.append(1)), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=mock_redeem), \
         patch.object(ps_mod, "send_order_email", side_effect=lambda *a, **k: emails_sent.append(1)):

        res = ps_mod.finalize_paid_order(
            order=dict(order_state),
            razorpay_payment_id="pay_normal_999",
            test_mode=False,
        )

    assert res["success"] is True
    assert res["payment_status"] == "paid"
    assert res["fulfillment_complete"] is True
    assert order_state["status"] == "placed"
    assert order_state["payment_status"] == "paid"
    assert order_state["fulfillment_status"] == "fulfilled"
    assert len(stock_deductions) == 1
    assert len(coupons_redeemed) == 1
    assert len(emails_sent) == 1


def test_21_failed_cas_update_does_not_execute_fulfillment_side_effects():
    """Verify that when the conditional update (CAS) fails to match and the order
    cannot be reconciled, finalize_paid_order raises HTTPException(409) and
    does NOT execute any fulfillment side-effects (stock, coupon, email).
    """
    import pytest
    from fastapi import HTTPException
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    order_state = {
        "id": 107,
        "order_id": "TRD-CAS-FAIL-001",
        "razorpay_order_id": "order_cas_fail_1",
        "status": "initiated",
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "coupon_status": "reserved",
        "coupon_code": "BUNDLE10",
        "total": 999.0,
    }
    stock_deductions = []
    coupons_redeemed = []
    emails_sent = []

    def mock_read(table, filters):
        # Order is read with status 'initiated' initially, and during re-read
        # still shows an unreconciled pending status from another competing process
        return [dict(order_state)]

    def mock_update(table, filters, updates):
        # Always simulate CAS claim failure
        return []

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "deduct_stock", side_effect=lambda *a, **k: stock_deductions.append(1)), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=lambda *a, **k: coupons_redeemed.append(1)), \
         patch.object(ps_mod, "send_order_email", side_effect=lambda *a, **k: emails_sent.append(1)):

        with pytest.raises(HTTPException) as exc_info:
            ps_mod.finalize_paid_order(
                order=dict(order_state),
                razorpay_payment_id="pay_conflict_999",
                test_mode=True,
            )

        assert exc_info.value.status_code == 409
        assert "Order status updated concurrently" in exc_info.value.detail

    # Crucial safety check: NO side effects executed
    assert len(stock_deductions) == 0, "No stock deduction should occur on failed CAS"
    assert len(coupons_redeemed) == 0, "No coupon redemption should occur on failed CAS"
    assert len(emails_sent) == 0, "No email should be dispatched on failed CAS"


def test_22_paid_order_cannot_be_cancelled_by_customer():
    """Verify that a customer cannot cancel an order that has already been paid.
    Proves:
    1. cancel_order_logic raises HTTPException(400).
    2. Order status remains 'placed'.
    3. Redeemed coupon is NOT released.
    4. Stock is NOT modified.
    """
    import pytest
    from fastapi import HTTPException
    from unittest.mock import patch
    from app.services.order_service import cancel_order_logic

    order_state = {
        "id": 122,
        "order_id": "TRD-PAID-CANCEL-001",
        "user_id": 55,
        "customer": {"user_id": 55, "name": "Buyer"},
        "status": "placed",
        "payment_status": "paid",
        "coupon_status": "redeemed",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_paid_122",
    }
    released_offers = []

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_state)]
        return []

    def mock_update(table, filters, updates):
        order_state.update(updates)
        return [dict(order_state)]

    dummy_req = DummyRequest(session={"user": {"id": 55, "email": "buyer@example.com"}})

    with patch("app.services.order_service.get_session_user", return_value={"id": 55, "email": "buyer@example.com"}), \
         patch("app.services.order_service.db.read", side_effect=mock_read), \
         patch("app.services.order_service.db.update", side_effect=mock_update), \
         patch("app.services.order_service.db.release_coupon_offer", side_effect=lambda *a, **k: released_offers.append(1)):

        with pytest.raises(HTTPException) as exc_info:
            cancel_order_logic("TRD-PAID-CANCEL-001", dummy_req)

        assert exc_info.value.status_code == 400
        assert "already been paid" in exc_info.value.detail

    # Invariants
    assert order_state["status"] == "placed"
    assert order_state["payment_status"] == "paid"
    assert order_state["coupon_status"] == "redeemed"
    assert len(released_offers) == 0


def test_23_cancelled_order_rejects_conflicting_second_payment_id():
    """Verify that an already-cancelled order that has already recorded payment_id A
    rejects a subsequent conflicting capture attempt with payment_id B.
    Proves:
    1. finalize_paid_order raises HTTPException(400 or 409).
    2. The first recorded payment ID is preserved and not overwritten.
    """
    import pytest
    from fastapi import HTTPException
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    order_state = {
        "id": 123,
        "order_id": "TRD-CANCEL-DUAL-PAY",
        "status": "cancelled",
        "payment_status": "paid",
        "razorpay_payment_id": "pay_first_recorded",
        "fulfillment_status": "manual_review_required",
    }

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_state)]
        return []

    def mock_update(table, filters, updates):
        order_state.update(updates)
        return [dict(order_state)]

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update):

        with pytest.raises(HTTPException) as exc_info:
            ps_mod.finalize_paid_order(
                order=dict(order_state),
                razorpay_payment_id="pay_second_conflicting",
                test_mode=True,
            )

        assert exc_info.value.status_code in (400, 409)
        assert "pay_first_recorded" in exc_info.value.detail

    # First payment ID must not be overwritten
    assert order_state["razorpay_payment_id"] == "pay_first_recorded"


def test_24_cancellation_releases_reserved_offer_but_never_redeemed_coupon():
    """Verify that cancelling an unpaid pending order releases a reserved offer,
    but never releases an already-redeemed coupon.
    """
    from unittest.mock import patch
    from app.services.order_service import cancel_order_logic

    # Case 1: Unpaid pending order with reserved coupon offer
    order_pending = {
        "id": 124,
        "order_id": "TRD-PENDING-OFFER",
        "user_id": 66,
        "customer": {"user_id": 66},
        "status": "initiated",
        "payment_status": "pending",
        "coupon_status": "reserved",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_res_124",
    }
    released_offers = []

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_pending)]
        return []

    def mock_update(table, filters, updates):
        order_pending.update(updates)
        return [dict(order_pending)]

    dummy_req = DummyRequest(session={"user": {"id": 66, "email": "buyer66@example.com"}})

    with patch("app.services.order_service.get_session_user", return_value={"id": 66, "email": "buyer66@example.com"}), \
         patch("app.services.order_service.db.read", side_effect=mock_read), \
         patch("app.services.order_service.db.update", side_effect=mock_update), \
         patch("app.services.order_service.db.release_coupon_offer", side_effect=lambda *a, **k: released_offers.append(k.get("offer_id") or (a[2] if len(a) > 2 else "unknown"))):

        res = cancel_order_logic("TRD-PENDING-OFFER", dummy_req)
        assert res["success"] is True

    assert order_pending["status"] == "cancelled"
    assert order_pending["coupon_status"] == "released"
    assert len(released_offers) == 1
    assert released_offers[0] == "offer_res_124"

    # Case 2: Order with already-redeemed coupon - cancellation must never release it
    order_redeemed = {
        "id": 125,
        "order_id": "TRD-REDEEMED-OFFER",
        "user_id": 66,
        "customer": {"user_id": 66},
        "status": "initiated",
        "payment_status": "pending",
        "coupon_status": "redeemed",
        "coupon_code": "BUNDLE10",
        "fbt_offer_id": "offer_red_125",
    }
    released_offers_case2 = []

    def mock_read_2(table, filters):
        if table == "orders":
            return [dict(order_redeemed)]
        return []

    def mock_update_2(table, filters, updates):
        order_redeemed.update(updates)
        return [dict(order_redeemed)]

    with patch("app.services.order_service.get_session_user", return_value={"id": 66, "email": "buyer66@example.com"}), \
         patch("app.services.order_service.db.read", side_effect=mock_read_2), \
         patch("app.services.order_service.db.update", side_effect=mock_update_2), \
         patch("app.services.order_service.db.release_coupon_offer", side_effect=lambda *a, **k: released_offers_case2.append(1)):

        res2 = cancel_order_logic("TRD-REDEEMED-OFFER", dummy_req)
        assert res2["success"] is True

    assert order_redeemed["status"] == "cancelled"
    assert order_redeemed["coupon_status"] == "redeemed"
    assert len(released_offers_case2) == 0, "Redeemed coupon must NEVER be released on cancellation"
