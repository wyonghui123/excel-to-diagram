#!/usr/bin/env python3
# test_push_db.py - 验证 push_db.py round-trip 正确性.
"""
测试场景:
1. 准备: 本地创建测试 SQLite (3 表: small/medium/big, 总 ~2MB)
2. push 到 staging 临时路径
3. pull 回本地
4. 验证: 行数一致 + integrity ok

需要 staging core_service (19200) 可达.

用法:
    python tools/test_push_db.py [--keep]
"""
import argparse
import base64
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.yonaa_exec import yexec, KNOWN_PORTS
from tools.push_db import push_db, PushError


def _heredoc(inner):
    """把 Python 脚本 base64 编码, 用 heredoc 传到 staging."""
    b64 = base64.b64encode(inner.encode('utf-8')).decode('ascii')
    return f"python3 -c \"import base64,sys;exec(base64.b64decode(sys.stdin.read().strip()).decode('utf-8'))\" <<< {b64}"


def _create_local_test_db(path, rows_per_table={'small': 100, 'medium': 10000, 'big': 1000}):
    """本地创建测试 DB (small/medium/big)."""
    import sqlite3
    if os.path.exists(path):
        os.remove(path)
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE small (id INTEGER PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE medium (id INTEGER PRIMARY KEY, data TEXT)')
    c.execute('CREATE TABLE big (id INTEGER PRIMARY KEY, payload BLOB)')
    for i in range(rows_per_table['small']):
        c.execute('INSERT INTO small VALUES (?, ?)', (i, 'name_' + str(i)))
    for i in range(rows_per_table['medium']):
        c.execute('INSERT INTO medium VALUES (?, ?)', (i, 'x' * 100))
    for i in range(rows_per_table['big']):
        c.execute('INSERT INTO big VALUES (?, ?)', (i, 'y' * 1000))
    c.commit()
    c.close()
    sz = os.path.getsize(path)
    print(f'[test]   created local test db: {path} ({sz:,} bytes)')
    return sz


def _verify_local_db(local_db_path, expected_counts):
    """验证本地 DB: integrity + 行数匹配预期."""
    import sqlite3
    if not os.path.exists(local_db_path):
        raise PushError(f'local db not found: {local_db_path}')
    conn = sqlite3.connect(local_db_path)
    try:
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise PushError(f'integrity_check failed: {integrity}')
        for table, expected in expected_counts.items():
            actual = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if actual != expected:
                raise PushError(f'{table} count mismatch: got {actual}, expected {expected}')
            print(f'[test]   [OK] {table}: {actual}')
    finally:
        conn.close()


def _cleanup_remote(remote_db, port):
    """清理远端测试 DB."""
    cmd = _heredoc(
        f'import os; os.remove("{remote_db}") if os.path.exists("{remote_db}") else None; print("OK")'
    )
    yexec(cmd, port=port, timeout=10)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--keep', action='store_true', help='保留测试文件 (用于手动检查)')
    p.add_argument('--port', type=int, default=KNOWN_PORTS['core_staging'], help='staging port')
    args = p.parse_args()

    port = args.port

    # 测试用路径
    test_db_remote = '/tmp/test_push_db_target.db'
    test_db_local_src = os.path.join(tempfile.gettempdir(), 'test_push_db_source.db')
    test_db_local_pulled = os.path.join(tempfile.gettempdir(), 'test_push_db_pulled.db')

    print(f'[test] port={port}')
    print(f'[test] remote test db: {test_db_remote}')
    print(f'[test] local source:   {test_db_local_src}')
    print(f'[test] local pulled:   {test_db_local_pulled}')

    # 清理已有文件
    for p_ in (test_db_local_src, test_db_local_pulled):
        if os.path.exists(p_):
            os.remove(p_)

    rows_per_table = {'small': 100, 'medium': 10000, 'big': 1000}
    push_result = None
    try:
        # 0. 清理远端残留
        print('\n[test] Step 0: cleanup remote residue')
        _cleanup_remote(test_db_remote, port)

        # 1. 本地创建测试 DB
        print('\n[test] Step 1: create local test db')
        local_size = _create_local_test_db(test_db_local_src, rows_per_table)

        # 2. push 到 staging 临时路径
        print('\n[test] Step 2: push_db to staging')
        push_result = push_db(
            local_db=test_db_local_src,
            target='staging',
            remote_db=test_db_remote,
            port=port,
            backup=False,  # 临时文件, 无需备份
            cleanup=True,
        )
        print(f'[test]   push result: {push_result}')
        assert push_result['integrity'] == 'ok', f'integrity: {push_result["integrity"]}'
        assert push_result['restored_to'] == test_db_remote

        # 3. pull 回本地验证
        print('\n[test] Step 3: pull_db back from staging')
        # 用 tools.pull_db 的 pull_db 函数
        from tools.pull_db import pull_db
        pull_result = pull_db(
            remote_db=test_db_remote,
            local_db=test_db_local_pulled,
            backup=None,
            port=port,
            cleanup=True,
        )
        print(f'[test]   pull result: {pull_result}')
        assert pull_result['integrity'] == 'ok', f'integrity: {pull_result["integrity"]}'

        # 4. 验证内容
        print('\n[test] Step 4: verify pulled db')
        _verify_local_db(test_db_local_pulled, rows_per_table)

        print('\n[test] [OK] ALL CHECKS PASSED (push round-trip verified)')
        return 0
    except PushError as e:
        print(f'\n[test] [FAIL] PUSH ERROR: {e}')
        return 1
    except Exception as e:
        print(f'\n[test] [FAIL] UNEXPECTED ERROR: {e}')
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 清理 (除非 --keep)
        if not args.keep:
            try:
                _cleanup_remote(test_db_remote, port)
                print(f'[test] cleaned up remote: {test_db_remote}')
            except Exception as e:
                print(f'[test] cleanup remote failed (ignore): {e}')
            for p_ in (test_db_local_src, test_db_local_pulled):
                if os.path.exists(p_):
                    os.remove(p_)
                    print(f'[test] cleaned up: {p_}')
        else:
            print(f'[test] --keep: 保留文件')


if __name__ == '__main__':
    sys.exit(main())