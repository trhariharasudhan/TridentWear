#!/usr/bin/env python3
"""Fix static mock API routes to handle /api/v1/ prefixes for orders, tracking."""
import re

path = 'frontend/assets/js/shared/api.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

fixes = []

# Fix 1: /api/orders (GET) - add /api/v1/orders alias
old1 = '  if (pathname === "/api/orders" && method === "GET") {'
new1 = '  if ((pathname === "/api/orders" || pathname === "/api/v1/orders") && method === "GET") {'
if old1 in content:
    content = content.replace(old1, new1)
    fixes.append('Fix 1: /api/v1/orders GET alias added')
else:
    fixes.append('Fix 1: /api/orders GET NOT FOUND')

# Fix 2: Tracking route - add v1 support
old2 = '  const trackingMatch = pathname.match(/^\\/api\\/orders\\/([^/]+)\\/tracking$/);\r\n  if (trackingMatch && method === "GET") {'
new2 = '  const trackingMatch = pathname.match(/^\\/api(?:\\/v1)?\\/orders\\/([^/]+)\\/tracking$/);\r\n  if (trackingMatch && method === "GET") {'
if old2 in content:
    content = content.replace(old2, new2)
    fixes.append('Fix 2: /api/v1/orders/id/tracking alias added')
else:
    # Try LF only
    old2_lf = '  const trackingMatch = pathname.match(/^\\/api\\/orders\\/([^/]+)\\/tracking$/);\n  if (trackingMatch && method === "GET") {'
    if old2_lf in content:
        new2_lf = '  const trackingMatch = pathname.match(/^\\/api(?:\\/v1)?\\/orders\\/([^/]+)\\/tracking$/);\n  if (trackingMatch && method === "GET") {'
        content = content.replace(old2_lf, new2_lf)
        fixes.append('Fix 2: /api/v1/orders/id/tracking alias added (LF)')
    else:
        # Just find and show
        idx = content.find('trackingMatch')
        fixes.append(f'Fix 2: NOT FOUND - snippet: {repr(content[idx:idx+120])}')

# Fix 3: Wishlist - add /api/v1/wishlist alias
old3 = '  if (pathname === "/api/wishlist" && method === "GET") {'
new3 = '  if ((pathname === "/api/wishlist" || pathname === "/api/v1/wishlist") && method === "GET") {'
if old3 in content:
    content = content.replace(old3, new3)
    fixes.append('Fix 3: /api/v1/wishlist GET alias added')
else:
    fixes.append('Fix 3: /api/wishlist GET NOT FOUND')

# Fix 4: Wishlist add - add /api/v1/wishlist/add alias
old4 = '  if (pathname === "/api/wishlist/add" && method === "POST") {'
new4 = '  if ((pathname === "/api/wishlist/add" || pathname === "/api/v1/wishlist/add") && method === "POST") {'
if old4 in content:
    content = content.replace(old4, new4)
    fixes.append('Fix 4: /api/v1/wishlist/add alias added')
else:
    fixes.append('Fix 4: /api/wishlist/add NOT FOUND')

# Fix 5: Wishlist remove - add /api/v1/wishlist/remove alias
old5 = '  if (pathname === "/api/wishlist/remove" && ["DELETE", "POST"].includes(method)) {'
new5 = '  if ((pathname === "/api/wishlist/remove" || pathname === "/api/v1/wishlist/remove") && ["DELETE", "POST"].includes(method)) {'
if old5 in content:
    content = content.replace(old5, new5)
    fixes.append('Fix 5: /api/v1/wishlist/remove alias added')
else:
    fixes.append('Fix 5: /api/wishlist/remove NOT FOUND')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

for fix in fixes:
    print(fix)
print('DONE')
