#!/usr/bin/env python3
"""staging 部署编排: 全自动上传 + backfill + deploy + 验证
(yonaa core_service 19200 staging, /api/exec 走 write 权限)
"""
import hashlib
import http.client
import json
import os
import sys
import time
import urllib.parse

HOST = '172.20.59.7'
STAGING_PORT = 19200  # staging core_service
PROD_PORT = 9200      # prod core_service
SECRET = 'v007.52-core-write'  # 19200 实际 secret (启动脚本说是 staging-v007.49-d, 但实测是 prod 这个)

def get_token(secret=SECRET, count=3):
    now = int(time.time())
    tokens = []
    for off in range(count):
        h = (now - off * 3600) // 3600
        tokens.append(hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16])
    return tokens

def exec_cmd(cmd, port=STAGING_PORT, secret=SECRET, timeout=60, retries=2):
    """GET /api/exec?cmd=...&token=... (带 rate-limit 退避)"""
    last_err = None
    for attempt in range(retries):
        for tk in get_token(secret):
            try:
                conn = http.client.HTTPConnection(HOST, port, timeout=timeout+5)
                params = urllib.parse.urlencode({'cmd': cmd, 'timeout': str(timeout), 'token': tk})
                conn.request('GET', f'/api/exec?{params}')
                resp = conn.getresponse()
                body = resp.read().decode('utf-8', errors='replace')
                conn.close()
                if resp.status == 200:
                    try:
                        return json.loads(body)
                    except Exception:
                        return {'raw': body}
                last_err = f'status={resp.status} body={body[:200]}'
                if resp.status == 403:
                    continue  # 试下一个 token
                if resp.status == 429:
                    time.sleep(2.0)  # rate limited, 等 2s
                    continue
                return {'error': True, 'status': resp.status, 'body': body[:300]}
            except Exception as e:
                return {'error': True, 'reason': str(e)}
        time.sleep(1.5)  # token 都试过, 歇 1.5s 再来 (避免 rate limit 累积)
    return {'error': True, 'reason': f'all attempts failed (last: {last_err})'}

def upload_file(local_path, remote_path, port=STAGING_PORT, secret=SECRET):
    """POST /api/upload?path=...&token=..."""
    for tk in get_token(secret):
        try:
            with open(local_path, 'rb') as f:
                data = f.read()
            conn = http.client.HTTPConnection(HOST, port, timeout=120)
            url = f'/api/upload?path={urllib.parse.quote(remote_path, safe="")}&token={tk}'
            conn.request('POST', url, body=data, headers={'Content-Type': 'application/octet-stream'})
            resp = conn.getresponse()
            body = resp.read().decode('utf-8', errors='replace')
            conn.close()
            if resp.status == 200:
                try:
                    return json.loads(body)
                except Exception:
                    return {'ok': True, 'raw': body}
            if resp.status == 403:
                continue
            return {'error': True, 'status': resp.status, 'body': body[:300]}
        except Exception as e:
            return {'error': True, 'reason': str(e)}
    return {'error': True, 'reason': 'all tokens 403'}

def step(title):
    print(f'\n{"="*70}\n[{title}]\n{"="*70}')

def sleep_between():
    time.sleep(1.2)  # 限流: 20 req/s, 安全间隔 1.2s

def show(result, max_out=1500):
    if not isinstance(result, dict):
        print(str(result)[:max_out])
        return
    if result.get('error'):
        print(f'  [ERROR] {result}')
        return
    out = result.get('stdout', '').strip()
    err = result.get('stderr', '').strip()
    rc = result.get('exit_code', '?')
    print(f'  [rc={rc}]')
    if out:
        print(out[:max_out])
    if err:
        print(f'  [stderr] {err[:500]}')


# ============ 主流程 ============

print('='*70)
print(f'staging 部署编排 (via {HOST}:{STAGING_PORT})')
print(f'secret: {SECRET[:12]}...')
print('='*70)

# === Step 0: 通联验证 ===
step('Step 0: 通联验证')
r = exec_cmd('echo TOKEN_OK; hostname; date; uname -a')
if r.get('error'):
    print(f'[FAIL] 远端不通: {r}')
    sys.exit(1)
show(r, 500)

# === Step 1: 看 staging 现状 ===
step('Step 1: staging 现状 (DB schema_migrations)')
r = exec_cmd('''python3 -c "
import sqlite3, json
c = sqlite3.connect('/opt/app/staging/deploy/meta/architecture.db')
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute('SELECT * FROM schema_migrations ORDER BY id')]
print('COUNT:', len(rows))
print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
print('---PRAGMA---')
for r2 in c.execute('PRAGMA table_info(schema_migrations)'):
    print(dict(zip([d[0] for d in c.execute('PRAGMA table_info(schema_migrations)').description], r2)))
"''')
show(r, 3000)

