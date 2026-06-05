#!/usr/bin/env python3
"""Find auth/me, logout and refreshAuthState calls in site.js"""
path = 'frontend/assets/js/shared/site.js'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '/api/v1/auth' in line or '/api/auth' in line or 'refreshAuthState' in line or 'getCurrentUser' in line:
        print(f"L{i+1}: {line.rstrip()}")
