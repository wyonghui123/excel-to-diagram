#!/usr/bin/env python3
"""prod_deploy_orchestrator.py - 一键 PROD 部署 (默认 daily, --mode hotfix)

基于 staging_deploy_orchestrator.py 改:
  1. port: 9200 (prod) vs 19200 (staging)
  2. deploy_root: /opt/app/deployments vs /opt/app/staging/deploy
  3. log_service port: 9101 vs 19101
  4. 多: PHASE 2 备份 (deploy.sh 自动)
  5. 多: 通知 (手动 - 群里说)

用法:
  python tools/prod_deploy_orchestrator.py                 # daily 模式
  DEPLOY_MODE=hotfix python tools/prod_deploy_orchestrator.py  # hotfix 模式

详见: docs/DEPLOY_RHYTHM.md
"""
import hashlib
import http.client
import json
import os
import sys
import time
import urllib.parse

HOST = '172.20.59.7'
PROD_PORT = 9200       # prod core_service (写)
SECRET = 'v007.52-core-write'

# 注: 工具本身只通过 9200 跑 (走 core_service 19200 启 prod 服务)
# prod core_service 19200 是 staging, prod 是 9200

# 上传文件清单 (与 staging 同步, 但走 prod 路径)
LOCAL = r'd:\filework\release-prep-worktree'
REMOTE_BASE = '/opt/app/deployments'   # prod root

FILES_TO_UPLOAD = [
    # migration
    (f'{LOCAL}/tools/backfill_schema_migrations.py', f'{REMOTE_BASE}/tools/backfill_schema_migrations.py'),
    (f'{LOCAL}/meta/core/migration_runner.py', f'{REMOTE_BASE}/meta/core/migration_runner.py'),
    (f'{LOCAL}/tools/migration_lint.py', f'{REMOTE_BASE}/tools/migration_lint.py'),
    (f'{LOCAL}/tools/migration_lint.legacy.yaml', f'{REMOTE_BASE}/tools/migration_lint.legacy.yaml'),
    (f'{LOCAL}/tools/monitor_migrations.py', f'{REMOTE_BASE}/tools/monitor_migrations.py'),
    (f'{LOCAL}/tools/rename_migrations_flyway.py', f'{REMOTE_BASE}/tools/rename_migrations_flyway.py'),
    (f'{LOCAL}/tools/log_service.py', f'{REMOTE_BASE}/tools/log_service.py'),
    # 远端操作工具 (供后续 agent 调用)
    (f'{LOCAL}/tools/yonaa_exec.py', f'{REMOTE_BASE}/tools/yonaa_exec.py'),
    (f'{LOCAL}/tools/remote_capability_probe.py', f'{REMOTE_BASE}/tools/remote_capability_probe.py'),
]


def get_token(secret=SECRET, count=3):
    now = int(time.time())
    return [hashlib.sha256(f"{secret}:{(now-off*3600)//3600}".encode()).hexdigest()[:16] for off in range(count)]


def exec_cmd(cmd, port=PROD_PORT, secret=SECRET, timeout=60, retries=2, bg=False):
    last_err = None
    for attempt in range(retries):
        for tk in get_token(secret):
            try:
                conn = http.client.HTTPConnection(HOST, port, timeout=timeout+5)
                params = urllib.parse.urlencode({
                    'cmd': cmd, 'timeout': str(timeout), 'token': tk,
                    'bg': '1' if bg else '0',
                })
                conn.request('GET', f'/api/exec?{params}')
                resp = conn.getresponse()
                body = resp.read().decode('utf-8', errors='replace')
                conn.close()
                if resp.status == 200:
                    try:
                        return json.loads(body)
                    except Exception:
                        return {'raw': body, 'stdout': body, 'exit_code': 0, 'stderr': ''}
                if resp.status == 403:
                    continue
                if resp.status == 429:
                    time.sleep(2.0); break
                if resp.status == 0:
                    break
                return {'error': True, 'status': resp.status, 'body': body[:200]}
            except Exception as e:
                last_err = {'error': True, 'error_class': 'network', 'reason': str(e)[:200]}
        time.sleep(1.0)
    return last_err or {'error': True, 'reason': 'all retries failed'}


def sleep_between(sec=1.2):
    time.sleep(sec)


def show(r, max_len=2000):
    if r.get('error'):
        print(f'  [ERR] {r}')
        return
    out = r.get('stdout', '') or ''
    err = r.get('stderr', '') or ''
    code = r.get('exit_code', '?')
    if out:
        out = out[:max_len] + ('...' if len(out) > max_len else '')
        print(f'  [stdout exit={code}] {out}')
    if err:
        err = err[:500]
        print(f'  [stderr] {err}')


def step(label):
    print(f'\n{"="*70}\n{label}\n{"="*70}')


# 复用 yonaa_exec 的 upload 函数 (从 staging_deploy_orchestrator 复制)
def upload_file(local, remote, port=PROD_PORT, secret=SECRET, timeout=120):
    """通过 yonaa_exec.yupload (代理) — 实际走 core_service /api/upload"""
    sys.path.insert(0, f'{LOCAL}/tools')
    try:
        from yonaa_exec import yupload
        return yupload(local, remote, port=port, secret=secret, timeout=timeout)
    except Exception as e:
        return {'error': True, 'error_class': 'import', 'reason': str(e)}


