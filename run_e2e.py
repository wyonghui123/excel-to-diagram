import subprocess
import os
import sys

os.chdir(r'd:\filework\excel-to-diagram')
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'

r = subprocess.run(
    [sys.executable, 'test_bidirectional_e2e.py'],
    capture_output=True,
    env=env,
    timeout=180
)
out = r.stdout.decode('utf-8', errors='replace')
err = r.stderr.decode('utf-8', errors='replace')
print('=== STDOUT ===')
print(out)
print('=== STDERR ===')
print(err)
print('RC:', r.returncode)

with open('e2e_run.log', 'wb') as f:
    f.write(b'=== STDOUT ===\n')
    f.write(out.encode('utf-8'))
    f.write(b'\n=== STDERR ===\n')
    f.write(err.encode('utf-8'))
    f.write(f'\nRC: {r.returncode}\n'.encode('utf-8'))
