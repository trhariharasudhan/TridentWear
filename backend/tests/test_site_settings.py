"""Admin-editable storefront settings: public read, admin-only write, validation, audit log."""
import os
import pytest
from fastapi.testclient import TestClient

from tests.test_addresses import _signin, data


@pytest.fixture
def client():
    from app.main import app
    import app.main as main_mod
    with TestClient(app) as c:
        main_mod.rate_limit_records.clear()
        yield c


def _admin(c):
    r = c.post("/api/v1/auth/login", json={"email": os.getenv("ADMIN_EMAIL", "admin@trident.local"), "password": os.getenv("ADMIN_PASSWORD", "Admin@123")})
    if r.status_code != 200:
        pytest.skip("admin seed not available")
    return {"Authorization": f"Bearer {data(r)['token']}"}


def _product_ids(n=5):
    """Real ids from the DB (earlier tests may have changed the catalog); seed a few if needed."""
    from app.core.db_switch import db
    ids = [int(p["id"]) for p in db.read("products", {}) if p.get("id") is not None]
    nxt = max(ids or [1000]) + 1
    while len(ids) < n:
        db.insert("products", {"id": nxt, "name": f"Seed {nxt}", "price": 999, "stock": 5, "category": "tshirt", "sizes": ["M"]})
        ids.append(nxt); nxt += 1
    return ids[:n]


def test_public_defaults(client):
    s = data(client.get("/api/v1/site"))["site"]
    assert s["announcements"] and s["contact"]["email"] and s["rail"] == []


def test_customer_cannot_edit(client):
    h = _signin(client, "notadmin@example.com")
    assert client.put("/api/v1/admin/site", json={"hero_line": "hacked"}, headers=h).status_code in (401, 403)
    assert client.put("/api/v1/admin/site", json={"hero_line": "hacked"}).status_code in (401, 403)


def test_admin_edit_roundtrip_and_audit(client):
    h = _admin(client)
    ids = _product_ids(5)
    body = {"announcements": ["  Diwali drop is live  ", "Use FESTIVE10 for 10% off"], "hero_line": "New: linen camp shirts",
            "rail": ids, "drop": ids[:4], "drop_title": "Diwali drop", "contact": {"email": "care@tridentwear.in", "whatsapp": "919876543210"}}
    r = client.put("/api/v1/admin/site", json=body, headers=h)
    assert r.status_code == 200, r.text
    s = data(client.get("/api/v1/site"))["site"]
    assert s["announcements"][0] == "Diwali drop is live" and s["rail"] == ids and s["drop"] == ids[:4]
    assert s["contact"]["email"] == "care@tridentwear.in" and s["contact"]["phone"]  # untouched fields kept
    from app.core.db_switch import db
    assert any(a.get("target_entity") == "site_settings" for a in db.read("admin_audit_logs", {}))


@pytest.mark.parametrize("body,msg", [
    ({"announcements": []}, "between 1 and 6"),
    ({"announcements": [str(i) for i in range(7)]}, "between 1 and 6"),
    ({"rail": "IDS2"}, "at least 4"),
    ({"rail": [999999]}, "doesn't exist"),
    ({"drop": "IDS5"}, "at most 4"),
    ({"contact": {"email": "nope"}}, "valid contact email"),
    ({"contact": {"whatsapp": "+91 98765"}}, "digits only"),
    ({"contact": {"instagram": "javascript:alert(1)"}}, "https://"),
])
def test_validation(client, body, msg):
    h = _admin(client)
    for k, v in list(body.items()):
        if isinstance(v, str) and v.startswith("IDS"):
            body = {**body, k: _product_ids(int(v[3:]))}
    r = client.put("/api/v1/admin/site", json=body, headers=h)
    assert r.status_code == 400 and msg in r.text, r.text
