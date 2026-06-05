#!/usr/bin/env python3
"""Fix static mock in api.js for /api/v1/contact and /api/v1/orders stats"""
path = 'frontend/assets/js/shared/api.js'
with open(path, encoding='utf-8') as f:
    content = f.read()

fixes = []

# Fix /api/contact -> also intercept /api/v1/contact
old1 = '  if (pathname === "/api/contact" && method === "POST") {'
new1 = '  if ((pathname === "/api/contact" || pathname === "/api/v1/contact") && method === "POST") {'
if old1 in content:
    content = content.replace(old1, new1)
    fixes.append('Fix 1: /api/v1/contact alias added')
else:
    fixes.append('Fix 1: /api/contact NOT FOUND')

# Fix /api/admin/orders -> also intercept /api/v1/admin/orders
old2 = '  if ((pathname === "/api/admin/orders" || pathname === "/api/v1/admin/orders") && method === "GET") {'
if old2 in content:
    fixes.append('Fix 2: /api/v1/admin/orders already aliased')
else:
    # Try to find it
    import re
    m = re.search(r'if .pathname.*admin/orders.*method.*GET', content)
    if m:
        fixes.append(f'Fix 2: already handled differently: {m.group()[:80]}')
    else:
        fixes.append('Fix 2: /api/admin/orders NOT FOUND')

# Check /api/v1/orders (already fixed earlier)
if '"/api/v1/orders"' in content and '"/api/orders"' in content:
    fixes.append('Fix 3: /api/v1/orders already aliased')
else:
    fixes.append('Fix 3: /api/v1/orders NOT aliased')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

for fix in fixes:
    print(fix)
print('DONE')
