#!/usr/bin/env python3
"""Normalize all CSS version query strings to the latest version across all HTML pages."""
import os
import re

LATEST_VERSION = "20260430-v3"
pages_dir = 'frontend'
fixed = []

# Also fix JS version query strings
JS_LATEST = "9"  # as used in most imports already

def fix_file(full_path):
    try:
        with open(full_path, encoding='utf-8') as f:
            content = f.read()
        
        original = content
        # Fix CSS version
        content = re.sub(r'styles\.css\?v=[^"]+', f'styles.css?v={LATEST_VERSION}', content)
        
        if content != original:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f'ERROR {full_path}: {e}')
        return False

for root, dirs, files in os.walk(pages_dir):
    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__']]
    for f in files:
        if f.endswith('.html'):
            full = os.path.join(root, f)
            if fix_file(full):
                fixed.append(full.replace('frontend/', ''))

print(f'Fixed {len(fixed)} HTML files:')
for f in fixed:
    print(f'  {f}')
print('All CSS versions now:', LATEST_VERSION)
