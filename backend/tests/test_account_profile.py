"""Profile preferences, birthday validation and account deletion (anonymise, keep orders)."""
import pytest
from fastapi.testclient import TestClient

from tests.test_addresses import _signin, data, GOOD


@pytest.fixture
def client():
    from app.main import app
    import app.main as main_mod
    with TestClient(app) as c:
        main_mod.rate_limit_records.clear()
        yield c


def test_settings_are_whitelisted_and_persist(client):
    h = _signin(client, "prefs@example.com")
    prof = data(client.get("/api/v1/account/profile", headers=h))
    assert prof["settings"] == {"order_updates_email": True, "order_updates_whatsapp": False, "new_drops": True, "marketing": False}
    r = client.put("/api/v1/account/profile", json={"settings": {"order_updates_whatsapp": True, "evil": "x"}}, headers=h)
    assert r.status_code == 200, r.text
    s = data(client.get("/api/v1/account/profile", headers=h))["settings"]
    assert s["order_updates_whatsapp"] is True and "evil" not in s and s["new_drops"] is True


@pytest.mark.parametrize("bday,ok", [("1999-05-17", True), ("2024-01-01", False), ("1999-02-30", False), ("17/05/1999", False), ("", True)])
def test_birthday_validation(client, bday, ok):
    h = _signin(client, f"bday{abs(hash(bday))}@example.com")
    r = client.put("/api/v1/account/profile", json={"birthday": bday}, headers=h)
    assert (r.status_code == 200) is ok, r.text
    if ok and bday:
        assert data(client.get("/api/v1/account/profile", headers=h))["birthday"] == bday


def test_delete_account_anonymises_and_blocks_login(client):
    email = "leaving@example.com"
    h = _signin(client, email)
    client.post("/api/v1/account/addresses", json=GOOD, headers=h)
    assert client.post("/api/v1/account/delete", json={"password": "wrong-pass", "confirm": "DELETE"}, headers=h).status_code == 400
    assert client.post("/api/v1/account/delete", json={"password": "Trident123", "confirm": "nope"}, headers=h).status_code == 400
    r = client.post("/api/v1/account/delete", json={"password": "Trident123", "confirm": "delete"}, headers=h)
    assert r.status_code == 200, r.text
    # token no longer works, and the old email/password can't sign in
    assert client.get("/api/v1/account/profile", headers=h).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "Trident123"}).status_code in (400, 401, 403)
    from app.core.db_switch import db
    assert not db.read("users", {"email": email})
    assert not [a for a in db.read("addresses", {}) if a.get("street") == GOOD["street"] and a.get("user_id") is None]


def test_admin_cannot_self_delete(client):
    import os
    login = client.post("/api/v1/auth/login", json={"email": os.getenv("ADMIN_EMAIL", "admin@trident.local"), "password": os.getenv("ADMIN_PASSWORD", "Admin@123")})
    if login.status_code != 200:
        pytest.skip("admin seed not available in this environment")
    h = {"Authorization": f"Bearer {data(login)['token']}"}
    r = client.post("/api/v1/account/delete", json={"password": "x", "confirm": "DELETE"}, headers=h)
    assert r.status_code == 403
