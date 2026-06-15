import subprocess, os, sys
os.chdir(r'd:\filework\excel-to-diagram')
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
r = subprocess.run([sys.executable, 'test_svg_structure.py'], capture_output=True, env=env, timeout=180)
out = r.stdout.decode('utf-8', errors='replace')
err = r.stderr.decode('utf-8', errors='replace')
print('STDOUT:')
print(out)
print('STDERR:')
print(err)
print('RC:', r.returncode)
