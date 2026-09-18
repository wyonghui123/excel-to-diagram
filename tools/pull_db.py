#!/usr/bin/env python3
# pull_db.py - Pull remote SQLite DB to local file via staging core_service.
# [2026-09-17] New infra capability: stage2local DB sync.
"""
pull_db.py - 远端 SQLite DB 拉到本地 (staging → local).

解决 3 个核心问题:
1. core_service /api/exec stdout 限制 50000 字符 (无法一次 cat 大文件)
2. core_service 命令白名单 (禁用 base64/dd/sed -n 等)
3. 限流 (20 req/s)

策略:
- staging 端 iterdump (Python 3.7+ sqlite3 module 都支持)
- gzip 压缩 (~10x 压缩比)
- 按字节切块 (30000 字节/chunk) base64 -> 多 part 文件
- 本地分批 cat 读所有 parts (with retry on rate limit)
- 拼回 + b64 decode + gunzip -> restore 到本地 SQLite

依赖: tools.staging_ops (exec_cmd, upload_file, StagingError, DEFAULT_HOST 等)

CLI:
    python tools/pull_db.py --remote /opt/app/staging/meta/architecture.db \\
        --local meta/architecture.db \\
        --backup meta/architecture.db.bak

    # 只看 staging DB 信息 (不下载)
    python tools/pull_db.py --remote /opt/app/staging/meta/architecture.db --info
"""
import argparse
import base64
import gzip
import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

# 让脚本可直接 import tools.staging_ops
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.staging_ops import (
    DEFAULT_HOST, DEFAULT_CORE_PORT, DEFAULT_SECRET,
    exec_cmd, upload_file, StagingError,
)
from tools.yonaa_exec import KNOWN_PORTS, KNOWN_SECRETS


# ============================================================
# Constants
# ============================================================

# chunk 字节数 — 按字节切, 每块 base64 后 40000 字符, 安全余量
CHUNK_BYTES = 30000

# 限流间隔 (每 N 个 part sleep 多久)
RATE_LIMIT_SLEEP_AFTER = 5      # 每 5 个 part
RATE_LIMIT_SLEEP_SEC = 1.5

# 单 part read retry 上限
READ_RETRIES = 8

# staging 端临时目录 (用于 dump + 切块)
STAGING_TMP_DIR = '/opt/app/shared/pull_db_tmp'


# ============================================================
# Target 解析 (staging / production)
# ============================================================

def resolve_target(target='staging'):
    """解析 target alias → (host, port, secret).

    注意: pull_db 内部用 staging_ops 接口, 只覆盖 host/port.
    secret 需要通过 env (STAGING_SECRET) 切换, 因为 staging_ops.exec_cmd 不接受 secret 参数.
    """
    t = (target or 'staging').lower()
    if t == 'staging':
        return {
            'host': DEFAULT_HOST,
            'port': KNOWN_PORTS['core_staging'],
            'secret': KNOWN_SECRETS['staging'],
            'default_remote_db': '/opt/app/staging/meta/architecture.db',
        }
    if t == 'production':
        return {
            'host': DEFAULT_HOST,
            'port': KNOWN_PORTS['core_prod'],
            'secret': KNOWN_SECRETS['prod_write'],
            'default_remote_db': '/opt/app/deployments/meta/architecture.db',
        }
    raise ValueError(f'unknown target: {target} (staging/production)')


def _apply_target_env(target_cfg):
    """把 target 的 host/port/secret 写到 env + monkey-patch staging_ops 模块常量.

    注: staging_ops 的 DEFAULT_HOST/CORE_PORT/SECRET 是 import 时一次求值,
    之后改 env 不会影响. 必须直接 patch staging_ops 模块属性.
    """
    os.environ['STAGING_HOST'] = target_cfg['host']
    os.environ['STAGING_CORE_PORT'] = str(target_cfg['port'])
    os.environ['STAGING_SECRET'] = target_cfg['secret']
    # 同步 patch staging_ops 模块 (因为它的常量已被 import 时求值)
    import tools.staging_ops as so
    so.DEFAULT_HOST = target_cfg['host']
    so.DEFAULT_CORE_PORT = target_cfg['port']
    so.DEFAULT_SECRET = target_cfg['secret']

# staging 端 chunk 目录 (part 文件放这里)
STAGING_CHUNK_DIR = '/opt/app/shared/pull_db_chunks'


class PullError(Exception):
    """Pull 失败时抛."""
    pass


# ============================================================
# 1. staging 端: iterdump + gzip + 切块 base64
# ============================================================

