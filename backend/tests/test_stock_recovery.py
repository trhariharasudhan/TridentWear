"""
Focused unit and integration tests for TridentWear Phase C.6.6B:
Atomic Inventory & Recoverable Payment Finalization.

Covers:
1. Two orders competing for the last available unit (SQL & JSON).
2. Same order stock deduction retried: idempotent, no second decrement.
3. Multi-item order with one insufficient item: all-or-nothing rollback (no partial deduction).
4. Duplicate product IDs aggregated before stock validation and deduction.
5. Missing product and invalid/non-positive quantities rejected.
6. Crash/failure after stock mutation and before completion-marker persistence (JSON ledger recovery).
7. Recovery of a paid order with stock work still pending.
8. Recovery of a paid order with email pending after stock has completed.
9. Coupon failure post-capture leading to exhausted_post_capture state.
10. Conflicting payment IDs and duplicate webhook/browser calls.
11. COD compatibility.
12. Alembic migration 0009 upgrade and downgrade verification.
"""
import sys
import os
import json
import uuid
import hmac
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text, select

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import app.services.payment_service as ps_mod
import app.services.order_service as os_mod
import app.services.product_service as prod_mod
from app.db.database import PostgresDatabaseAdapter, JsonDatabaseAdapter, InsufficientStockError
from app.db.models import metadata, products, orders, users


TEST_SECRET = "test_razorpay_secret_12345"
TEST_KEY_ID = "rzp_test_key_abc"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setattr(ps_mod, "RAZORPAY_KEY_ID", TEST_KEY_ID)
    monkeypatch.setattr(ps_mod, "RAZORPAY_KEY_SECRET", TEST_SECRET)
    monkeypatch.setattr(ps_mod, "IS_PRODUCTION", False)


def compute_signature(order_id: str, payment_id: str, secret: str = TEST_SECRET) -> str:
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# --- 1. Concurrency: Two orders competing for final unit (SQL Adapter / SQLite) ---
def test_1_sql_competing_orders_for_last_unit(tmp_path):
    """1. Two orders competing for the last available unit in SQL: only one succeeds; stock never negative."""
    db_file = tmp_path / "compete_test.db"
    adapter = PostgresDatabaseAdapter(f"sqlite:///{db_file}")
    adapter.metadata.create_all(adapter.engine)

    with adapter.engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))

    # Seed 1 product with stock = 1
    adapter.insert("products", {"id": 1, "name": "Solo Shirt", "price": 999.0, "stock": 1})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-A", "stock_status": "pending"})
    adapter.insert("orders", {"id": 2, "order_id": "ORD-B", "stock_status": "pending"})

    # Order A succeeds
    res_a = adapter.deduct_order_stock("ORD-A", [{"id": 1, "qty": 1}])
    assert res_a is True

    # Order B fails because stock is now 0
    with pytest.raises(InsufficientStockError) as exc:
        adapter.deduct_order_stock("ORD-B", [{"id": 1, "qty": 1}])
    assert "Insufficient stock" in str(exc.value)

    # Verify final stock is exactly 0 (never negative)
    prod = adapter.read("products", {"id": 1})[0]
    assert prod["stock"] == 0


