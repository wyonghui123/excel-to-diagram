# -*- coding: utf-8 -*-
"""v175 统一资源模型迁移测试（建表 / 枚举 / 权限 / 菜单 / 列改名 / 幂等 / 回滚）

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      §FR-001 ~ FR-004 / §FR-007 / §FR-011 / §TR-001 / §9.3

口径:
  用最小基础设施表（menus / menu_permissions / permissions / permission_sets /
  permission_set_permissions / enum_types / enum_values /
  work_order_operations 旧列）在临时库重放 migrate ——
  验证建表 + 枚举种子 + 权限授予 + 菜单挂主数据 + 工序列改名/加列，
  复跑只 SKIP，回滚删表/菜单并保留 permissions 与枚举。
  不写真实开发库；本文件不含裸 SQL DML（播种经 factories）。
"""
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.migrations.v175__resource_domain_foundation import (  # noqa: E402
    CAPABILITY_TABLE,
    ENUM_SEEDS,
    GROUP_TABLE,
    INDEXES,
    MEMBER_TABLE,
    MENUS,
    OPERATIONS_TABLE,
    PARENT_MENU,
    PERMISSIONS,
    RATE_TABLE,
    RESOURCE_TABLE,
    SKILL_TABLE,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._pricing_p2_helpers import seed_row  # noqa: E402

TABLES = (SKILL_TABLE, RESOURCE_TABLE, GROUP_TABLE, MEMBER_TABLE,
          CAPABILITY_TABLE, RATE_TABLE)

INFRA_DDL = (
    """
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code VARCHAR(200) UNIQUE NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200),
    page_type VARCHAR(200) NOT NULL DEFAULT 'object_list',
    object_types TEXT,
    primary_object_type VARCHAR(200),
    bo_bindings TEXT,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    data_permission_hint TEXT,
    page_config TEXT,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    color VARCHAR(200),
    description VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    show_in_sidebar INTEGER DEFAULT 1,
    auto_generated INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE menu_permissions (
    menu_code VARCHAR(200) UNIQUE NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200) NOT NULL,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    data_permission_hint TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
""",
    """
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    resource_type VARCHAR(200),
    action VARCHAR(200)
)
""",
    """
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME
)
""",
    """
CREATE TABLE enum_types (
    id VARCHAR(200) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL,
    mutability VARCHAR(200) NOT NULL,
    dimension_schema TEXT,
    description TEXT,
    created_at DATETIME
)
""",
    """
CREATE TABLE enum_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enum_type_id VARCHAR(200) NOT NULL,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_en VARCHAR(200),
    dimensions TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    parent_code VARCHAR(200),
    metadata TEXT,
    created_at DATETIME
)
""",
    """
CREATE TABLE work_order_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    work_center_id INTEGER,
    operation_name VARCHAR(200) NOT NULL,
    setup_minutes REAL,
    run_minutes REAL,
    required_skill VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'pending',
    created_at DATETIME,
    updated_at DATETIME
)
""",
)


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / 'resource_domain.db'
    conn = sqlite3.connect(str(db))
    try:
        for ddl in INFRA_DDL:
            conn.execute(ddl)
        seed_row(conn, 'menus', menu_code=PARENT_MENU, menu_name='主数据',
                 menu_path='', page_type='multi_object_hub', is_active=1,
                 show_in_sidebar=1)
        seed_row(conn, 'permission_sets', code='admin', name='管理员', is_active=1)
        seed_row(conn, 'permission_sets', code='default', name='默认权限集',
                 is_active=1)
        conn.commit()
    finally:
        conn.close()
    return db


def _scalar(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _columns(path: Path, table: str) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[1] for r in conn.execute(
            'PRAGMA table_info({0})'.format(table))}
    finally:
        conn.close()


def _index_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def test_fresh_creates_tables_indexes_enums_permissions_menus(tmp_path):
    db = _make_db(tmp_path)
    assert _columns(db, OPERATIONS_TABLE) >= {'work_center_id', 'required_skill'}
    assert migrate(db) is True

    conn = sqlite3.connect(str(db))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    for table in TABLES:
        assert table in names, '缺表 {0}'.format(table)

    index_names = _index_names(db)
    for name, _table, _sql in INDEXES:
        assert name in index_names, '缺索引 {0}'.format(name)

    assert _scalar(db, 'SELECT COUNT(*) FROM enum_types')[0] == len(ENUM_SEEDS)
    expected_values = sum(len(seed[3]) for seed in ENUM_SEEDS)
    assert _scalar(db, 'SELECT COUNT(*) FROM enum_values')[0] == expected_values

    assert _scalar(db, 'SELECT COUNT(*) FROM permissions')[0] == len(PERMISSIONS)
    for code, _name, _rtype, _action in PERMISSIONS:
        assert _scalar(db, 'SELECT 1 FROM permissions WHERE code=?', (code,))

    for set_code in ('admin', 'default'):
        set_row = _scalar(
            db, 'SELECT id FROM permission_sets WHERE code=?', (set_code,))
        assert set_row, '缺权限集 {0}'.format(set_code)
        assert _scalar(
            db, 'SELECT COUNT(*) FROM permission_set_permissions '
                'WHERE permission_set_id=?', (set_row[0],)
        )[0] == len(PERMISSIONS)

    menus = _scalar(db, 'SELECT COUNT(*) FROM menus WHERE parent_menu=?',
                    (PARENT_MENU,))[0]
    assert menus == len(MENUS)
    row = _scalar(db, 'SELECT menu_path, show_in_sidebar, is_active '
                      'FROM menus WHERE menu_code=?', ('resource-list',))
    assert row == ('/resources', 0, 1)
    assert _scalar(db, 'SELECT COUNT(*) FROM menu_permissions')[0] == len(MENUS)
    assert verify(db) is True


def test_operations_columns_renamed_and_added(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True

    cols = _columns(db, OPERATIONS_TABLE)
    assert 'work_center_id' not in cols
    assert 'resource_group_id' in cols
    assert 'required_skill_id' in cols
    assert 'teardown_minutes' in cols
    # 旧文本列保留只读
    assert 'required_skill' in cols

    assert 'idx_work_order_operation_resource_group' in _index_names(db)
    assert 'idx_work_order_operation_required_skill' in _index_names(db)


def test_rerun_is_idempotent(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True

    before = (
        _scalar(db, 'SELECT COUNT(*) FROM menus')[0],
        _scalar(db, 'SELECT COUNT(*) FROM menu_permissions')[0],
        _scalar(db, 'SELECT COUNT(*) FROM permissions')[0],
        _scalar(db, 'SELECT COUNT(*) FROM permission_set_permissions')[0],
        _scalar(db, 'SELECT COUNT(*) FROM enum_types')[0],
        _scalar(db, 'SELECT COUNT(*) FROM enum_values')[0],
        len(_index_names(db)),
        tuple(sorted(_columns(db, OPERATIONS_TABLE))),
    )
    assert migrate(db) is True
    after = (
        _scalar(db, 'SELECT COUNT(*) FROM menus')[0],
        _scalar(db, 'SELECT COUNT(*) FROM menu_permissions')[0],
        _scalar(db, 'SELECT COUNT(*) FROM permissions')[0],
        _scalar(db, 'SELECT COUNT(*) FROM permission_set_permissions')[0],
        _scalar(db, 'SELECT COUNT(*) FROM enum_types')[0],
        _scalar(db, 'SELECT COUNT(*) FROM enum_values')[0],
        len(_index_names(db)),
        tuple(sorted(_columns(db, OPERATIONS_TABLE))),
    )
    assert after == before
    assert verify(db) is True


def test_rollback_drops_tables_and_menus_keeps_permissions(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True

    assert rollback(db) is True

    conn = sqlite3.connect(str(db))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    for table in TABLES:
        assert table not in names
    assert _scalar(db, 'SELECT 1 FROM menus WHERE menu_code=?',
                   ('resource-list',)) is None
    assert _scalar(db, 'SELECT COUNT(*) FROM menu_permissions')[0] == 0
    # 权限码保留（可能已被角色授予）
    assert _scalar(db, 'SELECT COUNT(*) FROM permissions')[0] == len(PERMISSIONS)
    # 列名改回
    cols = _columns(db, OPERATIONS_TABLE)
    assert 'work_center_id' in cols
    assert 'resource_group_id' not in cols
    assert verify(db) is False
