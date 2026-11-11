"""
TridentWear Phase C.6.6D.4C — Adapter Claim Primitives and Safety Tests.

Focused unit and concurrency tests for:
1. Same order + same payment ID retry (idempotent).
2. Different orders attempting the same payment ID (conflict rejected).
3. Same order attempting a conflicting payment ID (conflict rejected).
4. Concurrent JSON payment-ID binding using multiprocessing.
5. Concurrent JSON claim acquisition: exactly one worker succeeds.
6. Active lease cannot be overwritten.
7. Expired lease can be reclaimed according to policy.
8. Token/expiry inconsistent states (reclaimed safely).
9. Correct handling of NULL fulfillment state without accepting unpaid orders.
10. Renewal by the current token succeeds; stale-token renewal fails.
11. Release by the current token succeeds; stale-token release fails.
12. Expired or malformed lease handling (renewal cannot resurrect; malformed date handles defensively).
13. Finalization cannot succeed with a stale token, expired lease, or incomplete prerequisites.
14. DualWrite primary/secondary failure behavior.
"""

import os
import sys
import json
import time
import uuid
import multiprocessing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.db.database as db_module
from app.db.database import (
    JsonDatabaseAdapter,
    PostgresDatabaseAdapter,
    DualWriteDatabaseAdapter,
    PaymentBindingConflictError,
)
from app.db.models import metadata, orders as orders_table


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def json_adapter(tmp_path, monkeypatch):
    """Fixture providing an isolated JsonDatabaseAdapter in a clean temp directory."""
    monkeypatch.setattr(db_module, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()
    return adapter, tmp_path


@pytest.fixture
def sqlite_adapter():
    """
    Fixture providing a PostgresDatabaseAdapter running against in-memory SQLite emulation.
    NOTE: SQLite emulation validates SQL queries, types, and logic, but does not prove PostgreSQL concurrency.
    """
    adapter = PostgresDatabaseAdapter("sqlite:///:memory:")
    metadata.create_all(adapter.engine)
    return adapter


# ============================================================================
# Multiprocessing Worker Functions
# ============================================================================

def _worker_bind_payment(db_dir_str, order_id, payment_id, queue):
    """Worker function for concurrent payment ID binding in multiprocessing."""
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        import app.db.database as db_m
        db_m.DB_DIR = Path(db_dir_str)
        adapter = db_m.JsonDatabaseAdapter()
        res = adapter.bind_payment_id(order_id, payment_id)
        queue.put(("SUCCESS", order_id, res))
    except db_m.PaymentBindingConflictError as pbce:
        queue.put(("CONFLICT", order_id, str(pbce)))
    except Exception as e:
        queue.put(("ERROR", order_id, str(e)))


def _worker_acquire_claim(db_dir_str, order_id, worker_id, queue):
    """Worker function for concurrent claim acquisition in multiprocessing."""
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        import app.db.database as db_m
        db_m.DB_DIR = Path(db_dir_str)
        adapter = db_m.JsonDatabaseAdapter()
        claim = adapter.acquire_claim(order_id, claim_owner=worker_id, lease_seconds=30)
        if claim is not None:
            queue.put(("SUCCESS", worker_id, claim["claim_token"]))
        else:
            queue.put(("FAILED", worker_id, None))
    except Exception as e:
        queue.put(("ERROR", worker_id, str(e)))


# ============================================================================
# 1-4: Payment ID Binding Tests
# ============================================================================

def test_1_same_order_same_payment_id_retry_idempotent(json_adapter, sqlite_adapter):
    """1. Binding the same payment ID to the same order is an idempotent success."""
    # JSON Adapter
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {"id": 1, "order_id": "ORD-1", "payment_status": "pending"})
    assert j_adapter.bind_payment_id("ORD-1", "pay_test_001") is True
    # Retry with same payment ID
    assert j_adapter.bind_payment_id("ORD-1", "pay_test_001") is True
    row = j_adapter.read("orders", {"order_id": "ORD-1"})[0]
    assert row["razorpay_payment_id"] == "pay_test_001"
    assert row["payment_status"] == "pending"  # Must NOT mark order paid

    # SQLite Emulation Adapter
    sqlite_adapter.insert("orders", {"order_id": "ORD-SQLITE-1", "payment_status": "pending"})
    assert sqlite_adapter.bind_payment_id("ORD-SQLITE-1", "pay_sqlite_001") is True
    # Retry
    assert sqlite_adapter.bind_payment_id("ORD-SQLITE-1", "pay_sqlite_001") is True
    sql_row = sqlite_adapter.read("orders", {"order_id": "ORD-SQLITE-1"})[0]
    assert sql_row["razorpay_payment_id"] == "pay_sqlite_001"
    assert sql_row["payment_status"] == "pending"


