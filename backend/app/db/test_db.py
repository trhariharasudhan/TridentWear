"""
Isolated test-database helpers.

Every test gets its own throw-away JSON database directory so tests can never
touch the developer's real `db/` folder (see app.core.db_switch safety guards).

NOTE: this file was previously excluded from Git by the `test_*.py` rule in
.gitignore, which broke the whole suite on fresh clones. It is now explicitly
re-included in .gitignore.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Tuple

from app.core.db_switch import get_default_db_dir, validate_db_safety
from app.db.database import JsonDatabaseAdapter

# Tables seeded from the dev DB when available (catalog data is safe to copy)
SEED_TABLES = ("products", "coupons")
# Tables that always start empty
EMPTY_TABLES = (
    "orders",
    "users",
    "wishlist",
    "reviews",
    "contacts",
    "stock_allocations",
    "coupon_redemptions",
    "audit_logs",
)

# Fallback coupon seed (mirrors DEFAULT_COUPONS in app/api/coupons.py) so a
# fresh clone — where db/coupons.json is git-ignored — still has test data.
DEFAULT_COUPONS = [
    {"code": "TRIDENTFIRST", "discount_pct": 20.0, "expires_at": "2027-12-31",
     "usage_limit": 1000, "usage_count": 0, "is_active": True},
    {"code": "TRIDENT10", "discount_pct": 10.0, "expires_at": "2027-12-31",
     "usage_limit": 5000, "usage_count": 0, "is_active": True},
]


def _write_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def create_isolated_test_db(seed_data: bool = True, base_dir: Optional[Path] = None) -> Path:
    """Create a fresh temp DB directory and return its path."""
    parent = Path(base_dir) if base_dir else None
    test_dir = Path(tempfile.mkdtemp(prefix="trident_test_db_", dir=parent)).resolve()

    dev_db = get_default_db_dir()
    for table in SEED_TABLES:
        dst = test_dir / f"{table}.json"
        src = dev_db / f"{table}.json"
        if seed_data and src.exists():
            shutil.copy2(src, dst)
        elif seed_data and table == "coupons":
            _write_json(dst, DEFAULT_COUPONS)
        else:
            _write_json(dst, [])

    for table in EMPTY_TABLES:
        _write_json(test_dir / f"{table}.json", [])

    validate_db_safety(db_dir=test_dir)
    return test_dir


def cleanup_isolated_test_db(test_dir: Path) -> None:
    """Remove a temp DB directory. Refuses to delete the real dev DB."""
    test_dir = Path(test_dir).resolve()
    if test_dir == get_default_db_dir():
        raise RuntimeError("Refusing to delete the development database directory")
    shutil.rmtree(test_dir, ignore_errors=True)


@contextmanager
def isolated_test_database(seed_data: bool = True) -> Iterator[Tuple[Path, JsonDatabaseAdapter]]:
    """Context manager yielding (dir, adapter); always cleans up, even on failure."""
    test_dir = create_isolated_test_db(seed_data=seed_data)
    try:
        yield test_dir, JsonDatabaseAdapter(db_dir=test_dir)
    finally:
        cleanup_isolated_test_db(test_dir)
