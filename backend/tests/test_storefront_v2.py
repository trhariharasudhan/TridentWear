"""
Regression tests for the v2 storefront changes:
admin bootstrap, client test_mode gating, analytics revenue, upload validation,
product field passthrough, try-on API and the new page router.
"""
import io
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Admin@12345")
    import app.services.auth_service as auth
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_RAW", "Admin@12345", raising=False)
    from app.main import app
    with TestClient(app) as c:
        _reset_state()
        yield c


def _reset_state():
    """Other suites share the adapter; pin a known admin password and the real catalog."""
    import bcrypt
    from pathlib import Path
    from app.core.db_switch import db
    from app.services.auth_service import ensure_admin_user
    import app.main as main_mod
    main_mod.rate_limit_records.clear()  # earlier suites share the TestClient IP
    ensure_admin_user()
    pw = bcrypt.hashpw(b"Admin@12345", bcrypt.gensalt()).decode()
    db.update("users", {"email": "admin@trident.local"}, {"password_hash": pw, "is_active": True, "role": "admin"})
    catalog = json.loads((Path(__file__).resolve().parents[2] / "db/products.json").read_text())
    for prod in db.read("products", {}):
        db.delete("products", {"id": prod["id"]})
    for prod in catalog:
        db.insert("products", prod)


def _admin_token(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@trident.local", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


# ---------------------------------------------------------------- admin bootstrap
def test_admin_can_log_in_after_startup(client):
    assert _admin_token(client)


def test_ensure_admin_user_is_idempotent(client):
    from app.services.auth_service import ensure_admin_user
    from app.core.db_switch import db
    ensure_admin_user(); ensure_admin_user()
    admins = [u for u in db.read("users", {}) if u.get("email") == "admin@trident.local"]
    assert len(admins) == 1 and admins[0]["role"] == "admin"


def test_admin_seeded_even_when_customers_exist(monkeypatch, client):
    from app.core.db_switch import db
    from app.services.auth_service import ensure_admin_user
    for u in db.read("users", {}):
        db.delete("users", {"id": u["id"]})
    db.insert("users", {"id": 7, "email": "c@example.com", "role": "customer"})
    ensure_admin_user()
    assert db.read("users", {"email": "admin@trident.local"})


# ---------------------------------------------------------------- test_mode gate
def test_client_test_mode_ignored_in_production(monkeypatch):
    from app.core.config import allow_client_test_mode
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert allow_client_test_mode(True) is False
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert allow_client_test_mode(True) is True
    assert allow_client_test_mode(False) is False


# ---------------------------------------------------------------- analytics
def test_revenue_excludes_cancelled_and_unpaid(monkeypatch):
    import app.services.admin_service as svc
    orders = [
        {"order_id": "A", "status": "placed", "payment_status": "paid", "total": 1000, "items": [{"name": "Tee", "qty": 1}]},
        {"order_id": "B", "status": "placed", "payment_status": "cod_pending", "total": 500, "items": []},
        {"order_id": "C", "status": "cancelled", "payment_status": "paid", "total": 9000, "items": []},
        {"order_id": "D", "status": "placed", "payment_status": "pending", "total": 7000, "items": []},
    ]
    monkeypatch.setattr(svc, "load_orders", lambda: orders)
    data = svc.get_analytics_data()
    assert data["total_revenue"] == 1500
    assert data["paid_orders"] == 2
    assert data["total_orders"] == 4
    assert len(data["revenue_by_day"]) == 14
    assert data["status_breakdown"]["cancelled"] == 1


# ---------------------------------------------------------------- uploads
def test_upload_rejects_non_image_bytes(client):
    token = _admin_token(client)
    files = {"image": ("evil.png", io.BytesIO(b"<script>alert(1)</script>"), "image/png")}
    r = client.post("/api/v1/admin/products", headers={"Authorization": f"Bearer {token}"},
                    data={"name": "Test Tee", "category": "tshirt", "price": "799", "stock": "5"}, files=files)
    assert r.status_code == 400
    assert "valid image" in r.json()["error"]["message"]


def test_upload_accepts_real_png_and_saves_extras(client):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGBA", (20, 24), (10, 10, 10, 255)).save(buf, format="PNG"); buf.seek(0)
    token = _admin_token(client)
    r = client.post("/api/v1/admin/products", headers={"Authorization": f"Bearer {token}"},
                    data={"name": "Test Tee", "category": "tshirt", "price": "799", "stock": "5",
                          "mrp": "999", "base_color": "Black", "color_hex": "#111111"},
                    files={"image": ("tee.png", buf, "image/png")})
    assert r.status_code == 200, r.text
    product = r.json()["data"]["product"]
    assert product["mrp"] == 999 and product["color_hex"] == "#111111"
    assert product["image"].startswith("/images/uploads/")


def test_admin_rejects_bad_colour(client):
    token = _admin_token(client)
    r = client.post("/api/v1/admin/products", headers={"Authorization": f"Bearer {token}"},
                    data={"name": "Test Tee", "category": "tshirt", "price": "799", "stock": "5", "color_hex": "red;x"})
    assert r.status_code == 400


# ---------------------------------------------------------------- catalog passthrough
def test_products_expose_storefront_fields(client):
    r = client.get("/api/v1/products")
    p = next(x for x in r.json()["data"]["products"] if x["id"] == 1)
    for key in ("gallery", "tryon", "slug", "color_hex", "mrp", "style_code"):
        assert key in p, key
    assert p["gallery"][0].startswith("/images/products/")


def test_catalog_has_unique_ids_and_existing_images():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "frontend/assets/data/products.json").read_text())
    ids = [p["id"] for p in data]
    assert len(ids) == len(set(ids))
    for p in data:
        for g in p["gallery"]:
            assert (root / "frontend/assets/images" / g.removeprefix("/images/")).exists(), g
        assert "rating" not in p, "no fabricated ratings in seed data"


