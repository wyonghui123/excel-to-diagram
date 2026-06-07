import subprocess
import time
import os
import sys

os.environ['PORT'] = '3011'
os.environ['SKIP_PORT_CHECK'] = '1'

os.chdir(r'd:\filework\excel-to-diagram\meta')

proc = subprocess.Popen(
    [sys.executable, 'server.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    env={**os.environ, 'PORT': '3011'}
)

print("Backend server started on port 3011, waiting for startup...")
time.sleep(8)
print("Backend should be ready now")

for line in proc.stdout:
    print(line, end='')
