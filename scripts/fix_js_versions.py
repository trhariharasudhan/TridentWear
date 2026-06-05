#!/usr/bin/env python3
"""Fix non-standard JS version strings in a few HTML files."""
import os
import re

LATEST_JS_VERSION = "20260430-v3"
files_to_fix = [
    'frontend/pages/admin/chat.html',
    'frontend/pages/info/about.html',
    'frontend/pages/support/chat.html',
]

for path in files_to_fix:
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
        original = content
        # Normalize JS file version strings (not CSS, just script src ?v=)
        content = re.sub(r'(\.js)\?v=20260424(-mobile-grid|-polish|)', r'\g<1>?v=' + LATEST_JS_VERSION, content)
        content = re.sub(r'(\.js)\?v=20260425(-polish|)', r'\g<1>?v=' + LATEST_JS_VERSION, content)
        if content != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Fixed: {path}')
        else:
            print(f'No change: {path}')
    except Exception as e:
        print(f'ERROR {path}: {e}')
