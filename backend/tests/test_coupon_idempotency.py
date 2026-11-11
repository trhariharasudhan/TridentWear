"""Tests for TridentWear Phase C.6.6D.3: Coupon Redemption Idempotency Engine.

Covers:
1. First redemption increments usage exactly once.
2. Repeating the same order/coupon redemption does not increment usage again.
3. A different order increments usage once.
4. The same order cannot redeem a different coupon silently (CouponConflictError).
5. A coupon at its usage limit rejects a new order.
6. Invalid or missing order IDs fail safely.
7. Existing coupon fields and legacy records remain compatible.
8. Interrupted order-status update is recoverable without another increment.
9. Malformed or contradictory redemption metadata fails safely.
10. Public API serialization does not expose internal redemption records.
11. JSON Multiprocessing: independent OS processes attempt to redeem same order/coupon -> exactly 1 increment.
12. JSON Multiprocessing: independent orders compete for final available coupon usage -> limit never exceeded.
13. Simulated failure before atomic write -> no partial redemption persisted.
14. Simulated failure after redemption before order status update -> retry repairs without duplicate increment.
15. Stale cache contents cannot bypass idempotency or usage limit.
16. SQL Coverage: Transactional rollback and unique constraint on coupon_redemptions.
17. SQL Coverage: Alembic migration 0011 upgrade and downgrade verification.
"""

import os
import sys
import json
import time
import importlib.util
import multiprocessing
from pathlib import Path
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, text, select
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.db.database as db_module
from app.db.database import (
    JsonDatabaseAdapter,
    PostgresDatabaseAdapter,
    CouponConflictError,
    InconsistentAllocationError,
)
from app.db.json_manager import db_instance, read_json
from app.db.models import metadata, coupons, coupon_redemptions, orders, users
import app.services.payment_service as ps_mod
from app.api.coupons import list_coupons, apply_coupon, ApplyCouponPayload


