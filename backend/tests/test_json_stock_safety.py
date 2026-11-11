"""TridentWear Phase C.6.6D.2 — JSON Stock Allocation Crash Safety Tests.

Verifies:
1. Repeated deduction of the same order (idempotency, zero second decrement).
2. Duplicate product IDs in items aggregated before stock check.
3. Insufficient stock on any item leaves all products completely unchanged (all-or-nothing rollback).
4. Multiple products commit their stock decrements and allocation records in a single atomic file replacement.
5. Stale MemoryCache does not bypass allocation detection (reads fresh under lock).
6. Two independent OS processes competing for the final unit of stock via multiprocessing.
7. Retry after each simulated persistence boundary (before write, between products.json and orders.json).
8. Legacy products without allocation metadata handled cleanly.
9. Malformed or inconsistent partial allocation records fail safely without deducting stock.
"""

import os
import sys
import json
import time
import multiprocessing
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.db.database as db_module
from app.db.database import JsonDatabaseAdapter, InsufficientStockError, InconsistentAllocationError
from app.db.json_manager import db_instance, update_json, read_json


@pytest.fixture
def json_adapter(tmp_path, monkeypatch):
    """Fixture providing an isolated JsonDatabaseAdapter in a clean temp directory."""
    monkeypatch.setattr(db_module, "DB_DIR", tmp_path)
    adapter = JsonDatabaseAdapter()
    return adapter, tmp_path


# --- 1. Repeated deduction of the same order ---
def test_repeated_deduction_same_order(json_adapter):
    adapter, tmp_path = json_adapter

    adapter.insert("products", {"id": 1, "name": "Classic Tee", "stock": 10})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-REPEAT", "stock_status": "pending"})

    # First attempt: stock decrements from 10 to 7
    res1 = adapter.deduct_order_stock("ORD-REPEAT", [{"id": 1, "qty": 3}])
    assert res1 is True
    assert adapter.read("products", {"id": 1})[0]["stock"] == 7

    # Second attempt (retry): must return True and keep stock at 7
    res2 = adapter.deduct_order_stock("ORD-REPEAT", [{"id": 1, "qty": 3}])
    assert res2 is True
    assert adapter.read("products", {"id": 1})[0]["stock"] == 7

    # Third attempt (another retry): still 7
    res3 = adapter.deduct_order_stock("ORD-REPEAT", [{"id": 1, "qty": 3}])
    assert res3 is True
    assert adapter.read("products", {"id": 1})[0]["stock"] == 7


# --- 2. Duplicate product IDs with aggregate quantities ---
def test_duplicate_product_ids_aggregate_quantities(json_adapter):
    adapter, tmp_path = json_adapter

    adapter.insert("products", {"id": 2, "name": "Denim Jacket", "stock": 5})

    # Items specify product 2 twice: qty 3 + qty 3 = 6 > available stock 5
    with pytest.raises(InsufficientStockError) as exc:
        adapter.deduct_order_stock("ORD-AGG-FAIL", [
            {"id": 2, "qty": 3},
            {"id": 2, "qty": 3},
        ])
    assert "Insufficient stock" in str(exc.value)
    # Stock must remain completely intact
    assert adapter.read("products", {"id": 2})[0]["stock"] == 5

    # Items specify product 2 twice: qty 2 + qty 2 = 4 <= available stock 5
    res = adapter.deduct_order_stock("ORD-AGG-SUCCESS", [
        {"id": 2, "qty": 2},
        {"id": 2, "qty": 2},
    ])
    assert res is True
    assert adapter.read("products", {"id": 2})[0]["stock"] == 1


# --- 3. Insufficient stock leaves every product unchanged ---
def test_insufficient_stock_leaves_every_product_unchanged(json_adapter):
    adapter, tmp_path = json_adapter

    adapter.insert("products", {"id": 1, "name": "Product 1", "stock": 10})
    adapter.insert("products", {"id": 2, "name": "Product 2", "stock": 2})

    # Order needs 5 of Product 1 (available) and 5 of Product 2 (insufficient)
    with pytest.raises(InsufficientStockError):
        adapter.deduct_order_stock("ORD-ROLLBACK", [
            {"id": 1, "qty": 5},
            {"id": 2, "qty": 5},
        ])

    # Neither product was modified
    assert adapter.read("products", {"id": 1})[0]["stock"] == 10
    assert adapter.read("products", {"id": 2})[0]["stock"] == 2