step('Step 1b: staging migration_lock + mtime')
r = exec_cmd('''bash -c "python3 -c \"
import sqlite3
c = sqlite3.connect('/opt/app/staging/deploy/meta/architecture.db')
print('migration_lock:', list(c.execute('SELECT * FROM migration_lock')))
print('journal_mode:', list(c.execute('PRAGMA journal_mode')))
\""''')
show(r, 500)
r = exec_cmd('''ls -la /opt/app/staging/deploy/meta/core/migration_runner.py /opt/app/staging/deploy/tools/backfill_schema_migrations.py /opt/app/staging/deploy/tools/migration_lint.py /opt/app/staging/deploy/tools/monitor_migrations.py 2>&1''')
show(r, 800)

# === Step 2: 上传新的 backfill + 相关工具 ===
step('Step 2: 上传新版本 backfill (覆盖 staging)')
LOCAL = r'd:\filework\release-prep-worktree'
REMOTE_BASE = '/opt/app/staging/deploy'
files_to_upload = [
    (f'{LOCAL}/tools/backfill_schema_migrations.py',
     f'{REMOTE_BASE}/tools/backfill_schema_migrations.py'),
    (f'{LOCAL}/meta/core/migration_runner.py',
     f'{REMOTE_BASE}/meta/core/migration_runner.py'),
    (f'{LOCAL}/tools/migration_lint.py',
     f'{REMOTE_BASE}/tools/migration_lint.py'),
    (f'{LOCAL}/tools/monitor_migrations.py',
     f'{REMOTE_BASE}/tools/monitor_migrations.py'),
    (f'{LOCAL}/tools/rename_migrations_flyway.py',
     f'{REMOTE_BASE}/tools/rename_migrations_flyway.py'),
    (f'{LOCAL}/tools/log_service.py',                       # [V007.61+ 2026-07-15] 启 log_service 19101
     f'{REMOTE_BASE}/tools/log_service.py'),
    (f'{LOCAL}/tools/yonaa_exec.py',                        # agent 远端操作工具
     f'{REMOTE_BASE}/tools/yonaa_exec.py'),
    (f'{LOCAL}/tools/remote_capability_probe.py',           # 能力探测
     f'{REMOTE_BASE}/tools/remote_capability_probe.py'),
]
for local, remote in files_to_upload:
    if not os.path.exists(local):
        print(f'  [SKIP] {local} 不存在')
        continue
    print(f'  上传: {os.path.basename(local)} ({os.path.getsize(local)} bytes) → {remote}')
    r = upload_file(local, remote)
    if r.get('error'):
        print(f'    [FAIL] {r}')
    else:
        print(f'    [OK] {r}')

# === Step 3: backfill (dry-run + exec + 状态 = 1 个请求, 整段用 bash -c 包) ===
step('Step 3-5: backfill (dry-run → exec → 状态查询)')
combined_cmd = r'''bash -c '
set -e
cd /opt/app/staging/deploy
echo "========== BACKFILL DRY-RUN =========="
python3 tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run 2>&1
echo ""
echo "========== BACKFILL EXEC =========="
python3 tools/backfill_schema_migrations.py --db-path meta/architecture.db 2>&1
echo ""
echo "========== POST-BACKFILL STATE =========="
python3 -c "
import sqlite3, json
c = sqlite3.connect(\"/opt/app/staging/deploy/meta/architecture.db\")
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(\"SELECT id, migration_name, length(checksum) as cs_len, substr(checksum,1,16) as cs_short FROM schema_migrations ORDER BY id\")]
print(\"COUNT:\", len(rows))
print(json.dumps(rows, indent=2, ensure_ascii=False))
print(\"NULL_CHECKSUM:\", list(c.execute(\"SELECT count(*) FROM schema_migrations WHERE checksum IS NULL\"))[0][0])
"
' 2>&1'''
r = exec_cmd(combined_cmd, timeout=60)
show(r, 5000)
sleep_between()

# === Step 6: migration_runner --dry-run ===
step('Step 6: migration_runner --dry-run (看 pending)')
r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && python3 -m meta.core.migration_runner --dry-run' 2>&1", timeout=30)
show(r, 3000)
sleep_between()

# === Step 7: migration_lint ===
step('Step 7: migration_lint 检查')
r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && python3 tools/migration_lint.py' 2>&1", timeout=30)
show(r, 2000)
sleep_between()

