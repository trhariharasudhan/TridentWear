"""Saved addresses API (/api/v1/account/addresses).

Addresses used to live on the user record, which the SQL adapter dropped (no column),
so they vanished in postgres mode. They now use the `addresses` table in both modes.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    import app.main as main_mod
    with TestClient(app) as c:
        main_mod.rate_limit_records.clear()
        yield c


def _signin(c, email="addr@example.com"):
    r = c.post("/api/v1/auth/register", json={"name": "Addr Tester", "email": email, "password": "Trident123", "terms": True})
    assert r.status_code == 200, r.text
    otp = (r.json().get("data") or r.json()).get("dev_otp")
    assert otp, r.json()
    v = c.post("/api/auth/otp/verify-email", json={"email": email, "otp": otp})
    assert v.status_code == 200, v.text
    login = c.post("/api/v1/auth/login", json={"email": email, "password": "Trident123"})
    assert login.status_code == 200, login.text
    token = (login.json().get("data") or login.json())["token"]
    return {"Authorization": f"Bearer {token}"}


def data(r):
    j = r.json()
    return j.get("data", j)


GOOD = {"label": "Home", "street": "12 MG Road, 2nd Cross", "area": "BTM Layout", "city": "Bengaluru", "state": "Karnataka", "pin": "560068"}


def test_requires_sign_in(client):
    assert client.get("/api/v1/account/addresses").status_code == 401


def test_first_address_becomes_default_and_lists(client):
    h = _signin(client, "first@example.com")
    r = client.post("/api/v1/account/addresses", json=GOOD, headers=h)
    assert r.status_code == 200, r.text
    a = data(r)["address"]
    assert a["is_default"] is True and a["address_id"].startswith("ADR-") and a["country"] == "India"
    listed = data(client.get("/api/v1/account/addresses", headers=h))["addresses"]
    assert [x["address_id"] for x in listed] == [a["address_id"]]


def test_switch_default_and_delete_promotes_next(client):
    h = _signin(client, "switch@example.com")
    a1 = data(client.post("/api/v1/account/addresses", json=GOOD, headers=h))["address"]
    a2 = data(client.post("/api/v1/account/addresses", json={**GOOD, "label": "Work", "is_default": True}, headers=h))["address"]
    listed = data(client.get("/api/v1/account/addresses", headers=h))["addresses"]
    assert [x["is_default"] for x in listed].count(True) == 1 and listed[0]["address_id"] == a2["address_id"]

    client.put(f"/api/v1/account/addresses/{a1['address_id']}", json={"is_default": True}, headers=h)
    listed = data(client.get("/api/v1/account/addresses", headers=h))["addresses"]
    assert listed[0]["address_id"] == a1["address_id"] and sum(x["is_default"] for x in listed) == 1

    assert client.delete(f"/api/v1/account/addresses/{a1['address_id']}", headers=h).status_code == 200
    listed = data(client.get("/api/v1/account/addresses", headers=h))["addresses"]
    assert len(listed) == 1 and listed[0]["is_default"] is True  # remaining one promoted


@pytest.mark.parametrize("bad,msg", [
    ({"pin": "012345"}, "PIN"), ({"pin": "5600"}, "PIN"), ({"street": "1"}, "street"), ({"city": ""}, "city"),
])
def test_validation(client, bad, msg):
    h = _signin(client, f"bad{abs(hash(str(bad)))}@example.com")
    r = client.post("/api/v1/account/addresses", json={**GOOD, **bad}, headers=h)
    assert r.status_code == 400 and msg.lower() in r.text.lower()


def test_cannot_touch_someone_elses_address(client):
    owner = _signin(client, "owner@example.com")
    a = data(client.post("/api/v1/account/addresses", json=GOOD, headers=owner))["address"]
    other = _signin(client, "intruder@example.com")
    assert client.put(f"/api/v1/account/addresses/{a['address_id']}", json={"city": "Chennai"}, headers=other).status_code == 404
    assert client.delete(f"/api/v1/account/addresses/{a['address_id']}", headers=other).status_code == 404
    still = data(client.get("/api/v1/account/addresses", headers=owner))["addresses"]
    assert still[0]["city"] == "Bengaluru"