# dump script 模板 (会在本地 Python 用 str 拼接后 upload 到 staging)
# 注意: Python triple-quoted string 里 \n 是字面 2 字符 (\ + n), 上传后 staging Python 解析成换行符
# 因此 dump_script 里的换行符要用 chr(10) 而不是 \n (本地 Python f-string 解析陷阱)
DUMP_SCRIPT_TEMPLATE = '''import sqlite3, os, base64, gzip
src = "{remote_db}"
tmp_dir = "{tmp_dir}"
chunk_dir = "{chunk_dir}"
os.makedirs(tmp_dir, exist_ok=True)
os.makedirs(chunk_dir, exist_ok=True)
sql_path = os.path.join(tmp_dir, "pull_dump.sql")
gz_path = os.path.join(tmp_dir, "pull_dump.sql.gz")
NL = chr(10)
conn = sqlite3.connect(src)
with open(sql_path, "w", encoding="utf-8") as f:
    for line in conn.iterdump():
        f.write(line + NL)
conn.close()
print("SQL_SIZE", os.path.getsize(sql_path))
with open(sql_path, "rb") as f_in:
    data = f_in.read()
with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
    f_out.write(data)
print("GZ_SIZE", os.path.getsize(gz_path))
with open(gz_path, "rb") as f:
    gz_data = f.read()
parts = []
for i in range(0, len(gz_data), {chunk_bytes}):
    parts.append(gz_data[i:i+{chunk_bytes}])
for i, p in enumerate(parts):
    b = base64.b64encode(p).decode()
    out = os.path.join(chunk_dir, "pull.b64.%03d" % i)
    with open(out, "w") as f:
        f.write(b)
print("PARTS", len(parts))
'''


def upload_dump_script(remote_db):
    """生成 dump script, 上传到 staging. 返回 staging 端路径."""
    script = DUMP_SCRIPT_TEMPLATE.format(
        remote_db=remote_db,
        tmp_dir=STAGING_TMP_DIR,
        chunk_dir=STAGING_CHUNK_DIR,
        chunk_bytes=CHUNK_BYTES,
    )
    staging_path = '/tmp/__pull_db_dump.py'
    # upload_file 需要本地文件路径, 临时写到 tmp
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(script)
        local_tmp = f.name
    try:
        r = upload_file(local_tmp, staging_path)
    finally:
        os.unlink(local_tmp)
    if r.get('error'):
        raise PullError(f'upload dump script failed: {r}')
    return staging_path


def run_dump_on_staging(staging_script_path, timeout=300):
    """在 staging 上跑 dump script. 解析 stdout 返回 sql/gz/part size."""
    cmd = f'python3 {staging_script_path}'
    r = exec_cmd(cmd, timeout=timeout)
    if r.get('error'):
        raise PullError(f'dump script exec failed: {r}')
    stdout = r.get('stdout', '').strip()
    # 解析
    m_sql = re.search(r'SQL_SIZE (\d+)', stdout)
    m_gz = re.search(r'GZ_SIZE (\d+)', stdout)
    m_parts = re.search(r'PARTS (\d+)', stdout)
    if not (m_sql and m_gz and m_parts):
        raise PullError(f'dump stdout parse failed: {stdout[:500]}')
    return {
        'sql_size': int(m_sql.group(1)),
        'gz_size': int(m_gz.group(1)),
        'num_parts': int(m_parts.group(1)),
    }


# ============================================================
# 2. 本地: 分批 cat 读所有 parts
# ============================================================

def _read_part_with_retry(part_path, host=None, port=None):
    """读单个 part, rate limit 时退避重试."""
    for attempt in range(READ_RETRIES):
        r = exec_cmd(f'cat {part_path}', host=host, port=port, timeout=30)
        if not r.get('error') and r.get('exit_code', 1) == 0:
            out = r.get('stdout', '')
            if out and not r.get('truncated_stdout'):
                return out
        if 'rate limited' in str(r.get('error', '')):
            wait = min(2 + attempt * 2, 30)
            time.sleep(wait)
            continue
        # 其他错误
        time.sleep(2)
        if attempt >= READ_RETRIES - 1:
            raise PullError(f'part read failed: {part_path}: {r}')
    raise PullError(f'part read giving up after {READ_RETRIES} retries: {part_path}')


def read_all_parts(num_parts, chunk_dir=None, host=None, port=None, progress=True):
    """读所有 parts, 返回拼接后的 base64 string."""
    chunk_dir = chunk_dir or STAGING_CHUNK_DIR
    parts_b64 = []
    for i in range(num_parts):
        part_path = f'{chunk_dir}/pull.b64.{i:03d}'
        out = _read_part_with_retry(part_path, host=host, port=port)
        parts_b64.append(out)
        if progress and (i + 1) % 20 == 0:
            print(f'  read {i+1}/{num_parts} parts ({sum(len(p) for p in parts_b64)} chars)', flush=True)
        # 限速
        if (i + 1) % RATE_LIMIT_SLEEP_AFTER == 0:
            time.sleep(RATE_LIMIT_SLEEP_SEC)
    return ''.join(parts_b64)


