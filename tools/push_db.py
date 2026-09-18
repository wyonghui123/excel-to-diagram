#!/usr/bin/env python3
# push_db.py - Push local SQLite DB to remote (staging / production).
# [2026-09-17] New infra capability: local2remote DB sync.
"""
push_db.py - 本地 SQLite DB 推到远端 (local → staging / production).

解决 3 个核心问题:
1. local SQLite 文件可能很大, base64 后超 stdout 50000 字符
2. 不依赖 staging exec_cmd (只需 upload_file 即可, 兼容 read-only 端口如 observability 9201)
3. 限流 + 重试

策略:
- 本地 iterdump + gzip + 按字节切块 base64 → upload 到远端 (part 文件)
- 远端收到 part 文件后, 上传一个 restore script, exec 触发合并 + gunzip + restore

依赖: tools.yonaa_exec (yupload, yuploaderun)

CLI:
    # 默认推到 staging
    python tools/push_db.py --local meta/architecture.db

    # 推到 production
    python tools/push_db.py --target production --local meta/architecture.db

    # 指定远端路径
    python tools/push_db.py --target staging --local meta/architecture.db --remote /opt/app/staging/meta/architecture.db

    # 不备份远端原 DB
    python tools/push_db.py --local meta/architecture.db --no-backup
"""
import argparse
import base64
import gzip
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.yonaa_exec import yexec, yuploaderun, yupload, KNOWN_PORTS


# ============================================================
# Constants
# ============================================================

CHUNK_BYTES = 30000  # 字节/块 (同 pull_db)

STAGING_REMOTE_HOST = '172.20.59.7'
STAGING_REMOTE_PORT = KNOWN_PORTS['core_staging']  # 19200
STAGING_SECRET = 'staging-v007.49-d'  # 默认 staging secret

PROD_REMOTE_HOST = '172.20.59.7'
PROD_REMOTE_PORT = KNOWN_PORTS['core_prod']  # 9200
PROD_SECRET = 'prod_write'  # alias → v007.52-core-write

# 远端临时目录 (用于 chunk + restore script)
REMOTE_TMP_DIR = '/opt/app/shared/push_db_tmp'
REMOTE_CHUNK_DIR = '/opt/app/shared/push_db_chunks'


# ============================================================
# Target 解析
# ============================================================

class PushError(Exception):
    """Push 失败时抛."""
    pass


def resolve_target(target, port=None, secret=None):
    """解析 target alias → (port, secret, default_remote_db).

    Args:
        target: 'staging' | 'production' | 'local'
        port/secret: 覆盖默认值

    Returns:
        dict: {'port': int, 'secret': str, 'default_remote_db': str}
    """
    t = (target or 'staging').lower()
    if t == 'staging':
        return {
            'port': port or STAGING_REMOTE_PORT,
            'secret': secret or STAGING_SECRET,
            'default_remote_db': '/opt/app/staging/meta/architecture.db',
        }
    if t == 'production':
        return {
            'port': port or PROD_REMOTE_PORT,
            'secret': secret or PROD_SECRET,
            'default_remote_db': '/opt/app/deployments/meta/architecture.db',
        }
    if t == 'local':
        raise PushError("'local' target 不需要 push (已是本地)")
    raise PushError(f'unknown target: {target} (staging/production/local)')


# ============================================================
# 1. 本地: iterdump + gzip + 切块 base64 + upload
# ============================================================