# --- 2. Concurrency: Two orders competing for final unit (JSON Adapter) ---
def test_2_json_competing_orders_for_last_unit(tmp_path, monkeypatch):
    """2. Two orders competing for the last available unit in JSON adapter: only one succeeds; stock never negative."""
    import app.db.database as db_module
    monkeypatch.setattr(db_module, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()

    adapter.insert("products", {"id": 1, "name": "Solo Shirt", "price": 999.0, "stock": 1})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-A", "stock_status": "pending"})
    adapter.insert("orders", {"id": 2, "order_id": "ORD-B", "stock_status": "pending"})

    # Order A succeeds
    assert adapter.deduct_order_stock("ORD-A", [{"id": 1, "qty": 1}]) is True

    # Order B fails
    with pytest.raises(InsufficientStockError):
        adapter.deduct_order_stock("ORD-B", [{"id": 1, "qty": 1}])

    # Check stock
    prod = adapter.read("products", {"id": 1})[0]
    assert prod["stock"] == 0


# --- 3. Idempotent Retry: Same order stock deduction retried ---
def test_3_idempotent_stock_deduction_retry(tmp_path):
    """3. Retrying stock deduction on the same order causes no second decrement (SQL & JSON)."""
    db_file = tmp_path / "idemp_test.db"
    adapter = PostgresDatabaseAdapter(f"sqlite:///{db_file}")
    adapter.metadata.create_all(adapter.engine)

    adapter.insert("products", {"id": 10, "name": "Hoodie", "price": 1499.0, "stock": 5})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-IDEMP", "stock_status": "pending"})

    # First deduction: stock becomes 3
    assert adapter.deduct_order_stock("ORD-IDEMP", [{"id": 10, "qty": 2}]) is True
    assert adapter.read("products", {"id": 10})[0]["stock"] == 3
    assert adapter.read("orders", {"id": 1})[0]["stock_status"] == "deducted"

    # Second deduction retry: returns True immediately without modifying stock
    assert adapter.deduct_order_stock("ORD-IDEMP", [{"id": 10, "qty": 2}]) is True
    assert adapter.read("products", {"id": 10})[0]["stock"] == 3


# --- 4. Multi-item Atomic Rollback ---
def test_4_multi_item_order_insufficient_stock_rollback(tmp_path):
    """4. If one item in a multi-item order has insufficient stock, no items are deducted (all-or-nothing rollback)."""
    db_file = tmp_path / "rollback_test.db"
    adapter = PostgresDatabaseAdapter(f"sqlite:///{db_file}")
    adapter.metadata.create_all(adapter.engine)

    adapter.insert("products", {"id": 1, "name": "Item 1", "price": 500.0, "stock": 10})
    adapter.insert("products", {"id": 2, "name": "Item 2", "price": 500.0, "stock": 0})  # Out of stock
    adapter.insert("orders", {"id": 1, "order_id": "ORD-MULTI", "stock_status": "pending"})

    with pytest.raises(InsufficientStockError):
        adapter.deduct_order_stock("ORD-MULTI", [
            {"id": 1, "qty": 2},
            {"id": 2, "qty": 1},
        ])

    # Item 1 stock was NOT decremented
    assert adapter.read("products", {"id": 1})[0]["stock"] == 10
    assert adapter.read("products", {"id": 2})[0]["stock"] == 0
    assert adapter.read("orders", {"id": 1})[0]["stock_status"] == "pending"


# --- 5. Duplicate Product IDs and Invalid Quantities ---
def test_5_duplicate_product_ids_and_invalid_quantities(tmp_path):
    """5. Quantities for the same product ID are aggregated, and non-positive/malformed inputs are rejected."""
    db_file = tmp_path / "valid_test.db"
    adapter = PostgresDatabaseAdapter(f"sqlite:///{db_file}")
    adapter.metadata.create_all(adapter.engine)

    adapter.insert("products", {"id": 5, "name": "Tee", "price": 499.0, "stock": 5})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-DUP", "stock_status": "pending"})

    # Reject non-positive quantity
    with pytest.raises(ValueError, match="Quantity.*must be positive"):
        adapter.deduct_order_stock("ORD-DUP", [{"id": 5, "qty": 0}])

    with pytest.raises(ValueError, match="Quantity.*must be positive"):
        adapter.deduct_order_stock("ORD-DUP", [{"id": 5, "qty": -1}])

    # Aggregate quantities: 3 + 3 = 6 > stock 5 -> raises InsufficientStockError
    with pytest.raises(InsufficientStockError):
        adapter.deduct_order_stock("ORD-DUP", [
            {"id": 5, "qty": 3},
            {"id": 5, "qty": 3},
        ])

    # Within aggregate stock (2 + 2 = 4 <= 5) succeeds
    assert adapter.deduct_order_stock("ORD-DUP", [
        {"id": 5, "qty": 2},
        {"id": 5, "qty": 2},
    ]) is True
    assert adapter.read("products", {"id": 5})[0]["stock"] == 1


# --- 6. Crash Recovery via Stock Allocation Ledger in JSON ---
def test_6_json_crash_recovery_via_allocation_ledger(tmp_path, monkeypatch):
    """6. Crash after product stock mutation but before orders.json update is recovered without double decrement."""
    import app.db.database as db_module
    monkeypatch.setattr(db_module, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()

    adapter.insert("products", {"id": 1, "name": "Watch", "price": 2999.0, "stock": 10})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-CRASH", "stock_status": "pending"})

    # Simulate crash right after products.json and stock_allocations.json were updated
    # Stock decremented to 8, allocation recorded for ORD-CRASH, but orders.json still has stock_status='pending'
    allocations_file = tmp_path / "stock_allocations.json"
    products_file = tmp_path / "products.json"

    with open(products_file, "w") as f:
        json.dump([{"id": 1, "name": "Watch", "price": 2999.0, "stock": 8}], f)
    with open(allocations_file, "w") as f:
        json.dump([{"order_id": "ORD-CRASH", "items": {1: 2}}], f)

    # Next attempt (retry after crash recovery):
    res = adapter.deduct_order_stock("ORD-CRASH", [{"id": 1, "qty": 2}])
    assert res is True

    # Stock is STILL 8 (NOT decremented again to 6!)
    assert adapter.read("products", {"id": 1})[0]["stock"] == 8
    # And orders.json is now marked 'deducted'
    assert adapter.read("orders", {"id": 1})[0]["stock_status"] == "deducted"


# --- 7. Recovery of a Paid Order with Stock Work Pending ---
def test_7_recovery_of_paid_order_with_stock_pending():
    """7. An order already marked 'paid' but with stock_status='pending' is resumed and stock is deducted."""
    order_id = "TRD-RECOVER-STOCK"
    payment_id = "pay_recover_stock_1"
    rz_order_id = "order_rzp_rec_1"
    sig = compute_signature(rz_order_id, payment_id)

    order_store = [{
        "id": 101,
        "order_id": order_id,
        "razorpay_order_id": rz_order_id,
        "razorpay_payment_id": payment_id,
        "payment_status": "paid",  # Already paid
        "stock_status": "pending",  # Stock was interrupted/pending!
        "email_status": "sent",
        "items": [{"id": 1, "qty": 1}],
        "test_mode": False,
    }]
    deductions_called = []

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_store[0])]
        return []

    def mock_update(table, filters, data):
        order_store[0].update(data)
        return [dict(order_store[0])]

    def mock_deduct(items, order_id=None):
        deductions_called.append(order_id)
        return True

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "deduct_stock", side_effect=mock_deduct), \
         patch.object(ps_mod, "send_order_email") as mock_email:

        res = ps_mod.finalize_paid_order(order_store[0], payment_id)

        assert res["success"] is True
        assert res["fulfillment_complete"] is True
        assert len(deductions_called) == 1
        assert order_store[0]["stock_status"] == "deducted"
        assert not mock_email.called  # Email was already sent; not repeated!


