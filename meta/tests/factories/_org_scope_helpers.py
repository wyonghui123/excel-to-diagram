# -*- coding: utf-8 -*-
"""OrgScopeService 单元测试辅助（规格 24）

包含 raw SQL，位于 factories/ 目录（conftest 白名单豁免）。
"""
import os
import sqlite3
import tempfile
from typing import Iterator, Tuple


class _DS:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(sql, params or [])
        return cur


def make_test_ds() -> Iterator[Tuple[object, str]]:
    """创建临时 SQLite 库 + DS 包装，并写入组织树与权限集范围。

    组织树:
        1 集团
        ├── 2 华东
        │   └── 3 上海
        └── 4 华北
            └── 5 北京
        6 外部（孤立）

    用户 100 属于组织 2，权限集 10 的 org 范围为 include [2]（含子树）+ exclude [3]。
    """
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orgs (
            id INTEGER PRIMARY KEY, parent_id INTEGER, name TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT, primary_org_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS org_members (user_id INTEGER, org_id INTEGER);
        CREATE TABLE IF NOT EXISTS org_permission_sets (
            org_id INTEGER, permission_set_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS user_permission_sets (
            user_id INTEGER, permission_set_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS permission_set_dimension_scopes (
            permission_set_id INTEGER, dimension_code TEXT,
            dimension_values TEXT, scope_mode TEXT DEFAULT 'include',
            inherit_children INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS control_parameter_defs (
            id INTEGER PRIMARY KEY, code TEXT, default_value TEXT
        );
        CREATE TABLE IF NOT EXISTS org_functions (
            id INTEGER PRIMARY KEY, org_id INTEGER, function_type TEXT
        );
        CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY, org_id INTEGER);

        INSERT INTO orgs (id, parent_id, name) VALUES
            (1, NULL, '集团'), (2, 1, '华东'), (3, 2, '上海'),
            (4, 1, '华北'), (5, 4, '北京'), (6, NULL, '外部');
        INSERT INTO org_members (user_id, org_id) VALUES (100, 2);
        INSERT INTO org_permission_sets (org_id, permission_set_id) VALUES (2, 10);
        INSERT INTO permission_set_dimension_scopes
            (permission_set_id, dimension_code, dimension_values, scope_mode, inherit_children)
            VALUES (10, 'org', '[2]', 'include', 1),
                   (10, 'org', '[3]', 'exclude', 0);
        INSERT INTO org_functions (org_id, function_type) VALUES
            (2, 'inventory'), (2, 'procurement'), (4, 'sales');
    """)
    conn.commit()

    ds = _DS(conn)
    try:
        yield ds, tmp.name
    finally:
        conn.close()
        os.unlink(tmp.name)


def insert_user(ds, user_id: int = 200, primary_org_id=None) -> int:
    ds.execute(
        'INSERT INTO users (id, username, primary_org_id) VALUES (?, ?, ?)',
        [user_id, 'user_%s' % user_id, primary_org_id],
    )
    return user_id


def set_control_parameter(ds, value: str) -> None:
    ds.execute(
        "INSERT INTO control_parameter_defs (code, default_value) VALUES ('org_scope_enforce', ?)",
        [value],
    )


def insert_location(ds, org_id: int, location_id: int = 9) -> int:
    ds.execute('INSERT INTO locations (id, org_id) VALUES (?, ?)', [location_id, org_id])
    return location_id
