# -*- coding: utf-8 -*-
"""v176 统一资源模型 P2b 迁移测试（建表 / 枚举 / 权限 / 菜单 / 幂等 / 回滚）

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      §FR-014 / §9.2 目标架构 / §9.3 数据模型表 / §9.5 实施顺序

口径:
  用最小基础设施表（menus / menu_permissions / permissions / permission_sets /
  permission_set_permissions / enum_types / enum_values）在临时库重放 migrate ——
  验证 8 表 + 索引 + 8 组枚举 + 32 权限 + 8 菜单挂主数据，
  复跑只 SKIP；回滚删表 / 菜单 / 权限。
  不写真实开发库；本文件不含裸 SQL DML（播种经 factories）。
"""
import os
import sqlite3
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.migrations.v176__resource_domain_p2b import (  # noqa: E402
    ASSIGNMENT_TABLE,
    CALENDAR_SHIFT_TABLE,
    CAPACITY_TABLE,
    DEFINITION_OP_TABLE,
    DEFINITION_TABLE,
    ENUM_SEEDS,
    INDEXES,
    MENUS,
    PARENT_MENU,
    PERMISSIONS,
    REQUIREMENT_TABLE,
    SHIFT_TABLE,
    TERRITORY_ASSIGNMENT_TABLE,
    UNIQUE_KEYS,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._pricing_p2_helpers import seed_row  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

TABLES = (SHIFT_TABLE, CALENDAR_SHIFT_TABLE, DEFINITION_TABLE, DEFINITION_OP_TABLE,
          REQUIREMENT_TABLE, CAPACITY_TABLE, ASSIGNMENT_TABLE,
          TERRITORY_ASSIGNMENT_TABLE)

# bo_id -> 该对象 yaml 中所有枚举字段的 (field_id, enum_type_id)
ENUM_FIELDS_BY_BO = {
    'shift': [('shift_type', 'shift_type')],
    'work_definition': [('definition_kind', 'definition_kind'),
                        ('status', 'work_definition_status')],
    'work_definition_operation': [('status', 'work_definition_status')],
    'operation_resource_requirement': [('role', 'requirement_role')],
    'resource_capacity': [('capacity_category', 'capacity_category')],
    'resource_assignment': [('status', 'assignment_status'),
                            ('source', 'assignment_source')],
    'resource_territory_assignment': [('coverage_level', 'coverage_level')],
}

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
)


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / 'resource_domain_p2b.db'
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


def _table_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _index_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def _load_raw(bo_id):
    with open(os.path.join(SCHEMA_DIR, bo_id + '.yaml'), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get('fields') or []:
        if f.get('id') == field_id:
            return f
    return None


def test_fresh_creates_tables_indexes_enums_permissions_menus(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True

    names = _table_names(db)
    for table in TABLES:
        assert table in names, '缺表 {0}'.format(table)

    index_names = _index_names(db)
    for name, _table, _sql in INDEXES:
        assert name in index_names, '缺索引 {0}'.format(name)
    assert len(UNIQUE_KEYS) == 7

    assert _scalar(db, 'SELECT COUNT(*) FROM enum_types')[0] == len(ENUM_SEEDS)
    expected_values = sum(len(seed[3]) for seed in ENUM_SEEDS)
    assert expected_values == 28
    assert _scalar(db, 'SELECT COUNT(*) FROM enum_values')[0] == expected_values

    assert _scalar(db, 'SELECT COUNT(*) FROM permissions')[0] == len(PERMISSIONS)
    assert len(PERMISSIONS) == 32
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
    assert len(MENUS) == 8
    assert _scalar(db, 'SELECT COUNT(*) FROM menu_permissions')[0] == len(MENUS)
    assert verify(db) is True


def test_menu_codes_paths_and_ordering(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            'SELECT menu_code, menu_path, sort_order, show_in_sidebar, '
            'primary_object_type FROM menus WHERE parent_menu=? '
            'ORDER BY sort_order', (PARENT_MENU,)).fetchall()
    finally:
        conn.close()

    assert [r[0] for r in rows] == [
        'shift-list', 'calendar-shift-list', 'work-definition-list',
        'work-definition-operation-list', 'operation-resource-requirement-list',
        'resource-capacity-list', 'resource-assignment-list',
        'resource-territory-assignment-list']
    assert [r[2] for r in rows] == list(range(93, 101))
    assert all(r[3] == 0 for r in rows)
    assert [r[4] for r in rows] == [m['primary_object_type'] for m in MENUS]
    for menu, row in zip(MENUS, rows):
        assert row[1] == menu['menu_path']


def test_enum_seeds_match_schema_declarations():
    """type id 与 schema 的 enum_type_id 一字不差，取值顺序与 enum_values 一致。"""
    seeds = {seed[0]: [v[0] for v in seed[3]] for seed in ENUM_SEEDS}
    assert set(seeds) == {t for _bo, fields in ENUM_FIELDS_BY_BO.items()
                          for _fid, t in fields}
    for bo_id, fields in ENUM_FIELDS_BY_BO.items():
        schema = _load_raw(bo_id)
        for field_id, type_id in fields:
            field = _field(schema, field_id)
            assert field is not None, '{0}.{1} 缺失'.format(bo_id, field_id)
            assert field['value_help']['source']['enum_type_id'] == type_id
            assert [v['value'] for v in field['enum_values']] == seeds[type_id], \
                '{0} 取值与枚举种子不一致'.format(type_id)


def test_permission_codes_two_segment(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True
    for action in ('read', 'create', 'update', 'delete'):
        for bo, _label in (
                ('shift', '班次'), ('calendar_shift', '日历班次'),
                ('work_definition', '作业定义'),
                ('work_definition_operation', '作业定义工序'),
                ('operation_resource_requirement', '工序资源要求'),
                ('resource_capacity', '资源产能'),
                ('resource_assignment', '资源分配'),
                ('resource_territory_assignment', '资源区域分配')):
            code = '{0}:{0}_{1}'.format(bo, action)
            assert _scalar(db, 'SELECT action, resource_type FROM permissions '
                              'WHERE code=?', (code,)) == (action, bo)


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
        len(_table_names(db)),
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
        len(_table_names(db)),
    )
    assert after == before
    assert verify(db) is True


def test_rollback_drops_tables_menus_permissions(tmp_path):
    db = _make_db(tmp_path)
    assert migrate(db) is True

    assert rollback(db) is True

    names = _table_names(db)
    for table in TABLES:
        assert table not in names
    assert _scalar(db, 'SELECT 1 FROM menus WHERE menu_code=?',
                   ('shift-list',)) is None
    assert _scalar(db, 'SELECT COUNT(*) FROM menu_permissions')[0] == 0
    assert _scalar(db, 'SELECT COUNT(*) FROM permissions')[0] == 0
    assert _scalar(db, 'SELECT COUNT(*) FROM permission_set_permissions')[0] == 0
    # 枚举种子保留（可能已被其他对象引用）
    assert _scalar(db, 'SELECT COUNT(*) FROM enum_types')[0] == len(ENUM_SEEDS)
    assert verify(db) is False
