#!/usr/bin/env python3
"""Fix normalizeImagePath in api.js to handle backend /images/ paths."""
import re

path = 'frontend/assets/js/shared/api.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace normalizeImagePath function
# Match the existing function (handles both CRLF and LF)
old_pattern = r'function normalizeImagePath\(value\) \{[^}]+\}'
new_func = (
    'function normalizeImagePath(value) {\r\n'
    '  if (!value) {\r\n'
    '    return "/assets/images/hero-banner.jpg";\r\n'
    '  }\r\n'
    '  if (value.startsWith("data:") || /^https?:\\/\\//.test(value)) {\r\n'
    '    return value;\r\n'
    '  }\r\n'
    '  // Backend serves images at /images/ - remap to /assets/images/ for frontend\r\n'
    '  if (value.startsWith("/images/")) {\r\n'
    '    return `/assets${value}`;\r\n'
    '  }\r\n'
    '  if (value.startsWith("/")) {\r\n'
    '    return value;\r\n'
    '  }\r\n'
    '  return `/${String(value).replace(/^\\.?\\//, "")}`;\r\n'
    '}'
)

new_content = re.sub(old_pattern, new_func, content, flags=re.DOTALL)
if new_content == content:
    print('WARNING: pattern not matched - no change made')
    # Try to print what's there for debug
    idx = content.find('function normalizeImagePath')
    print(repr(content[idx:idx+200]))
else:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('SUCCESS: normalizeImagePath updated')