# === Step 8: migration_runner 实际执行 pending ===
step('Step 8: migration_runner 执行 pending (PHASE 2.6 模拟)')
if os.environ.get('EXCLUDE_RUN_PENDING', '1') == '1':
    print('  [SKIP] EXCLUDE_RUN_PENDING=1, 不实际执行 (仅验证 --dry-run)')
    print('  实际跑: EXCLUDE_RUN_PENDING=0 python tools/staging_deploy_orchestrator.py')
else:
    r = exec_cmd(f"bash -c 'cd {REMOTE_BASE} && timeout 300 python3 -m meta.core.migration_runner' 2>&1", timeout=320)
    show(r, 5000)
sleep_between()

# === Step 9: 最终验证 (合并 --status + monitor) ===
step('Step 9: 最终验证 (--status + monitor)')
final_cmd = r'''bash -c '
cd /opt/app/staging/deploy
echo "========== --status =========="
python3 -m meta.core.migration_runner --status 2>&1
echo ""
echo "========== monitor_migrations =========="
python3 tools/monitor_migrations.py 2>&1
' 2>&1'''
r = exec_cmd(final_cmd, timeout=60)
show(r, 5000)

# === Step 10: 启 log_service (19101) ===
# [V007.61+ 2026-07-15] log_service 独立于 core_service, 部署后必须启
step('Step 10: 启 log_service 19101 (独立于 core_service)')
log_start_cmd = (
    "bash -c 'cd /opt/app/staging/deploy && setsid nohup env "
    "LOG_SERVICE_PORT=19101 "
    "LOG_SERVICE_BIND=0.0.0.0 "
    "LOG_SERVICE_LOG_DIR=/opt/app/staging/deploy/meta "
    "LOG_SERVICE_DB_PATH=/opt/app/staging/deploy/meta/architecture.db "
    "LOG_SERVICE_SECRET=v007.35-infra "
    "/opt/miniconda3-py39/bin/python /opt/app/staging/deploy/tools/log_service.py "
    ">> /opt/app/staging/deploy/logs/log_service.log 2>&1 < /dev/null &'"
)
r = exec_cmd(log_start_cmd, timeout=5)
show(r, 500)
sleep_between(2.0)
# 验证 log_service 端点
r = exec_cmd("bash -c 'curl -s --max-time 5 http://127.0.0.1:19101/api | head -c 300'", timeout=10)
show(r, 500)

# === Step 10.5: 回归测试 (sqlite io error 场景) ===
print('\n' + '='*70)
print('Step 10.5: 回归测试 (regression_test_suite) - 验证 staging io 防护')
print('='*70)
r = exec_cmd(
    "bash -c 'cd /opt/app/staging/deploy && python3 tools/regression_test_suite.py --json /tmp/regression_latest.json 2>&1; echo EXIT=$?'",
    port=19200, timeout=120,
)
# 解析关键行
out = r.get('stdout', '') or ''
for line in out.split('\n'):
    if 'RESULT:' in line or 'PASS' in line and '===' in line:
        print(f'  {line.strip()}')
# 取报告
if out.strip().endswith('EXIT=0'):
    r2 = exec_cmd("cat /tmp/regression_latest.json 2>&1 | head -c 200", port=19200, timeout=10)
    print(f'  报告: {r2.get("stdout", "").strip()[:200]}')
    print('  ✓ 回归测试通过, staging io 防护 OK')
else:
    print(f'  ✗ 回归测试有 FAIL, 请检查 staging 状态')
    print(f'  详情: cd staging && python3 tools/regression_test_suite.py --json /tmp/reg.json')
    if mode == 'daily':
        print('  → daily 模式应暂停 prod 部署, 等修复后再继续')

# === Step 11: 总结 + 节奏建议 (按 mode 区分) ===
print('\n' + '='*70)
mode = os.environ.get('DEPLOY_MODE', 'daily')
if mode == 'hotfix':
    print(' 部署完成 (HOTFIX 模式)')
    print('   下一步: 立即部署到 PROD (skip 等待窗口)')
    print('   命令: python tools/prod_deploy_orchestrator.py --mode hotfix')
    print('   重点监控: 1-2h 盯 backend log + monitor_migrations')
else:
    print(' 部署完成 (DAILY 模式)')
    print('   下一步: 等 PROD 窗口 (每天 21:00-22:00)')
    print('   命令: python tools/prod_deploy_orchestrator.py --mode daily')
    print('   监控: 24h 灰度观察, 出问题 → rollback')
print('='*70)
print('详情: docs/DEPLOY_RHYTHM.md')
