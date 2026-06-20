# -*- coding: utf-8 -*-
"""
test_coupon_crud.py — Test suite for admin coupon CRUD and validation.
"""
import urllib.request
import urllib.error
import json
import sys
import os

BASE = os.getenv("TRIDENT_BASE_URL", "http://127.0.0.1:8020")
PASS = 0
FAIL = 0

def http(path, method='GET', data=None, token=None):
    body = json.dumps(data).encode() if data else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            ct = r.headers.get('Content-Type', '')
            if 'application/json' in ct and raw:
                return json.loads(raw), r.status
            return {}, r.status
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
            ct = e.headers.get('Content-Type', '') if hasattr(e, 'headers') else ''
            return (json.loads(raw) if 'application/json' in ct and raw else {}), e.code
        except Exception:
            return {}, e.code

def check(label: str, got_status: int, want_status: int, body: dict) -> None:
    global PASS, FAIL
    ok = got_status == want_status
    mark = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {label} -> HTTP {got_status} (Expected {want_status})")
    if not ok:
        print("    Response:", body)

def main():
    print("TridentWear — Coupon CRUD & Validation Tests")
    print("=============================================")

    # 1. Admin login
    login_res, status = http('/api/v1/auth/login', 'POST', {'email': 'admin@trident.local', 'password': 'Admin@123'})
    if status != 200:
        print("Admin login failed! Status:", status)
        sys.exit(1)
    
    atoken = login_res['data']['token']
    print("Admin logged in successfully.")

    # 2. Get list of coupons
    coupons, s = http('/api/v1/admin/coupons', 'GET', token=atoken)
    check("List coupons", s, 200, coupons)

    # 3. Create a coupon TESTCRUD
    create_payload = {
        "code": "TESTCRUD",
        "discount_pct": 30.0,
        "expires_at": "2029-12-31",
        "usage_limit": 10,
        "is_active": True
    }
    res, s = http('/api/v1/admin/coupons', 'POST', create_payload, token=atoken)
    check("Create coupon TESTCRUD", s, 200, res)

    # 4. Try creating a duplicate coupon code
    res_dup, s_dup = http('/api/v1/admin/coupons', 'POST', create_payload, token=atoken)
    check("Create duplicate coupon TESTCRUD fails", s_dup, 400, res_dup)

    # 5. Update TESTCRUD discount and limit
    update_payload = {
        "discount_pct": 50.0,
        "usage_limit": 20
    }
    res_upd, s_upd = http('/api/v1/admin/coupons/TESTCRUD', 'PUT', update_payload, token=atoken)
    check("Update coupon TESTCRUD", s_upd, 200, res_upd)

    # 6. Apply TESTCRUD (should work)
    res_app, s_app = http('/api/v1/coupons/apply', 'POST', {"code": "TESTCRUD", "subtotal": 1000.0})
    check("Apply active coupon TESTCRUD", s_app, 200, res_app)
    if s_app == 200:
        data_payload = res_app.get("data", {}) if "data" in res_app else res_app
        if data_payload.get("discount_pct") == 50.0:
            print("  [PASS] Correct updated discount percentage applied")
        else:
            print("  [FAIL] Mismatched discount pct applied", res_app)

    # 7. Disable coupon TESTCRUD
    res_dis, s_dis = http('/api/v1/admin/coupons/TESTCRUD', 'PUT', {"is_active": False}, token=atoken)
    check("Disable coupon TESTCRUD", s_dis, 200, res_dis)

    # 8. Try applying disabled coupon (should fail)
    res_app_dis, s_app_dis = http('/api/v1/coupons/apply', 'POST', {"code": "TESTCRUD", "subtotal": 1000.0})
    check("Apply disabled coupon TESTCRUD rejected", s_app_dis, 400, res_app_dis)

    # 9. Create an expired coupon TESTEXPIRED
    expired_payload = {
        "code": "TESTEXPIRED",
        "discount_pct": 10.0,
        "expires_at": "2020-01-01",
        "usage_limit": 5,
        "is_active": True
    }
    res_exp, s_exp = http('/api/v1/admin/coupons', 'POST', expired_payload, token=atoken)
    check("Create expired coupon TESTEXPIRED", s_exp, 200, res_exp)

    # 10. Try applying expired coupon (should fail)
    res_app_exp, s_app_exp = http('/api/v1/coupons/apply', 'POST', {"code": "TESTEXPIRED", "subtotal": 1000.0})
    check("Apply expired coupon TESTEXPIRED rejected", s_app_exp, 400, res_app_exp)

    # 11. Delete coupons
    res_del1, s_del1 = http('/api/v1/admin/coupons/TESTCRUD', 'DELETE', token=atoken)
    check("Delete coupon TESTCRUD", s_del1, 200, res_del1)

    res_del2, s_del2 = http('/api/v1/admin/coupons/TESTEXPIRED', 'DELETE', token=atoken)
    check("Delete coupon TESTEXPIRED", s_del2, 200, res_del2)

    # 12. Try applying deleted coupon (should fail)
    res_app_del, s_app_del = http('/api/v1/coupons/apply', 'POST', {"code": "TESTCRUD", "subtotal": 1000.0})
    check("Apply deleted coupon TESTCRUD rejected", s_app_del, 404, res_app_del)

    print("=============================================")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
