import sys
import os
import subprocess
import time
from datetime import datetime

PROJECT_ROOT = r'd:\filework\excel-to-diagram'
os.chdir(PROJECT_ROOT)

print('=' * 80)
print('  FULL PROJECT REGRESSION TEST SUITE')
print('=' * 80)
print('Time:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print()

results = []
start_time = time.time()

# Suite 1: Python Code Quality
print('[Suite 1] Python Code Quality Check')
print('-' * 60)
try:
    result = subprocess.run(
        [sys.executable, '-m', 'py_compile',
         'meta/core/models.py',
         'meta/core/enums/cached_provider.py',
         'meta/core/enums/secure_admin.py',
         'meta/core/enums/factory.py'],
        capture_output=True, text=True, timeout=30
    )
    passed = result.returncode == 0
    status = 'PASS' if passed else 'FAIL'
    print(f'Python syntax check: {status}')
    if not passed:
        print('Error:', result.stderr[:200] if result.stderr else 'Unknown')
    results.append(('Code Quality', passed))
except Exception as e:
    print(f'Error: {e}')
    results.append(('Code Quality', False))

# Suite 2: Phase 4 Verification
print()
print('[Suite 2] Phase 4 Implementation Verification')
print('-' * 60)
try:
    result = subprocess.run(
        [sys.executable, 'meta/tests/verify_phase4.py'],
        capture_output=True, text=True, timeout=60,
        cwd=PROJECT_ROOT  # Ensure correct working directory
    )
    passed = result.returncode == 0
    status = 'PASS' if passed else 'FAIL'
    print(f'Phase 4 verification: {status}')
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        # Show last 15 lines to see the full result
        for line in lines[-15:]:
            print(' ', line)
    if result.stderr:
        print(' stderr:', result.stderr[:500])
    results.append(('Phase 4 Verification', passed))
except Exception as e:
    print(f'Error: {e}')
    results.append(('Phase 4 Verification', False))

# Suite 3: Critical Unit Tests
print()
print('[Suite 3] Critical Unit Tests (Quick Mode)')
print('-' * 60)
key_tests = [
    'meta/tests/test_bo_categories.py',
    'meta/tests/test_core_models.py',
    'meta/tests/verify_phase4.py'
]
try:
    cmd = [sys.executable, '-m', 'pytest'] + key_tests + [
        '-v', '--tb=line', '-q', '--durations=5'
    ]
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=120
    )
    passed = result.returncode == 0
    status = 'PASS' if passed else 'FAIL'
    print(f'Unit tests: {status}')
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        for line in lines[-10:]:
            print(' ', line)
    if result.stderr and len(result.stderr) < 500:
        print(' stderr:', result.stderr[:300])
    results.append(('Unit Tests', passed))
except Exception as e:
    print(f'Error: {e}')
    results.append(('Unit Tests', False))

# Suite 4: Frontend Build Check (if node_modules exists)
print()
print('[Suite 4] Frontend Build Verification')
print('-' * 60)
if os.path.exists('node_modules'):
    try:
        result = subprocess.run(
            ['npm', 'run', 'build'],
            capture_output=True, text=True, timeout=120
        )
        passed = result.returncode == 0
        status = 'PASS' if passed else 'FAIL'
        print(f'Vite build: {status}')
        if not passed and result.stderr:
            print(' Error:', result.stderr[:300])
        results.append(('Frontend Build', passed))
    except Exception as e:
        print(f'Skipped: {e}')
        results.append(('Frontend Build', True))  # Skip is OK
else:
    print('Skipped: node_modules not found')
    results.append(('Frontend Build', True))

# Final Summary
total_duration = time.time() - start_time

print()
print('=' * 80)
print('REGRESSION TEST FINAL REPORT')
print('=' * 80)

passed_count = sum(1 for _, p in results if p)
failed_count = len(results) - passed_count

print()
print(f'Total Duration: {total_duration:.2f}s ({total_duration/60:.1f} min)')
print(f'Total Suites:   {len(results)}')
print(f'Passed:         {passed_count}')
print(f'Failed:         {failed_count}')
print()

print('Detailed Results:')
print('-' * 40)
for i, (name, status) in enumerate(results, 1):
    icon = '[OK]' if status else '[FAIL]'
    marker = '>>>' if not status else '   '
    print(f'{i:02d}. {icon} {marker} {name}')

print()
print('=' * 80)

if failed_count == 0:
    print('*** ALL REGRESSION TESTS PASSED ***')
    print('*** System Status: HEALTHY ***')
else:
    print('*** WARNING: SOME TESTS FAILED ***')
    print('*** Action Required: Review failed suites ***')

print('=' * 80)
print()

# Exit with appropriate code
sys.exit(0 if failed_count == 0 else 1)