def local_dump_and_chunk(local_db_path, chunk_dir_remote, chunk_bytes=CHUNK_BYTES,
                        port=None, secret=None):
    """本地: iterdump → gzip → 切块 base64 → upload 每个 part 到远端.

    Returns:
        dict: {'sql_size': int, 'gz_size': int, 'num_parts': int, 'total_b64_chars': int}
    """
    # 本地 iterdump
    if not os.path.exists(local_db_path):
        raise PushError(f'local db not found: {local_db_path}')
    sql_path = tempfile.NamedTemporaryFile(suffix='.sql', delete=False, mode='w', encoding='utf-8').name
    try:
        c = sqlite3.connect(local_db_path)
        with open(sql_path, 'w', encoding='utf-8') as f:
            for line in c.iterdump():
                f.write(line + '\n')
        c.close()
        sql_size = os.path.getsize(sql_path)
        print(f'[push_db]   sql dumped: {sql_size:,} bytes', flush=True)

        # gzip
        gz_path = sql_path + '.gz'
        with open(sql_path, 'rb') as f_in:
            data = f_in.read()
        with gzip.open(gz_path, 'wb', compresslevel=6) as f_out:
            f_out.write(data)
        gz_size = os.path.getsize(gz_path)
        print(f'[push_db]   gzipped: {gz_size:,} bytes ({gz_size / max(sql_size, 1) * 100:.1f}%)', flush=True)

        # 切块 base64 + upload
        with open(gz_path, 'rb') as f:
            gz_data = f.read()
        parts = []
        for i in range(0, len(gz_data), chunk_bytes):
            parts.append(gz_data[i:i + chunk_bytes])

        print(f'[push_db]   uploading {len(parts)} parts to {chunk_dir_remote}...', flush=True)
        for i, p in enumerate(parts):
            b = base64.b64encode(p).decode('ascii')
            # 把 base64 字符串写到本地临时文件, 再 upload
            tmp = tempfile.NamedTemporaryFile(suffix='.b64', delete=False, mode='w', encoding='ascii').name
            try:
                with open(tmp, 'w') as f:
                    f.write(b)
                remote_path = f'{chunk_dir_remote}/push.b64.{i:03d}'
                r = yupload(tmp, remote_path, port=port, secret=secret)
                if r.get('error'):
                    raise PushError(f'upload part {i} failed: {r}')
            finally:
                os.unlink(tmp)
            if (i + 1) % 20 == 0:
                print(f'      uploaded {i + 1}/{len(parts)}', flush=True)

        return {
            'sql_size': sql_size,
            'gz_size': gz_size,
            'num_parts': len(parts),
        }
    finally:
        # 清理本地临时文件
        for p in [sql_path, sql_path + '.gz']:
            if os.path.exists(p):
                os.unlink(p)


# ============================================================
# 2. 远端: 合并 + gunzip + restore
# ============================================================

# restore script 模板 — 在远端跑, 合并 parts + gunzip + restore DB
RESTORE_SCRIPT_TEMPLATE = '''import sqlite3, os, base64, gzip, shutil
chunk_dir = "{chunk_dir}"
remote_db = "{remote_db}"
tmp_dir = "{tmp_dir}"
backup = {backup_enable}
os.makedirs(tmp_dir, exist_ok=True)
NL = chr(10)
sql_path = os.path.join(tmp_dir, "restore.sql")
gz_path = sql_path + ".gz"

# 合并所有 parts (按文件名排序)
parts = sorted([f for f in os.listdir(chunk_dir) if f.startswith("push.b64.")])
print("PARTS", len(parts))
full_b64 = ""
for p in parts:
    with open(os.path.join(chunk_dir, p), "r") as f:
        full_b64 += f.read()
print("B64_LEN", len(full_b64))
gz_bytes = base64.b64decode(full_b64)
print("GZ_SIZE", len(gz_bytes))
sql_bytes = gzip.decompress(gz_bytes)
print("SQL_SIZE", len(sql_bytes))

# 备份原 DB (如果存在且 backup=True)
if backup and os.path.exists(remote_db):
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = remote_db + ".pre_push_" + ts
    shutil.copy2(remote_db, bak)
    print("BACKED_UP", bak, os.path.getsize(bak))

# restore 到临时文件再 move
tmp_db = remote_db + ".push_restore_tmp"
if os.path.exists(tmp_db):
    os.remove(tmp_db)
c = sqlite3.connect(tmp_db)
c.executescript(sql_bytes.decode("utf-8"))
c.commit()
c.close()

# integrity check
test = sqlite3.connect(tmp_db)
integrity = test.execute("PRAGMA integrity_check").fetchone()[0]
test.close()
print("INTEGRITY", integrity)
if integrity != "ok":
    os.remove(tmp_db)
    print("RESTORE_FAIL", integrity)
    exit(1)

# 替换
shutil.move(tmp_db, remote_db)
print("RESTORE_OK", remote_db, os.path.getsize(remote_db))
'''


def upload_restore_script(remote_db, backup=True, port=None, secret=None):
    """生成 restore script, 上传到远端. 返回远端路径."""
    script = RESTORE_SCRIPT_TEMPLATE.format(
        chunk_dir=REMOTE_CHUNK_DIR,
        tmp_dir=REMOTE_TMP_DIR,
        remote_db=remote_db,
        backup_enable=backup,
    )
    staging_path = '/tmp/__push_db_restore.py'
    # 本地临时
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(script)
        local_tmp = f.name
    try:
        r = yupload(local_tmp, staging_path, port=port, secret=secret)
    finally:
        os.unlink(local_tmp)
    if r.get('error'):
        raise PushError(f'upload restore script failed: {r}')
    return staging_path


