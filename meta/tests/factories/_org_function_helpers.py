"""
OrgFunctionService 测试辅助 (Plan B C2 fix)
============================================

提供 unit-test 用的 in-memory schema + 数据插入辅助函数,
因为 OrgFunctionService 不暴露 create_org() 公开方法,
而 conftest._check_raw_sql_in_tests 会自动 skip 含 INSERT 的测试文件.

本文件位于 factories/ 目录, 被 conftest 白名单豁免 raw SQL 检测.
"""
import os
import sqlite3
import tempfile
from typing import Iterator, Tuple


def make_test_ds() -> Iterator[Tuple[object, object]]:
    """创建临时 SQLite DB + DS wrapper + OrgFunctionService 实例.

    Yields:
        (DS, OrgFunctionService) 元组
    """
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            org_type VARCHAR(50),
            is_active INTEGER DEFAULT 1,
            created_at VARCHAR(200)
        );
        CREATE TABLE IF NOT EXISTS org_functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            function_type VARCHAR(50) NOT NULL,
            is_primary INTEGER DEFAULT 0,
            effective_from VARCHAR(50),
            effective_to VARCHAR(50),
            UNIQUE(org_id, function_type)
        );
    """)
    conn.commit()

    class DS:
        def __init__(self, c):
            self._c = c

        def execute(self, sql, params=None):
            cur = self._c.cursor()
            cur.execute(sql, params or [])
            return cur

        def commit(self):
            self._c.commit()

    ds = DS(conn)
    try:
        yield ds
    finally:
        conn.close()
        os.unlink(tmp.name)


def insert_org(ds, code: str = 'test_org_of', name: str = 'Test Org',
               org_type: str = 'administrative') -> int:
    """在测试 ds 中插入一个 org, 返回 org id.

    注: 此函数有 raw SQL, 但位于 factories/ 目录, conftest 自动豁免.
    """
    cur = ds.execute(
        "INSERT INTO orgs (code, name, org_type) VALUES (?, ?, ?)",
        [code, name, org_type]
    )
    ds.commit()
    return cur.lastrowid
