"""Dry-run CI marker behavior."""
import os
import subprocess
import sys
import re

# Simulate CI env
env = os.environ.copy()
env['TEST_ENTRY'] = '1'
env['PYTHONIOENCODING'] = 'utf-8'

print('=== Dry-run: unit and not deprecated ===')
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'meta/tests/', '-m', 'unit and not deprecated', '--collect-only', '-q'],
    capture_output=True, cwd='d:/filework/excel-to-diagram', timeout=60, env=env,
)
out = r.stdout.decode('utf-8', errors='ignore')
err = r.stderr.decode('utf-8', errors='ignore')
m = re.search(r'(\d+)\s+tests collected', out)
if m:
    print(f'  [OK] {m.group(1)} tests collected (deprecated excluded)')
else:
    print('  OUT:', out[-500:])
    print('  ERR:', err[-500:])

print('\n=== Dry-run: api and not deprecated ===')
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'meta/tests/', '-m', 'api and not deprecated', '--collect-only', '-q'],
    capture_output=True, cwd='d:/filework/excel-to-diagram', timeout=60, env=env,
)
out = r.stdout.decode('utf-8', errors='ignore')
m = re.search(r'(\d+)\s+tests collected', out)
if m:
    print(f'  [OK] {m.group(1)} tests collected')

print('\n=== Dry-run: deprecated only ===')
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'meta/tests/', '-m', 'deprecated', '--collect-only', '-q'],
    capture_output=True, cwd='d:/filework/excel-to-diagram', timeout=60, env=env,
)
out = r.stdout.decode('utf-8', errors='ignore')
m = re.search(r'(\d+)\s+tests collected', out)
if m:
    print(f'  [OK] {m.group(1)} deprecated tests collected (for sunset monitoring)')

print('\n=== Dry-run: engine tests (test_*_eng.py) ===')
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'meta/tests/', '-k', '_eng', '--collect-only', '-q'],
    capture_output=True, cwd='d:/filework/excel-to-diagram', timeout=60, env=env,
)
out = r.stdout.decode('utf-8', errors='ignore')
m = re.search(r'(\d+)\s+tests collected', out)
if m:
    print(f'  [OK] {m.group(1)} engine tests collected')
