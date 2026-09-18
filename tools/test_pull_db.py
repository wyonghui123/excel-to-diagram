#!/usr/bin/env python3
# test_pull_db.py - 验证 pull_db.py round-trip 正确性.
"""
测试场景:
1. 准备: 在 staging 上创建一个测试 SQLite (3 表: small/medium/big)
2. pull 到本地
3. 验证: 行数一致 + integrity ok

不需要 staging 后端服务, 只需要 core_service (19200) 可达.

用法:
    python tools/test_pull_db.py [--keep]   # --keep 保留测试文件
"""
import argparse
import base64
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.staging_ops import DEFAULT_HOST, DEFAULT_CORE_PORT, exec_cmd, upload_file
from tools.pull_db import pull_db, remote_db_info, PullError


# ============================================================
# Step 1: 在 staging 上准备测试 DB
# ============================================================

def _heredoc(inner):
    """把 Python 脚本 base64 编码, 用 heredoc 传到 staging (避免嵌套引号)."""
    b64 = base64.b64encode(inner.encode('utf-8')).decode('ascii')
    return f"python3 -c \"import base64,sys;exec(base64.b64decode(sys.stdin.read().strip()).decode('utf-8'))\" <<< {b64}"


def _create_test_db_on_staging(remote_test_db, host=None, port=None):
    """在 staging 上创建一个 SQLite 含 small/medium/big 3 表."""
    inner = (
        'import sqlite3, os\n'
        f'db = "{remote_test_db}"\n'
        'os.makedirs(os.path.dirname(db), exist_ok=True)\n'
        'if os.path.exists(db): os.remove(db)\n'
        'c = sqlite3.connect(db)\n'
        'c.execute("CREATE TABLE small (id INTEGER PRIMARY KEY, name TEXT)")\n'
        'c.execute("CREATE TABLE medium (id INTEGER PRIMARY KEY, data TEXT)")\n'
        'c.execute("CREATE TABLE big (id INTEGER PRIMARY KEY, payload BLOB)")\n'
        # small: 100 行
        'for i in range(100):\n'
        '    c.execute("INSERT INTO small VALUES (?, ?)", (i, "name_"+str(i)))\n'
        # medium: 10000 行
        'for i in range(10000):\n'
        '    c.execute("INSERT INTO medium VALUES (?, ?)", (i, "x" * 100))\n'
        # big: 1000 行, 每行 1000 字节 BLOB (总计 1MB)
        'for i in range(1000):\n'
        '    c.execute("INSERT INTO big VALUES (?, ?)", (i, "y" * 1000))\n'
        'c.commit()\n'
        'c.close()\n'
        'print("OK", os.path.getsize(db))\n'
    )
    r = exec_cmd(_heredoc(inner), host=host, port=port, timeout=60)
    if r.get('error') or 'OK' not in r.get('stdout', ''):
        raise PullError(f'create test db failed: {r}')
    print(f'[test] created test db on staging: {remote_test_db} ({r["stdout"].strip()})')


def _cleanup_test_db_on_staging(remote_test_db, host=None, port=None):
    """清理 staging 测试 DB."""
    inner = f'import os; os.remove("{remote_test_db}") if os.path.exists("{remote_test_db}") else None; print("OK")'
    r = exec_cmd(_heredoc(inner), host=host, port=port, timeout=10)
    return r


# ============================================================
# Step 2: pull 后验证
# ============================================================

def _verify_local_db(local_db_path, expected_counts):
    """验证本地 DB: integrity + 行数匹配预期."""
    if not os.path.exists(local_db_path):
        raise PullError(f'local db not found: {local_db_path}')
    conn = sqlite3.connect(local_db_path)
    try:
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise PullError(f'integrity_check failed: {integrity}')
        for table, expected in expected_counts.items():
            actual = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if actual != expected:
                raise PullError(f'{table} count mismatch: got {actual}, expected {expected}')
            print(f'[test]   [OK] {table}: {actual}')
    finally:
        conn.close()


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--keep', action='store_true', help='保留测试文件 (用于手动检查)')
    p.add_argument('--host', help='staging host')
    p.add_argument('--port', type=int, help='staging port')
    args = p.parse_args()

    host = args.host or DEFAULT_HOST
    port = args.port or DEFAULT_CORE_PORT

    # 准备测试 DB
    test_db_remote = '/tmp/test_pull_db_target.db'
    test_db_local = os.path.join(tempfile.gettempdir(), 'test_pull_db_local.db')

    print(f'[test] host={host}:{port}')
    print(f'[test] remote test db: {test_db_remote}')
    print(f'[test] local test db:  {test_db_local}')

    # 删除已有的本地测试文件
    if os.path.exists(test_db_local):
        os.remove(test_db_local)

    try:
        # 1. 在 staging 上创建测试 DB
        print('\n[test] Step 1: create test db on staging')
        _create_test_db_on_staging(test_db_remote, host=host, port=port)

        # 2. info 模式
        print('\n[test] Step 2: remote_db_info')
        info = remote_db_info(test_db_remote, host=host, port=port)
        print(f'[test]   {info}')

        # 3. pull
        print('\n[test] Step 3: pull_db')
        result = pull_db(
            remote_db=test_db_remote,
            local_db=test_db_local,
            backup=None,
            host=host,
            port=port,
            cleanup=True,
        )
        print(f'[test]   result: {result}')

        # 4. 验证
        print('\n[test] Step 4: verify local db')
        _verify_local_db(test_db_local, {'small': 100, 'medium': 10000, 'big': 1000})

        print('\n[test] [OK] ALL CHECKS PASSED')
        return 0
    except PullError as e:
        print(f'\n[test] [FAIL] PULL ERROR: {e}')
        return 1
    except Exception as e:
        print(f'\n[test] [FAIL] UNEXPECTED ERROR: {e}')
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 清理 staging 测试 DB
        _cleanup_test_db_on_staging(test_db_remote, host=host, port=port)
        if not args.keep and os.path.exists(test_db_local):
            os.remove(test_db_local)
            print(f'[test] cleaned up local test db')


if __name__ == '__main__':
    sys.exit(main())