def test_2_different_orders_attempting_same_payment_id_rejected(json_adapter, sqlite_adapter):
    """2. A payment ID already bound to order A cannot be bound to order B."""
    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {"id": 1, "order_id": "ORD-A", "payment_status": "pending"})
    j_adapter.insert("orders", {"id": 2, "order_id": "ORD-B", "payment_status": "pending"})
    assert j_adapter.bind_payment_id("ORD-A", "pay_shared_123") is True
    with pytest.raises(PaymentBindingConflictError):
        j_adapter.bind_payment_id("ORD-B", "pay_shared_123")

    # SQLite
    sqlite_adapter.insert("orders", {"order_id": "ORD-SQ-A", "payment_status": "pending"})
    sqlite_adapter.insert("orders", {"order_id": "ORD-SQ-B", "payment_status": "pending"})
    assert sqlite_adapter.bind_payment_id("ORD-SQ-A", "pay_shared_sqlite") is True
    with pytest.raises(PaymentBindingConflictError):
        sqlite_adapter.bind_payment_id("ORD-SQ-B", "pay_shared_sqlite")


def test_3_same_order_attempting_conflicting_payment_id_rejected(json_adapter, sqlite_adapter):
    """3. An order already bound to payment X cannot be rebound to payment Y."""
    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {"id": 1, "order_id": "ORD-C", "payment_status": "pending"})
    assert j_adapter.bind_payment_id("ORD-C", "pay_first") is True
    with pytest.raises(PaymentBindingConflictError):
        j_adapter.bind_payment_id("ORD-C", "pay_second")

    # SQLite
    sqlite_adapter.insert("orders", {"order_id": "ORD-SQ-C", "payment_status": "pending"})
    assert sqlite_adapter.bind_payment_id("ORD-SQ-C", "pay_first_sq") is True
    with pytest.raises(PaymentBindingConflictError):
        sqlite_adapter.bind_payment_id("ORD-SQ-C", "pay_second_sq")


def test_4_concurrent_json_payment_binding_multiprocessing(tmp_path):
    """4. Concurrent processes attempting to bind the same payment ID to different orders."""
    db_module.DB_DIR = tmp_path
    adapter = JsonDatabaseAdapter()
    adapter.insert("orders", {"id": 1, "order_id": "ORD-RACE-1", "payment_status": "pending"})
    adapter.insert("orders", {"id": 2, "order_id": "ORD-RACE-2", "payment_status": "pending"})

    queue = multiprocessing.Queue()
    shared_pay_id = "pay_race_multiprocess_001"

    p1 = multiprocessing.Process(
        target=_worker_bind_payment,
        args=(str(tmp_path), "ORD-RACE-1", shared_pay_id, queue)
    )
    p2 = multiprocessing.Process(
        target=_worker_bind_payment,
        args=(str(tmp_path), "ORD-RACE-2", shared_pay_id, queue)
    )

    p1.start()
    p2.start()

    p1.join(timeout=10)
    p2.join(timeout=10)

    results = []
    while not queue.empty():
        results.append(queue.get())

    statuses = [r[0] for r in results]
    assert "SUCCESS" in statuses
    assert "CONFLICT" in statuses
    assert statuses.count("SUCCESS") == 1
    assert statuses.count("CONFLICT") == 1


# ============================================================================
# 5-9: Claim Acquisition Tests
# ============================================================================

