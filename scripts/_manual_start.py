"""直接手动启 Waitress（detached + log），看 startup 哪一步卡住"""
import os, subprocess, sys, time
from pathlib import Path

ROOT = Path(r'd:\filework\excel-to-diagram')
LOGS = ROOT / 'logs'
LOGS.mkdir(exist_ok=True)

env = os.environ.copy()
env['AGENT_PORT'] = '3011'
env['PORT'] = '3011'
env['PYTHONUNBUFFERED'] = '1'

log = open(LOGS / 'waitress_manual.log', 'wb')
p = subprocess.Popen(
    [sys.executable, '-u', 'waitress_server.py'],
    cwd=str(ROOT),
    env=env,
    stdout=log, stderr=subprocess.STDOUT,
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
)
print(f"spawned pid={p.pid}")
print("waiting 15s...")
time.sleep(15)
log.flush()
print("done. tail log:")
log_text = (LOGS / 'waitress_manual.log').read_text(errors='replace')
print(log_text[-2000:])