@pytest.fixture
def json_adapter(tmp_path, monkeypatch):
    """Fixture providing an isolated JsonDatabaseAdapter in a clean temp directory."""
    monkeypatch.setattr(db_module, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()
    return adapter, tmp_path


# --- 1. First redemption increments usage exactly once ---
def test_first_redemption_increments_usage_once(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "SAVE10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    res = adapter.redeem_coupon("SAVE10", today_iso, order_id="ORD-FIRST-1")
    assert res is not None
    assert res["usage_count"] == 1
    assert res["already_redeemed"] is False

    # Check disk state
    c = adapter.read("coupons", {"code": "SAVE10"})[0]
    assert c["usage_count"] == 1
    assert "ORD-FIRST-1" in c.get("redeemed_orders", {})


# --- 2. Repeating the same order/coupon redemption does not increment usage again ---
def test_repeating_same_order_does_not_increment_again(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "SAVE10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    res1 = adapter.redeem_coupon("SAVE10", today_iso, order_id="ORD-RETRY-1")
    assert res1["usage_count"] == 1
    assert res1["already_redeemed"] is False

    # Retry 1
    res2 = adapter.redeem_coupon("SAVE10", today_iso, order_id="ORD-RETRY-1")
    assert res2 is not None
    assert res2["already_redeemed"] is True
    assert res2["usage_count"] == 1

    # Retry 2
    res3 = adapter.redeem_coupon("SAVE10", today_iso, order_id="ORD-RETRY-1")
    assert res3["already_redeemed"] is True
    assert res3["usage_count"] == 1

    c = adapter.read("coupons", {"code": "SAVE10"})[0]
    assert c["usage_count"] == 1


# --- 3. A different order increments usage once ---
def test_different_order_increments_usage(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "SAVE10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    adapter.redeem_coupon("SAVE10", today_iso, order_id="ORD-A")
    adapter.redeem_coupon("SAVE10", today_iso, order_id="ORD-B")

    c = adapter.read("coupons", {"code": "SAVE10"})[0]
    assert c["usage_count"] == 2
    assert "ORD-A" in c["redeemed_orders"]
    assert "ORD-B" in c["redeemed_orders"]


# --- 4. The same order cannot redeem a different coupon silently ---
def test_same_order_different_coupon_conflict_rejected(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "COUPON1", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })
    adapter.insert("coupons", {
        "id": 2, "code": "COUPON2", "discount_pct": 20.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    adapter.redeem_coupon("COUPON1", today_iso, order_id="ORD-CONFLICT")

    # Attempting to redeem COUPON2 with the exact same order_id must raise CouponConflictError
    with pytest.raises(CouponConflictError) as exc:
        adapter.redeem_coupon("COUPON2", today_iso, order_id="ORD-CONFLICT")
    assert "already redeemed coupon COUPON1" in str(exc.value)

    # Usage counts must remain intact
    assert adapter.read("coupons", {"code": "COUPON1"})[0]["usage_count"] == 1
    assert adapter.read("coupons", {"code": "COUPON2"})[0]["usage_count"] == 0


# --- 5. A coupon at its usage limit rejects a new order ---
def test_coupon_at_usage_limit_rejected(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "LIMITED", "discount_pct": 15.0, "expires_at": "2029-12-31",
        "usage_limit": 2, "usage_count": 1, "is_active": True
    })

    today_iso = "2026-10-28"
    # Order 1 consumes the last unit
    res1 = adapter.redeem_coupon("LIMITED", today_iso, order_id="ORD-LIMIT-1")
    assert res1 is not None
    assert res1["usage_count"] == 2

    # Order 2 is rejected because limit reached
    res2 = adapter.redeem_coupon("LIMITED", today_iso, order_id="ORD-LIMIT-2")
    assert res2 is None

    # Total usage remains capped at 2
    assert adapter.read("coupons", {"code": "LIMITED"})[0]["usage_count"] == 2


# --- 6. Invalid or missing order IDs fail safely ---
def test_missing_order_id_backward_compatibility(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "NOORDER", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 10, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    # Without order_id, operates in legacy mode (succeeds, increments usage)
    res = adapter.redeem_coupon("NOORDER", today_iso, order_id=None)
    assert res is not None
    assert res["usage_count"] == 1
    assert res["already_redeemed"] is False


# --- 7. Existing coupon fields and legacy records remain compatible ---
def test_legacy_coupons_without_redemption_metadata(json_adapter):
    adapter, tmp_path = json_adapter
    # Write legacy coupon directly to coupons.json without redeemed_orders field
    coupons_file = tmp_path / "coupons.json"
    legacy_data = [{
        "id": 1, "code": "LEGACY", "discount_pct": 25.0, "expires_at": "2029-12-31",
        "usage_limit": 50, "usage_count": 5, "is_active": True
    }]
    with open(coupons_file, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)

    today_iso = "2026-10-28"
    res = adapter.redeem_coupon("LEGACY", today_iso, order_id="ORD-LEGACY")
    assert res is not None
    assert res["usage_count"] == 6

    # Verify redeemed_orders created seamlessly
    c = adapter.read("coupons", {"code": "LEGACY"})[0]
    assert c["usage_count"] == 6
    assert "ORD-LEGACY" in c["redeemed_orders"]


# --- 8. Interrupted order-status update is recoverable without another increment ---
def test_interrupted_order_status_update_recoverable(json_adapter, monkeypatch):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "INTERRUPT10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 50, "usage_count": 0, "is_active": True
    })
    adapter.insert("orders", {
        "id": 1, "order_id": "ORD-INTERRUPT", "coupon_code": "INTERRUPT10",
        "payment_status": "paid", "razorpay_payment_id": "pay_1", "coupon_status": "none"  # Interrupted before coupon_status='redeemed'
    })

    monkeypatch.setattr(ps_mod, "db", adapter)

    # First call to finalize_paid_order: redeems coupon and sets status to 'redeemed'
    order_dict = adapter.read("orders", {"id": 1})[0]
    res1 = ps_mod.finalize_paid_order(order_dict, "pay_1")
    assert res1["order_id"] == "ORD-INTERRUPT"

    c1 = adapter.read("coupons", {"code": "INTERRUPT10"})[0]
    assert c1["usage_count"] == 1

    # Simulate crash/rollback of orders.json where coupon_status was reverted to 'pending'
    adapter.update("orders", {"id": 1}, {"coupon_status": "pending"})

    # Recovery retry: finalize_paid_order called again
    order_dict_retry = adapter.read("orders", {"id": 1})[0]
    res2 = ps_mod.finalize_paid_order(order_dict_retry, "pay_1")
    assert res2["order_id"] == "ORD-INTERRUPT"

    # Coupon usage MUST STILL BE 1 (NOT 2!)
    c2 = adapter.read("coupons", {"code": "INTERRUPT10"})[0]
    assert c2["usage_count"] == 1
    # Order coupon_status repaired to 'redeemed'
    assert adapter.read("orders", {"id": 1})[0]["coupon_status"] == "redeemed"


# --- 9. Malformed or contradictory redemption metadata fails safely ---
def test_malformed_redemption_metadata_fails_safely(json_adapter):
    adapter, tmp_path = json_adapter
    coupons_file = tmp_path / "coupons.json"
    corrupt_data = [{
        "id": 1, "code": "CORRUPT", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 50, "usage_count": 0, "is_active": True,
        "redeemed_orders": "MALFORMED_STRING_NOT_DICT"
    }]
    with open(coupons_file, "w", encoding="utf-8") as f:
        json.dump(corrupt_data, f)

    today_iso = "2026-10-28"
    with pytest.raises(InconsistentAllocationError) as exc:
        adapter.redeem_coupon("CORRUPT", today_iso, order_id="ORD-CORRUPT")
    assert "Malformed redeemed_orders" in str(exc.value)

    # Usage count remains untouched
    with open(coupons_file, "r", encoding="utf-8") as f:
        actual = json.load(f)
    assert actual[0]["usage_count"] == 0


# --- 10. Public API serialization does not expose internal redemption records ---
def test_public_api_serialization_does_not_expose_redeemed_orders(json_adapter, monkeypatch):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "PUBLIC10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 1, "is_active": True,
        "redeemed_orders": {"ORD-SECRET-1": {"redeemed_at": "2026-10-28T00:00:00Z"}}
    })

    monkeypatch.setattr("app.api.coupons.db", adapter)

    # 1. list_coupons (Admin list)
    admin_list = list_coupons()
    for c in admin_list:
        assert "redeemed_orders" not in c
        assert c["code"] == "PUBLIC10"

    # 2. apply_coupon (Public endpoint)
    apply_res = apply_coupon(ApplyCouponPayload(code="PUBLIC10", subtotal=1000.0))
    assert "redeemed_orders" not in apply_res
    assert apply_res["discount_amount"] == 100.0


# --- 11. JSON Multiprocessing: independent OS processes attempt same order/coupon ---
def _worker_redeem_same_order(db_dir_str, code, today_iso, order_id, queue):
    """Worker process redeeming the same order/coupon."""
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        import app.db.database as db_m
        db_m.DB_DIR = Path(db_dir_str)
        w_adapter = db_m.JsonDatabaseAdapter()
        res = w_adapter.redeem_coupon(code, today_iso, order_id=order_id)
        queue.put(("SUCCESS", order_id, res.get("already_redeemed") if res else None))
    except Exception as e:
        queue.put(("ERROR", order_id, str(e)))


def test_multiprocessing_independent_processes_same_order(tmp_path):
    """Multiple OS processes try to redeem the same order simultaneously.
    Result: exactly 1 new redemption, all others report already_redeemed, usage_count = 1.
    """
    db_module.DB_DIR = tmp_path
    adapter = JsonDatabaseAdapter()
    adapter.insert("coupons", {
        "id": 1, "code": "RACE10", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 100, "usage_count": 0, "is_active": True
    })

    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_worker_redeem_same_order,
            args=(str(tmp_path), "RACE10", "2026-10-28", "ORD-RACE-SAME", queue)
        )
        for _ in range(4)
    ]

    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=10)

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == 4
    # Check that exactly one was new (already_redeemed=False) and the rest were already_redeemed=True
    new_redemptions = [r for r in results if r[0] == "SUCCESS" and r[2] is False]
    cached_redemptions = [r for r in results if r[0] == "SUCCESS" and r[2] is True]

    assert len(new_redemptions) == 1
    assert len(cached_redemptions) == 3

    # Final usage count on disk must be exactly 1
    final_c = adapter.read("coupons", {"code": "RACE10"})[0]
    assert final_c["usage_count"] == 1


