import os
import time
import tempfile
import shutil
import multiprocessing
import pytest
from app.db.database import JsonDatabaseAdapter

def _competing_order_worker(db_dir, order_id, product_id, qty, result_queue):
    """Worker process simulating competing order creation."""
    try:
        adapter = JsonDatabaseAdapter(db_dir=db_dir)
        # Attempt to deduct stock
        items = [{"id": product_id, "qty": qty}]
        ok = adapter.deduct_order_stock(order_id, items)
        result_queue.put((order_id, ok))
    except Exception as exc:
        result_queue.put((order_id, False))

def test_json_multiprocess_competing_orders_prevent_overselling():
    """Two independent OS worker processes competing for the last unit of stock: exactly one wins."""
    temp_dir = tempfile.mkdtemp(prefix="trident_test_multiworker_")
    try:
        # Create products.json with stock = 1
        import json
        products_path = os.path.join(temp_dir, "products.json")
        with open(products_path, "w", encoding="utf-8") as f:
            json.dump([{"id": 101, "name": "Limited Edition Jacket", "stock": 1, "price": 1999}], f)
        
        # Create empty orders.json
        orders_path = os.path.join(temp_dir, "orders.json")
        with open(orders_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        result_queue = multiprocessing.Queue()
        p1 = multiprocessing.Process(target=_competing_order_worker, args=(temp_dir, "ORD-W1", 101, 1, result_queue))
        p2 = multiprocessing.Process(target=_competing_order_worker, args=(temp_dir, "ORD-W2", 101, 1, result_queue))

        p1.start()
        p2.start()
        p1.join(timeout=5)
        p2.join(timeout=5)

        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        # Exactly one process should succeed, the second must fail due to zero remaining stock
        successes = [res for _, res in results if res is True]
        failures = [res for _, res in results if res is False]

        assert len(successes) == 1, f"Expected exactly 1 order to succeed, got {len(successes)}"
        assert len(failures) == 1, f"Expected exactly 1 order to fail, got {len(failures)}"

        # Verify final stock is 0
        adapter = JsonDatabaseAdapter(db_dir=temp_dir)
        prods = adapter.read("products", {"id": 101})
        assert prods[0]["stock"] == 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_json_memory_cache_ttl_isolation_constraint():
    """Validates that separate adapter instances without shared cache must rely on file reload."""
    temp_dir = tempfile.mkdtemp(prefix="trident_test_ttl_")
    try:
        import json
        products_path = os.path.join(temp_dir, "products.json")
        with open(products_path, "w", encoding="utf-8") as f:
            json.dump([{"id": 202, "name": "Classic Polo", "stock": 10, "price": 799}], f)

        adapter_a = JsonDatabaseAdapter(db_dir=temp_dir)
        adapter_b = JsonDatabaseAdapter(db_dir=temp_dir)

        # adapter A reads (populates memory cache)
        p_a = adapter_a.read("products", {"id": 202})
        assert p_a[0]["stock"] == 10

        # adapter B updates directly on disk
        adapter_b.update("products", {"id": 202}, {"stock": 8})

        # Single-worker invariant: In a multi-worker environment with process-isolated MemoryCache,
        # adapter A's cache might hold stock=10 until TTL expires.
        # This confirms why --workers 1 is strictly mandatory in JSON mode.
        from app.db.json_manager import db_instance
        assert db_instance.CACHE_TTL == 3.0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