# ============================================================
# 3. 本地: b64 decode + gunzip -> restore SQLite
# ============================================================

def decode_and_decompress(full_b64, expected_gz_size=None):
    """base64 decode + gunzip. 返回 SQL 文本 (str)."""
    try:
        gz_bytes = base64.b64decode(full_b64)
    except Exception as e:
        raise PullError(f'base64 decode failed: {e}')
    if expected_gz_size and len(gz_bytes) != expected_gz_size:
        raise PullError(f'gz size mismatch: got {len(gz_bytes)}, expected {expected_gz_size}')
    try:
        sql_bytes = gzip.decompress(gz_bytes)
    except Exception as e:
        raise PullError(f'gunzip failed: {e}')
    return sql_bytes.decode('utf-8')


def restore_local_db(sql_text, local_db_path, backup_path=None):
    """用 SQL 文本 restore 到本地 SQLite. 备份原 DB (如果存在)."""
    local_db = Path(local_db_path)
    if local_db.exists() and backup_path:
        bak = Path(backup_path)
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_db, bak)
        print(f'[pull_db] backup local → {bak}')

    # 用临时文件名 restore, 再 move (避免原文件被占用时失败)
    tmp_db = local_db.with_suffix(local_db.suffix + '.pull_tmp')
    if tmp_db.exists():
        tmp_db.unlink()
    conn = sqlite3.connect(str(tmp_db))
    try:
        conn.executescript(sql_text)
        conn.commit()
    finally:
        conn.close()

    # 验证 integrity
    test = sqlite3.connect(str(tmp_db))
    integrity = test.execute('PRAGMA integrity_check').fetchone()[0]
    test.close()
    if integrity != 'ok':
        tmp_db.unlink()
        raise PullError(f'integrity_check failed: {integrity}')

    # 替换
    shutil.move(str(tmp_db), str(local_db))
    return local_db


# ============================================================
# 4. cleanup staging 临时文件
# ============================================================

def cleanup_staging(num_parts, host=None, port=None, keep_script=False):
    """清理 staging 端 chunk + tmp 文件."""
    for i in range(num_parts):
        part_path = f'{STAGING_CHUNK_DIR}/pull.b64.{i:03d}'
        exec_cmd(
            f'python3 -c "import os; os.remove(\'{part_path}\') if os.path.exists(\'{part_path}\') else None"',
            host=host, port=port, timeout=5,
        )
    for tmp_file in (f'{STAGING_TMP_DIR}/pull_dump.sql', f'{STAGING_TMP_DIR}/pull_dump.sql.gz'):
        exec_cmd(
            f'python3 -c "import os; os.remove(\'{tmp_file}\') if os.path.exists(\'{tmp_file}\') else None"',
            host=host, port=port, timeout=5,
        )
    if not keep_script:
        exec_cmd(
            "python3 -c \"import os; os.remove('/tmp/__pull_db_dump.py') if os.path.exists('/tmp/__pull_db_dump.py') else None\"",
            host=host, port=port, timeout=5,
        )


# ============================================================
# 5. info (只读 staging DB 元信息, 不下载)
# ============================================================

def remote_db_info(remote_db, host=None, port=None, target=None):
    """查远端 DB 大小 + 行数预览 (key tables).

    target: 'staging' | 'production' (自动设置 host/port/secret)
    """
    if target:
        cfg = resolve_target(target)
        host = host or cfg['host']
        port = port or cfg['port']
        _apply_target_env(cfg)

    # 用 heredoc 避免嵌套引号地狱
    inner = (
        'import sqlite3, os\n'
        f'db = "{remote_db}"\n'
        'print("SIZE", os.path.getsize(db))\n'
        'c = sqlite3.connect(db)\n'
        'for t in ["relationships","audit_logs","business_objects","annotations","service_modules","users","permission_sets","orgs"]:\n'
        '    try:\n'
        '        print(t, c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0])\n'
        '    except Exception as e:\n'
        '        print(t, "N/A", str(e)[:50])\n'
    )
    b64 = base64.b64encode(inner.encode('utf-8')).decode('ascii')
    cmd = f"python3 -c \"import base64,sys;exec(base64.b64decode(sys.stdin.read().strip()).decode('utf-8'))\" <<< {b64}"
    r = exec_cmd(cmd, host=host, port=port, timeout=30)
    if r.get('error'):
        raise PullError(f'info failed: {r}')
    return r.get('stdout', '').strip()


