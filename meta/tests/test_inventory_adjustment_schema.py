# -*- coding: utf-8 -*-
"""INV-4 YAML 声明与 v203 迁移测试（spec FR-001~FR-007 / §9.3.3）。

覆盖:
  · 4 个 YAML 可加载、表名与迁移常量一致、行对象父子关系；
  · auto_crud=False、ensure_crud_actions 不产生裸 delete/batch 动作，
    delete 权限复用 update；
  · 状态迁移规则数量 / 方向 / action_ref；
  · v203 真实迁移：4 表 / 7 类型 / ADJ+CNT 序列 / 18 权限 / 2 菜单 / 4 参数，
    verify=True、重复 migrate 幂等、rollback 后 4 表消失。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pathlib
import sqlite3

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.yaml_loader import ensure_crud_actions, load_yaml_file
from meta.migrations import v201__inventory_foundation as v201
from meta.migrations import v203__inventory_adjustment as v203

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

# 与 test_inventory_schema.py 保持一致的迁移依赖基础表
BASE_SCHEMA = """
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT, name TEXT,
                   status TEXT DEFAULT 'active');
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    pattern TEXT,
    scope_fields TEXT,
    date_field TEXT,
    start_value INTEGER,
    on_exhaust TEXT,
    preview TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT,
    resource_type TEXT,
    action TEXT
);
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER,
    permission_code TEXT,
    permission_id INTEGER,
    granted INTEGER,
    created_at TEXT
);
CREATE TABLE menus (
    menu_code TEXT PRIMARY KEY,
    menu_name TEXT,
    menu_path TEXT,
    page_type TEXT,
    object_types TEXT,
    primary_object_type TEXT,
    bo_bindings TEXT,
    required_permissions TEXT,
    parent_menu TEXT,
    icon TEXT,
    color TEXT,
    description TEXT,
    sort_order INTEGER,
    is_active INTEGER DEFAULT 1,
    show_in_sidebar INTEGER DEFAULT 0,
    auto_generated INTEGER DEFAULT 0
);
CREATE TABLE menu_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code TEXT,
    menu_name TEXT,
    menu_path TEXT,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    parent_menu TEXT,
    icon TEXT,
    sort_order INTEGER,
    is_active INTEGER DEFAULT 1,
    data_permission_hint TEXT,
    UNIQUE (menu_code)
);
CREATE TABLE control_parameter_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    domain TEXT,
    value_type TEXT,
    target_bo TEXT,
    default_value TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE control_parameter_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_parameter_id INTEGER,
    value TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE procurement_seed (id INTEGER PRIMARY KEY);
