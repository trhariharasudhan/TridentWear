#!/usr/bin/env python3
"""Find the login handler block in api.js"""
path = 'frontend/assets/js/shared/api.js'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'api/auth/login' in line:
        # Print surrounding 30 lines
        start = max(0, i)
        end = min(len(lines), i + 40)
        for j in range(start, end):
            print(f"L{j+1}: {lines[j]}", end='')
        print()
        break
