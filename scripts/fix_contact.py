#!/usr/bin/env python3
"""Fix contact.js to use /api/v1/contact"""
path = 'frontend/assets/js/pages/contact.js'
with open(path, encoding='utf-8') as f:
    content = f.read()

# Also fix the static mock to intercept /api/contact -> /api/v1/contact
old = '"/api/contact"'
new = '"/api/v1/contact"'
if old in content:
    new_content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'FIXED: {old} -> {new}')
else:
    print('NOT FOUND in contact.js, showing relevant lines:')
    for i, line in enumerate(content.split('\n')):
        if 'contact' in line.lower() and 'api' in line.lower():
            print(f'L{i+1}: {line}')
