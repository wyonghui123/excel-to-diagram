"""查找 log_service.py 在 prod 和 staging 的真实路径"""
import sys
sys.path.insert(0, r'd:\filework\worktrees/release-prep\tools')
from yonaa_exec import yexec

for target, port in [('prod', 9200), ('staging', 19200)]:
    print(f"\n========== {target} ==========")
    cmds = [
        # prod 是 /opt/app/deployments/tools/log_service.py
        # staging 真实目录是 v20260713_223807_staging
        'ls -la /opt/app/staging/deploy/v20260713_223807_staging/tools/log_service.py',
        'ls -la /opt/app/deployments/tools/log_service.py',
        # 看 systemd unit 里实际 ExecStart 指向哪
        'cat /etc/systemd/system/log_service_prod.service | grep ExecStart',
        'cat /etc/systemd/system/log_service_staging.service | grep ExecStart',
        # 看真实存在的 deployment 目录
        'ls -d /opt/app/deployments/v* 2>/dev/null || echo "no v* dirs"',
        'ls -d /opt/app/staging/deploy/v* 2>/dev/null || echo "no v* dirs"',
    ]
    for cmd in cmds:
        r = yexec(cmd, port=port, secret='prod_write', timeout=10)
        out = r.get('stdout', '') or r.get('stderr', '')
        print(f"$ {cmd}\n{out}")