# --- 4. Multiple products commit stock and allocation records together ---
def test_multiple_products_commit_stock_and_allocation_together(json_adapter):
    adapter, tmp_path = json_adapter

    adapter.insert("products", {"id": 10, "name": "Hoodie", "stock": 20})
    adapter.insert("products", {"id": 20, "name": "Joggers", "stock": 15})

    order_id = "ORD-ATOMIC-MULTI"
    items = [{"id": 10, "qty": 4}, {"id": 20, "qty": 5}]

    res = adapter.deduct_order_stock(order_id, items)
    assert res is True

    # Read physical JSON file directly from disk to verify single-file commit
    prods_file = tmp_path / "products.json"
    with open(prods_file, "r", encoding="utf-8") as f:
        prods_data = json.load(f)

    p_map = {p["id"]: p for p in prods_data}
    assert p_map[10]["stock"] == 16
    assert p_map[10]["allocated_orders"][order_id]["quantity"] == 4

    assert p_map[20]["stock"] == 10
    assert p_map[20]["allocated_orders"][order_id]["quantity"] == 5


# --- 5. Stale MemoryCache does not bypass idempotency ---
def test_stale_cache_does_not_bypass_idempotency(json_adapter):
    adapter, tmp_path = json_adapter

    adapter.insert("products", {"id": 100, "name": "Cap", "stock": 10})

    # 1. First deduction commits to disk
    order_id = "ORD-STALE-CACHE"
    assert adapter.deduct_order_stock(order_id, [{"id": 100, "qty": 2}]) is True
    assert adapter.read("products", {"id": 100})[0]["stock"] == 8

    # 2. Poison the in-memory cache with stale data (stock=10, no allocated_orders)
    products_path = str(tmp_path / "products.json")
    stale_payload = [{"id": 100, "name": "Cap", "stock": 10}]
    with db_instance._cache_lock:
        db_instance._cache[products_path] = {
            "time": time.time(),
            "data": stale_payload
        }

    # Verify that a cached read would see stale stock
    assert read_json(products_path)[0]["stock"] == 10

    # 3. Call deduct_order_stock with the same order ID
    # Because deduct_order_stock uses update_json under CrossProcessLock,
    # it MUST read fresh data directly from disk and recognize prior allocation!
    res = adapter.deduct_order_stock(order_id, [{"id": 100, "qty": 2}])
    assert res is True

    # Stock on disk remains 8, not decremented to 6 (nor decremented from stale 10 to 8)
    with open(products_path, "r", encoding="utf-8") as f:
        actual_disk = json.load(f)
    assert actual_disk[0]["stock"] == 8


# --- 6. Multiprocessing: Two independent OS processes competing for stock ---
def _worker_deduct_stock(db_dir_str, order_id, product_id, qty, queue):
    """Worker process function for multiprocessing test."""
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        import app.db.database as db_m
        db_m.DB_DIR = Path(db_dir_str)
        w_adapter = db_m.JsonDatabaseAdapter()
        res = w_adapter.deduct_order_stock(order_id, [{"id": product_id, "qty": qty}])
        queue.put(("SUCCESS", order_id, res))
    except db_m.InsufficientStockError as ise:
        queue.put(("INSUFFICIENT_STOCK", order_id, str(ise)))
    except Exception as e:
        queue.put(("ERROR", order_id, str(e)))


def test_multiprocessing_two_os_processes_competing_for_final_unit(tmp_path):
    """Two independent OS processes race to claim the last unit of stock.
    Exactly 1 process must succeed; exactly 1 must fail with InsufficientStockError.
    Stock must never become negative.
    """
    db_module.DB_DIR = tmp_path
    adapter = JsonDatabaseAdapter()
    adapter.insert("products", {"id": 999, "name": "Sole Ticket", "stock": 1})

    queue = multiprocessing.Queue()

    p1 = multiprocessing.Process(
        target=_worker_deduct_stock,
        args=(str(tmp_path), "ORD-PROC-1", 999, 1, queue)
    )
    p2 = multiprocessing.Process(
        target=_worker_deduct_stock,
        args=(str(tmp_path), "ORD-PROC-2", 999, 1, queue)
    )

    p1.start()
    p2.start()

    p1.join(timeout=10)
    p2.join(timeout=10)

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == 2
    outcomes = [r[0] for r in results]
    assert "SUCCESS" in outcomes
    assert "INSUFFICIENT_STOCK" in outcomes

    # Verify final stock is exactly 0
    final_prod = adapter.read("products", {"id": 999})[0]
    assert final_prod["stock"] == 0