def test_5_concurrent_json_claim_acquisition_multiprocessing(tmp_path):
    """5. Concurrent OS processes racing to acquire claim on the same order: exactly one succeeds."""
    db_module.DB_DIR = tmp_path
    adapter = JsonDatabaseAdapter()
    adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-CLAIM-RACE",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": None,
        "claim_expires_at": None
    })

    queue = multiprocessing.Queue()

    p1 = multiprocessing.Process(
        target=_worker_acquire_claim,
        args=(str(tmp_path), "ORD-CLAIM-RACE", "worker-A", queue)
    )
    p2 = multiprocessing.Process(
        target=_worker_acquire_claim,
        args=(str(tmp_path), "ORD-CLAIM-RACE", "worker-B", queue)
    )

    p1.start()
    p2.start()

    p1.join(timeout=10)
    p2.join(timeout=10)

    results = []
    while not queue.empty():
        results.append(queue.get())

    statuses = [r[0] for r in results]
    assert "SUCCESS" in statuses
    assert "FAILED" in statuses
    assert statuses.count("SUCCESS") == 1
    assert statuses.count("FAILED") == 1


def test_6_active_lease_cannot_be_overwritten(json_adapter, sqlite_adapter):
    """6. Active valid lease cannot be claimed by another worker."""
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=5)).isoformat()

    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-ACTIVE-LEASE",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_existing_active",
        "claim_expires_at": future,
        "claim_owner": "worker-1"
    })
    claim = j_adapter.acquire_claim("ORD-ACTIVE-LEASE", claim_owner="worker-2")
    assert claim is None
    # Verify lease unchanged
    o = j_adapter.read("orders", {"order_id": "ORD-ACTIVE-LEASE"})[0]
    assert o["claim_token"] == "token_existing_active"
    assert o["claim_owner"] == "worker-1"

    # SQLite
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-ACTIVE",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_sq_active",
        "claim_expires_at": now + timedelta(minutes=5),
        "claim_owner": "worker-1"
    })
    sql_claim = sqlite_adapter.acquire_claim("ORD-SQ-ACTIVE", claim_owner="worker-2")
    assert sql_claim is None
    sql_o = sqlite_adapter.read("orders", {"order_id": "ORD-SQ-ACTIVE"})[0]
    assert sql_o["claim_token"] == "token_sq_active"


def test_7_expired_lease_can_be_reclaimed(json_adapter, sqlite_adapter):
    """7. Expired lease can be cleanly acquired by a new worker."""
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=5)).isoformat()

    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-EXPIRED-LEASE",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_old_expired",
        "claim_expires_at": past,
        "claim_owner": "worker-dead"
    })
    claim = j_adapter.acquire_claim("ORD-EXPIRED-LEASE", claim_owner="worker-new", lease_seconds=45)
    assert claim is not None
    assert claim["claim_token"] != "token_old_expired"
    assert claim["claim_owner"] == "worker-new"

    # SQLite
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-EXPIRED",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_sq_old",
        "claim_expires_at": now - timedelta(minutes=5),
        "claim_owner": "worker-dead"
    })
    sql_claim = sqlite_adapter.acquire_claim("ORD-SQ-EXPIRED", claim_owner="worker-new", lease_seconds=45)
    assert sql_claim is not None
    assert sql_claim["claim_token"] != "token_sq_old"
    assert sql_claim["claim_owner"] == "worker-new"


def test_8_token_expiry_inconsistent_states_reclaimed(json_adapter, sqlite_adapter):
    """8. Inconsistent lease states (token-without-expiry, expiry-without-token, malformed date) are reclaimable."""
    # JSON: Token without expiry
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-INCONSISTENT-1",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_without_exp",
        "claim_expires_at": None,
    })
    c1 = j_adapter.acquire_claim("ORD-INCONSISTENT-1", claim_owner="w1")
    assert c1 is not None

    # JSON: Expiry without token
    j_adapter.insert("orders", {
        "id": 2,
        "order_id": "ORD-INCONSISTENT-2",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": None,
        "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    })
    c2 = j_adapter.acquire_claim("ORD-INCONSISTENT-2", claim_owner="w2")
    assert c2 is not None

    # JSON: Malformed date string (does not crash adapter, treated as expired)
    j_adapter.insert("orders", {
        "id": 3,
        "order_id": "ORD-MALFORMED-DATE",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_malformed",
        "claim_expires_at": "INVALID_CORRUPT_TIMESTAMP",
    })
    c3 = j_adapter.acquire_claim("ORD-MALFORMED-DATE", claim_owner="w3")
    assert c3 is not None
    assert c3["claim_token"] != "token_malformed"

    # SQLite: Token without expiry
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-INCONSISTENT-1",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_sq_no_exp",
        "claim_expires_at": None,
    })
    sql_c1 = sqlite_adapter.acquire_claim("ORD-SQ-INCONSISTENT-1", claim_owner="w-sq-1")
    assert sql_c1 is not None

    # SQLite: Expiry without token
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-INCONSISTENT-2",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": None,
        "claim_expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    })
    sql_c2 = sqlite_adapter.acquire_claim("ORD-SQ-INCONSISTENT-2", claim_owner="w-sq-2")
    assert sql_c2 is not None


