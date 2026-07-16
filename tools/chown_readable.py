"""
chown 所有 log_service 启动需要读的文件/目录给 nobody

关键路径:
- /opt/app/deployments/tools/log_service.py       (prod+staging 实际跑的文件)
- /opt/app/deployments/meta/*                     (prod DB + backups)
- /opt/app/deployments/logs/*                     (prod logs)
- /opt/app/staging/meta/architecture.db           (staging DB)
- /opt/app/staging/deploy/current (symlink)        → 跟随
- /opt/app/staging/logs/*                         (staging logs)
- /opt/miniconda3-py39/bin/python                 (Python 解释器)
"""
import sys
sys.path.insert(0, r'd:\filework\release-prep-worktree\tools')
from yonaa_exec import yexec

cmds_prod = [
    # 让 log_service.py 可读 (root:root 755 → nobody 可读)
    'chmod a+r /opt/app/deployments/tools/log_service.py',
    'chmod a+rx /opt/app/deployments/tools',
    # tools 目录下其他可能用到的脚本
    'ls /opt/app/deployments/tools/ | head -20',
    # Python 解释器 nobody 应该能跑 (默认就是)
    'ls -la /opt/miniconda3-py39/bin/python',
    # meta 目录内所有文件 (包括 backup) 全部 nobody 可写
    'chmod -R u+rwX,g+rwX,o+rX /opt/app/deployments/meta',
    # logs 同理
    'chmod -R u+rwX,g+rwX,o+rX /opt/app/deployments/logs',
]

cmds_staging = [
    # staging 也是同样路径 (tools 是 symlink)
    'chmod a+r /opt/app/deployments/tools/log_service.py',
    # DB 文件本体 + 父目录
    'chmod -R u+rwX,g+rwX,o+rX /opt/app/staging/meta',
    'chmod -R u+rwX,g+rwX,o+rX /opt/app/staging/logs',
    # staging 部署目录里的所有 backup/chaos 文件 (systemd unit 文件不在 deploy_root, 但运行时不读这些)
    'chmod -R a+rX /opt/app/staging/deploy/v20260713_223807_staging',
]

# 跑 prod
print("\n========== prod ==========")
for cmd in cmds_prod:
    print(f"\n$ {cmd}")
    r = yexec(cmd, port=9200, secret='prod_write', timeout=30)
    out = r.get('stdout', '') or r.get('stderr', '')
    print(out)

# 跑 staging
print("\n========== staging ==========")
for cmd in cmds_staging:
    print(f"\n$ {cmd}")
    r = yexec(cmd, port=19200, secret='prod_write', timeout=30)
    out = r.get('stdout', '') or r.get('stderr', '')
    print(out)

# 最终验证: 模拟 nobody 读
print("\n========== 验证: nobody 能不能读 log_service.py ==========")
for target, port in [('prod', 9200), ('staging', 19200)]:
    print(f"\n[{target}]")
    r = yexec(
        'sudo -u nobody cat /opt/app/deployments/tools/log_service.py | head -3 2>&1 || '
        'su -s /bin/bash nobody -c "head -3 /opt/app/deployments/tools/log_service.py" 2>&1',
        port=port, secret='prod_write', timeout=10)
    out = r.get('stdout', '') or r.get('stderr', '')
    print(out)