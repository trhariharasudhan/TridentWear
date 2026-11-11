"""Tests for fulfillment_status schema additions and Alembic migration 0010.

Tests run in-memory against SQLite and inspect SQLAlchemy metadata.
No real or application database is migrated or modified.
"""

import importlib.util
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from sqlalchemy import create_engine, text
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.db.models import orders, users, metadata


def test_orders_model_metadata_includes_fulfillment_status():
    """Verify SQLAlchemy Table definition for orders includes fulfillment_status."""
    assert "fulfillment_status" in orders.c
    col = orders.c.fulfillment_status
    assert col.name == "fulfillment_status"
    assert isinstance(col.type, sa.String)
    assert col.nullable is True
    assert col.default.arg == "pending"
    assert str(col.server_default.arg) == "pending"
    
    # Verify index presence in table indexes
    index_names = {idx.name for idx in orders.indexes}
    assert any("fulfillment_status" in idx.name for idx in orders.indexes)


def test_migration_0010_revision_chain():
    """Verify revision and down_revision match the actual chain from 0009."""
    spec_0009 = importlib.util.spec_from_file_location(
        "migration_0009",
        str(BACKEND_DIR / "alembic/versions/20261028_0009_add_fulfillment_statuses_to_orders.py")
    )
    mod_0009 = importlib.util.module_from_spec(spec_0009)
    spec_0009.loader.exec_module(mod_0009)

    spec_0010 = importlib.util.spec_from_file_location(
        "migration_0010",
        str(BACKEND_DIR / "alembic/versions/20261028_0010_add_fulfillment_status_to_orders.py")
    )
    mod_0010 = importlib.util.module_from_spec(spec_0010)
    spec_0010.loader.exec_module(mod_0010)

    assert mod_0009.revision == "20261028_0009"
    assert mod_0009.down_revision == "20261028_0008"

    assert mod_0010.revision == "20261028_0010"
    assert mod_0010.down_revision == mod_0009.revision
    assert mod_0010.branch_labels is None
    assert mod_0010.depends_on is None


def test_migration_0010_upgrade_and_downgrade():
    """Verify upgrade adds fulfillment_status and index, downgrade safely removes them."""
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
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
                stock_status VARCHAR,
                email_status VARCHAR,
                tracking_id VARCHAR,
                courier VARCHAR,
                estimated_delivery VARCHAR,
                test_mode BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0010",
        str(BACKEND_DIR / "alembic/versions/20261028_0010_add_fulfillment_status_to_orders.py")
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
    assert "fulfillment_status" in cols

    indexes = [idx["name"] for idx in insp.get_indexes("orders")]
    assert "ix_orders_fulfillment_status" in indexes

    # Verify existing rows can insert with default value
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO orders (order_id) VALUES ('ord_test_01')"))
        res = conn.execute(text("SELECT fulfillment_status FROM orders WHERE order_id = 'ord_test_01'")).fetchone()
        assert res[0] == "pending"

    # 2. Downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.downgrade()

    insp_after = sa.inspect(engine)
    cols_after = {c["name"] for c in insp_after.get_columns("orders")}
    assert "fulfillment_status" not in cols_after

    indexes_after = [idx["name"] for idx in insp_after.get_indexes("orders")]
    assert "ix_orders_fulfillment_status" not in indexes_after


