import subprocess
import os
import sys

env = os.environ.copy()
env['PORT'] = '3011'

os.chdir(r'd:\filework\excel-to-diagram\meta')

proc = subprocess.Popen(
    [sys.executable, 'server.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    env=env
)

print("Backend server starting on port 3011...")

import time
time.sleep(15)
print("Backend should be ready now - keeping server running...")
proc.wait()
