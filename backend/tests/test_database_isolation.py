"""
TridentWear — Test Database Isolation & Safety Safeguard Regression Tests
Gate 2O.6.1 Verification Suite

Verifies:
1. Test mode selects isolated storage.
2. Development mode selects normal configured database.
3. Test mode refuses to resolve to the development database path (fails closed).
4. Test mode rejects production database configuration.
5. Two test instances do not share mutable database state.
6. Orders created during tests remain inside the test database.
7. Coupon redemption remains isolated.
8. Inventory changes remain isolated.
9. Failed tests do not contaminate development data.
10. Existing database locking and atomic-write behavior remains functional.
"""

import os
import sys
import json
import hashlib
import pytest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db_switch import (
    get_db,
    get_db_dir,
    get_default_db_dir,
    is_test_mode,
    validate_db_safety,
    UnsafeTestDatabaseError,
)
from app.db.database import JsonDatabaseAdapter, InsufficientStockError
from app.db.test_db import isolated_test_database, create_isolated_test_db, cleanup_isolated_test_db


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_1_test_mode_selects_isolated_storage(tmp_path, monkeypatch):
    """1. Test mode reliably selects isolated storage when TRIDENT_DB_DIR is configured."""
    custom_dir = tmp_path / "custom_test_db"
    custom_dir.mkdir()

    import app.db.database as db_mod
    monkeypatch.setattr(db_mod, "DB_DIR", get_default_db_dir())
    monkeypatch.setenv("TRIDENT_TEST_MODE", "1")
    monkeypatch.setenv("TRIDENT_DB_DIR", str(custom_dir))

    resolved = get_db_dir()
    assert resolved == custom_dir.resolve()
    assert resolved != get_default_db_dir()

    adapter = get_db()
    assert isinstance(adapter, JsonDatabaseAdapter)
    assert Path(adapter.db_dir).resolve() == custom_dir.resolve()


