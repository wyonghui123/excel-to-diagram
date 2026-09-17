"""
DimensionScopeEngine 测试辅助 (Plan B C3 fix)
=============================================

提供 unit-test 用的 in-memory schema + 数据种子辅助函数.
DDL + DML 集中在此 (位于 factories/ 目录, conftest 自动白名单).
"""
import os
import sqlite3
import tempfile
from typing import Iterator

import sys
from pathlib import Path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def make_dim_scope_engine_ds() -> Iterator[object]:
    """创建临时 SQLite DB + DS wrapper, 含 permission_set_dimension_scopes + menus.

    Yields:
        DS-like wrapper (cursor 自动 commit).
    """
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS permission_set_dimension_scopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            dimension_code TEXT NOT NULL,
            dimension_values TEXT,
            inherit_children INTEGER DEFAULT 1,
            scope_mode VARCHAR(20) DEFAULT 'include'
        );
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_code TEXT UNIQUE NOT NULL,
            menu_name TEXT,
            parent_menu TEXT,
            primary_object_type TEXT,
            object_types TEXT,
            auto_generated INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            show_in_sidebar INTEGER DEFAULT 1,
            required_permissions TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT
        );
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            product_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            version_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            sub_domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT,
            service_module_id INTEGER
        );
    """)
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def commit(self):
            self._conn.commit()

    try:
        yield MockDS(conn)
    finally:
        conn.close()
        os.unlink(db_path)


def seed_basic_scope(ds) -> None:
    """种子数据: permission_set_id=1, dimension=product, value=[1]."""
    import json
    ds.execute(
        "INSERT INTO permission_set_dimension_scopes (permission_set_id, dimension_code, dimension_values, inherit_children) VALUES (?, ?, ?, ?)",
        [1, 'product', json.dumps([1]), 1]
    )
    ds.execute(
        "INSERT INTO products (name, code) VALUES (?, ?)",
        ['Product1', 'P1']
    )


def seed_menu_domain(ds) -> None:
    """添加 menu_domain 行 (供 derive_* 测试)."""
    import json
    ds.execute(
        "INSERT INTO menus (menu_code, menu_name, primary_object_type, object_types, auto_generated, is_active, required_permissions) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ['menu_domain', 'Domain Menu', 'domain', json.dumps(['domain']), 1, 1, json.dumps(['domain:read'])]
    )