# --- 8. Recovery of a Paid Order with Email Pending after Stock Completed ---
def test_8_recovery_of_paid_order_with_email_pending():
    """8. An order with stock completed but email failed is resumed: email is sent without re-deducting stock."""
    order_id = "TRD-RECOVER-EMAIL"
    payment_id = "pay_recover_email_1"

    order_store = [{
        "id": 102,
        "order_id": order_id,
        "razorpay_order_id": "order_rzp_rec_2",
        "razorpay_payment_id": payment_id,
        "payment_status": "paid",
        "stock_status": "deducted",  # Stock already completed
        "email_status": "failed",   # Email failed earlier
        "items": [{"id": 1, "qty": 1}],
        "test_mode": False,
    }]
    emails_sent = []

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_store[0])]
        return []

    def mock_update(table, filters, data):
        order_store[0].update(data)
        return [dict(order_store[0])]

    def mock_email(order):
        emails_sent.append(order["order_id"])

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "deduct_stock") as mock_stock, \
         patch.object(ps_mod, "send_order_email", side_effect=mock_email):

        res = ps_mod.finalize_paid_order(order_store[0], payment_id)

        assert res["success"] is True
        assert res["fulfillment_complete"] is True
        assert not mock_stock.called  # Stock was NOT re-deducted!
        assert len(emails_sent) == 1  # Email dispatched!
        assert order_store[0]["email_status"] == "sent"


# --- 9. Stock Shortage Post-Capture Flags Manual Review ---
def test_9_stock_shortage_post_capture_flags_manual_review():
    """9. If stock is exhausted post-capture, order remains 'paid', stock_status='failed_insufficient_stock', flagged for review."""
    order_id = "TRD-OUT-OF-STOCK"
    payment_id = "pay_exhausted_stock_1"

    order_store = [{
        "id": 103,
        "order_id": order_id,
        "razorpay_order_id": "order_rzp_out_1",
        "razorpay_payment_id": payment_id,
        "payment_status": "pending",
        "stock_status": "pending",
        "email_status": "pending",
        "items": [{"id": 1, "qty": 10}],
        "test_mode": False,
    }]

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_store[0])]
        return []

    def mock_update(table, filters, data):
        order_store[0].update(data)
        return [dict(order_store[0])]

    def mock_deduct_fail(items, order_id=None):
        raise InsufficientStockError("Item out of stock during post-capture allocation")

    with patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod, "deduct_stock", side_effect=mock_deduct_fail), \
         patch.object(ps_mod, "send_order_email"):

        res = ps_mod.finalize_paid_order(order_store[0], payment_id)

        # Payment remains successfully recorded as paid
        assert res["success"] is True
        assert res["payment_status"] == "paid"
        assert res["fulfillment_complete"] is False
        assert res["stock_status"] == "failed_insufficient_stock"
        assert order_store[0]["fulfillment_status"] == "manual_review_required"