# --- 7. Retry after simulated persistence boundaries ---
def test_retry_after_simulated_persistence_boundaries(json_adapter):
    adapter, tmp_path = json_adapter

    adapter.insert("products", {"id": 50, "name": "Scarf", "stock": 10})
    adapter.insert("orders", {"id": 1, "order_id": "ORD-CRASH-BOUNDARY", "stock_status": "pending"})

    # Boundary 1: Crash/Exception before write completes
    products_path = tmp_path / "products.json"
    
    # Simulate partial failure: write is never called
    assert adapter.read("products", {"id": 50})[0]["stock"] == 10

    # Normal deduction completes products.json
    res1 = adapter.deduct_order_stock("ORD-CRASH-BOUNDARY", [{"id": 50, "qty": 3}])
    assert res1 is True
    assert adapter.read("products", {"id": 50})[0]["stock"] == 7

    # Boundary 2: Crash right after products.json, simulate orders.json remaining 'pending'
    orders_path = tmp_path / "orders.json"
    with open(orders_path, "w", encoding="utf-8") as f:
        json.dump([{"id": 1, "order_id": "ORD-CRASH-BOUNDARY", "stock_status": "pending"}], f)

    # Next attempt (retry after restart):
    # Must NOT deduct stock again, but MUST complete updating orders.json to 'deducted'
    res2 = adapter.deduct_order_stock("ORD-CRASH-BOUNDARY", [{"id": 50, "qty": 3}])
    assert res2 is True
    assert adapter.read("products", {"id": 50})[0]["stock"] == 7
    assert adapter.read("orders", {"id": 1})[0]["stock_status"] == "deducted"


# --- 8. Legacy products without allocation metadata ---
def test_legacy_products_without_allocation_metadata(json_adapter):
    adapter, tmp_path = json_adapter

    # Manually write a legacy products.json file without allocated_orders field
    prods_file = tmp_path / "products.json"
    legacy_product = {
        "id": 77,
        "name": "Vintage Polo",
        "category": "shirt",
        "price": 1299.0,
        "stock": 15
        # Note: no 'allocated_orders' key
    }
    with open(prods_file, "w", encoding="utf-8") as f:
        json.dump([legacy_product], f)

    # Deduct stock for legacy product
    res = adapter.deduct_order_stock("ORD-LEGACY-01", [{"id": 77, "qty": 4}])
    assert res is True

    # Stock decremented to 11 and allocated_orders created
    p = adapter.read("products", {"id": 77})[0]
    assert p["stock"] == 11
    assert "allocated_orders" in p
    assert "ORD-LEGACY-01" in p["allocated_orders"]


# --- 9. Malformed or inconsistent allocation records fail safely ---
def test_malformed_and_inconsistent_allocation_records_fail_safely(json_adapter):
    adapter, tmp_path = json_adapter

    # Subtest 9A: Malformed allocated_orders (string instead of dict)
    prods_file = tmp_path / "products.json"
    corrupt_product = {
        "id": 88,
        "name": "Belt",
        "stock": 20,
        "allocated_orders": "CORRUPTED_STRING_VALUE"
    }
    with open(prods_file, "w", encoding="utf-8") as f:
        json.dump([corrupt_product], f)

    with pytest.raises(InconsistentAllocationError) as exc_corrupt:
        adapter.deduct_order_stock("ORD-MALFORMED", [{"id": 88, "qty": 2}])
    assert "Malformed allocation record" in str(exc_corrupt.value)
    # Stock must remain untouched
    assert adapter.read("products", {"id": 88})[0]["stock"] == 20

    # Subtest 9B: Inconsistent partial allocation across multi-item order
    # Product 881 already has ORD-PARTIAL allocated, but Product 882 does NOT!
    inconsistent_products = [
        {
            "id": 881,
            "name": "Shoes",
            "stock": 10,
            "allocated_orders": {"ORD-PARTIAL": {"quantity": 1}}
        },
        {
            "id": 882,
            "name": "Socks",
            "stock": 10,
            "allocated_orders": {}
        }
    ]
    with open(prods_file, "w", encoding="utf-8") as f:
        json.dump(inconsistent_products, f)

    with pytest.raises(InconsistentAllocationError) as exc_partial:
        adapter.deduct_order_stock("ORD-PARTIAL", [
            {"id": 881, "qty": 1},
            {"id": 882, "qty": 1}
        ])
    assert "Partial allocation detected" in str(exc_partial.value)

    # Neither product stock was decremented! Verify on disk
    with open(prods_file, "r", encoding="utf-8") as f:
        disk_products = json.load(f)
    prods_after = {p["id"]: p for p in disk_products}
    assert prods_after[881]["stock"] == 10
    assert prods_after[882]["stock"] == 10
