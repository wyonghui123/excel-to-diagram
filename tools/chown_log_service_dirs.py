"""
chown nobody:nobody 所有 log_service 需要写的目录
- /opt/app/deployments/meta  (prod DB)
- /opt/app/deployments/logs  (prod 日志)
- /opt/app/staging/meta  (staging DB)
- /opt/app/staging/deploy/meta  (staging log dir)
- /opt/app/staging/logs  (staging 日志)
"""
import sys
sys.path.insert(0, r'd:\filework\release-prep-worktree\tools')
from yonaa_exec import yexec

# 路径白名单 (按 prod / staging 拆分)
PROD_DIRS = [
    '/opt/app/deployments/meta',
    '/opt/app/deployments/logs',
]
STAGING_DIRS = [
    '/opt/app/staging/meta',
    '/opt/app/staging/deploy/meta',
    '/opt/app/staging/logs',
]

def do_one(target: str, dirs: list):
    """在远端 chown 一批目录"""
    # 先 ls 看现状
    cmd = ' ; '.join([f'ls -ld {d}' for d in dirs])
    print(f"\n=== [{target}] 当前 owner ===")
    r = yexec(cmd, port=9200 if target == 'prod' else 19200,
              secret='prod_write', timeout=10)
    print(r.get('stdout', r.get('stderr', r)))

    # 创建目录 (如果不存在)
    cmd = ' ; '.join([f'mkdir -p {d}' for d in dirs])
    r = yexec(cmd, port=9200 if target == 'prod' else 19200,
              secret='prod_write', timeout=10)
    print(f"[{target}] mkdir 返回: {r.get('stdout', r.get('stderr', r))}")

    # chown nobody:nobody -R
    cmd = ' ; '.join([f'chown -R nobody:nobody {d}' for d in dirs])
    print(f"\n=== [{target}] 跑 chown ===")
    r = yexec(cmd, port=9200 if target == 'prod' else 19200,
              secret='prod_write', timeout=30)
    print(r.get('stdout', r.get('stderr', r)))

    # 验证
    cmd = ' ; '.join([f'ls -ld {d} && ls -l {d} | head -5' for d in dirs])
    print(f"\n=== [{target}] chown 后状态 ===")
    r = yexec(cmd, port=9200 if target == 'prod' else 19200,
              secret='prod_write', timeout=10)
    print(r.get('stdout', r.get('stderr', r)))


if __name__ == '__main__':
    do_one('prod', PROD_DIRS)
    do_one('staging', STAGING_DIRS)
    print('\n[DONE] chown 完成')