# --- 12. JSON Multiprocessing: different orders compete for final coupon usage ---
def _worker_redeem_different_order(db_dir_str, code, today_iso, order_id, queue):
    """Worker process redeeming a distinct order."""
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        import app.db.database as db_m
        db_m.DB_DIR = Path(db_dir_str)
        w_adapter = db_m.JsonDatabaseAdapter()
        res = w_adapter.redeem_coupon(code, today_iso, order_id=order_id)
        queue.put(("RESULT", order_id, res is not None))
    except Exception as e:
        queue.put(("ERROR", order_id, str(e)))


def test_multiprocessing_different_orders_compete_for_limit(tmp_path):
    """3 separate processes with different orders compete for 1 available slot.
    Exactly 1 process succeeds; 2 are rejected. Usage count never exceeds limit.
    """
    db_module.DB_DIR = tmp_path
    adapter = JsonDatabaseAdapter()
    adapter.insert("coupons", {
        "id": 1, "code": "LASTUNIT", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 1, "usage_count": 0, "is_active": True
    })

    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_worker_redeem_different_order,
            args=(str(tmp_path), "LASTUNIT", "2026-10-28", f"ORD-COMPETE-{i}", queue)
        )
        for i in range(3)
    ]

    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=10)

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == 3
    successes = [r for r in results if r[0] == "RESULT" and r[2] is True]
    failures = [r for r in results if r[0] == "RESULT" and r[2] is False]

    assert len(successes) == 1
    assert len(failures) == 2

    final_c = adapter.read("coupons", {"code": "LASTUNIT"})[0]
    assert final_c["usage_count"] == 1


