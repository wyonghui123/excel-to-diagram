"""
chown staging 的 deploy/current 目录 (因为 meta 是软链接 → current)
并确保所有 staging log_service 需要写的文件都是 nobody:nobody
"""
import sys
sys.path.insert(0, r'd:\filework\release-prep-worktree\tools')
from yonaa_exec import yexec

# staging 真实的 DB 路径
# /opt/app/staging/meta/architecture.db
# /opt/app/staging/deploy/meta -> /opt/app/staging/deploy/current (symlink)
# 所以需要 chown /opt/app/staging/deploy/current

cmds = [
    # 看 current 是啥
    'ls -ld /opt/app/staging/deploy/current',
    # chown current 目录
    'chown -R nobody:nobody /opt/app/staging/deploy/current',
    # 再看
    'ls -ld /opt/app/staging/deploy/current',
    'ls -ld /opt/app/staging/deploy/current/meta 2>&1 || echo "no meta subdir"',
    # 看 symlink target 是不是真的可写
    'ls -la /opt/app/staging/deploy/current/architecture.db 2>&1 || echo "no db at root, ok"',
    'ls -la /opt/app/staging/meta/architecture.db',
    # 看 log_service.py 当前是不是 nobody 可读
    'ls -la /opt/app/staging/deploy/current/tools/log_service.py',
]

for i, cmd in enumerate(cmds):
    print(f"\n=== [{i}] {cmd} ===")
    r = yexec(cmd, port=19200, secret='prod_write', timeout=10)
    out = r.get('stdout', '') or r.get('stderr', '')
    print(out)