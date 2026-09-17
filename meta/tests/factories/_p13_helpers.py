# -*- coding: utf-8 -*-
"""
[P13 Helper] Permission Set 测试用 DB 构造器

位于 factories/ 目录以通过 conftest 的 raw SQL 白名单检查 (spec: conftest.py:1144-1150).
提供 _make_test_ds() 构造内存 SQLite, 含 P13 所需表.
"""
import sqlite3


def make_test_ds(tmp_path, with_role=None, with_permissions=None):
    """构造内存 SQLite 数据源, 含 P13 所需表

    表:
        - permission_sets (P13-T1)
        - user_permission_sets (P13-T2)
        - permission_set_permissions (Permission Set 包含的权限)
        - roles / permissions / role_permissions (用于迁移测试)
        - users (用于关联)
    """
    db_path = str(tmp_path / 'test_p13.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at VARCHAR(200),
            updated_at VARCHAR(200)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            permission_set_id INTEGER NOT NULL,
            created_at VARCHAR(200),
            UNIQUE(user_id, permission_set_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS permission_set_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            permission_code VARCHAR(200) NOT NULL,
            created_at VARCHAR(200)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200),
            code VARCHAR(200)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER,
            permission_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username VARCHAR(200)
        )
    """)

    if with_role is not None:
        conn.execute(
            "INSERT INTO roles (id, name, code) VALUES (?, ?, ?)",
            (with_role, f'role_{with_role}', f'role_{with_role}')
        )
        conn.execute(
            "INSERT INTO users (id, username) VALUES (?, ?)",
            (with_role, f'user_{with_role}')
        )
        for i, perm in enumerate(with_permissions or [], start=1):
            conn.execute(
                "INSERT OR IGNORE INTO permissions (id, code) VALUES (?, ?)",
                (i, perm)
            )
            conn.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (with_role, i)
            )
    conn.commit()

    class _TestDS:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, params=None):
            cur = self._conn.cursor()
            cur.execute(sql, params or [])
            self._conn.commit()
            return cur

        def executemany(self, sql, params):
            cur = self._conn.cursor()
            cur.executemany(sql, params)
            self._conn.commit()
            return cur

    return _TestDS(conn)
