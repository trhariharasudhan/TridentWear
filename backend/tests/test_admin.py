import urllib.request, json

import os
BASE = os.getenv("TRIDENT_BASE_URL", "http://127.0.0.1:8020")

def call(path, method='GET', data=None, token=None):
    body = json.dumps(data).encode() if data else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
    	with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

# 1. Admin login
print('--- ADMIN LOGIN ---')
res, status = call('/api/v1/auth/login', 'POST', {'email': 'admin@trident.local', 'password': 'Admin@123'})
if status != 200:
    print('FAIL:', status, res)
else:
    token = res['data']['token']
    user = res['data']['user']
    print('Logged in as:', user.get('email'), 'role=', user.get('role'))

    # 2. Get all orders (admin)
    print()
    print('--- ADMIN: ALL ORDERS ---')
    r, s = call('/api/v1/admin/orders', token=token)
    if s == 200:
        orders = r.get('data') or []
        print('Orders count:', len(orders))
    else:
        print('FAIL', s, r)

    # 3. Get all products
    print()
    print('--- ADMIN: ALL PRODUCTS ---')
    r, s = call('/api/v1/products', token=token)
    if s == 200:
        d = r.get('data', {})
        cnt = d.get('count') if isinstance(d, dict) else len(d) if isinstance(d, list) else '?'
        print('Products count:', cnt)
    else:
        print('FAIL', s, r)

    # 4. Non-admin access control
    print()
    print('--- NON-ADMIN ACCESS GUARD ---')
    cres, _ = call('/api/v1/auth/login', 'POST', {'email': 'customer@trident.local', 'password': 'password'})
    ctoken = cres['data']['token']
    r, s = call('/api/v1/admin/orders', token=ctoken)
    print('Customer -> /api/v1/admin/orders:', 'HTTP', s)
    print('ACCESS GUARD:', 'PASS' if s in (401, 403) else 'FAIL - no guard!')
