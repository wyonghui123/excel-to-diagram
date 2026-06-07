"""Run all 12 refactored test files and report results."""
import subprocess
import sys

files = [
    'test_agent_api.py',
    'test_filter_variant_api.py',
    'test_value_help_api.py',
    'test_annotation_routes_api.py',
    'test_data_permission_api.py',
    'test_object_identity_api.py',
    'test_query_api.py',
    'test_permission_rule_api.py',
    'test_owner_transfer_api.py',
    'test_export_import_api.py',
    'test_task_api.py',
    'test_user_group_api.py',
]

for f in files:
    try:
        r = subprocess.run(
            [sys.executable, 'd:/filework/test.py', '--file', f'meta/tests/{f}'],
            capture_output=True, cwd='d:/filework/excel-to-diagram', timeout=120,
        )
        out = r.stdout.decode('utf-8', errors='ignore')
        # Find last "X passed" or "X failed"
        import re
        m = re.search(r'(\d+)\s+(passed|failed|error)', out.split('===============')[-1] if '=========' in out else out)
        if m:
            count, status = m.group(1), m.group(2)
            icon = 'OK' if status == 'passed' else 'FAIL'
            print(f'  [{icon}] {f:45s} {count} {status}', flush=True)
        else:
            print(f'  [???] {f:45s} no summary', flush=True)
            # Print last 3 lines for debugging
            lines = out.splitlines()
            for l in lines[-3:]:
                if l.strip():
                    print(f'       {l[:120]}', flush=True)
    except Exception as e:
        print(f'  [ERR] {f:45s} {e}', flush=True)