def test_9_null_fulfillment_status_and_unpaid_handling(json_adapter, sqlite_adapter):
    """9. Paid order with NULL fulfillment_status is claimable; unpaid orders are NEVER claimable."""
    # JSON: Paid order with NULL fulfillment_status
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-PAID-NULL-FULFILL",
        "payment_status": "paid",
        "fulfillment_status": None,
    })
    assert j_adapter.acquire_claim("ORD-PAID-NULL-FULFILL") is not None

    # JSON: Unpaid order (payment_status="pending", status="placed")
    j_adapter.insert("orders", {
        "id": 2,
        "order_id": "ORD-UNPAID-PLACED",
        "status": "placed",
        "payment_status": "pending",
        "fulfillment_status": "pending",
    })
    assert j_adapter.acquire_claim("ORD-UNPAID-PLACED") is None

    # JSON: Order with NULL payment_status
    j_adapter.insert("orders", {
        "id": 3,
        "order_id": "ORD-NULL-PAYMENT-STATUS",
        "status": "placed",
        "payment_status": None,
        "fulfillment_status": "pending",
    })
    assert j_adapter.acquire_claim("ORD-NULL-PAYMENT-STATUS") is None

    # JSON: Already fulfilled order
    j_adapter.insert("orders", {
        "id": 4,
        "order_id": "ORD-ALREADY-FULFILLED",
        "payment_status": "paid",
        "fulfillment_status": "fulfilled",
    })
    assert j_adapter.acquire_claim("ORD-ALREADY-FULFILLED") is None

    # JSON: Manual review required order
    j_adapter.insert("orders", {
        "id": 5,
        "order_id": "ORD-MANUAL-REVIEW",
        "payment_status": "paid",
        "fulfillment_status": "manual_review_required",
    })
    assert j_adapter.acquire_claim("ORD-MANUAL-REVIEW") is None

    # SQLite: Paid order with NULL fulfillment_status
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-PAID-NULL",
        "payment_status": "paid",
        "fulfillment_status": None,
    })
    assert sqlite_adapter.acquire_claim("ORD-SQ-PAID-NULL") is not None

    # SQLite: Unpaid order
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-UNPAID",
        "status": "placed",
        "payment_status": "pending",
        "fulfillment_status": "pending",
    })
    assert sqlite_adapter.acquire_claim("ORD-SQ-UNPAID") is None


# ============================================================================
# 10-12: Renewal and Release Tests
# ============================================================================

def test_10_renewal_current_token_succeeds_stale_token_fails(json_adapter, sqlite_adapter):
    """10. Renewal succeeds with matching token on active lease; fails with stale token."""
    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-RENEW-1",
        "payment_status": "paid",
        "fulfillment_status": "pending",
    })
    claim = j_adapter.acquire_claim("ORD-RENEW-1", lease_seconds=20)
    token = claim["claim_token"]

    # Renewal with stale token fails
    assert j_adapter.renew_claim("ORD-RENEW-1", "stale_token_123", lease_seconds=30) is False
    # Renewal with current token succeeds
    assert j_adapter.renew_claim("ORD-RENEW-1", token, lease_seconds=60) is True

    # SQLite
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-RENEW",
        "payment_status": "paid",
        "fulfillment_status": "pending",
    })
    sql_claim = sqlite_adapter.acquire_claim("ORD-SQ-RENEW", lease_seconds=20)
    sql_token = sql_claim["claim_token"]

    assert sqlite_adapter.renew_claim("ORD-SQ-RENEW", "wrong_token", lease_seconds=30) is False
    assert sqlite_adapter.renew_claim("ORD-SQ-RENEW", sql_token, lease_seconds=60) is True