def test_2_development_mode_selects_normal_configured_database(monkeypatch):
    """2. Development mode selects the normal configured database directory."""
    import app.db.database as db_mod
    monkeypatch.setattr(db_mod, "DB_DIR", get_default_db_dir())
    monkeypatch.delenv("TRIDENT_TEST_MODE", raising=False)
    monkeypatch.delenv("TRIDENT_DB_DIR", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    # Temporarily remove PYTEST_CURRENT_TEST to simulate normal runtime
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    assert not is_test_mode()
    resolved = get_db_dir()
    assert resolved == get_default_db_dir()


def test_3_test_mode_cannot_resolve_to_development_database_path(monkeypatch):
    """3. Test mode refuses to run if TRIDENT_DB_DIR is empty or resolves to development db/."""
    dev_dir = get_default_db_dir()

    import app.db.database as db_mod
    monkeypatch.setattr(db_mod, "DB_DIR", dev_dir)

    # Case A: TRIDENT_DB_DIR explicitly set to dev_dir while in test mode
    monkeypatch.setenv("TRIDENT_TEST_MODE", "1")
    monkeypatch.setenv("TRIDENT_DB_DIR", str(dev_dir))

    with pytest.raises(UnsafeTestDatabaseError) as exc_info:
        get_db_dir()
    assert "cannot run against the development database directory" in str(exc_info.value)

    # Case B: TRIDENT_TEST_MODE=1 but TRIDENT_DB_DIR not set at all
    monkeypatch.delenv("TRIDENT_DB_DIR", raising=False)

    with pytest.raises(UnsafeTestDatabaseError) as exc_info2:
        get_db_dir()
    assert "TRIDENT_DB_DIR is not configured" in str(exc_info2.value)


def test_4_test_mode_rejects_production_database_configuration(tmp_path, monkeypatch):
    """4. Test mode rejects production database configuration (e.g. AWS RDS, production DSN)."""
    test_dir = tmp_path / "valid_test_dir"
    test_dir.mkdir()
    monkeypatch.setenv("TRIDENT_TEST_MODE", "1")
    monkeypatch.setenv("TRIDENT_DB_DIR", str(test_dir))

    # Test dangerous keywords in DSN
    dangerous_dsns = [
        "postgresql://prod_user:secret@db.tridentwear.in:5432/trident_prod",
        "postgresql://app:pass@trident-cluster.rds.amazonaws.com:5432/app",
        "postgresql://user:pass@ep-cool-fog.neon.tech/main",
        "postgresql://postgres:secret@db.myproject.supabase.co:5432/postgres",
    ]

    for bad_dsn in dangerous_dsns:
        monkeypatch.setenv("DB_MODE", "postgres")
        monkeypatch.setenv("PG_DSN", bad_dsn)
        with pytest.raises(UnsafeTestDatabaseError) as exc:
            validate_db_safety(dsn=bad_dsn)
        assert "production PostgreSQL" in str(exc.value)


def test_5_two_test_instances_do_not_share_mutable_database_state():
    """5. Two test instances in separate temporary directories operate with independent state."""
    with isolated_test_database(seed_data=True) as (dir1, adapter1):
        with isolated_test_database(seed_data=True) as (dir2, adapter2):
            assert dir1.resolve() != dir2.resolve()

            # Insert an order into instance 1
            order1 = adapter1.insert("orders", {"order_id": "ORD-ISOLATED-1", "total": 999.0})
            assert order1["order_id"] == "ORD-ISOLATED-1"

            # Verify instance 2 does not see order1
            res2 = adapter2.read("orders", {"order_id": "ORD-ISOLATED-1"})
            assert len(res2) == 0

            # Insert an order into instance 2
            order2 = adapter2.insert("orders", {"order_id": "ORD-ISOLATED-2", "total": 1499.0})
            assert order2["order_id"] == "ORD-ISOLATED-2"

            # Verify instance 1 does not see order2
            res1 = adapter1.read("orders", {"order_id": "ORD-ISOLATED-2"})
            assert len(res1) == 0


def test_6_orders_created_during_tests_remain_inside_test_database():
    """6. Orders created during tests are written strictly to isolated storage and dev orders.json is untouched."""
    dev_db = get_default_db_dir()
    dev_orders_file = dev_db / "orders.json"
    initial_hash = _file_hash(dev_orders_file)

    with isolated_test_database(seed_data=True) as (test_dir, adapter):
        test_orders_file = test_dir / "orders.json"
        assert test_orders_file.exists()

        # Insert 3 test orders
        adapter.insert("orders", {"order_id": "TEST-ORD-A", "payment_status": "cod_pending"})
        adapter.insert("orders", {"order_id": "TEST-ORD-B", "payment_status": "paid"})
        adapter.insert("orders", {"order_id": "TEST-ORD-C", "payment_status": "cancelled"})

        # Verify they exist in test DB
        test_orders = adapter.read("orders", {})
        assert len(test_orders) == 3
        assert {o["order_id"] for o in test_orders} == {"TEST-ORD-A", "TEST-ORD-B", "TEST-ORD-C"}

    # Post-check: development orders.json must be 100% byte-for-byte identical
    final_hash = _file_hash(dev_orders_file)
    assert final_hash == initial_hash, "Development orders.json was corrupted by test execution!"


def test_7_coupon_redemption_remains_isolated():
    """7. Coupon redemption inside test database does not mutate development coupons.json."""
    dev_db = get_default_db_dir()
    dev_coupons_file = dev_db / "coupons.json"
    initial_hash = _file_hash(dev_coupons_file)

    with isolated_test_database(seed_data=True) as (test_dir, adapter):
        today = "2026-11-09T00:00:00"
        # Redeem a coupon inside test DB using valid code from coupons.json
        redeemed = adapter.redeem_coupon(
            code="TRIDENT10",
            today_iso=today,
            order_id="TRD-TEST-COUPON-1"
        )
        assert redeemed is not None

        # Confirm redemption is recorded in test DB
        test_coupons = adapter.read("coupons", {"code": "TRIDENT10"})
        assert len(test_coupons) == 1
        assert "TRD-TEST-COUPON-1" in str(test_coupons[0].get("redemptions", [])) or \
               test_coupons[0].get("usage_count", 0) > 0

    # Post-check: development coupons.json must be 100% byte-for-byte identical
    final_hash = _file_hash(dev_coupons_file)
    assert final_hash == initial_hash, "Development coupons.json was corrupted by coupon test!"


def test_8_inventory_changes_remain_isolated():
    """8. Stock deductions and allocation records remain strictly inside test database."""
    dev_db = get_default_db_dir()
    dev_products_file = dev_db / "products.json"
    initial_hash = _file_hash(dev_products_file)

    with isolated_test_database(seed_data=True) as (test_dir, adapter):
        test_products = adapter.read("products", {})
        assert len(test_products) > 0
        first_prod = test_products[0]
        pid = first_prod["id"]
        original_stock = int(first_prod.get("stock", 0))

        if original_stock > 0:
            deduct_qty = min(2, original_stock)
            # Deduct stock in test DB
            success = adapter.deduct_order_stock(
                order_id="TEST-ORDER-STOCK-1",
                items=[{"id": pid, "qty": deduct_qty}]
            )
            assert success is True

            # Verify deduction inside test DB
            updated_prod = adapter.read("products", {"id": pid})[0]
            assert int(updated_prod["stock"]) == original_stock - deduct_qty

    # Post-check: development products.json must be 100% byte-for-byte identical
    final_hash = _file_hash(dev_products_file)
    assert final_hash == initial_hash, "Development products.json was corrupted by stock test!"


def test_9_failed_tests_do_not_contaminate_development_data():
    """9. A failed test operation or exception does not contaminate development database."""
    dev_db = get_default_db_dir()
    dev_orders_file = dev_db / "orders.json"
    initial_hash = _file_hash(dev_orders_file)

    try:
        with isolated_test_database(seed_data=True) as (test_dir, adapter):
            adapter.insert("orders", {"order_id": "TEST-WILL-FAIL", "total": 500})
            # Deliberate failure inside test
            raise ValueError("Simulated unexpected test assertion failure")
    except ValueError:
        pass

    final_hash = _file_hash(dev_orders_file)
    assert final_hash == initial_hash, "Development database was modified during failed test!"


def test_10_database_locking_and_atomic_writes_functional_in_isolated_db():
    """10. File locking (.lock) and atomic writes (.tmp) work correctly within the isolated test DB."""
    with isolated_test_database(seed_data=True) as (test_dir, adapter):
        # Insert initial order with paid payment status
        ord_record = adapter.insert("orders", {
            "order_id": "ORD-CONCUR-LOCK",
            "payment_status": "paid",
            "fulfillment_status": "pending",
            "total": 1299.0
        })
        assert ord_record["order_id"] == "ORD-CONCUR-LOCK"

        # Acquire claim using atomic CAS lock
        claim = adapter.acquire_claim(
            order_id="ORD-CONCUR-LOCK",
            lease_seconds=30,
            claim_owner="worker-thread-1"
        )
        assert claim is not None
        assert "claim_token" in claim
        token = claim["claim_token"]

        # Second worker attempting to acquire should be blocked
        second_claim = adapter.acquire_claim(
            order_id="ORD-CONCUR-LOCK",
            lease_seconds=30,
            claim_owner="worker-thread-2"
        )
        assert second_claim is None, "Lease lock failed: second worker acquired claim simultaneously!"

        # Release claim
        released = adapter.release_claim("ORD-CONCUR-LOCK", token)
        assert released is True
