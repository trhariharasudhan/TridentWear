#!/usr/bin/env python3
"""Check JS import version strings in HTML files."""
import os
import re

pages_dir = 'frontend'
for root, dirs, files in os.walk(pages_dir):
    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__']]
    for f in files:
        if f.endswith('.html'):
            full = os.path.join(root, f)
            try:
                c = open(full, encoding='utf-8').read()
            except Exception:
                continue
            # Find JS script tags with version strings
            matches = re.findall(r'src="[^"]+\?v=([^"]+)"', c)
            if matches:
                versions = set(matches)
                if len(versions) > 1:
                    print(f'{full.replace("frontend/", "")}: Multiple JS versions: {versions}')
                else:
                    v = list(versions)[0]
                    if v not in ('9', '20260430-v3', '20260423-frontend'):
                        print(f'{full.replace("frontend/", "")}: Non-standard JS version: {v}')
print('Done')