def run_restore_on_remote(script_path, timeout=300, port=None, secret=None):
    """在远端跑 restore script. 解析 stdout 返回 restore 信息."""
    cmd = f'python3 {script_path}'
    r = yexec(cmd, port=port, secret=secret, timeout=timeout)
    if r.get('error'):
        raise PushError(f'restore script exec failed: {r}')
    stdout = r.get('stdout', '').strip()
    # 解析
    if 'RESTORE_FAIL' in stdout:
        raise PushError(f'remote restore failed: {stdout}')
    if 'RESTORE_OK' not in stdout:
        raise PushError(f'restore stdout parse failed: {stdout[:500]}')
    m_parts = re.search(r'PARTS (\d+)', stdout)
    m_gz = re.search(r'GZ_SIZE (\d+)', stdout)
    m_sql = re.search(r'SQL_SIZE (\d+)', stdout)
    m_int = re.search(r'INTEGRITY (\w+)', stdout)
    m_ok = re.search(r'RESTORE_OK (\S+) (\d+)', stdout)
    m_bak = re.search(r'BACKED_UP (\S+) (\d+)', stdout)
    return {
        'num_parts': int(m_parts.group(1)) if m_parts else 0,
        'gz_size': int(m_gz.group(1)) if m_gz else 0,
        'sql_size': int(m_sql.group(1)) if m_sql else 0,
        'integrity': m_int.group(1) if m_int else 'unknown',
        'restored_to': m_ok.group(1) if m_ok else None,
        'restored_size': int(m_ok.group(2)) if m_ok else 0,
        'backup_path': m_bak.group(1) if m_bak else None,
        'backup_size': int(m_bak.group(2)) if m_bak else 0,
        'stdout': stdout,
    }


# ============================================================
# 3. cleanup
# ============================================================

def cleanup_remote(num_parts, port=None, secret=None, keep_script=False):
    """清理远端 part + restore script."""
    for i in range(num_parts):
        part_path = f'{REMOTE_CHUNK_DIR}/push.b64.{i:03d}'
        # rm 不在白名单, 用 python
        cmd = f"python3 -c \"import os; os.remove('{part_path}') if os.path.exists('{part_path}') else None\""
        yexec(cmd, port=port, secret=secret, timeout=10)
    for tmp_file in (f'{REMOTE_TMP_DIR}/restore.sql', f'{REMOTE_TMP_DIR}/restore.sql.gz'):
        cmd = f"python3 -c \"import os; os.remove('{tmp_file}') if os.path.exists('{tmp_file}') else None\""
        yexec(cmd, port=port, secret=secret, timeout=10)
    if not keep_script:
        cmd = "python3 -c \"import os; os.remove('/tmp/__push_db_restore.py') if os.path.exists('/tmp/__push_db_restore.py') else None\""
        yexec(cmd, port=port, secret=secret, timeout=10)


# ============================================================
# 4. remote db info (推送前看目标 DB 状态)
# ============================================================

def remote_db_info(target='staging', remote_db=None, port=None, secret=None):
    """查目标 DB 大小 + 行数预览 (key tables)."""
    cfg = resolve_target(target, port=port, secret=secret)
    remote_db = remote_db or cfg['default_remote_db']
    inner = (
        'import sqlite3, os\n'
        f'db = "{remote_db}"\n'
        'print("DB", db)\n'
        'print("EXISTS", os.path.exists(db))\n'
        'if os.path.exists(db):\n'
        '    print("SIZE", os.path.getsize(db))\n'
        '    c = sqlite3.connect(db)\n'
        '    for t in ["relationships","audit_logs","business_objects","annotations","users","permission_sets","orgs"]:\n'
        '        try:\n'
        '            print(t, c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])\n'
        '        except Exception as e:\n'
        '            print(t, "N/A", str(e)[:50])\n'
    )
    b64 = base64.b64encode(inner.encode('utf-8')).decode('ascii')
    cmd = f"python3 -c \"import base64,sys;exec(base64.b64decode(sys.stdin.read().strip()).decode('utf-8'))\" <<< {b64}"
    r = yexec(cmd, port=cfg['port'], secret=cfg['secret'], timeout=30)
    if r.get('error'):
        raise PushError(f'remote info failed: {r}')
    return r.get('stdout', '').strip()


# ============================================================
# 5. high-level API
# ============================================================