# ---------------------------------------------------------------- try-on API
def test_tryon_status_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    d = client.get("/api/v1/tryon/status").json()["data"]
    assert d["ai_enabled"] is False and d["live_ar"] is True


def test_tryon_generate_requires_configuration(client, monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    r = client.post("/api/v1/tryon/generate", data={"product_id": "1"}, files={"photo": ("p.jpg", b"x", "image/jpeg")})
    assert r.status_code == 503


def test_tryon_generate_requires_login(client, monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "test-token")
    r = client.post("/api/v1/tryon/generate", data={"product_id": "1"}, files={"photo": ("p.jpg", b"x", "image/jpeg")})
    assert r.status_code == 401


def test_tryon_generate_calls_provider(client, monkeypatch):
    from PIL import Image
    import app.api.tryon as tryon
    monkeypatch.setenv("REPLICATE_API_TOKEN", "test-token")
    tryon._usage.clear()
    captured = {}

    def fake_provider(person, garment, desc, cat):
        captured.update(person=person[:22], garment=garment[:22], desc=desc)
        return "https://replicate.delivery/fake/out.png"
    monkeypatch.setattr(tryon, "_call_provider", fake_provider)
    buf = io.BytesIO(); Image.new("RGB", (64, 96), (200, 180, 160)).save(buf, format="JPEG"); buf.seek(0)
    token = _admin_token(client)
    r = client.post("/api/v1/tryon/generate", headers={"Authorization": f"Bearer {token}"},
                    data={"product_id": "1"}, files={"photo": ("me.jpg", buf, "image/jpeg")})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["image_url"].endswith("out.png")
    assert captured["person"].startswith("data:image/jpeg") and captured["garment"].startswith("data:image/jpeg")


# ---------------------------------------------------------------- pages
def test_pages_and_legacy_redirects(client):
    assert client.get("/").status_code == 200
    assert "AI Fit Check" in client.get("/tryon.html").text
    r = client.get("/products", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/shop.html"
    assert client.get("/nope.html").status_code == 404
    assert client.get("/sw.js").headers["content-type"].startswith("application/javascript")


def test_security_headers_allow_camera_only_on_self(client):
    h = client.get("/").headers
    assert "camera=(self)" in h["permissions-policy"]
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "unsafe-eval'" not in h["content-security-policy"].replace("wasm-unsafe-eval'", "")


# ---------------------------------------------------------------- dev simulated gateway
def _pending_payment(client):
    r = client.post("/api/v1/payments/create-order", json={"order_data": {
        "items": [{"id": 2, "qty": 1, "size": "M"}], "subtotal": 899,
        "customer": {"name": "Dev Tester", "email": "dev@example.com", "phone": "9876543210"},
        "shipping": {"address": "12 MG Road", "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"}}})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_dev_checkout_without_keys_completes_in_test_mode(client, monkeypatch):
    import app.services.payment_service as ps
    monkeypatch.setattr(ps, "RAZORPAY_KEY_ID", ""); monkeypatch.setattr(ps, "RAZORPAY_KEY_SECRET", "")
    pay = _pending_payment(client)
    r = client.post("/api/v1/payments/verify", json={"razorpay_order_id": pay["razorpay_order_id"], "razorpay_payment_id": "pay_dev_1",
                                                      "razorpay_signature": "mock", "order_data": {"test_mode": True}})
    assert r.status_code == 200, r.text
    from app.core.db_switch import db
    order = db.read("orders", {"order_id": pay["order_id"]})[0]
    assert order["payment_status"] == "paid" and order["payment_simulated"] is True


def test_production_never_simulates_payments(client, monkeypatch):
    import app.services.payment_service as ps
    monkeypatch.setattr(ps, "RAZORPAY_KEY_ID", ""); monkeypatch.setattr(ps, "RAZORPAY_KEY_SECRET", "")
    pay = _pending_payment(client)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(ps, "IS_PRODUCTION", True)
    r = client.post("/api/v1/payments/verify", json={"razorpay_order_id": pay["razorpay_order_id"], "razorpay_payment_id": "pay_dev_2",
                                                      "razorpay_signature": "mock", "order_data": {"test_mode": True}})
    assert r.status_code in (400, 503), r.text
