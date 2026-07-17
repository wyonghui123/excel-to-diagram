"""查找 staging log_service.py 实际位置"""
import sys
sys.path.insert(0, r'd:\filework\worktrees/release-prep\tools')
from yonaa_exec import yexec

cmds = [
    # staging 顶层 deploy 目录有没有
    'ls -la /opt/app/staging/deploy/tools/log_service.py 2>&1',
    'ls -la /opt/app/staging/deploy/ 2>&1 | head -20',
    # v20260713_223807_staging 目录里有什么
    'ls -la /opt/app/staging/deploy/v20260713_223807_staging/ 2>&1 | head -20',
    'ls -la /opt/app/staging/deploy/v20260713_223807_staging/tools/ 2>&1 | head -10',
    # 找所有 log_service.py
    'find /opt/app/staging -name "log_service.py" -type f 2>/dev/null',
]

for cmd in cmds:
    print(f"\n$ {cmd}")
    r = yexec(cmd, port=19200, secret='prod_write', timeout=10)
    out = r.get('stdout', '') or r.get('stderr', '')
    print(out)