def push_db(local_db, target='staging', remote_db=None, backup=True,
            port=None, secret=None, cleanup=True, dry_run=False):
    """主入口: 推 local_db 到远端 target.

    Args:
        local_db: 本地 DB 路径 (e.g. 'meta/architecture.db')
        target: 'staging' | 'production'
        remote_db: 远端目标路径 (None = 用 target 默认值)
        backup: 是否备份远端原 DB
        port/secret: 覆盖 target 默认值
        cleanup: 是否清理远端临时文件
        dry_run: 只准备, 不实际 restore

    Returns:
        dict: {'target': str, 'port': int, 'remote_db': str,
               'sql_size': int, 'gz_size': int, 'num_parts': int,
               'integrity': str, 'restored_to': str, 'restored_size': int,
               'backup_path': str or None, 'backup_size': int,
               'elapsed_sec': float}
    """
    cfg = resolve_target(target, port=port, secret=secret)
    remote_db = remote_db or cfg['default_remote_db']
    t_start = time.time()

    print(f'[push_db] target={target}, port={cfg["port"]}, secret={cfg["secret"][:10]}...', flush=True)
    print(f'[push_db] local={local_db}, remote={remote_db}, backup={backup}, dry_run={dry_run}', flush=True)

    # Step 1: 本地 dump + gzip + 切块 + upload
    print(f'[push_db] Step 1: local dump + gzip + chunk + upload...', flush=True)
    chunk_info = local_dump_and_chunk(local_db, REMOTE_CHUNK_DIR, chunk_bytes=CHUNK_BYTES,
                                       port=cfg['port'], secret=cfg['secret'])
    print(f'[push_db]   uploaded {chunk_info["num_parts"]} parts (gz={chunk_info["gz_size"]:,} bytes)', flush=True)

    # Step 2: 上传 restore script
    print(f'[push_db] Step 2: upload restore script...', flush=True)
    script_path = upload_restore_script(remote_db, backup=backup,
                                         port=cfg['port'], secret=cfg['secret'])
    print(f'[push_db]   uploaded → {script_path}', flush=True)

    # Step 3: 在远端跑 restore
    if dry_run:
        print(f'[push_db] dry_run=True, 跳过 restore', flush=True)
        return {
            'target': target,
            'port': cfg['port'],
            'remote_db': remote_db,
            'dry_run': True,
            'sql_size': chunk_info['sql_size'],
            'gz_size': chunk_info['gz_size'],
            'num_parts': chunk_info['num_parts'],
            'elapsed_sec': round(time.time() - t_start, 1),
        }

    print(f'[push_db] Step 3: remote restore...', flush=True)
    result = run_restore_on_remote(
        script_path,
        timeout=300,
        port=cfg['port'],
        secret=cfg['secret'],
    )
    print(f'[push_db]   integrity={result["integrity"]}', flush=True)
    print(f'[push_db]   restored {result["restored_to"]} ({result["restored_size"]:,} bytes)', flush=True)
    if result['backup_path']:
        print(f'[push_db]   backed up to {result["backup_path"]} ({result["backup_size"]:,} bytes)', flush=True)

    # Step 4: 清理
    if cleanup:
        print(f'[push_db] Step 4: cleanup...', flush=True)
        cleanup_remote(chunk_info['num_parts'], port=cfg['port'], secret=cfg['secret'])

    elapsed = time.time() - t_start
    print(f'[push_db] DONE in {elapsed:.1f}s', flush=True)
    return {
        'target': target,
        'port': cfg['port'],
        'remote_db': remote_db,
        'sql_size': chunk_info['sql_size'],
        'gz_size': chunk_info['gz_size'],
        'num_parts': chunk_info['num_parts'],
        'integrity': result['integrity'],
        'restored_to': result['restored_to'],
        'restored_size': result['restored_size'],
        'backup_path': result['backup_path'],
        'backup_size': result['backup_size'],
        'elapsed_sec': round(elapsed, 1),
    }


# ============================================================
# CLI
# ============================================================

def main():
    p = argparse.ArgumentParser(description='Push local SQLite DB to remote (staging/production)')
    p.add_argument('--local', help='本地 DB 路径 (--info 时不需要)')
    p.add_argument('--target', default='staging', choices=['staging', 'production'], help='目标环境 (默认 staging)')
    p.add_argument('--remote', help='远端 DB 路径 (默认用 target 默认路径)')
    p.add_argument('--no-backup', action='store_true', help='不备份远端原 DB')
    p.add_argument('--port', type=int, help='远端 port 覆盖')
    p.add_argument('--secret', help='远端 secret 覆盖')
    p.add_argument('--no-cleanup', action='store_true', help='不清理远端临时文件')
    p.add_argument('--dry-run', action='store_true', help='只准备, 不 restore')
    p.add_argument('--info', action='store_true', help='只看目标 DB 信息, 不推')
    args = p.parse_args()

    if args.info:
        print(remote_db_info(target=args.target, remote_db=args.remote,
                            port=args.port, secret=args.secret))
        return 0

    result = push_db(
        local_db=args.local or '',
        target=args.target,
        remote_db=args.remote,
        backup=not args.no_backup,
        port=args.port,
        secret=args.secret,
        cleanup=not args.no_cleanup,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())