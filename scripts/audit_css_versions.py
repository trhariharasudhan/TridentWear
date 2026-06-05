#!/usr/bin/env python3
"""Audit CSS version consistency across all HTML pages."""
import os
import re

pages_dir = 'frontend'
css_versions = {}
for root, dirs, files in os.walk(pages_dir):
    # Skip node_modules, __pycache__ etc
    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__']]
    for f in files:
        if f.endswith('.html'):
            full = os.path.join(root, f)
            try:
                c = open(full, encoding='utf-8').read()
            except Exception:
                continue
            m = re.search(r'styles\.css\?v=([^"]+)', c)
            if m:
                v = m.group(1)
                short = full.replace('frontend/', '')
                css_versions.setdefault(v, []).append(short)

for v, files in sorted(css_versions.items()):
    print('Version:', v)
    for f in files:
        print('  ', f)
