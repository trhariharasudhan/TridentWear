# -*- coding: utf-8 -*-
"""
test_user_management.py — Test suite for admin user management.
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
    print("TridentWear — User Management Tests")
    print("=============================================")

    # 1. Admin login
    login_res, status = http('/api/v1/auth/login', 'POST', {'email': 'admin@trident.local', 'password': 'Admin@123'})
    if status != 200:
        print("Admin login failed! Status:", status)
        sys.exit(1)
    
    admin_token = login_res['data']['token']
    admin_id = login_res['data']['user']['id']
    print(f"Admin logged in. ID: {admin_id}")

    # 2. Get list of users (safe serialization check)
    users_res, s = http('/api/v1/admin/users', 'GET', token=admin_token)
    check("List users", s, 200, users_res)
    if s == 200:
        users = users_res if isinstance(users_res, list) else users_res.get("data", [])
        
        # Verify no sensitive info is leaked
        leaked = False
        for u in users:
            for key in ['password_hash', 'password', 'otp', 'otp_hash', 'password_reset_token']:
                if key in u:
                    print(f"  [FAIL] Sensitive field '{key}' leaked in user serialization")
                    leaked = True
        if not leaked:
            print("  [PASS] Safe serialization verified (no secrets exposed)")
        else:
            global FAIL
            FAIL += 1

    # 3. Create a test customer session to verify status updates
    cust_register, s_reg = http('/api/v1/auth/register', 'POST', {
        'name': 'Test UserManagement',
        'email': 'usermgmt@trident.local',
        'password': 'Password@123'
    })
    
    # If smtp is mock, we get dev_otp.
    dev_otp = cust_register.get("dev_otp") or cust_register.get("data", {}).get("dev_otp")
    if dev_otp:
        # Verify OTP
        verify_res, s_ver = http('/api/auth/otp/verify-email', 'POST', {
            'email': 'usermgmt@trident.local',
            'otp': dev_otp
        })
        print(f"Verified customer: HTTP {s_ver}")

    # Login customer
    cust_login, s_log = http('/api/v1/auth/login', 'POST', {
        'email': 'usermgmt@trident.local',
        'password': 'Password@123'
    })
    
    if s_log != 200:
        print("Customer login failed! Status:", s_log)
        sys.exit(1)
        
    cust_token = cust_login['data']['token']
    cust_id = cust_login['data']['user']['id']
    print(f"Customer logged in. ID: {cust_id}")

    # Verify customer can access profile
    cust_profile, s_prof = http('/api/v1/account/profile', 'GET', token=cust_token)
    check("Customer access profile", s_prof, 200, cust_profile)

    # 4. Block customer
    block_res, s_block = http(f'/api/v1/admin/users/{cust_id}/status', 'PUT', {'is_active': False}, token=admin_token)
    check("Block customer", s_block, 200, block_res)

    # 5. Check blocked user session invalidation (existing token must be rejected)
    cust_profile_blocked, s_prof_blocked = http('/api/v1/account/profile', 'GET', token=cust_token)
    check("Blocked customer session invalidated", s_prof_blocked, 401, cust_profile_blocked)

    # 6. Try logging in again (should fail)
    cust_login_blocked, s_log_blocked = http('/api/v1/auth/login', 'POST', {
        'email': 'usermgmt@trident.local',
        'password': 'Password@123'
    })
    check("Blocked customer login rejected", s_log_blocked, 403, cust_login_blocked)

    # 7. Unblock customer
    unblock_res, s_unblock = http(f'/api/v1/admin/users/{cust_id}/status', 'PUT', {'is_active': True}, token=admin_token)
    check("Unblock customer", s_unblock, 200, unblock_res)

    # 8. Try logging in after unblock (should work)
    cust_login_unblocked, s_log_unblocked = http('/api/v1/auth/login', 'POST', {
        'email': 'usermgmt@trident.local',
        'password': 'Password@123'
    })
    check("Unblocked customer login succeeds", s_log_unblocked, 200, cust_login_unblocked)

    # 9. Promote customer to admin role
    promote_res, s_promote = http(f'/api/v1/admin/users/{cust_id}/role', 'PUT', {'role': 'admin'}, token=admin_token)
    check("Promote customer to admin", s_promote, 200, promote_res)

    # 10. Demote admin back to customer
    demote_res, s_demote = http(f'/api/v1/admin/users/{cust_id}/role', 'PUT', {'role': 'customer'}, token=admin_token)
    check("Demote admin to customer", s_demote, 200, demote_res)

    # 11. Self-block prevention (should return HTTP 400)
    self_block_res, s_self_block = http(f'/api/v1/admin/users/{admin_id}/status', 'PUT', {'is_active': False}, token=admin_token)
    check("Self-block prevention rejected", s_self_block, 400, self_block_res)

    # 12. Self-demotion prevention (should return HTTP 400)
    self_demote_res, s_self_demote = http(f'/api/v1/admin/users/{admin_id}/role', 'PUT', {'role': 'customer'}, token=admin_token)
    check("Self-demotion prevention rejected", s_self_demote, 400, self_demote_res)

    # Cleanup: delete created test user from users.json
    try:
        users_path = os.path.join(os.path.dirname(__file__), '../../db/users.json')
        if os.path.exists(users_path):
            with open(users_path, 'r', encoding='utf-8') as f:
                db_users = json.load(f)
            cleaned_users = [u for u in db_users if u.get('email') != 'usermgmt@trident.local']
            with open(users_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned_users, f, indent=2)
            print("  Cleaned up test user from users.json")
    except Exception as e:
        print("  Error during cleanup:", e)

    print("=============================================")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
