#!/usr/bin/env python3
"""Deploy delta zip to staging + DB safety preflight/backup/verify + graceful backend restart.

[2026-08-18 v2] 针对 DB 损坏根因加固:
  - 部署前 DB 安全预检: wal_checkpoint(PASSIVE) + journal_mode=DELETE + quick_check (fail-fast)
  - 部署前 DB 快照备份 + 备份 quick_check 校验
  - 优雅停止后端 (SIGTERM → 等待 → SIGKILL 兜底), 不再直接 pkill -9
  - 部署后 DB 完整性 + 关键表计数验证
  - 后端 13011 优雅重启

Usage (on staging): python3 _deploy_delta_staging.py /tmp/deploy-<VER>.zip

Mapping (matches staging baseline):
  changed/meta/*              -> /opt/app/staging/deploy/current/*   (strip meta/)
  changed/frontend_dist_files/* -> /opt/app/staging/frontend_dist_files/*
Handles DELETED.txt (only frontend_dist_files asset rotation).
Writes MANIFEST for future delta reconciliation.
"""
import os, sys, time, shutil, zipfile, sqlite3, subprocess, glob, signal

META_DIR = '/opt/app/staging/deploy/current'
FE_DIR = '/opt/app/staging/frontend_dist_files'
DB_PATH = '/opt/app/staging/deploy/meta/architecture.db'
BACKEND_PY = '/opt/miniconda3-py39/bin/python'
BACKEND_SRV = '/opt/app/staging/deploy/current/server.py'
BACKEND_PORT = 13011


def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, **kw)


def graceful_stop_backend():
    """SIGTERM → 等待退出 (10s) → SIGKILL 兜底. 避免 WAL 因强杀未正确关闭."""
    print('[stop] 优雅停止后端 (SIGTERM → 等待 → SIGKILL 兜底)')
    r = run("pkill -TERM -f 'server.py'")
    # 等待优雅退出
    for _ in range(10):
        r2 = run("pgrep -f 'server.py' | wc -l")
        if r2.stdout.strip() == '0':
            print('  [OK] 后端已优雅退出')
            return True
        time.sleep(1)
    # SIGKILL 兜底
    run("pkill -9 -f 'server.py'")
    print('  [WARN] 后端未在 10s 内退出, 已 SIGKILL 兜底')
    time.sleep(2)
    return True


def db_preflight(db_path):
    """PASSIVE checkpoint → journal_mode=DELETE → quick_check. 失败返回 False (fail-fast)."""
    print(f'[db-preflight] DB 安全预检: {db_path}')
    ok = True
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute('PRAGMA busy_timeout=10000')
        try:
            busy, log_frames, checkpointed = conn.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
            print(f'  wal_checkpoint(PASSIVE): busy={busy} log={log_frames} ckpt={checkpointed}')
            if busy:
                print('  [WARN] checkpoint 被并发连接阻塞 (确认服务已停止)')
        except Exception as e:
            print(f'  [ERROR] wal_checkpoint(PASSIVE) 失败: {e}')
            ok = False
        try:
            mode = conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0]
            print(f'  journal_mode=DELETE -> {mode}')
            if mode.lower() != 'delete':
                print(f'  [ERROR] journal_mode 未切到 DELETE (实际={mode})')
                ok = False
        except Exception as e:
            print(f'  [ERROR] journal_mode=DELETE 失败: {e}')
            ok = False
        try:
            qc = conn.execute('PRAGMA quick_check').fetchone()[0]
            if qc == 'ok':
                print('  quick_check: OK')
            else:
                print(f'  [FATAL] quick_check 失败: {qc}')
                ok = False
        except Exception as e:
            print(f'  [FATAL] quick_check 异常: {e}')
            ok = False
        conn.close()
    except Exception as e:
        print(f'  [FATAL] DB 打开失败: {e}')
        return False
    return ok


def db_backup(db_path):
    """部署前快照备份 + quick_check 校验."""
    ts = time.strftime('%Y%m%d_%H%M%S')
    dst = f'{db_path}.predeploy_{ts}'
    print(f'[db-backup] 快照备份: {dst}')
    try:
        shutil.copy2(db_path, dst)
        # 校验备份可用
        conn = sqlite3.connect(dst, timeout=10)
        qc = conn.execute('PRAGMA quick_check').fetchone()[0]
        conn.close()
        print(f'  backup quick_check: {qc}')
        return dst if qc == 'ok' else None
    except Exception as e:
        print(f'  [ERROR] 备份失败: {e}')
        return None


def db_verify(db_path):
    """部署后 DB 完整性 + 关键表计数验证."""
    print('[db-verify] 部署后 DB 验证')
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        qc = conn.execute('PRAGMA quick_check').fetchone()[0]
        users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        bos = conn.execute('SELECT COUNT(*) FROM business_objects').fetchone()[0]
        conn.close()
        print(f'  quick_check={qc} users={users} business_objects={bos}')
        return qc == 'ok'
    except Exception as e:
        print(f'  [FATAL] DB 验证失败: {e}')
        return False


