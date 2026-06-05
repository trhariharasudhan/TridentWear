#!/usr/bin/env python3
"""Fix multiple issues in api.js static mock handler."""
import re

path = 'frontend/assets/js/shared/api.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

fixes = []

# Fix 1: /api/auth/me should also handle /api/v1/auth/me 
old1 = '  if (pathname === "/api/auth/me" && method === "GET") {'
new1 = '  if ((pathname === "/api/auth/me" || pathname === "/api/v1/auth/me") && method === "GET") {'
if old1 in content:
    content = content.replace(old1, new1)
    fixes.append('Fix 1: /api/v1/auth/me intercept added')
else:
    fixes.append('Fix 1: NOT FOUND - ' + repr(content[content.find('/api/auth/me'):content.find('/api/auth/me')+100]))

# Fix 2: /api/auth/register should also handle /api/v1/auth/register
old2 = '  if (pathname === "/api/auth/register" && method === "POST") {'
new2 = '  if ((pathname === "/api/auth/register" || pathname === "/api/v1/auth/register") && method === "POST") {'
if old2 in content:
    content = content.replace(old2, new2)
    fixes.append('Fix 2: /api/v1/auth/register intercept added')
else:
    fixes.append('Fix 2: /api/auth/register NOT FOUND')

# Fix 3: /api/auth/login should also handle /api/v1/auth/login
old3 = '  if (pathname === "/api/auth/login" && method === "POST") {'
new3 = '  if ((pathname === "/api/auth/login" || pathname === "/api/v1/auth/login") && method === "POST") {'
if old3 in content:
    content = content.replace(old3, new3)
    fixes.append('Fix 3: /api/v1/auth/login intercept added')
else:
    fixes.append('Fix 3: /api/auth/login NOT FOUND')

# Fix 4: /api/auth/logout should also handle /api/v1/auth/logout
old4 = '  if (pathname === "/api/auth/logout" && method === "POST") {'
new4 = '  if ((pathname === "/api/auth/logout" || pathname === "/api/v1/auth/logout") && method === "POST") {'
if old4 in content:
    content = content.replace(old4, new4)
    fixes.append('Fix 4: /api/v1/auth/logout intercept added')
else:
    fixes.append('Fix 4: /api/auth/logout NOT FOUND')

# Fix 5: Add /api/v1/orders/stats to the /api/stats handler
old5 = '  if (pathname === "/api/stats" && method === "GET") {'
new5 = '  if ((pathname === "/api/stats" || pathname === "/api/v1/orders/stats") && method === "GET") {'
if old5 in content:
    content = content.replace(old5, new5)
    fixes.append('Fix 5: /api/v1/orders/stats intercept added')
else:
    fixes.append('Fix 5: /api/stats NOT FOUND')

# Fix 6: Add /api/v1/payments/ aliases for the COD/verify payment routes
# Already handled in static mock: pathname === "/api/payment/cod" || pathname === "/api/v1/payments/cod"
# Check if v1 aliases exist
if '"/api/v1/payments/cod"' in content:
    fixes.append('Fix 6: Payment v1 aliases already present')
else:
    fixes.append('Fix 6: Payment v1 aliases MISSING (needs manual check)')

# Fix 7: Add /api/v1/account/profile handler for profile page
if '"/api/v1/account/profile"' in content:
    fixes.append('Fix 7: /api/v1/account/profile already present')
else:
    fixes.append('Fix 7: /api/v1/account/profile MISSING')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

for fix in fixes:
    print(fix)
print('DONE')
