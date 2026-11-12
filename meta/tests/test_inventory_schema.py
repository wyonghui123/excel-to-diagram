# -*- coding: utf-8 -*-
"""库存模型基线测试（spec define-inventory-model §9.3 / TR-001）

覆盖:
  · YAML 声明：表名 / 只读权限双段码 / 无写动作 / 唯一索引；
  · v201 迁移：临时库建依赖表 → migrate → verify；重复执行幂等；
    rollback 生效；唯一约束真实生效。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pathlib
import sqlite3

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.migrations import v201__inventory_foundation as v201
from meta.tests import inventory_test_doubles as inv

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

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
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _fields(doc):
    return {f['id']: f for f in doc['fields']}


def _build_db(tmp_path, seed_sets=True):
    db = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(db))
    conn.executescript(BASE_SCHEMA)
    conn.execute("INSERT INTO orgs (id, code, name) VALUES (1, 'ORG1', '组织1')")
    conn.execute("INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
                 "object_types, primary_object_type, bo_bindings, "
                 "required_permissions, parent_menu, icon, sort_order, is_active, "
                 "show_in_sidebar, auto_generated) "
                 "VALUES ('procurement', '采购', '/procurement', 'module', '[]', "
                 "NULL, '[]', '[]', NULL, 'Cart', 10, 1, 1, 0)")
    # 模拟 auto-generator 生成的孤儿菜单
    conn.execute("INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
                 "object_types, primary_object_type, bo_bindings, "
                 "required_permissions, parent_menu, icon, sort_order, is_active, "
                 "show_in_sidebar, auto_generated) "
                 "VALUES ('inventory_balance-list', '库存余额-列表', '/x', "
                 "'object_list', '[]', 'inventory_balance', '[]', '[]', "
                 "'procurement', 'Boxes', 20, 1, 0, 1)")
    if seed_sets:
        conn.execute("INSERT INTO permission_sets (id, code, is_active) "
                     "VALUES (1, 'admin', 1)")
        conn.execute("INSERT INTO permission_sets (id, code, is_active) "
                     "VALUES (2, 'default', 1)")
    conn.commit()
    conn.close()
    return db


# ---------------- YAML 声明 ----------------

def test_transaction_schema_declares_append_only_object():
    doc = _load('inventory_transaction.yaml')
    assert doc['table_name'] == v201.TX_TABLE
    assert doc['display_name_field'] == 'transaction_no'
    assert doc['semantics']['category'] == 'business_document_line'
    fields = _fields(doc)
    for name in ('transaction_no', 'transaction_type_id', 'transaction_date',
                 'org_id', 'location_id', 'item_id', 'uom_id', 'qty',
                 'base_qty', 'direction', 'batch_id', 'stock_status',
                 'source_doc_type', 'source_doc_id', 'source_line_id',
                 'source_event_key', 'transfer_group_id',
                 'reversal_of_transaction_id'):
        assert name in fields, '缺字段 %s' % name
    assert fields['id']['semantics']['primary_key'] is True


def test_balance_schema_declares_projection_object():
    doc = _load('inventory_balance.yaml')
    assert doc['table_name'] == v201.BAL_TABLE
    assert doc['semantics']['category'] == 'master_data'
    fields = _fields(doc)
    for name in ('org_id', 'location_id', 'item_id', 'batch_id',
                 'stock_status', 'qty_on_hand', 'qty_reserved'):
        assert name in fields, '缺字段 %s' % name
    assert fields['batch_id'].get('default') == 0
    index = next(i for i in doc['indexes']
                 if i.get('name') == 'uq_inv_balance_segment')
    assert index['unique'] is True
    assert index['fields'] == ['org_id', 'location_id', 'item_id', 'batch_id',
                               'stock_status', 'stock_segment_type',
                               'project_id', 'project_task_id',
                               'sales_order_line_id', 'owner_party_id']


def test_readonly_schemas_have_no_write_actions():
    for name in ('inventory_transaction.yaml', 'inventory_balance.yaml'):
        doc = _load(name)
        assert doc['ui_view_config']['skip_auto_menu'] is True
        assert doc.get('create') is None, '%s 不应有 create' % name
        assert doc.get('update') is None, '%s 不应有 update' % name
        assert doc.get('delete') is None, '%s 不应有 delete' % name
        actions = (doc.get('ui_view_config', {}).get('list') or {}).get(
            'actions', [])
        assert actions == [], '%s 列表不应有行操作' % name


def test_readonly_schemas_loaded_actions_are_read_and_list_only():
    """平台加载后动作面恰为 read/list —— ensure_crud_actions 不得补写动作。"""
    from meta.core.yaml_loader import load_yaml_file

    for name, obj_id in (('inventory_transaction.yaml', 'inventory_transaction'),
                         ('inventory_balance.yaml', 'inventory_balance')):
        obj = load_yaml_file(str(SCHEMA_DIR / name))
        assert obj is not None, '%s 平台加载失败' % name
        actual = {a.id for a in obj.actions}
        assert actual == {obj_id + '_read', obj_id + '_list'}, (
            '%s 动作面应为 read/list，实际 %s' % (name, sorted(actual)))


def test_schema_permissions_map_read_and_list():
    expected = {
        'inventory_transaction.yaml': (
            'inventory_transaction:read',
            'inventory_transaction:read'),
        'inventory_balance.yaml': (
            'inventory_balance:read',
            'inventory_balance:read'),
    }
    for name, (read_code, list_code) in expected.items():
        perms = _load(name)['authorization']['permissions']
        assert perms['read'] == read_code
        assert perms['list'] == list_code


def test_permission_gate_uses_declared_read_codes():
    """crud_read/crud_list 按声明的单段码判定；写动作未授予即拒。"""
    from meta.core.permission_gate import evaluate, resolve_required_permission
    from meta.core.yaml_loader import load_yaml_file

    for name, obj_id in (('inventory_transaction.yaml', 'inventory_transaction'),
                         ('inventory_balance.yaml', 'inventory_balance')):
        load_yaml_file(str(SCHEMA_DIR / name))  # 注册进 registry
        read_code, source = resolve_required_permission(obj_id, 'crud_read')
        assert source == 'declared'
        assert read_code == '%s:read' % obj_id
        reader = {'user_id': 1, 'permissions': [read_code]}
        assert evaluate(reader, obj_id, 'crud_read').allowed is True
        assert evaluate(reader, obj_id, 'crud_list').allowed is True
        for action, suffix in (('crud_create', 'create'),
                               ('crud_update', 'update'),
                               ('crud_delete', 'delete')):
            required, _source = resolve_required_permission(obj_id, action)
            assert required == '%s:%s' % (obj_id, suffix)
            assert evaluate(reader, obj_id, action).allowed is False


def test_schemas_load_through_platform_loader():
    from meta.core.yaml_loader import load_yaml_file

    expected_fields = {
        'inventory_transaction.yaml': {'transaction_no', 'source_event_key'},
        'inventory_balance.yaml': {'qty_on_hand', 'qty_reserved'},
    }
    for name, fields in expected_fields.items():
        obj = load_yaml_file(str(SCHEMA_DIR / name))
        assert obj is not None, '%s 平台加载失败' % name
        loaded = {f.id for f in obj.fields}
        assert fields <= loaded, '%s 字段缺失: %s' % (name, fields - loaded)


# ---------------- v201 迁移 ----------------

def _columns(conn, table):
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        [table]).fetchone() is not None


def _index_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        [name]).fetchone() is not None


def test_migration_creates_tables_indexes_and_seeds(tmp_path):
    db = _build_db(tmp_path)
    assert v201.migrate(db) is True

    conn = sqlite3.connect(str(db))
    try:
        for table, _ddl in v201.TABLES:
            assert _table_exists(conn, table), '缺表 %s' % table
        for name, _table, _ddl in v201.INDEXES:
            assert _index_exists(conn, name), '缺索引 %s' % name

        codes = {row[0] for row in conn.execute(
            'SELECT code FROM inventory_transaction_types').fetchall()}
        assert codes == {t[0] for t in v201.TRANSACTION_TYPES}

        seq = conn.execute(
            'SELECT pattern, date_field, on_exhaust FROM number_sequences '
            'WHERE code=?', [v201.NUMBER_SEQUENCE[0]]).fetchone()
        assert seq == (v201.NUMBER_SEQUENCE[2], v201.NUMBER_SEQUENCE[3],
                       v201.NUMBER_SEQUENCE[5])

        perms = {row[0] for row in conn.execute(
            'SELECT code FROM permissions').fetchall()}
        assert perms == {p[0] for p in v201.PERMISSIONS}

        # 参数默认关闭
        params = dict(conn.execute(
            'SELECT code, default_value FROM control_parameter_defs').fetchall())
        assert params['inventory_posting_enabled'] == '0'
        assert params['inventory_allow_negative'] == '0'

        # org 默认库位列
        assert 'default_inventory_location_id' in _columns(conn, 'orgs')

        menu = conn.execute(
            'SELECT page_type, primary_object_type, parent_menu, '
            'show_in_sidebar FROM menus WHERE menu_code=?',
            [v201.INVENTORY_MENU_CODE]).fetchone()
        assert menu == ('object_list', 'inventory_balance',
                        v201.ROOT_MENU_CODE, 0)
        # 孤儿自动菜单被清理
        assert not conn.execute(
            "SELECT 1 FROM menus WHERE menu_code='inventory_balance-list'"
        ).fetchone()

        grants = conn.execute(
            'SELECT COUNT(*) FROM permission_set_permissions').fetchone()[0]
        assert grants == len(v201.PERMISSIONS) * len(v201.GRANT_TO_SETS)
    finally:
        conn.close()

    assert v201.verify(db) is True


def test_migration_is_idempotent(tmp_path):
    db = _build_db(tmp_path)
    assert v201.migrate(db) is True
    assert v201.migrate(db) is True

    conn = sqlite3.connect(str(db))
    try:
        count = conn.execute(
            'SELECT COUNT(*) FROM inventory_transaction_types').fetchone()[0]
        assert count == len(v201.TRANSACTION_TYPES)
        count = conn.execute(
            'SELECT COUNT(*) FROM number_sequences WHERE code=?',
            [v201.NUMBER_SEQUENCE[0]]).fetchone()[0]
        assert count == 1
        count = conn.execute(
            'SELECT COUNT(*) FROM permissions').fetchone()[0]
        assert count == len(v201.PERMISSIONS)
    finally:
        conn.close()


def test_rollback_drops_inventory_objects(tmp_path):
    db = _build_db(tmp_path)
    assert v201.migrate(db) is True
    assert v201.rollback(db) is True

    conn = sqlite3.connect(str(db))
    try:
        for table, _ddl in v201.TABLES:
            assert not _table_exists(conn, table), '%s 未删除' % table
        for name, _table, _ddl in v201.INDEXES:
            assert not _index_exists(conn, name), '%s 未删除' % name
        assert not conn.execute(
            'SELECT 1 FROM number_sequences WHERE code=?',
            [v201.NUMBER_SEQUENCE[0]]).fetchone()
        assert not conn.execute(
            'SELECT 1 FROM menus WHERE menu_code=?',
            [v201.INVENTORY_MENU_CODE]).fetchone()
        assert conn.execute('SELECT COUNT(*) FROM permissions').fetchone()[0] == 0
        assert not conn.execute(
            "SELECT 1 FROM control_parameter_defs "
            "WHERE code='inventory_posting_enabled'").fetchone()
        # org 列保留但取值清空
        assert 'default_inventory_location_id' in _columns(conn, 'orgs')
        assert conn.execute(
            'SELECT COUNT(*) FROM orgs WHERE default_inventory_location_id IS '
            'NOT NULL').fetchone()[0] == 0
        # 父菜单保留
        assert conn.execute(
            "SELECT 1 FROM menus WHERE menu_code='procurement'").fetchone()
    finally:
        conn.close()


def test_unique_constraints_are_effective(tmp_path):
    db = _build_db(tmp_path)
    assert v201.migrate(db) is True

    conn = sqlite3.connect(str(db))
    try:
        type_id = conn.execute(
            "SELECT id FROM inventory_transaction_types WHERE code='RCV_PO'"
        ).fetchone()[0]
        _insert = (
            'INSERT INTO inventory_transactions '
            '(transaction_no, transaction_type_id, transaction_date, org_id, '
            'location_id, item_id, uom_id, qty, base_qty, direction, batch_id, '
            'stock_status, source_doc_type, source_doc_id, source_line_id, '
            'source_event_key, reversal_of_transaction_id) '
            'VALUES (?, ?, ?, 1, 7, 900, 3, 10, 10, ?, 0, ?, ?, 1, 1, ?, ?)')
        conn.execute(_insert, ['INV-1', type_id, '2026-11-03', 'in',
                               'unrestricted', 'receipt', 'receipt:1:post', None])
        # 幂等键重复 → 拒绝
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_insert, ['INV-2', type_id, '2026-11-03', 'in',
                                   'unrestricted', 'receipt',
                                   'receipt:1:post', None])
        # 同一原分录反冲两次 → 拒绝
        conn.execute(_insert, ['INV-3', type_id, '2026-11-03', 'out',
                               'unrestricted', 'receipt', 'receipt:1:reverse', 1])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_insert, ['INV-4', type_id, '2026-11-03', 'out',
                                   'unrestricted', 'receipt',
                                   'receipt:1:reverse2', 1])
        # 余额唯一键重复 → 拒绝
        conn.execute(
            'INSERT INTO inventory_balances (org_id, location_id, item_id, '
            'batch_id, stock_status, qty_on_hand) '
            "VALUES (1, 7, 900, 0, 'unrestricted', 10)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO inventory_balances (org_id, location_id, item_id, '
                'batch_id, stock_status, qty_on_hand) '
                "VALUES (1, 7, 900, 0, 'unrestricted', 5)")
        # 数量必须为正（qty = 0 违反 CHECK）
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                'INSERT INTO inventory_transactions '
                '(transaction_no, transaction_type_id, transaction_date, org_id, '
                'location_id, item_id, uom_id, qty, base_qty, direction, '
                'batch_id, stock_status, source_doc_type, source_doc_id, '
                'source_line_id, source_event_key, '
                'reversal_of_transaction_id) '
                "VALUES ('INV-5', ?, '2026-11-03', 1, 7, 900, 3, 0, 0, 'in', "
                "0, 'unrestricted', 'receipt', 1, 5, 'receipt:1:zero', NULL)",
                [type_id])
        conn.rollback()
    finally:
        conn.close()


def test_test_doubles_reuse_migration_constants():
    """测试替身与迁移共用同一份 DDL / 种子，避免口径漂移。"""
    conn = inv.seed()
    try:
        for table, _ddl in v201.TABLES:
            assert _table_exists(conn, table), '替身缺表 %s' % table
        codes = {row[0] for row in conn.execute(
            'SELECT code FROM inventory_transaction_types').fetchall()}
        assert codes == {t[0] for t in v201.TRANSACTION_TYPES}
        assert conn.execute(
            'SELECT pattern FROM number_sequences WHERE code=?',
            [v201.NUMBER_SEQUENCE[0]]).fetchone()[0] == \
            v201.NUMBER_SEQUENCE[2]
    finally:
        conn.close()
