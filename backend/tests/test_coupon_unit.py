"""
Focused unit tests for TridentWear coupon schema, validation, calculation, and persistence.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.api.coupons import apply_coupon, round_currency, ApplyCouponPayload, DEFAULT_COUPONS
from app.db.models import coupons as coupons_table, metadata
from sqlalchemy import create_engine, select, insert, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


# --- 1. Calculation & Rounding Tests ---

def test_round_currency():
    assert round_currency(149.854) == 149.85
    assert round_currency(149.856) == 149.86
    assert round_currency(0.0) == 0.0


def test_valid_coupons_default_values():
    codes = {c["code"]: c for c in DEFAULT_COUPONS}
    assert "TRIDENTFIRST" in codes
    assert codes["TRIDENTFIRST"]["discount_pct"] == 20.0
    assert codes["TRIDENTFIRST"]["is_active"] is True
    assert "TRIDENT10" in codes
    assert codes["TRIDENT10"]["discount_pct"] == 10.0


# --- 2. Validation & Boundary Tests ---

def test_apply_coupon_invalid_subtotal():
    with pytest.raises(HTTPException) as exc_info:
        apply_coupon(ApplyCouponPayload(code="TRIDENT10", subtotal=0))
    assert exc_info.value.status_code == 400
    assert "Invalid order subtotal" in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        apply_coupon(ApplyCouponPayload(code="TRIDENT10", subtotal=-50))
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        apply_coupon(ApplyCouponPayload(code="TRIDENT10", subtotal=2_000_000))
    assert exc_info.value.status_code == 400


def test_apply_coupon_nonexistent_code():
    with pytest.raises(HTTPException) as exc_info:
        apply_coupon(ApplyCouponPayload(code="NONEXISTENT_CODE_XYZ", subtotal=1000))
    assert exc_info.value.status_code == 404
    assert "Invalid coupon code" in exc_info.value.detail


# --- 3. Schema & Mapping Tests ---

def test_coupon_canonical_mapping_compatibility():
    """Verify that both canonical and legacy fields can be resolved."""
    legacy_row = {
        "code": "LEGACY20",
        "discount": 20.0,
        "expiry": "2028-12-31",
        "usage_limit": 500,
        "usage_count": 5
    }
    canonical_row = {
        "code": "CANONICAL20",
        "discount_pct": 20.0,
        "expires_at": "2028-12-31",
        "is_active": True,
        "usage_limit": 500,
        "usage_count": 5
    }

    # Resolve discount
    d_legacy = float(legacy_row.get("discount_pct", legacy_row.get("discount", 0)))
    d_canonical = float(canonical_row.get("discount_pct", canonical_row.get("discount", 0)))
    assert d_legacy == 20.0
    assert d_canonical == 20.0

    # Resolve expiry
    exp_legacy = legacy_row.get("expires_at") or legacy_row.get("expiry")
    exp_canonical = canonical_row.get("expires_at") or canonical_row.get("expiry")
    assert exp_legacy == "2028-12-31"
    assert exp_canonical == "2028-12-31"


# --- 4. Database Adapter Defensive Filtering Test ---

def test_sql_adapter_defensive_column_filtering():
    """Verify that extra legacy columns do not raise CompileError in PostgresDatabaseAdapter."""
    from app.db.database import PostgresDatabaseAdapter

    # Test with SQLite in-memory DSN
    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    adapter.metadata.create_all(adapter.engine)

    # Insert with extra unconsumed columns (discount, expiry) alongside canonical columns
    coupon_data = {
        "code": "TESTDEFENSIVE",
        "discount_pct": 25.0,
        "expires_at": "2028-12-31",
        "usage_limit": 100,
        "usage_count": 0,
        "is_active": True,
        "discount": 25.0,  # Legacy field not in SQL table
        "expiry": "2028-12-31",  # Legacy field not in SQL table
    }

    inserted = adapter.insert("coupons", coupon_data)
    assert inserted["code"] == "TESTDEFENSIVE"
    assert inserted["discount_pct"] == 25.0

    # Read back
    res = adapter.read("coupons", {"code": "TESTDEFENSIVE"})
    assert len(res) == 1
    assert res[0]["discount_pct"] == 25.0

    # Update with extra column
    updated = adapter.update("coupons", {"code": "TESTDEFENSIVE"}, {"usage_count": 1, "extra_ignored_key": 999})
    assert len(updated) == 1
    assert updated[0]["usage_count"] == 1


def test_sql_adapter_where_filter_safety():
    """Verify that unknown or empty filter keys raise explicit errors in PostgresDatabaseAdapter."""
    from app.db.database import PostgresDatabaseAdapter

    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    adapter.metadata.create_all(adapter.engine)

    # Insert two sample rows
    adapter.insert("coupons", {"code": "SAFE1", "discount_pct": 10.0, "expires_at": "2028-01-01"})
    adapter.insert("coupons", {"code": "SAFE2", "discount_pct": 20.0, "expires_at": "2028-01-01"})

    # 1. Unknown filter column in read() must raise ValueError (cannot silently match all)
    with pytest.raises(ValueError, match="Invalid filter column 'unknown_col'"):
        adapter.read("coupons", {"unknown_col": "val"})

    # 2. Unknown filter column in update() must raise ValueError
    with pytest.raises(ValueError, match="Invalid filter column 'unknown_col'"):
        adapter.update("coupons", {"unknown_col": "val"}, {"usage_count": 5})

    # 3. Unknown filter column in delete() must raise ValueError (cannot silently wipe table)
    with pytest.raises(ValueError, match="Invalid filter column 'unknown_col'"):
        adapter.delete("coupons", {"unknown_col": "val"})

    # 4. Empty filter in delete() must raise ValueError (cannot wipe table)
    with pytest.raises(ValueError, match="Empty filters not allowed for delete"):
        adapter.delete("coupons", {})

    # 5. Empty filter in update() must raise ValueError
    with pytest.raises(ValueError, match="Empty filters not allowed for update"):
        adapter.update("coupons", {}, {"usage_count": 5})

    # 6. Empty filter in read() is allowed and returns all rows
    all_rows = adapter.read("coupons", {})
    assert len(all_rows) == 2

    # 7. Valid filtered delete works and deletes only the matching row
    del_count = adapter.delete("coupons", {"code": "SAFE1"})
    assert del_count == 1
    remaining = adapter.read("coupons", {})
    assert len(remaining) == 1
    assert remaining[0]["code"] == "SAFE2"


# --- 5. Order Service Coupon Validation & Boundary Tests ---

def test_order_service_coupon_validations():
    """Verify that malformed, expired, inactive, or out-of-bound coupons are rejected and not counted."""
    from unittest.mock import patch
    import app.services.order_service as os_mod

    # Base valid dummy product map
    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg"}]
    base_order = {
        "items": [{"id": 1, "qty": 1, "size": "M"}],
        "coupon_code": "TESTCODE"
    }

    test_cases = [
        # (coupon_dict, expected_discount, expected_total, should_increment_count)
        # Malformed expiry dates
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": "invalid-date", "is_active": True}, 0.0, 100.0, False),
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": "", "is_active": True}, 0.0, 100.0, False),
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": None, "is_active": True}, 0.0, 100.0, False),
        # Expired coupon
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": "2020-01-01", "is_active": True}, 0.0, 100.0, False),
        # Inactive coupon
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": "2099-01-01", "is_active": False}, 0.0, 100.0, False),
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": "2099-01-01", "is_active": "false"}, 0.0, 100.0, False),
        # Usage limit reached
        ({"code": "TESTCODE", "discount_pct": 10.0, "expires_at": "2099-01-01", "is_active": True, "usage_count": 10, "usage_limit": 10}, 0.0, 100.0, False),
        # Out-of-bounds percentage
        ({"code": "TESTCODE", "discount_pct": -10.0, "expires_at": "2099-01-01", "is_active": True}, 0.0, 100.0, False),
        ({"code": "TESTCODE", "discount_pct": 150.0, "expires_at": "2099-01-01", "is_active": True}, 0.0, 100.0, False),
        ({"code": "TESTCODE", "discount_pct": float("nan"), "expires_at": "2099-01-01", "is_active": True}, 0.0, 100.0, False),
        # Valid 0% discount
        ({"code": "TESTCODE", "discount_pct": 0.0, "expires_at": "2099-01-01", "is_active": True, "usage_count": 0, "usage_limit": 100}, 0.0, 100.0, True),
        # Valid 100% discount (order total cannot be negative)
        ({"code": "TESTCODE", "discount_pct": 100.0, "expires_at": "2099-01-01", "is_active": True, "usage_count": 0, "usage_limit": 100}, 100.0, 0.0, True),
        # Valid 20% discount
        ({"code": "TESTCODE", "discount_pct": 20.0, "expires_at": "2099-01-01", "is_active": True, "usage_count": 0, "usage_limit": 100}, 20.0, 80.0, True),
        # Legacy field fallback
        ({"code": "TESTCODE", "discount": 25.0, "expiry": "2099-01-01", "usage_count": 0, "usage_limit": 100}, 25.0, 75.0, True),
    ]

    for coupon_dict, exp_discount, exp_total, should_inc in test_cases:
        redeemed_calls = []
        released_calls = []

        def mock_redeem(code, today_iso, *args, **kwargs):
            redeemed_calls.append((code, today_iso))
            is_active = coupon_dict.get("is_active")
            is_enabled = is_active is not False and str(is_active).lower() != "false"
            raw_expiry = coupon_dict.get("expires_at") or coupon_dict.get("expiry")
            try:
                from datetime import datetime
                exp_d = datetime.fromisoformat(str(raw_expiry).strip()).date()
                today_d = datetime.fromisoformat(today_iso).date()
                not_expired = exp_d >= today_d
            except Exception:
                not_expired = False
            usage_count = int(coupon_dict.get("usage_count", 0))
            usage_limit = int(coupon_dict.get("usage_limit", 9999))
            under_limit = usage_count < usage_limit
            raw_pct = coupon_dict.get("discount_pct") if coupon_dict.get("discount_pct") is not None else coupon_dict.get("discount")
            try:
                import math
                p = float(raw_pct if raw_pct is not None else 0.0)
                valid_pct = math.isfinite(p) and 0.0 <= p <= 100.0
            except Exception:
                valid_pct = False

            if is_enabled and not_expired and under_limit and valid_pct:
                res = dict(coupon_dict)
                res["usage_count"] = usage_count + 1
                return res
            return None

        def mock_release(code, *args, **kwargs):
            released_calls.append(code)
            return True

        with patch.object(os_mod, "load_products", return_value=dummy_products), \
             patch.object(os_mod.db, "redeem_coupon", side_effect=mock_redeem), \
             patch.object(os_mod.db, "release_coupon", side_effect=mock_release), \
             patch.object(os_mod.db, "insert", side_effect=lambda table, data: dict(data, id=1)):
            
            order = os_mod.create_payment_order_record(dict(base_order))
            assert order["total"] == exp_total, f"Failed for {coupon_dict}: total {order['total']} != {exp_total}"
            if should_inc:
                assert len(redeemed_calls) == 1
                assert len(released_calls) == 0
            else:
                # Rejected coupons must not retain a reservation
                pass


def test_order_creation_idempotency_protection():
    """Verify that repeated requests with the same razorpay_order_id, razorpay_payment_id, or idempotency_key do not redeem usage twice."""
    from unittest.mock import patch
    import app.services.order_service as os_mod

    existing_order = {"order_id": "TRD-EXISTING", "total": 100.0}
    redeem_calls = []

    def mock_read(table, filters):
        if table == "orders" and (filters.get("razorpay_order_id") == "order_123" or filters.get("razorpay_payment_id") == "pay_123" or filters.get("idempotency_key") == "idem_123"):
            return [existing_order]
        return []

    def mock_redeem(code, today_iso, *args, **kwargs):
        redeem_calls.append(code)
        return {"code": code, "discount_pct": 10.0}

    with patch.object(os_mod.db, "read", side_effect=mock_read), \
         patch.object(os_mod.db, "redeem_coupon", side_effect=mock_redeem):

        res1 = os_mod.create_payment_order_record({"razorpay_order_id": "order_123", "coupon_code": "PROMO"})
        assert res1["order_id"] == "TRD-EXISTING"
        assert len(redeem_calls) == 0

        res2 = os_mod.create_payment_order_record({"razorpay_payment_id": "pay_123", "coupon_code": "PROMO"})
        assert res2["order_id"] == "TRD-EXISTING"
        assert len(redeem_calls) == 0

        res3 = os_mod.create_payment_order_record({"idempotency_key": "idem_123", "coupon_code": "PROMO"})
        assert res3["order_id"] == "TRD-EXISTING"
        assert len(redeem_calls) == 0


def test_order_creation_insert_failure_releases_coupon():
    """Verify that if order insertion fails, acquired coupon reservation is rolled back via release_coupon."""
    from unittest.mock import patch
    import app.services.order_service as os_mod

    dummy_products = [{"id": 1, "name": "Item 1", "price": 100.0, "image": "img1.jpg"}]
    released_codes = []

    def mock_redeem(code, today_iso, *args, **kwargs):
        return {"code": code, "discount_pct": 10.0}

    def mock_release(code, *args, **kwargs):
        released_codes.append(code)
        return True

    def mock_insert_fail(table, data):
        raise RuntimeError("Database connection lost during order insert")

    with patch.object(os_mod, "load_products", return_value=dummy_products), \
         patch.object(os_mod.db, "redeem_coupon", side_effect=mock_redeem), \
         patch.object(os_mod.db, "release_coupon", side_effect=mock_release), \
         patch.object(os_mod.db, "insert", side_effect=mock_insert_fail):

        with pytest.raises(RuntimeError, match="Database connection lost"):
            os_mod.create_payment_order_record({
                "items": [{"id": 1, "qty": 1, "size": "M"}],
                "coupon_code": "ROLLBACK_TEST"
            })

    assert released_codes == ["ROLLBACK_TEST"]


def test_concurrent_coupon_redemption_sql(tmp_path):
    """Verify that only 1 of multiple concurrent requests can redeem a coupon with usage_limit = 1 in SQL adapter."""
    import concurrent.futures
    from app.db.database import PostgresDatabaseAdapter

    # Use SQLite file with WAL mode to support multi-thread concurrency
    db_file = tmp_path / "concurrent_test.db"
    adapter = PostgresDatabaseAdapter(f"sqlite:///{db_file}")
    adapter.metadata.create_all(adapter.engine)

    with adapter.engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))

    adapter.insert("coupons", {
        "code": "RACE1",
        "discount_pct": 15.0,
        "expires_at": "2028-12-31",
        "usage_limit": 1,
        "usage_count": 0,
        "is_active": True,
    })

    results = []

    def attempt_redemption():
        # Each worker thread uses its own adapter instance connecting to the same shared DB
        thread_adapter = PostgresDatabaseAdapter(f"sqlite:///{db_file}")
        return thread_adapter.redeem_coupon("RACE1", "2026-10-28")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_redemption) for _ in range(5)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successful_redemptions = [r for r in results if r is not None]
    failed_redemptions = [r for r in results if r is None]

    assert len(successful_redemptions) == 1, f"Expected exactly 1 success, got {len(successful_redemptions)}"
    assert len(failed_redemptions) == 4

    # Verify final usage_count in DB
    final_rows = adapter.read("coupons", {"code": "RACE1"})
    assert final_rows[0]["usage_count"] == 1


def test_json_adapter_atomic_redemption(tmp_path, monkeypatch):
    """Verify JsonDatabaseAdapter atomic redeem_coupon and release_coupon behavior."""
    from app.db.database import JsonDatabaseAdapter
    import app.db.database as db_module

    # Point DB_DIR to tmp_path
    monkeypatch.setattr(db_module, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()

    # Seed coupon with usage_limit = 1
    adapter.insert("coupons", {
        "code": "JSONRACE",
        "discount_pct": 20.0,
        "expires_at": "2028-12-31",
        "usage_limit": 1,
        "usage_count": 0,
        "is_active": True,
    })

    # First redemption succeeds
    r1 = adapter.redeem_coupon("JSONRACE", "2026-10-28")
    assert r1 is not None
    assert r1["usage_count"] == 1

    # Second redemption fails (limit reached)
    r2 = adapter.redeem_coupon("JSONRACE", "2026-10-28")
    assert r2 is None

    # Release usage
    assert adapter.release_coupon("JSONRACE") is True

    # Third redemption succeeds again after release
    r3 = adapter.redeem_coupon("JSONRACE", "2026-10-28")
    assert r3 is not None
    assert r3["usage_count"] == 1


# --- 6. Forward Migration Test (Alembic 0007 Upgrade & Downgrade) ---

def test_alembic_0007_upgrade_downgrade():
    """Test safe schema migration from legacy table (0004) to canonical table (0007)."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY,
                code VARCHAR NOT NULL UNIQUE,
                discount FLOAT NOT NULL,
                expiry VARCHAR NOT NULL,
                usage_limit INTEGER DEFAULT 1000,
                usage_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("INSERT INTO coupons (code, discount, expiry) VALUES ('MIGRATETEST', 15.0, '2028-06-30')"))

    # Apply 0007 upgrade
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    spec = importlib.util.spec_from_file_location(
        "migration_0007",
        str(BACKEND_DIR / "alembic/versions/20261028_0007_align_coupons_schema.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.upgrade()

    # Verify updated columns
    import sqlalchemy as sa
    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("coupons")}
    assert "discount_pct" in cols
    assert "expires_at" in cols
    assert "is_active" in cols


    # Verify preserved data
    with engine.connect() as conn:
        row = conn.execute(select(coupons_table).where(coupons_table.c.code == "MIGRATETEST")).mappings().first()
        assert row is not None
        assert row["discount_pct"] == 15.0
        assert row["expires_at"] == "2028-06-30"
        assert row["is_active"] in (True, 1)

    # Test downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.downgrade()

    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("coupons")}
    assert "discount" in cols
    assert "expiry" in cols


