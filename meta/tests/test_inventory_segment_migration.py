# -*- coding: utf-8 -*-
"""v205 库存段铺底迁移测试（INV-2 S1）。

覆盖：段列 / 两新表 / 余额唯一键重建 / items 四列 / 5 枚举 / 5 权限 /
2 菜单 / 5 参数 / RSV 序列；存量回填 owned；幂等重跑；verify；rollback 拒绝。
"""

import importlib
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

_V201 = importlib.import_module('meta.migrations.v201__inventory_foundation')
_MIGRATION = importlib.import_module(
    'meta.migrations.v205__inventory_segment_reservation')

_SCHEMA = """
CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE enum_types (
    id TEXT PRIMARY KEY, name TEXT, category TEXT, mutability TEXT,
    dimension_schema TEXT, description TEXT, created_at TEXT
);
CREATE TABLE enum_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT, enum_type_id TEXT, code TEXT,
    name TEXT, name_en TEXT, sort_order INTEGER, is_active INTEGER,
    is_system INTEGER, created_at TEXT
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
    name TEXT, resource_type TEXT, action TEXT
);
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY, code TEXT, is_active INTEGER DEFAULT 1
);
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, permission_set_id INTEGER,
    permission_code TEXT, permission_id INTEGER, granted INTEGER,
    created_at TEXT
);
CREATE TABLE menus (
    menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT,
    page_type TEXT, object_types TEXT, primary_object_type TEXT,
    bo_bindings TEXT, required_permissions TEXT, parent_menu TEXT,
    icon TEXT, color TEXT, description TEXT, sort_order INTEGER,
    is_active INTEGER, show_in_sidebar INTEGER, auto_generated INTEGER
);
CREATE TABLE menu_permissions (
    menu_code TEXT PRIMARY KEY, menu_name TEXT, menu_path TEXT,
    required_permissions TEXT, required_any_permission INTEGER,
    parent_menu TEXT, icon TEXT, sort_order INTEGER, is_active INTEGER,
    data_permission_hint TEXT
);
CREATE TABLE control_parameter_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT,
    domain TEXT, value_type TEXT, target_bo TEXT, default_value TEXT,
    status TEXT, description TEXT, created_at TEXT
);
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT,
    pattern TEXT, scope_fields TEXT, date_field TEXT, start_value INTEGER,
    on_exhaust TEXT, preview TEXT, status TEXT, description TEXT,
    created_at TEXT
);
"""


def _build_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    for _table, sql in _V201.TABLES:
        conn.execute(sql)
    for _name, _table, sql in _V201.INDEXES:
        conn.execute(sql)
    conn.executescript("""
        INSERT INTO items (id, code) VALUES (900, 'ITM-900');
        INSERT INTO permission_sets (id, code, is_active)
            VALUES (1, 'admin', 1), (2, 'default', 1);
        INSERT INTO menus (menu_code, menu_name, menu_path, sort_order,
                           parent_menu, is_active, show_in_sidebar,
                           auto_generated)
            VALUES ('procurement', '采购', '/procurement', 5, '', 1, 1, 0);
        INSERT INTO inventory_transaction_types (
            code, name, category, direction, affects_on_hand, status,
            sort_order, description, created_at)
        VALUES ('OPENING', '期初库存导入', 'adjustment', 'in', 1, 'active',
                40, '期初', '2026-10-01');
        INSERT INTO inventory_transactions (
            transaction_no, transaction_type_id, transaction_date, org_id,
            location_id, item_id, uom_id, qty, base_qty, direction,
            stock_status, source_doc_type, source_doc_id, source_line_id,
            source_event_key)
        SELECT 'INV-OLD-1', id, '2026-10-01', 1, 7, 900, 1, 5, 5, 'in',
               'unrestricted', 'opening', 1, 1, 'evt-old'
        FROM inventory_transaction_types WHERE code = 'OPENING';
        INSERT INTO inventory_balances (
            org_id, location_id, item_id, batch_id, stock_status,
            qty_on_hand, qty_reserved)
        VALUES (1, 7, 900, 0, 'unrestricted', 5, 0);
    """)
    conn.commit()
    conn.close()


def _rows(path, sql, params=()):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _columns(path, table):
    conn = sqlite3.connect(str(path))
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
    finally:
        conn.close()


def _indexes(path):
    conn = sqlite3.connect(str(path))
    try:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    finally:
        conn.close()


