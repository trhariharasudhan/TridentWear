#!/usr/bin/env python3
"""Find and report all static mock route handlers in api.js"""
import re

path = 'frontend/assets/js/shared/api.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the handleStaticRequest function and print auth-related handlers
idx_start = content.find('async function handleStaticRequest')
if idx_start == -1:
    idx_start = content.find('function handleStaticRequest')
idx_end = content.find('\nexport function resolveUrl')
func_body = content[idx_start:idx_end]

# Print all pathname-related if statements
lines = func_body.split('\n')
for i, line in enumerate(lines):
    if ('pathname' in line and ('auth' in line.lower() or 'send-otp' in line.lower() or 'verify-otp' in line.lower())) or \
       ('auth/login' in line or 'auth/register' in line or 'auth/me' in line or 'auth/logout' in line):
        print(f"L{i}: {line.rstrip()}")
