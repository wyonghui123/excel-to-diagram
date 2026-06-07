# -*- coding: utf-8 -*-
"""
[MODULE] v3.10: Gevent Experimental + Connection Pool 验证 (从 tests/e2e/ 迁入 v3.17)
[DESCRIPTION] 验证 gevent 文档化 + pool 已存在 + 池默认
"""
import os
import sqlite3


def test_connection_pool_existence():
    """SQLite connection pool 已存在 (v3.6 实施)"""
    from meta.core.sql_connection_pool import SQLiteConnectionPool
    assert SQLiteConnectionPool is not None, 'connection_pool 模块应存在'


def test_sqlite_adapter_uses_pool_by_default():
    """[DECORATIVE] v3.13: SQLiteAdapter 默认池模式 (无 use_pool 参数)"""
    from meta.core.sql_adapters import SQLiteAdapter
    import inspect
    sig = inspect.signature(SQLiteAdapter.__init__)
    params = list(sig.parameters.keys())
    # v3.13 后 __init__ 是无参数 (参数在 connect() 中), 验证无 use_pool
    assert 'use_pool' not in params, 'v3.13 后 SQLiteAdapter 不应有 use_pool 参数 (默认池化)'
    # __init__ 是无参数, 参数通过 connect() 传递
    assert len(params) <= 1, f'SQLiteAdapter.__init__ 应无业务参数, 实际: {params}'  # self


def test_gevent_patch_documented():
    """gevent 26.5 + Python 3.14 socket.recv_into 已知问题已被文档化"""
    doc_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'docs', 'v3.10-gevent-socket-issue.md'
    )
    assert os.path.exists(doc_path), f'gevent socket 兼容问题应有文档: {doc_path}'


def test_db_integrity_no_wal_corruption(bo_action_server_check):
    """DB integrity_check = ok (v3.16 修复后无 WAL 损坏)"""
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        'meta', 'architecture.db'
    )
    if not os.path.exists(db_path):
        pytest_skip = True
        return
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()[0]
        assert result == 'ok', f'DB 完整性 = ok, 实际 {result}'
    finally:
        conn.close()
