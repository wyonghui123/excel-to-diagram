"""Test with snapshot path to see if env var is the issue"""
import subprocess, sys, os, glob

test_temp = r'd:\filework\test_temp'
snapshots = sorted(glob.glob(test_temp + r'\architecture_snapshot_*.db'))
if not snapshots:
    print("No snapshots found")
    sys.exit(1)

snap = snapshots[-1]
print(f'Using snapshot: {snap}')

env = os.environ.copy()
env['TEST_ENTRY'] = '1'
env['TESTING'] = 'true'
env['DISABLE_WRITE_QUEUE'] = 'true'
env['SQLITE_DB_PATH'] = snap
env['ARCH_DB_PATH'] = snap
env['TEST_DB_PATH'] = snap
env['TEST_TEMP_DIR'] = test_temp
env['PYTHONPATH'] = r'd:\filework'
env['PYTHONUNBUFFERED'] = '1'
env['DISABLE_RATE_LIMIT'] = 'true'
env['FAILED_TESTS_FILE'] = r'd:\filework\test_failed_snap.jsonl'

# Run test_bo_api.py which has 109 tests
PROJECT_ROOT = r'd:\filework\excel-to-diagram'
test_files = ['meta/tests/test_bo_api.py', 'meta/tests/test_enum_api.py']
for tf in test_files:
    full = os.path.join(PROJECT_ROOT, tf)
    print(f'Test file: {full} exists={os.path.exists(full)}')

result = subprocess.run(
    [sys.executable, '-u', '-m', 'pytest', 
     str(os.path.join(PROJECT_ROOT, 'meta/tests/test_bo_api.py')),
     '--tb=line', '-v', '-W', 'ignore', '-n', '0'],
    capture_output=True, env=env, cwd=PROJECT_ROOT, timeout=180
)

stdout = result.stdout.decode('utf-8', errors='replace')
stderr = result.stderr.decode('utf-8', errors='replace')

# Show summary
for line in stdout.split('\n')[-15:]:
    print(line)

print(f'\nReturn code: {result.returncode}')

# Count results
import re
passed = len(re.findall(r' PASSED', stdout))
failed = len(re.findall(r' FAILED', stdout))
errors_count = len(re.findall(r' ERROR', stdout))
print(f'Passed: {passed}, Failed: {failed}, Errors: {errors_count}')
print(f'SystemExit: {stdout.count("SystemExit")}')