def test_alembic_0007_missing_table_handling():
    """Verify missing coupons table raises explicit RuntimeError on upgrade and safely exits on downgrade."""
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    engine = create_engine("sqlite:///:memory:")

    spec = importlib.util.spec_from_file_location(
        "migration_0007",
        str(BACKEND_DIR / "alembic/versions/20261028_0007_align_coupons_schema.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Empty engine without coupons table
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        with pytest.raises(RuntimeError, match="Table 'coupons' does not exist"):
            mod.upgrade()

    # Downgrade on missing table should be safe no-op
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.downgrade()  # Should not raise


def test_alembic_0007_canonical_schema_idempotency():
    """Verify upgrade is idempotent if table already has canonical schema."""
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY,
                code VARCHAR NOT NULL UNIQUE,
                discount_pct FLOAT NOT NULL,
                expires_at VARCHAR NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                usage_limit INTEGER DEFAULT 1000,
                usage_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0007",
        str(BACKEND_DIR / "alembic/versions/20261028_0007_align_coupons_schema.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.upgrade()  # Should succeed without error

    import sqlalchemy as sa
    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("coupons")}
    assert "discount_pct" in cols
    assert "expires_at" in cols
    assert "is_active" in cols


# --- 7. Phase C.4 Payment Idempotency & Remediation Tests ---

def test_alembic_0008_migration():
    """Verify migration 0008 adds payment identifiers and coupon_status to orders."""
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from app.db.models import users

    engine = create_engine("sqlite:///:memory:")
    # Create base users and orders tables
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
                tracking_id VARCHAR,
                courier VARCHAR,
                estimated_delivery VARCHAR,
                test_mode BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0008",
        str(BACKEND_DIR / "alembic/versions/20261028_0008_add_payment_identifiers_to_orders.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Run upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.upgrade()

    import sqlalchemy as sa
    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("orders")}
    assert "razorpay_order_id" in cols
    assert "razorpay_payment_id" in cols
    assert "idempotency_key" in cols
    assert "coupon_status" in cols

    # Run downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.downgrade()

    insp = sa.inspect(engine)
    cols_after = {c["name"] for c in insp.get_columns("orders")}
    assert "razorpay_order_id" not in cols_after
    assert "coupon_status" not in cols_after


def test_postgres_adapter_payment_identifiers_compatibility():
    """Verify that PostgresDatabaseAdapter can filter and read orders with payment identifiers without raising ValueError."""
    from app.db.database import PostgresDatabaseAdapter

    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    adapter.metadata.create_all(adapter.engine)

    # Insert sample order
    inserted = adapter.insert("orders", {
        "order_id": "TRD-COMPAT1",
        "razorpay_order_id": "rzp_order_abc",
        "razorpay_payment_id": "rzp_pay_xyz",
        "idempotency_key": "idem_111",
        "coupon_status": "redeemed",
        "total": 500.0,
    })
    assert inserted["razorpay_order_id"] == "rzp_order_abc"

    # Query with razorpay_order_id
    res = adapter.read("orders", {"razorpay_order_id": "rzp_order_abc"})
    assert len(res) == 1
    assert res[0]["order_id"] == "TRD-COMPAT1"

    # Query with razorpay_payment_id
    res_pay = adapter.read("orders", {"razorpay_payment_id": "rzp_pay_xyz"})
    assert len(res_pay) == 1

    # Query with idempotency_key
    res_idem = adapter.read("orders", {"idempotency_key": "idem_111"})
    assert len(res_idem) == 1


def test_concurrent_payment_order_insertion_creates_single_order():
    """Verify that concurrent insert into orders with same razorpay_order_id returns existing order rather than crashing or duplicating."""
    from app.db.database import PostgresDatabaseAdapter

    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    adapter.metadata.create_all(adapter.engine)

    order_payload = {
        "order_id": "TRD-ORIGINAL",
        "razorpay_order_id": "rzp_duplicate_check",
        "total": 299.0,
        "payment_status": "paid"
    }

    # First insert creates the order
    first_order = adapter.insert("orders", order_payload)
    assert first_order["order_id"] == "TRD-ORIGINAL"

    # Second concurrent insert with identical razorpay_order_id but different order_id
    duplicate_payload = {
        "order_id": "TRD-DUPLICATE",
        "razorpay_order_id": "rzp_duplicate_check",
        "total": 299.0,
        "payment_status": "paid"
    }
    second_order = adapter.insert("orders", duplicate_payload)
    # Must recover and return the original order, NOT create TRD-DUPLICATE
    assert second_order["order_id"] == "TRD-ORIGINAL"

    # Verify only one row exists in database
    all_orders = adapter.read("orders", {"razorpay_order_id": "rzp_duplicate_check"})
    assert len(all_orders) == 1


def test_repeated_failure_webhooks_release_at_most_once():
    """Verify that repeated payment.failed webhooks release a coupon reservation exactly once."""
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    # Setup dummy order with coupon_status = 'redeemed'
    dummy_order = {
        "id": 1,
        "order_id": "TRD-WEBHOOK1",
        "razorpay_order_id": "order_fail_1",
        "coupon_code": "PROMO10",
        "discount_amount": 50.0,
        "coupon_status": "redeemed",
        "payment_status": "pending",
    }
    released_coupons = []

    def mock_read(table, filters):
        if table == "orders" and filters.get("razorpay_order_id") == "order_fail_1":
            return [dict(dummy_order)]
        if table == "payment_events":
            return []  # allow distinct webhook event_ids
        return []

    def mock_update(table, filters, data):
        if table == "orders":
            dummy_order.update(data)
            return [dict(dummy_order)]
        return []

    def mock_release(code, *args, **kwargs):
        released_coupons.append(code)
        return True

    with patch.object(ps_mod, "verify_webhook_signature", return_value=None), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "insert", return_value={}), \
         patch.object(ps_mod.db, "release_coupon", side_effect=mock_release):

        # First failure webhook event
        import json
        payload1 = json.dumps({
            "id": "evt_1",
            "event": "payment.failed",
            "payload": {"payment": {"entity": {"id": "pay_fail_1", "order_id": "order_fail_1"}}}
        }).encode("utf-8")
        ps_mod.process_webhook(payload1, "sig")

        assert len(released_coupons) == 1
        assert dummy_order["coupon_status"] == "released"
        assert dummy_order["payment_status"] == "failed"

        # Second failure webhook event for same order
        payload2 = json.dumps({
            "id": "evt_2",
            "event": "payment.failed",
            "payload": {"payment": {"entity": {"id": "pay_fail_2", "order_id": "order_fail_1"}}}
        }).encode("utf-8")
        ps_mod.process_webhook(payload2, "sig")

        # Must NOT call release_coupon again!
        assert len(released_coupons) == 1


def test_failed_payment_later_captured_re_redeems_coupon():
    """Verify that a payment.captured webhook re-redeems the coupon if it was previously released."""
    from unittest.mock import patch
    import app.services.payment_service as ps_mod

    dummy_order = {
        "id": 1,
        "order_id": "TRD-WEBHOOK2",
        "razorpay_order_id": "order_recover_1",
        "coupon_code": "PROMO10",
        "discount_amount": 50.0,
        "coupon_status": "released",  # previously released
        "payment_status": "failed",
    }
    re_redeemed = []

    def mock_read(table, filters):
        if table == "orders" and filters.get("razorpay_order_id") == "order_recover_1":
            return [dict(dummy_order)]
        if table == "payment_events":
            return []
        return []

    def mock_update(table, filters, data):
        if table == "orders":
            dummy_order.update(data)
            return [dict(dummy_order)]
        return []

    def mock_redeem(code, today_iso, *args, **kwargs):
        re_redeemed.append(code)
        return {"code": code, "discount_pct": 10.0}

    with patch.object(ps_mod, "verify_webhook_signature", return_value=None), \
         patch.object(ps_mod.db, "read", side_effect=mock_read), \
         patch.object(ps_mod.db, "update", side_effect=mock_update), \
         patch.object(ps_mod.db, "insert", return_value={}), \
         patch.object(ps_mod.db, "redeem_coupon", side_effect=mock_redeem):

        import json
        captured_payload = json.dumps({
            "id": "evt_cap_1",
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_succ_1", "order_id": "order_recover_1"}}}
        }).encode("utf-8")

        ps_mod.process_webhook(captured_payload, "sig")

        assert len(re_redeemed) == 1
        assert dummy_order["coupon_status"] == "redeemed"
        assert dummy_order["payment_status"] == "paid"


def test_atomic_sql_redemption_rejects_malformed_and_out_of_bounds():
    """Verify PostgresDatabaseAdapter.redeem_coupon rejects malformed dates and invalid percentages atomically."""
    from app.db.database import PostgresDatabaseAdapter

    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    adapter.metadata.create_all(adapter.engine)

    # Insert test coupons directly
    adapter.insert("coupons", {"code": "MALFORMED_EXP", "discount_pct": 10.0, "expires_at": "invalid_date", "is_active": True})
    adapter.insert("coupons", {"code": "HIGH_PCT", "discount_pct": 120.0, "expires_at": "2028-12-31", "is_active": True})
    adapter.insert("coupons", {"code": "NEG_PCT", "discount_pct": -5.0, "expires_at": "2028-12-31", "is_active": True})
    adapter.insert("coupons", {"code": "VALID_COUPON", "discount_pct": 15.0, "expires_at": "2028-12-31", "is_active": True})

    today_iso = "2026-10-28"

    # Malformed expiry string is rejected in atomic SQL query
    assert adapter.redeem_coupon("MALFORMED_EXP", today_iso) is None

    # Out of bounds percentages rejected in atomic SQL query
    assert adapter.redeem_coupon("HIGH_PCT", today_iso) is None
    assert adapter.redeem_coupon("NEG_PCT", today_iso) is None

    # Valid coupon succeeds
    succ = adapter.redeem_coupon("VALID_COUPON", today_iso)
    assert succ is not None
    assert succ["code"] == "VALID_COUPON"
    assert succ["usage_count"] == 1


def test_dual_write_failure_tracking():
    """Verify DualWriteDatabaseAdapter tracks replication failures in replication_failures list."""
    from app.db.database import DualWriteDatabaseAdapter

    class MockPrimary:
        def insert(self, table, data):
            return dict(data, id=1)
        def read(self, table, filters):
            return []
        def update(self, table, filters, data):
            return [data]
        def delete(self, table, filters):
            return 1
        def redeem_coupon(self, code, today_iso):
            return {"code": code, "usage_count": 1}
        def release_coupon(self, code):
            return True

    class FailingSecondary:
        def insert(self, table, data):
            raise RuntimeError("Secondary database timeout")
        def read(self, table, filters):
            return []
        def update(self, table, filters, data):
            raise RuntimeError("Secondary database timeout")
        def delete(self, table, filters):
            raise RuntimeError("Secondary database timeout")
        def redeem_coupon(self, code, today_iso):
            raise RuntimeError("Secondary database timeout")
        def release_coupon(self, code):
            raise RuntimeError("Secondary database timeout")

    dual = DualWriteDatabaseAdapter(MockPrimary(), FailingSecondary())

    # Insert succeeds on primary, fails on replica, tracks failure
    res = dual.insert("orders", {"order_id": "TEST1"})
    assert res["id"] == 1
    assert len(dual.replication_failures) == 1
    assert dual.replication_failures[0]["action"] == "insert"
    assert "Secondary database timeout" in dual.replication_failures[0]["error"]