def restart_backend():
    """优雅重启后端 13011 (env 与 restart_staging.py 一致)."""
    print('[restart] 启动后端 13011')
    env = dict(os.environ)
    env.update({
        'PORT': '13011',
        'SQLITE_DB_PATH': DB_PATH,
        'ARCH_DB_PATH': DB_PATH,
        'FLASK_DEBUG': 'true',
        'FLASK_SECRET_KEY': 'staging-flask-key-2026-07-14-staging-secret',
        'JWT_SECRET_KEY': 'staging-jwt-secret-2026-07-14-staging-jwt',
        'SERVER_BIND_HOST': '172.20.59.7',
    })
    logf = open('/opt/app/staging/logs/backend_deploy_delta.log', 'a')
    proc = subprocess.Popen(
        [BACKEND_PY, '-u', BACKEND_SRV],
        cwd=os.path.dirname(BACKEND_SRV),
        env=env, stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f'  backend PID={proc.pid}')
    # 等待端口就绪 (最长 30s)
    for _ in range(15):
        r = run(f"ss -tlnp 2>/dev/null | grep -q ':{BACKEND_PORT} ' && echo yes || echo no")
        if r.stdout.strip() == 'yes':
            print(f'  [OK] 后端 {BACKEND_PORT} listening')
            return True
        time.sleep(2)
    print('  [FATAL] 后端未就绪, 检查日志 /opt/app/staging/logs/backend_deploy_delta.log')
    return False


def main():
    if len(sys.argv) < 2:
        print('usage: python3 _deploy_delta_staging.py <zip_path> [--skip-restart]')
        return 1
    ZIP = sys.argv[1]
    SKIP_RESTART = '--skip-restart' in sys.argv
    if not os.path.exists(ZIP):
        print(f'[FATAL] zip not found: {ZIP}')
        return 1
    TMP = '/tmp/delta_extract_' + os.path.basename(ZIP).replace('.zip', '')
    if os.path.exists(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP)

    with zipfile.ZipFile(ZIP) as z:
        z.extractall(TMP)
    changed_root = os.path.join(TMP, 'changed')

    # ── 0. 优雅停止后端 + DB 预检 + 备份 ─────────────────────────
    if os.path.exists(DB_PATH):
        graceful_stop_backend()
        if not db_preflight(DB_PATH):
            print('[FATAL] DB 预检失败, 中止部署 (请先恢复 DB)')
            return 1
        if not db_backup(DB_PATH):
            print('[FATAL] 部署前备份失败, 中止部署')
            return 1

    # ── 1. deploy meta/* -> META_DIR ─────────────────────────────
    meta_src = os.path.join(changed_root, 'meta')
    n_meta = 0
    fail = 0
    if os.path.isdir(meta_src):
        for root, _dirs, files in os.walk(meta_src):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, meta_src)
                dst = os.path.join(META_DIR, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                    n_meta += 1
                except Exception as e:
                    fail += 1
                    print(f'  FAIL {rel}: {e}')
    print(f'[deploy] meta files copied: {n_meta}, failed: {fail}')

    # ── 2. deploy frontend_dist_files/* -> FE_DIR ────────────────
    fe_src = os.path.join(changed_root, 'frontend_dist_files')
    n_fe = 0
    if os.path.isdir(fe_src):
        for root, _dirs, files in os.walk(fe_src):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, fe_src)
                dst = os.path.join(FE_DIR, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                    n_fe += 1
                except Exception as e:
                    print(f'  FAIL {rel}: {e}')
    print(f'[deploy] frontend files copied: {n_fe}')

    # ── 3. DELETED.txt (frontend asset rotation) ─────────────────
    del_file = os.path.join(TMP, 'DELETED.txt')
    n_del = 0
    if os.path.exists(del_file):
        with open(del_file, encoding='utf-8') as fh:
            for line in fh:
                rel = line.strip()
                if not rel or rel.startswith('#'):
                    continue
                if rel.startswith('frontend_dist_files/'):
                    dst = os.path.join(FE_DIR, rel[len('frontend_dist_files/'):])
                    if os.path.isfile(dst):
                        os.remove(dst)
                        n_del += 1
                else:
                    print(f'  SKIP non-frontend delete: {rel}')
    print(f'[deploy] frontend deleted (asset rotation): {n_del}')

    # ── 4. write MANIFEST ────────────────────────────────────────
    man_src = os.path.join(TMP, 'MANIFEST')
    if os.path.exists(man_src):
        shutil.copy2(man_src, os.path.join(META_DIR, 'MANIFEST'))
        print(f'[deploy] MANIFEST written to {META_DIR}/MANIFEST')

    # ── 5. 重启后端 + 部署后验证 ─────────────────────────────────
    if not SKIP_RESTART:
        if not restart_backend():
            return 1
        time.sleep(6)
        if not db_verify(DB_PATH):
            print('[FATAL] 部署后 DB 验证失败')
            return 1

    print(f'[deploy] DONE: meta={n_meta} frontend={n_fe} deleted={n_del}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
