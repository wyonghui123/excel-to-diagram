"""Run remaining 3 test files and report results."""
import subprocess
import sys

files = [
    'meta/tests/test_owner_transfer_api.py',
    'meta/tests/test_user_group_api.py',
]

for f in files:
    print(f"\n=== {f} ===", flush=True)
    try:
        r = subprocess.run(
            [sys.executable, 'd:/filework/test.py', '--file', f],
            capture_output=True, timeout=120, cwd='d:/filework/excel-to-diagram',
        )
        # Try utf-8 then gbk
        for enc in ('utf-8', 'gbk'):
            try:
                out = (r.stdout or b'').decode(enc, errors='ignore')
                break
            except Exception:
                continue
        else:
            out = (r.stdout or b'').decode('utf-8', errors='ignore')
        # Find last passed/failed summary
        lines = out.splitlines()
        summary = [l for l in lines if 'passed' in l.lower() or 'failed' in l.lower() or 'error' in l.lower()]
        for line in summary[-3:]:
            print(f"  {line}", flush=True)
        if r.returncode != 0:
            print(f"  [exit code: {r.returncode}]", flush=True)
    except Exception as e:
        print(f"  [error: {e}]", flush=True)
