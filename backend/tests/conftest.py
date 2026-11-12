"""
Pytest configuration and global fixtures for TridentWear test suite.
"""

import sys
import os
import shutil
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.db.test_db import isolated_test_database, create_isolated_test_db, cleanup_isolated_test_db
from app.core.db_switch import get_default_db_dir


@pytest.fixture(autouse=True)
def default_test_db_isolation(tmp_path, monkeypatch):
    """
    Autouse fixture that ensures every pytest test runs with TRIDENT_TEST_MODE=1
    and TRIDENT_DB_DIR set to an isolated temporary sandbox by default.
    Tests can still override TRIDENT_DB_DIR or monkeypatch app.db.database.DB_DIR.
    """
    # Create isolated test db for the test
    test_dir = tmp_path / "auto_test_db"
    test_dir.mkdir(exist_ok=True)

    # Copy clean seed tables from dev db
    dev_db = get_default_db_dir()
    for table in ("products", "coupons"):
        src = dev_db / f"{table}.json"
        dst = test_dir / f"{table}.json"
        if src.exists():
            shutil.copy2(src, dst)
        elif table == "coupons":
            from app.db.test_db import DEFAULT_COUPONS
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_COUPONS, f)
        else:
            with open(dst, "w", encoding="utf-8") as f:
                f.write("[]")

    for table in ("orders", "wishlist", "stock_allocations", "coupon_redemptions"):
        with open(test_dir / f"{table}.json", "w", encoding="utf-8") as f:
            f.write("[]")

    monkeypatch.setenv("TRIDENT_TEST_MODE", "1")
    monkeypatch.setenv("TRIDENT_DB_DIR", str(test_dir))


@pytest.fixture
def isolated_db():
    """
    Explicit fixture for tests requesting a dedicated isolated test database.
    """
    with isolated_test_database(seed_data=True) as (test_dir, adapter):
        yield adapter, test_dir


# Live-server smoke scripts: they call http://127.0.0.1:8020 at import time.
# Run them only when a server is up:  TRIDENT_LIVE_TESTS=1 pytest backend/tests
collect_ignore = []
if os.getenv("TRIDENT_LIVE_TESTS", "").strip() not in ("1", "true", "yes"):
    collect_ignore = ["test_admin.py", "test_basic.py", "test_payment_security.py", "test_phase5.py"]
