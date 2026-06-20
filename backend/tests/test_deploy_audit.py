import os

with open('.gitignore') as f:
    gi = f.read()

checks = [
    ('.env protected', '.env' in gi),
    ('__pycache__/ ignored', '__pycache__/' in gi),
    ('node_modules/ ignored', 'node_modules/' in gi),
    ('*.log ignored', '*.log' in gi),
    ('db/*.tmp.json ignored', 'db/*.tmp.json' in gi),
    ('db/*.backup.json ignored', 'db/*.backup.json' in gi),
    ('*.pyc ignored', '*.pyc' in gi),
]
print('=== .gitignore coverage ===')
for name, ok in checks:
    print(('[OK]  ' if ok else '[WARN]'), name)

print()
print('=== deployment files ===')
targets = [
    'backend/requirements.txt',
    'requirements.txt',
    'backend/pyproject.toml',
    'Procfile',
    'render.yaml',
    'railway.toml',
    'Dockerfile',
    'docker-compose.yml',
    'backend/.env',
    '.env.example',
]
for f in targets:
    status = 'EXISTS' if os.path.exists(f) else 'MISSING'
    print(f'  {status}  {f}')
