"""验证 nobody 起服务 + 端口活"""
import sys
sys.path.insert(0, r'd:\filework\release-prep-worktree\tools')
from yonaa_exec import yexec

for target, port in [('prod', 9200), ('staging', 19200)]:
    print(f"\n========== {target} ==========")
    cmds = [
        # 用 PID 直接看 (从 systemctl status 拿)
        f'ps -p 28433 -o pid,user,cmd 2>&1' if target == 'prod' else f'ps -p 28464 -o pid,user,cmd 2>&1',
        # 通用: 看所有 nobody 跑的 python
        f'ps -ef | grep nobody | grep -v grep',
        # 端口监听
        f'netstat -tlnp 2>/dev/null | grep -E ":(9101|19101)"',
        # 端口探测
        f'curl -s -o /dev/null -w "%{{http_code}}\\n" http://localhost:{9101 if target == "prod" else 19101}/api/health 2>&1',
    ]
    for cmd in cmds:
        print(f"\n$ {cmd}")
        r = yexec(cmd, port=port, secret='prod_write', timeout=10)
        out = r.get('stdout', '') or r.get('stderr', '')
        print(out)