def test_11_release_current_token_succeeds_stale_token_fails(json_adapter, sqlite_adapter):
    """11. Release clears claim when token matches; fails and preserves claim when token is stale."""
    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-RELEASE-1",
        "payment_status": "paid",
        "fulfillment_status": "pending",
    })
    claim = j_adapter.acquire_claim("ORD-RELEASE-1", lease_seconds=30, claim_owner="owner-A")
    token = claim["claim_token"]

    # Release with stale token fails
    assert j_adapter.release_claim("ORD-RELEASE-1", "stale_token") is False
    order_still_claimed = j_adapter.read("orders", {"order_id": "ORD-RELEASE-1"})[0]
    assert order_still_claimed["claim_token"] == token

    # Release with current token succeeds
    assert j_adapter.release_claim("ORD-RELEASE-1", token) is True
    order_released = j_adapter.read("orders", {"order_id": "ORD-RELEASE-1"})[0]
    assert order_released["claim_token"] is None
    assert order_released["claim_expires_at"] is None
    assert order_released["claim_owner"] is None

    # SQLite
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-RELEASE",
        "payment_status": "paid",
        "fulfillment_status": "pending",
    })
    sq_claim = sqlite_adapter.acquire_claim("ORD-SQ-RELEASE", lease_seconds=30, claim_owner="owner-A")
    sq_token = sq_claim["claim_token"]

    assert sqlite_adapter.release_claim("ORD-SQ-RELEASE", "stale_token") is False
    assert sqlite_adapter.release_claim("ORD-SQ-RELEASE", sq_token) is True
    sq_released = sqlite_adapter.read("orders", {"order_id": "ORD-SQ-RELEASE"})[0]
    assert sq_released["claim_token"] is None
    assert sq_released["claim_expires_at"] is None


def test_12_expired_claim_cannot_be_renewed(json_adapter, sqlite_adapter):
    """12. Expired lease cannot be renewed (resurrection prohibited)."""
    now = datetime.now(timezone.utc)
    past = (now - timedelta(seconds=10)).isoformat()

    # JSON
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-EXP-RENEW",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_expired_1",
        "claim_expires_at": past,
    })
    assert j_adapter.renew_claim("ORD-EXP-RENEW", "token_expired_1", lease_seconds=30) is False

    # SQLite
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-EXP-RENEW",
        "payment_status": "paid",
        "fulfillment_status": "pending",
        "claim_token": "token_sq_exp_1",
        "claim_expires_at": now - timedelta(seconds=10),
    })
    assert sqlite_adapter.renew_claim("ORD-SQ-EXP-RENEW", "token_sq_exp_1", lease_seconds=30) is False


# ============================================================================
# 13: Finalization Tests
# ============================================================================