def test_migration_0010_missing_table_handling():
    """Verify runtime error raised when orders table does not exist."""
    engine = create_engine("sqlite:///:memory:")

    spec = importlib.util.spec_from_file_location(
        "migration_0010",
        str(BACKEND_DIR / "alembic/versions/20261028_0010_add_fulfillment_status_to_orders.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        with pytest.raises(RuntimeError, match="Table 'orders' does not exist"):
            mod.upgrade()


def test_migration_0010_idempotent_upgrade():
    """Verify upgrade does not fail if column already exists."""
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                order_id VARCHAR NOT NULL UNIQUE,
                fulfillment_status VARCHAR DEFAULT 'pending'
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0010",
        str(BACKEND_DIR / "alembic/versions/20261028_0010_add_fulfillment_status_to_orders.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        # Should execute safely without error
        mod.upgrade()

    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("orders")}
    assert "fulfillment_status" in cols



def test_orders_model_metadata_includes_claim_fields():
    """Verify SQLAlchemy Table definition for orders includes claim fields and indexes."""
    for field in ("claim_token", "claim_expires_at", "claim_owner"):
        assert field in orders.c
        col = orders.c[field]
        assert col.nullable is True

    assert isinstance(orders.c.claim_token.type, sa.String)
    assert isinstance(orders.c.claim_expires_at.type, sa.DateTime)
    assert isinstance(orders.c.claim_owner.type, sa.String)

    index_names = {idx.name for idx in orders.indexes}
    assert any("claim_token" in idx.name for idx in orders.indexes)
    assert any("claim_expires_at" in idx.name for idx in orders.indexes)


def test_migration_0012_revision_chain():
    """Verify revision and down_revision match the actual chain from 0011."""
    spec_0011 = importlib.util.spec_from_file_location(
        "migration_0011",
        str(BACKEND_DIR / "alembic/versions/20261028_0011_add_coupon_redemptions_table.py")
    )
    mod_0011 = importlib.util.module_from_spec(spec_0011)
    spec_0011.loader.exec_module(mod_0011)

    spec_0012 = importlib.util.spec_from_file_location(
        "migration_0012",
        str(BACKEND_DIR / "alembic/versions/20261028_0012_add_order_claim_columns.py")
    )
    mod_0012 = importlib.util.module_from_spec(spec_0012)
    spec_0012.loader.exec_module(mod_0012)

    assert mod_0011.revision == "20261028_0011"
    assert mod_0012.revision == "20261028_0012"
    assert mod_0012.down_revision == mod_0011.revision
    assert mod_0012.branch_labels is None
    assert mod_0012.depends_on is None


def test_migration_0012_upgrade_and_downgrade():
    """Verify upgrade adds claim columns and indexes, downgrade safely removes them."""
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                order_id VARCHAR NOT NULL UNIQUE,
                fulfillment_status VARCHAR DEFAULT 'pending'
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0012",
        str(BACKEND_DIR / "alembic/versions/20261028_0012_add_order_claim_columns.py")
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
    assert "claim_token" in cols
    assert "claim_expires_at" in cols
    assert "claim_owner" in cols

    indexes = [idx["name"] for idx in insp.get_indexes("orders")]
    assert "ix_orders_claim_token" in indexes
    assert "ix_orders_claim_expires_at" in indexes

    # Verify existing rows can insert with NULL claim fields
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO orders (order_id) VALUES ('ord_claim_01')"))
        res = conn.execute(text("SELECT claim_token, claim_expires_at, claim_owner FROM orders WHERE order_id = 'ord_claim_01'")).fetchone()
        assert res[0] is None
        assert res[1] is None
        assert res[2] is None

    # 2. Downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.downgrade()

    insp_after = sa.inspect(engine)
    cols_after = {c["name"] for c in insp_after.get_columns("orders")}
    assert "claim_token" not in cols_after
    assert "claim_expires_at" not in cols_after
    assert "claim_owner" not in cols_after

    indexes_after = [idx["name"] for idx in insp_after.get_indexes("orders")]
    assert "ix_orders_claim_token" not in indexes_after
    assert "ix_orders_claim_expires_at" not in indexes_after


def test_migration_0012_missing_table_handling():
    """Verify runtime error raised when orders table does not exist."""
    engine = create_engine("sqlite:///:memory:")

    spec = importlib.util.spec_from_file_location(
        "migration_0012",
        str(BACKEND_DIR / "alembic/versions/20261028_0012_add_order_claim_columns.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        with pytest.raises(RuntimeError, match="Table 'orders' does not exist"):
            mod.upgrade()


def test_migration_0012_idempotent_upgrade():
    """Verify upgrade does not fail if columns already exist."""
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                order_id VARCHAR NOT NULL UNIQUE,
                claim_token VARCHAR,
                claim_expires_at DATETIME,
                claim_owner VARCHAR
            )
        """))

    spec = importlib.util.spec_from_file_location(
        "migration_0012",
        str(BACKEND_DIR / "alembic/versions/20261028_0012_add_order_claim_columns.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        mod.op._proxy = Operations(ctx)
        mod.upgrade()

    insp = sa.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("orders")}
    assert "claim_token" in cols
    assert "claim_expires_at" in cols
    assert "claim_owner" in cols