def main():
    mode = os.environ.get('DEPLOY_MODE', 'daily')
    print(f'PROD 部署编排 (mode={mode})')
    print(f'详见: docs/DEPLOY_RHYTHM.md')

    # Step 0: 探测
    step('Step 0: 探测 prod 9200 通')
    r = exec_cmd("echo OK")
    if r.get('error'):
        print(f'  ✗ prod 9200 不通: {r}'); sys.exit(1)
    print(f'  ✓ {r.get("stdout", "").strip()}')
    sleep_between()

    # Step 1: 检查 staging 状态 (确认 prod 部署前 staging 健康)
    if mode == 'daily':
        step('Step 1: 确认 staging 状态 (daily 模式必须 staging 已验证)')
        r = exec_cmd("bash -c 'python3 -c \"import sqlite3; c=sqlite3.connect(\\\"/opt/app/staging/deploy/meta/architecture.db\\\"); print(\\\"FAILED:\\\", c.execute(\\\"SELECT COUNT(*) FROM schema_migrations WHERE status=\\\\\\\"FAILED\\\\\\\"\\\").fetchone()[0])\"' 2>&1", port=19200)
        out = r.get('stdout', '').strip()
        if 'FAILED: 0' in out:
            print('  ✓ staging 0 FAILED, 可以部署 prod')
        else:
            print(f'  ✗ staging 有 FAILED, 禁止 prod 部署: {out}')
            print('  → 先修 staging, 或切 hotfix 模式')
            sys.exit(1)
        sleep_between()

    # Step 2: 上传新文件
    step('Step 2: 上传新文件')
    for local, remote in FILES_TO_UPLOAD:
        if not os.path.exists(local):
            print(f'  [SKIP] {local} 不存在')
            continue
        r = upload_file(local, remote)
        if r.get('error'):
            print(f'  [FAIL] {local} → {remote}: {r}')
            if mode == 'daily':
                print('  → daily 模式禁止继续 (会污染 prod)')
                sys.exit(1)
        else:
            print(f'  [OK] {os.path.basename(local)} ({os.path.getsize(local)} bytes) → {remote}')
        sleep_between()

    # Step 3: migration_lint
    step('Step 3: migration_lint (prod)')
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && python3 tools/migration_lint.py 2>&1; echo EXIT=$?'")
    show(r, 3000)
    sleep_between()

    # Step 4: 备份 (部署前)
    step('Step 4: 备份 prod DB (deploy.sh PHASE 2 自动)')
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && cp meta/architecture.db backups/architecture.db.pre_prod_deploy_$(date +%Y%m%d_%H%M%S) 2>&1'")
    if r.get('error'):
        print(f'  ✗ 备份失败: {r}')
        if mode == 'daily':
            print('  → daily 模式禁止继续')
            sys.exit(1)
    else:
        print('  ✓ 备份完成')
        # 验证备份
        r = exec_cmd("ls -la /opt/app/deployments/backups/ | tail -3")
        show(r, 500)
    sleep_between()

    # Step 5: backfill (新环境才需要, prod 已有表会幂等)
    step('Step 5: backfill_schema_migrations (dry-run)')
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && python3 tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run 2>&1 | head -20'")
    show(r, 3000)
    sleep_between()

    # Step 6: migration_runner --dry-run
    step('Step 6: migration_runner --dry-run (看 pending)')
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && python3 -m meta.core.migration_runner --dry-run 2>&1'")
    show(r, 3000)
    sleep_between()

    # Step 7: 实际跑 migration
    if mode == 'hotfix':
        print('\n  [HOTFIX] 跳过 dry-run 暂停, 立即跑')
    step('Step 7: 跑 migration (实际)')
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && timeout 300 python3 -m meta.core.migration_runner 2>&1'")
    show(r, 5000)
    sleep_between()

    # Step 8: 验证
    step('Step 8: 最终验证 (--status + monitor)')
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && python3 -m meta.core.migration_runner --status 2>&1; echo === MONITOR ===; python3 tools/monitor_migrations.py 2>&1'")
    show(r, 5000)
    sleep_between()

    # Step 9: 启 log_service (9101)
    step('Step 9: 启 log_service 9101')
    start_log = (
        "bash -c 'cd /opt/app/deployments && setsid nohup env "
        "LOG_SERVICE_PORT=9101 LOG_SERVICE_BIND=0.0.0.0 "
        "LOG_SERVICE_LOG_DIR=/opt/app/deployments/meta "
        "LOG_SERVICE_DB_PATH=/opt/app/deployments/meta/architecture.db "
        "LOG_SERVICE_SECRET=v007.35-infra "
        "/opt/miniconda3-py39/bin/python /opt/app/deployments/tools/log_service.py "
        ">> /opt/app/deployments/logs/log_service.log 2>&1 < /dev/null &'"
    )
    r = exec_cmd(start_log, timeout=5, bg=True)
    print(f'  start: {r.get("pid", r)}')
    sleep_between(2.0)
    r = exec_cmd("bash -c 'curl -s --max-time 5 http://127.0.0.1:9101/api | head -c 200'")
    show(r, 500)
    sleep_between()

    # 总结
    print('\n' + '='*70)
    if mode == 'hotfix':
        print(' PROD 部署完成 (HOTFIX 模式)')
        print('   监控重点 (1-2h):')
        print('   - tail -f /opt/app/shared/logs/backend-*.log')
        print('   - 跑 monitor_migrations 至少 1 次')
        print('   - 用户反馈 (群里)')
    else:
        print(' PROD 部署完成 (DAILY 模式)')
        print('   灰度观察 24h:')
        print('   - 监控 backend log')
        print('   - 跑 monitor_migrations 至少 2 次 (6h/24h)')
        print('   - 出问题 → rollback (用旧版本 vXXX)')
    print('='*70)


if __name__ == '__main__':
    main()
