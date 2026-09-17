"""启动前端 + 后端（detached + log）"""
import os
import sys
import subprocess
import time
from pathlib import Path

ROOT = Path(r'd:\filework\excel-to-diagram')
LOGS = ROOT / 'logs'
LOGS.mkdir(exist_ok=True)

# 1. 前端 vite (port 3004)
print("Starting vite on 3004...")
vite_log = LOGS / 'vite.log'
v = subprocess.Popen(
    ['cmd', '/c', 'cd /d d:\\filework\\excel-to-diagram && npm run dev -- --port 3004 --host 127.0.0.1'],
    stdout=open(vite_log, 'ab'), stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
)
print(f"  vite pid={v.pid}")

# 2. 后端 flask (port 3010)
print("Starting flask on 3010...")
env = os.environ.copy()
env['PORT'] = '3010'
env['SKIP_PORT_CHECK'] = '1'

flask_log = LOGS / 'flask3010.log'
f = subprocess.Popen(
    [sys.executable, 'server.py'],
    cwd=str(ROOT / 'meta'),
    env=env,
    stdout=open(flask_log, 'ab'),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
)
print(f"  flask pid={f.pid}")

print("Waiting 18s for warmup...")
time.sleep(18)
print("Done")