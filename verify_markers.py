"""Quick marker syntax check (only counts, no execution)."""
import os
import subprocess
import sys
import re

env = os.environ.copy()
env['TEST_ENTRY'] = '1'
env['PYTHONIOENCODING'] = 'utf-8'

# Just check the 17 new test files specifically
files_to_check = [
    'meta/tests/test_user_group_api.py',
    'meta/tests/test_owner_transfer_api.py',
    'meta/tests/test_agent_api.py',
]

for f in files_to_check:
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', f, '--collect-only', '-q', '--no-header'],
        capture_output=True, cwd='d:/filework/excel-to-diagram', timeout=30, env=env,
    )
    out = r.stdout.decode('utf-8', errors='ignore')
    m = re.search(r'(\d+)\s+tests collected', out)
    if m:
        print(f'  {f:50s} {m.group(1)} tests')
    else:
        # Just print a status
        print(f'  {f:50s} status={r.returncode}, last 200: {out[-200:]}')