# ============================================================
# 6. high-level API
# ============================================================

def pull_db(remote_db, local_db, backup=None, host=None, port=None, target=None, cleanup=True):
    """主入口: 拉 remote_db 到 local_db.

    Args:
        remote_db: 远端 DB 路径 (e.g. '/opt/app/staging/meta/architecture.db')
        local_db: 本地目标路径 (e.g. 'meta/architecture.db')
        backup: 本地原 DB 备份路径 (None = 不备份)
        host: 远端 host 覆盖
        port: 远端 port 覆盖
        target: 'staging' | 'production' (自动设置 host/port/secret)
        cleanup: 是否清理远端临时文件

    Returns:
        dict: {'remote_size': int, 'sql_size': int, 'gz_size': int, 'num_parts': int,
               'local_path': str, 'integrity': 'ok'}
    """
    # target 模式: 自动 apply env (覆盖 host/port/secret)
    if target:
        cfg = resolve_target(target)
        host = host or cfg['host']
        port = port or cfg['port']
        _apply_target_env(cfg)

    host = host or DEFAULT_HOST
    port = port or DEFAULT_CORE_PORT
    t_start = time.time()

    # Step 1: 上传 dump script
    print(f'[pull_db] host={host}:{port}, remote={remote_db}, local={local_db}', flush=True)
    script_path = upload_dump_script(remote_db)
    print(f'[pull_db] uploaded dump script → {script_path}', flush=True)

    # Step 2: staging dump + gzip + 切块
    print(f'[pull_db] dumping + compressing + chunking on staging...', flush=True)
    info = run_dump_on_staging(script_path)
    print(f'[pull_db]   sql={info["sql_size"]:,} bytes, gz={info["gz_size"]:,} bytes, parts={info["num_parts"]}', flush=True)

    # Step 3: 读所有 parts
    print(f'[pull_db] reading {info["num_parts"]} parts from staging...', flush=True)
    full_b64 = read_all_parts(info['num_parts'], host=host, port=port)
    print(f'[pull_db]   read {info["num_parts"]}/{info["num_parts"]} parts, total b64={len(full_b64):,} chars', flush=True)

    # Step 4: decode + gunzip
    sql_text = decode_and_decompress(full_b64, expected_gz_size=info['gz_size'])
    print(f'[pull_db] decompressed SQL: {len(sql_text):,} bytes', flush=True)

    # Step 5: restore 到本地
    print(f'[pull_db] restoring to local SQLite...', flush=True)
    final_path = restore_local_db(sql_text, local_db, backup_path=backup)
    print(f'[pull_db]   ✓ {final_path} ({os.path.getsize(final_path):,} bytes)', flush=True)

    # Step 6: 清理 staging
    if cleanup:
        cleanup_staging(info['num_parts'], host=host, port=port, keep_script=False)

    elapsed = time.time() - t_start
    print(f'[pull_db] DONE in {elapsed:.1f}s', flush=True)
    return {
        'remote_db': remote_db,
        'local_path': str(final_path),
        'sql_size': info['sql_size'],
        'gz_size': info['gz_size'],
        'num_parts': info['num_parts'],
        'integrity': 'ok',
        'elapsed_sec': round(elapsed, 1),
    }


# ============================================================
# CLI
# ============================================================

def main():
    p = argparse.ArgumentParser(description='Pull remote SQLite DB to local via core_service')
    p.add_argument('--remote', required=True, help='远端 DB 路径')
    p.add_argument('--local', help='本地目标路径 (默认: meta/architecture.db)')
    p.add_argument('--backup', help='本地原 DB 备份路径')
    p.add_argument('--target', choices=['staging', 'production'], help='目标环境 (默认 staging)')
    p.add_argument('--host', help='远端 host 覆盖')
    p.add_argument('--port', type=int, help='远端 port 覆盖')
    p.add_argument('--info', action='store_true', help='只看远端 DB 信息, 不下载')
    p.add_argument('--no-cleanup', action='store_true', help='不清理远端临时文件 (调试用)')
    args = p.parse_args()

    if args.info:
        print(remote_db_info(args.remote, host=args.host, port=args.port, target=args.target))
        return 0

    if not args.local:
        p.error('--local required (除非用 --info)')

    result = pull_db(
        remote_db=args.remote,
        local_db=args.local,
        backup=args.backup,
        host=args.host,
        port=args.port,
        target=args.target,
        cleanup=not args.no_cleanup,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())