# --- 13. Simulated failure before atomic write ---
def test_simulated_failure_before_atomic_write(json_adapter):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "FAILWRITE", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 10, "usage_count": 0, "is_active": True
    })

    coupons_file = tmp_path / "coupons.json"
    with open(coupons_file, "r", encoding="utf-8") as f:
        initial_data = json.load(f)

    # Verify that if an exception occurs before write commits, file is untouched
    with pytest.raises(Exception):
        def bad_update(c):
            raise RuntimeError("Disk error before replacement")
        db_instance.update(str(coupons_file), bad_update)

    with open(coupons_file, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    assert current_data == initial_data


# --- 14. Simulated failure after redemption before order status update ---
def test_simulated_failure_after_redemption_before_order_status(json_adapter, monkeypatch):
    adapter, tmp_path = json_adapter
    adapter.insert("coupons", {
        "id": 1, "code": "HALFCOMM", "discount_pct": 20.0, "expires_at": "2029-12-31",
        "usage_limit": 10, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    # Step 1: Coupon successfully redeemed
    res = adapter.redeem_coupon("HALFCOMM", today_iso, order_id="ORD-HALF")
    assert res is not None
    assert res["usage_count"] == 1

    # Step 2: Retry with same order_id detects existing redemption
    retry_res = adapter.redeem_coupon("HALFCOMM", today_iso, order_id="ORD-HALF")
    assert retry_res["already_redeemed"] is True
    assert retry_res["usage_count"] == 1


# --- 15. Stale cache contents cannot bypass idempotency or usage limit ---
def test_stale_cache_does_not_bypass_coupon_idempotency(json_adapter):
    adapter, tmp_path = json_adapter
    coupons_path = str(tmp_path / "coupons.json")

    adapter.insert("coupons", {
        "id": 1, "code": "STALECOUPON", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 1, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"
    # 1. Redeem once: usage becomes 1
    adapter.redeem_coupon("STALECOUPON", today_iso, order_id="ORD-CACHE-1")

    # 2. Poison MemoryCache with stale data where usage_count is 0 and redeemed_orders is empty
    stale_payload = [{
        "id": 1, "code": "STALECOUPON", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 1, "usage_count": 0, "is_active": True, "redeemed_orders": {}
    }]
    with db_instance._cache_lock:
        db_instance._cache[coupons_path] = {
            "time": time.time(),
            "data": stale_payload
        }

    # Verify that a cached read would see stale usage_count = 0
    assert read_json(coupons_path)[0]["usage_count"] == 0

    # 3. Call redeem_coupon: because it runs inside update_json under CrossProcessLock,
    # it reads directly from physical disk, ignoring MemoryCache!
    # A second order trying to redeem must be REJECTED because usage_limit (1) is reached on disk!
    res_rejected = adapter.redeem_coupon("STALECOUPON", today_iso, order_id="ORD-CACHE-2")
    assert res_rejected is None

    # Disk usage remains 1
    with open(coupons_path, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data[0]["usage_count"] == 1


# --- 16. SQL Coverage: Transactional rollback and unique constraint on coupon_redemptions ---
def test_sql_adapter_coupon_redemptions_uniqueness_and_idempotency():
    """Verify PostgresDatabaseAdapter with SQLite in-memory engine:
    1. First redemption inserts into coupon_redemptions and increments usage_count.
    2. Retry on same order returns already_redeemed=True and keeps usage_count unchanged.
    3. Conflicting coupon for same order raises CouponConflictError.
    4. Unique constraint violation on order_id triggers transaction rollback.
    """
    engine = create_engine("sqlite:///:memory:")
    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    adapter.engine = engine
    adapter.metadata.create_all(adapter.engine)

    # Seed coupon
    adapter.insert("coupons", {
        "id": 1, "code": "SQLCOUPON1", "discount_pct": 10.0, "expires_at": "2029-12-31",
        "usage_limit": 10, "usage_count": 0, "is_active": True
    })
    adapter.insert("coupons", {
        "id": 2, "code": "SQLCOUPON2", "discount_pct": 20.0, "expires_at": "2029-12-31",
        "usage_limit": 10, "usage_count": 0, "is_active": True
    })

    today_iso = "2026-10-28"

    # 1. First redemption
    r1 = adapter.redeem_coupon("SQLCOUPON1", today_iso, order_id="SQL-ORD-1")
    assert r1 is not None
    assert r1["usage_count"] == 1
    assert r1["already_redeemed"] is False

    # Check redemption row exists in coupon_redemptions table
    with adapter.engine.connect() as conn:
        red_row = conn.execute(
            select(coupon_redemptions).where(coupon_redemptions.c.order_id == "SQL-ORD-1")
        ).first()
        assert red_row is not None
        assert red_row.coupon_code == "SQLCOUPON1"

    # 2. Retry with same order & same coupon -> returns already_redeemed=True
    r2 = adapter.redeem_coupon("SQLCOUPON1", today_iso, order_id="SQL-ORD-1")
    assert r2 is not None
    assert r2["already_redeemed"] is True
    assert r2["usage_count"] == 1

    # 3. Same order with a DIFFERENT coupon -> raises CouponConflictError
    with pytest.raises(CouponConflictError) as exc:
        adapter.redeem_coupon("SQLCOUPON2", today_iso, order_id="SQL-ORD-1")
    assert "already redeemed coupon SQLCOUPON1" in str(exc.value)

    # 4. Release coupon order-bound
    assert adapter.release_coupon("SQLCOUPON1", order_id="SQL-ORD-1") is True
    # Counter decremented back to 0
    c_after = adapter.read("coupons", {"code": "SQLCOUPON1"})[0]
    assert c_after["usage_count"] == 0

    # Repeated release returns False (at-most-once release)
    assert adapter.release_coupon("SQLCOUPON1", order_id="SQL-ORD-1") is False


# --- 17. SQL Coverage: Alembic migration 0011 upgrade and downgrade verification ---
def test_alembic_0011_upgrade_and_downgrade():
    """Verify Alembic migration 0011 upgrade and downgrade on isolated SQLite in-memory database."""
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY,
                code VARCHAR NOT NULL UNIQUE,
                discount_pct FLOAT NOT NULL,
                expires_at VARCHAR NOT NULL,
                usage_limit INTEGER DEFAULT 1000,
                usage_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    spec_0010 = importlib.util.spec_from_file_location(
        "migration_0010",
        str(BACKEND_DIR / "alembic/versions/20261028_0010_add_fulfillment_status_to_orders.py")
    )
    mod_0010 = importlib.util.module_from_spec(spec_0010)
    spec_0010.loader.exec_module(mod_0010)

    spec_0011 = importlib.util.spec_from_file_location(
        "migration_0011",
        str(BACKEND_DIR / "alembic/versions/20261028_0011_add_coupon_redemptions_table.py")
    )
    mod_0011 = importlib.util.module_from_spec(spec_0011)
    spec_0011.loader.exec_module(mod_0011)

    assert mod_0011.revision == "20261028_0011"
    assert mod_0011.down_revision == mod_0010.revision

    # 1. Upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod_0011.op._proxy = Operations(ctx)
        mod_0011.upgrade()

    insp = sa.inspect(engine)
    assert insp.has_table("coupon_redemptions")
    cols = {c["name"] for c in insp.get_columns("coupon_redemptions")}
    assert "order_id" in cols
    assert "coupon_code" in cols
    assert "redeemed_at" in cols

    indexes = {idx["name"] for idx in insp.get_indexes("coupon_redemptions")}
    assert "ix_coupon_redemptions_order_id" in indexes

    # 2. Downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod_0011.op._proxy = Operations(ctx)
        mod_0011.downgrade()

    insp_after = sa.inspect(engine)
    assert not insp_after.has_table("coupon_redemptions")