def test_migration_applies(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True

    for table in ('inventory_transactions', 'inventory_balances'):
        assert set(_MIGRATION.SEGMENT_COL_NAMES) <= _columns(db, table)
    for col in ('so_segment_enabled', 'consignment_enabled',
                'hard_peg_default', 'valuation_relevant'):
        assert col in _columns(db, 'items')

    indexes = _indexes(db)
    assert _MIGRATION.NEW_BALANCE_INDEX in indexes
    assert _MIGRATION.OLD_BALANCE_INDEX not in indexes
    for name, _table, _sql in _MIGRATION.INDEXES:
        assert name in indexes
    for table, _sql in _MIGRATION.TABLES:
        assert _columns(db, table)


def test_backfill_owned_and_zero_sentinels(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True

    tx = _rows(db, 'SELECT * FROM inventory_transactions')[0]
    bal = _rows(db, 'SELECT * FROM inventory_balances')[0]
    for row in (tx, bal):
        assert row['stock_segment_type'] == 'owned'
        for col in ('project_id', 'project_task_id',
                    'sales_order_line_id', 'owner_party_id'):
            assert row[col] == 0
    assert bal['qty_on_hand'] == 5
    assert _rows(db, 'SELECT COUNT(*) AS n FROM inventory_balances')[0]['n'] == 1


def test_segment_schema_seeds(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True

    for type_id, _name, _desc, values in _MIGRATION.ENUM_SEEDS:
        assert _rows(db, 'SELECT id FROM enum_types WHERE id=?',
                     (type_id,))
        codes = {row['code'] for row in _rows(
            db, 'SELECT code FROM enum_values WHERE enum_type_id=?',
            (type_id,))}
        assert {code for code, _n, _e in values} == codes

    for code, *_ in _MIGRATION.PERMISSIONS:
        assert _rows(db, 'SELECT id FROM permissions WHERE code=?', (code,))
    for menu in _MIGRATION.MENUS:
        row = _rows(db, 'SELECT parent_menu FROM menus WHERE menu_code=?',
                    (menu['menu_code'],))[0]
        assert row['parent_menu'] == 'procurement'
    for code, _name, _vt, default, _target, _desc in _MIGRATION.PARAM_DEFS:
        row = _rows(db, 'SELECT default_value FROM control_parameter_defs '
                        'WHERE code=?', (code,))[0]
        assert row['default_value'] == default
    assert _rows(db, 'SELECT code FROM number_sequences WHERE code=?',
                 (_MIGRATION.NUMBER_SEQUENCE[0],))


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True
    assert _MIGRATION.migrate(db, skip_backup=True) is True
    counts = {
        'permissions': _rows(db, 'SELECT COUNT(*) AS n FROM permissions '
                                 'WHERE code LIKE ?', ('inventory_reservation:%',))[0]['n'],
        'menus': _rows(db, 'SELECT COUNT(*) AS n FROM menus WHERE menu_code IN '
                           "('inventory-reservation-list', "
                           "'demand-trace-link-list')")[0]['n'],
        'params': _rows(db, 'SELECT COUNT(*) AS n FROM control_parameter_defs')[0]['n'],
    }
    assert counts == {'permissions': 4, 'menus': 2, 'params': 5}


def test_verify_passes(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True
    assert _MIGRATION.verify(db) is True


def test_rollback_refuses_non_owned(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True

    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO inventory_balances (org_id, location_id, item_id, "
                 "batch_id, stock_status, qty_on_hand, qty_reserved, "
                 "stock_segment_type, project_id, project_task_id) "
                 "VALUES (1, 7, 900, 0, 'unrestricted', 1, 0, 'project_task', 1, 9)")
    conn.commit()
    conn.close()

    assert _MIGRATION.rollback(db) is False
    assert _rows(db, "SELECT name FROM sqlite_master WHERE type='table' "
                     "AND name='inventory_reservations'")
    assert _MIGRATION.NEW_BALANCE_INDEX in _indexes(db)


def test_rollback_cleans_when_all_owned(tmp_path):
    db = tmp_path / 'inv205.db'
    _build_db(db)
    assert _MIGRATION.migrate(db, skip_backup=True) is True
    assert _MIGRATION.rollback(db) is True

    indexes = _indexes(db)
    assert _MIGRATION.NEW_BALANCE_INDEX not in indexes
    assert _MIGRATION.OLD_BALANCE_INDEX in indexes
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name IN ('inventory_reservations', 'demand_trace_links')"
        ).fetchone()[0] == 0
    finally:
        conn.close()
