import subprocess, os, sys
os.chdir(r'd:\filework\excel-to-diagram')
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
r = subprocess.run([sys.executable, 'test_e2e_console.py'], capture_output=True, env=env, timeout=180)
out = r.stdout.decode('utf-8', errors='replace')
print(out)
print('RC:', r.returncode)
