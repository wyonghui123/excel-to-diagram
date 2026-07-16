import subprocess
r = subprocess.run(['cmd.exe', '/c', '"C:\Program Files\Git\bin\bash.exe" --version'], capture_output=True, text=True, timeout=10)
print('STDOUT:', r.stdout)
print('STDERR:', r.stderr)
print('RC:', r.returncode)