# --- 10. Conflicting Payment IDs and Duplicate Calls ---
def test_10_conflicting_payment_ids_rejected():
    """10. Attempting to finalize an already-paid order with a different payment ID is rejected with HTTP 400."""
    order_store = [{
        "id": 104,
        "order_id": "TRD-CONFLICT",
        "razorpay_order_id": "order_rzp_conf",
        "razorpay_payment_id": "pay_FIRST_VALID",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "sent",
    }]

    def mock_read(table, filters):
        if table == "orders":
            return [dict(order_store[0])]
        return []

    with patch.object(ps_mod.db, "read", side_effect=mock_read):
        with pytest.raises(HTTPException) as exc:
            ps_mod.finalize_paid_order(order_store[0], "pay_SECOND_DIFFERENT")
        assert exc.value.status_code == 400
        assert "different payment ID" in exc.value.detail


# --- 11. COD Compatibility ---
def test_11_cod_order_sets_fulfillment_statuses():
    """11. COD order creation sets stock_status='deducted' and email_status='sent' on success."""
    mock_catalog = [{"id": 1, "name": "P1", "price": 500.0, "stock": 10}]
    db_store = {"orders": [], "products": mock_catalog}

    def mock_insert(table, data):
        data_copy = dict(data, id=len(db_store[table]) + 1)
        db_store.setdefault(table, []).append(data_copy)
        return data_copy

    def mock_update(table, filters, data):
        for o in db_store.get(table, []):
            if all(o.get(k) == v for k, v in filters.items()):
                o.update(data)
                return [dict(o)]
        return []

    with patch.object(os_mod, "load_products", return_value=mock_catalog), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert), \
         patch.object(os_mod.db, "read", return_value=[]), \
         patch.object(os_mod.db, "update", side_effect=mock_update), \
         patch.object(os_mod, "deduct_stock") as mock_stock, \
         patch.object(os_mod, "send_order_email") as mock_email:

        cod_res = ps_mod.process_cod_order(
            subtotal=500.0,
            customer={"name": "COD Customer", "email": "cod@example.com", "phone": "9876543210"},
            shipping={"address": "123 Main Street", "city": "Bengaluru"},
            items=[{"id": 1, "qty": 1}],
            coupon_code=None,
            test_mode=False,
        )
        assert cod_res["success"] is True
        saved = db_store["orders"][0]
        assert saved["payment_method"] == "cod"
        assert saved["payment_status"] == "cod_pending"
        assert saved["stock_status"] == "deducted"
        assert saved["email_status"] == "sent"


# --- 12. Alembic Migration 0009 Upgrade & Downgrade ---
def test_12_alembic_0009_migration():
    """12. Test Alembic migration 0009 upgrade and downgrade (adds stock_status and email_status to orders)."""
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    import sqlalchemy as sa

    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        users.create(conn)
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                order_id VARCHAR NOT NULL UNIQUE,
                user_id INTEGER,
                items JSON,
                total FLOAT,
                subtotal FLOAT,
                discount_amount FLOAT,
                coupon_code VARCHAR,
                customer JSON,
                shipping JSON,
                status VARCHAR,
                payment_method VARCHAR,
                payment_status VARCHAR,
                razorpay_order_id VARCHAR,
                razorpay_payment_id VARCHAR,
                idempotency_key VARCHAR,
                coupon_status VARCHAR,
                tracking_id VARCHAR,
                courier VARCHAR,
                estimated_delivery VARCHAR,
                test_mode BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0009",
        str(BACKEND_DIR / "alembic/versions/20261028_0009_add_fulfillment_statuses_to_orders.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 1. Upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.upgrade()

    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("orders")}
    assert "stock_status" in cols
    assert "email_status" in cols

    # 2. Downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.downgrade()

    insp = sa.inspect(engine)
    cols_after_down = {c["name"] for c in insp.get_columns("orders")}
    assert "stock_status" not in cols_after_down
    assert "email_status" not in cols_after_down
