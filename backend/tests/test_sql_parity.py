"""
Regression tests for postgres-mode data loss found on 2026-11-11.

The SQL adapter drops keys that have no column. That silently broke:
  * product MRP / gallery / try-on anchors (storefront v2 fields)
  * email-signup OTP (users.otp / users.otp_expiry) -> signup could never be verified
  * orders.fbt_offer_id (bundle offer never released on cancel) and payment_simulated
Plus: Postgres SERIAL sequences were not advanced after explicit-id inserts
(admin seeded as id=1 -> first signup hit users_pkey UniqueViolation),
and an expired OTP was accepted because its HTTPException was swallowed.

The Postgres test runs only when TW_TEST_PG_DSN points at a disposable database:
  TW_TEST_PG_DSN=postgresql://tw:twpass@127.0.0.1:5432/tridentwear_test pytest backend/tests/test_sql_parity.py
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.db.models import metadata

ROOT = Path(__file__).resolve().parents[2]


def test_every_catalog_field_has_a_products_column():
    catalog = json.loads((ROOT / "db/products.json").read_text(encoding="utf-8"))
    keys = set().union(*(row.keys() for row in catalog)) - {"allocated_orders"}
    missing = keys - set(metadata.tables["products"].c.keys())
    assert not missing, f"products table would silently drop: {sorted(missing)}"


@pytest.mark.parametrize("table,cols", [
    ("users", {"otp", "otp_expiry"}),
    ("orders", {"fbt_offer_id", "fbt_token", "payment_simulated"}),
])
def test_runtime_fields_have_columns(table, cols):
    assert cols <= set(metadata.tables[table].c.keys())


def _verify_with(monkeypatch, expiry, otp="123456"):
    import app.services.auth_service as auth
    user = {"id": 7, "email": "a@b.co", "otp": otp, "otp_expiry": expiry, "otp_verification_status": False}
    monkeypatch.setattr(auth, "find_user_by_email", lambda email: user)
    monkeypatch.setattr(auth, "update_user", lambda uid, changes: {**user, **changes})
    monkeypatch.setattr(auth, "serialize_user", lambda u: {"id": u["id"]})
    return auth.verify_email_otp(SimpleNamespace(email="a@b.co", otp=otp))


@pytest.mark.parametrize("expiry", [
    (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),  # JSON mode stores a string
    datetime.now(timezone.utc) - timedelta(minutes=1),               # SQL mode returns a datetime
])
def test_expired_otp_is_rejected(monkeypatch, expiry):
    with pytest.raises(HTTPException) as exc:
        _verify_with(monkeypatch, expiry)
    assert exc.value.status_code == 400 and "expired" in exc.value.detail.lower()


@pytest.mark.parametrize("expiry", [
    (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    datetime.now(timezone.utc) + timedelta(minutes=5),
    "not-a-date",  # unparseable expiry falls back to the OTP check, as before
])
def test_valid_otp_is_accepted(monkeypatch, expiry):
    assert _verify_with(monkeypatch, expiry)["success"] is True


@pytest.mark.skipif(not os.getenv("TW_TEST_PG_DSN"), reason="needs a disposable Postgres (TW_TEST_PG_DSN)")
def test_postgres_explicit_id_insert_advances_sequence():
    from app.db.database import PostgresDatabaseAdapter
    adapter = PostgresDatabaseAdapter(os.environ["TW_TEST_PG_DSN"])
    metadata.drop_all(adapter.engine)
    metadata.create_all(adapter.engine)
    try:
        adapter.insert("users", {"id": 1, "email": "admin@x.co", "role": "admin"})
        second = adapter.insert("users", {"email": "first-signup@x.co", "role": "customer",
                                          "otp": "654321", "otp_expiry": datetime.now(timezone.utc).isoformat()})
        assert second["id"] == 2
        assert second["otp"] == "654321" and second["otp_expiry"] is not None

        catalog = json.loads((ROOT / "db/products.json").read_text(encoding="utf-8"))
        adapter.insert("products", catalog[0])
        row = adapter.read("products", {"id": catalog[0]["id"]})[0]
        assert row["mrp"] == catalog[0]["mrp"] and row["gallery"] == catalog[0]["gallery"]
        assert row["tryon"] == catalog[0]["tryon"]
    finally:
        metadata.drop_all(adapter.engine)