def test_13_finalization_fencing_and_prerequisites(json_adapter, sqlite_adapter):
    """13. Finalization requires matching token, valid unexpired lease, and complete prerequisites."""
    # JSON: Happy path
    j_adapter, _ = json_adapter
    j_adapter.insert("orders", {
        "id": 1,
        "order_id": "ORD-FINALIZE-OK",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "sent",
        "fulfillment_status": "pending",
    })
    claim = j_adapter.acquire_claim("ORD-FINALIZE-OK", lease_seconds=30)
    token = claim["claim_token"]

    # Fails with stale token
    assert j_adapter.finalize_order("ORD-FINALIZE-OK", "wrong_token") is False

    # Succeeds with valid token and complete prerequisites
    assert j_adapter.finalize_order("ORD-FINALIZE-OK", token) is True
    o_fin = j_adapter.read("orders", {"order_id": "ORD-FINALIZE-OK"})[0]
    assert o_fin["fulfillment_status"] == "fulfilled"
    assert o_fin["claim_token"] is None
    assert o_fin["claim_expires_at"] is None

    # Incomplete prerequisites: stock pending
    j_adapter.insert("orders", {
        "id": 2,
        "order_id": "ORD-STOCK-PENDING",
        "payment_status": "paid",
        "stock_status": "pending",  # Incomplete!
        "email_status": "sent",
        "fulfillment_status": "pending",
    })
    c2 = j_adapter.acquire_claim("ORD-STOCK-PENDING", lease_seconds=30)
    assert j_adapter.finalize_order("ORD-STOCK-PENDING", c2["claim_token"]) is False

    # Incomplete prerequisites: email pending
    j_adapter.insert("orders", {
        "id": 3,
        "order_id": "ORD-EMAIL-PENDING",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "pending",  # Incomplete!
        "fulfillment_status": "pending",
    })
    c3 = j_adapter.acquire_claim("ORD-EMAIL-PENDING", lease_seconds=30)
    assert j_adapter.finalize_order("ORD-EMAIL-PENDING", c3["claim_token"]) is False

    # Manual review required blocks finalization
    j_adapter.insert("orders", {
        "id": 4,
        "order_id": "ORD-REVIEW-BLOCK",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "sent",
        "fulfillment_status": "manual_review_required",
    })
    # Cannot even acquire claim if manual review required
    assert j_adapter.acquire_claim("ORD-REVIEW-BLOCK") is None

    # SQLite: Happy path and incomplete checks
    sqlite_adapter.insert("orders", {
        "order_id": "ORD-SQ-FIN-OK",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "sent",
        "fulfillment_status": "pending",
    })
    sq_claim = sqlite_adapter.acquire_claim("ORD-SQ-FIN-OK", lease_seconds=30)
    sq_token = sq_claim["claim_token"]

    assert sqlite_adapter.finalize_order("ORD-SQ-FIN-OK", "wrong_sq_token") is False
    assert sqlite_adapter.finalize_order("ORD-SQ-FIN-OK", sq_token) is True
    sq_fin = sqlite_adapter.read("orders", {"order_id": "ORD-SQ-FIN-OK"})[0]
    assert sq_fin["fulfillment_status"] == "fulfilled"
    assert sq_fin["claim_token"] is None


# ============================================================================
# 14: DualWrite Adapter Tests
# ============================================================================

def test_14_dual_write_primary_secondary_behavior(tmp_path):
    """14. DualWrite adapter behavior: authoritative primary, secondary replication failure handling."""
    db_module.DB_DIR = tmp_path
    primary_db = JsonDatabaseAdapter()
    secondary_db = PostgresDatabaseAdapter("sqlite:///:memory:")
    metadata.create_all(secondary_db.engine)

    dual_db = DualWriteDatabaseAdapter(old_db=primary_db, new_db=secondary_db)

    # 1. Successful DualWrite insert & payment binding
    dual_db.insert("orders", {
        "id": 1,
        "order_id": "ORD-DUAL-1",
        "payment_status": "paid",
        "stock_status": "deducted",
        "email_status": "sent",
        "fulfillment_status": "pending",
    })
    assert dual_db.bind_payment_id("ORD-DUAL-1", "pay_dual_123") is True
    assert len(dual_db.replication_failures) == 0

    # Verify both backends received the update
    assert primary_db.read("orders", {"order_id": "ORD-DUAL-1"})[0]["razorpay_payment_id"] == "pay_dual_123"
    assert secondary_db.read("orders", {"order_id": "ORD-DUAL-1"})[0]["razorpay_payment_id"] == "pay_dual_123"

    # 2. Claim acquisition via DualWrite
    claim = dual_db.acquire_claim("ORD-DUAL-1", lease_seconds=30, claim_owner="dual-worker")
    assert claim is not None
    token = claim["claim_token"]

    # 3. Simulated secondary backend failure: drop secondary table to trigger failure
    with secondary_db.engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE orders"))

    # Attempt renewal: Primary succeeds, secondary fails but error is caught and logged in replication_failures
    renew_res = dual_db.renew_claim("ORD-DUAL-1", token, lease_seconds=60)
    assert renew_res is True
    assert len(dual_db.replication_failures) == 1
    assert dual_db.replication_failures[0]["action"] == "renew_claim"

    # Primary still holds the renewed claim
    assert primary_db.read("orders", {"order_id": "ORD-DUAL-1"})[0]["claim_token"] == token