"""


def _load(name):
    return load_yaml_file(str(SCHEMA_DIR / name))


def _build_db(tmp_path):
    db = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(db))
    conn.executescript(BASE_SCHEMA)
    conn.execute("INSERT INTO orgs (id, code, name) VALUES (1, 'ORG1', '组织1')")
    conn.execute(
        "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
        "object_types, primary_object_type, bo_bindings, "
        "required_permissions, parent_menu, icon, sort_order, is_active, "
        "show_in_sidebar, auto_generated) "
        "VALUES ('procurement', '采购', '/procurement', 'module', '[]', "
        "NULL, '[]', '[]', NULL, 'Cart', 10, 1, 1, 0)")
    conn.execute(
        "INSERT INTO permission_sets (id, code, is_active) "
        "VALUES (1, 'admin', 1)")
    conn.execute(
        "INSERT INTO permission_sets (id, code, is_active) "
        "VALUES (2, 'default', 1)")
    conn.commit()
    conn.close()
    return db


def _table_names(conn):
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


# ---------------- YAML 声明 ----------------

def test_four_yaml_files_load_with_expected_table_names():
    adjustment = _load('inventory_adjustment.yaml')
    adjustment_line = _load('inventory_adjustment_line.yaml')
    count = _load('inventory_count.yaml')
    count_line = _load('inventory_count_line.yaml')

    assert adjustment.table_name == v203.ADJ_TABLE
    assert adjustment_line.table_name == v203.ADJ_LINE_TABLE
    assert count.table_name == v203.CNT_TABLE
    assert count_line.table_name == v203.CNT_LINE_TABLE

    assert adjustment_line.parent_object == 'inventory_adjustment'
    assert adjustment_line.hierarchy['parent_field'] == 'adjustment_id'
    assert count_line.parent_object == 'inventory_count'
    assert count_line.hierarchy['parent_field'] == 'count_id'


def test_auto_crud_disabled_and_crud_actions_are_read_only_sets():
    adjustment = _load('inventory_adjustment.yaml')
    adjustment_line = _load('inventory_adjustment_line.yaml')
    count = _load('inventory_count.yaml')
    count_line = _load('inventory_count_line.yaml')

    # auto_crud 是 YAML 声明性意图（框架按「已声明 CRUD 则短路」生效），
    # 与 audit_log / party 等既有 schema 的校验口径一致：直接读原始 YAML。
    for name in ('inventory_adjustment.yaml', 'inventory_adjustment_line.yaml',
                 'inventory_count.yaml', 'inventory_count_line.yaml'):
        raw = yaml.safe_load(
            (SCHEMA_DIR / name).read_text(encoding='utf-8'))
        assert raw['import_export']['auto_crud'] is False

    # 头对象：加载后动作面恰为 read/list/create/update，无裸 delete/batch
    for obj in (adjustment, count):
        expected = {'%s_read' % obj.id, '%s_list' % obj.id,
                    '%s_create' % obj.id, '%s_update' % obj.id}
        assert {action.id for action in obj.actions} == expected
        assert ensure_crud_actions(obj) is obj
        assert {action.id for action in obj.actions} == expected
        assert not any(action.id.endswith(('_delete', '_batch'))
                       for action in obj.actions)
        assert obj.authorization['permissions']['delete'] == \
            '%s:update' % obj.id

    # 行对象：YAML 不声明任何裸动作，删除 / 编辑复用父对象 update 权限
    for name, obj in (('inventory_adjustment_line.yaml', adjustment_line),
                      ('inventory_count_line.yaml', count_line)):
        raw = yaml.safe_load(
            (SCHEMA_DIR / name).read_text(encoding='utf-8'))
        assert raw.get('actions') in (None, [])
        assert obj.authorization['permissions']['delete'] == \
            '%s:update' % obj.parent_object
        assert obj.authorization['permissions']['create'] == \
            '%s:update' % obj.parent_object


def test_state_transition_rules_match_spec():
    adjustment = _load('inventory_adjustment.yaml')
    rules = {rule.id: rule for rule in adjustment.get_state_transitions()}
    assert len(rules) == 4
    assert set(rules) == {
        'release_inventory_adjustment', 'post_inventory_adjustment',
        'reverse_inventory_adjustment', 'cancel_inventory_adjustment'}

    assert set(rules['release_inventory_adjustment'].from_states) == {'draft'}
    assert rules['release_inventory_adjustment'].to_state == 'released'
    assert set(rules['post_inventory_adjustment'].from_states) == {
        'draft', 'released'}
    assert rules['post_inventory_adjustment'].to_state == 'posted'
    assert set(rules['reverse_inventory_adjustment'].from_states) == {'posted'}
    assert rules['reverse_inventory_adjustment'].to_state == 'reversed'
    assert set(rules['cancel_inventory_adjustment'].from_states) == {
        'draft', 'released'}
    assert rules['cancel_inventory_adjustment'].to_state == 'cancelled'

    for rule in rules.values():
        assert rule.action_ref
    assert rules['post_inventory_adjustment'].action_ref == \
        'inventory_adjustment:post'

    count = _load('inventory_count.yaml')
    count_rules = {rule.id: rule for rule in count.get_state_transitions()}
    assert len(count_rules) == 5
    assert set(count_rules) == {
        'start_inventory_count', 'submit_inventory_count',
        'approve_inventory_count', 'post_inventory_count',
        'cancel_inventory_count'}
    assert set(count_rules['start_inventory_count'].from_states) == {'draft'}
    assert count_rules['start_inventory_count'].to_state == 'counting'
    assert set(count_rules['submit_inventory_count'].from_states) == \
        {'counting'}
    assert count_rules['submit_inventory_count'].to_state == 'submitted'
    assert set(count_rules['approve_inventory_count'].from_states) == \
        {'submitted'}
    assert count_rules['approve_inventory_count'].to_state == 'approved'
    assert set(count_rules['post_inventory_count'].from_states) == {'approved'}
    assert count_rules['post_inventory_count'].to_state == 'posted'
    assert set(count_rules['cancel_inventory_count'].from_states) == {
        'draft', 'counting', 'submitted', 'approved'}
    assert count_rules['cancel_inventory_count'].to_state == 'cancelled'
    for rule in count_rules.values():
        assert rule.action_ref


# ---------------- 真实迁移 ----------------

def test_v203_migrate_verify_idempotent_and_rollback(tmp_path):
    db = _build_db(tmp_path)
    assert v201.migrate(db, skip_backup=True) is True
    assert v203.migrate(db, skip_backup=True) is True
    assert v203.verify(db) is True

    conn = sqlite3.connect(str(db))
    try:
        tables = _table_names(conn)
        for table, _sql in v203.TABLES:
            assert table in tables

        type_codes = [code for code, *_rest in v203.TRANSACTION_TYPES]
        found = {row[0] for row in conn.execute(
            'SELECT code FROM inventory_transaction_types')}
        assert len(type_codes) == 7
        assert set(type_codes) <= found

        sequences = {row[0] for row in conn.execute(
            'SELECT code FROM number_sequences WHERE code IN (?, ?)',
            ('ADJ', 'CNT'))}
        assert sequences == {'ADJ', 'CNT'}
        assert conn.execute(
            "SELECT COUNT(*) FROM number_sequences WHERE code='ADJ' "
            "AND pattern='ADJ-{DATE:yyyymm}-{SEQ:6}'").fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM number_sequences WHERE code='CNT' "
            "AND pattern='CNT-{DATE:yyyymm}-{SEQ:6}'").fetchone()[0] == 1

        permission_codes = [row[0] for row in v203.PERMISSIONS]
        # tasks.md 枚举为调整 9 条（含 opening）+ 盘点 9 条（含 update）。
        # spec/checklist 里的「17 条」是旧计数；盘点单头/行编辑依赖
        # inventory_count_update（count_line 的写权限映射到它），不可删。
        assert len(permission_codes) == 18
        found_permissions = {row[0] for row in conn.execute(
            'SELECT code FROM permissions')}
        assert set(permission_codes) <= found_permissions
        assert conn.execute(
            'SELECT COUNT(*) FROM permissions WHERE code IN (%s)'
            % ','.join('?' * len(permission_codes)),
            permission_codes).fetchone()[0] == 18

        menu_codes = {row[0] for row in conn.execute(
            'SELECT menu_code FROM menus WHERE menu_code IN (?, ?)',
            (v203.ADJ_MENU_CODE, v203.CNT_MENU_CODE))}
        assert menu_codes == {v203.ADJ_MENU_CODE, v203.CNT_MENU_CODE}

        param_codes = [entry[0] for entry in v203.PARAM_DEFS]
        assert len(param_codes) == 4
        found_params = {row[0] for row in conn.execute(
            'SELECT code FROM control_parameter_defs')}
        assert set(param_codes) <= found_params
        assert conn.execute(
            'SELECT COUNT(*) FROM control_parameter_defs WHERE code IN (%s)'
            % ','.join('?' * len(param_codes)),
            param_codes).fetchone()[0] == 4

        before = {
            'permissions': conn.execute(
                'SELECT COUNT(*) FROM permissions').fetchone()[0],
            'types': conn.execute(
                'SELECT COUNT(*) FROM inventory_transaction_types'
            ).fetchone()[0],
            'params': conn.execute(
                'SELECT COUNT(*) FROM control_parameter_defs').fetchone()[0],
        }
    finally:
        conn.close()

    # 幂等：再次执行不新增权限 / 类型 / 参数
    assert v203.migrate(db, skip_backup=True) is True
    conn = sqlite3.connect(str(db))
    try:
        after = {
            'permissions': conn.execute(
                'SELECT COUNT(*) FROM permissions').fetchone()[0],
            'types': conn.execute(
                'SELECT COUNT(*) FROM inventory_transaction_types'
            ).fetchone()[0],
            'params': conn.execute(
                'SELECT COUNT(*) FROM control_parameter_defs').fetchone()[0],
        }
    finally:
        conn.close()
    assert after == before

    assert v203.rollback(db) is True
    conn = sqlite3.connect(str(db))
    try:
        remaining = _table_names(conn)
    finally:
        conn.close()
    for table, _sql in v203.TABLES:
        assert table not in remaining
