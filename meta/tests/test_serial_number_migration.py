# -*- coding: utf-8 -*-
"""v202 序列号对象模型迁移测试（spec §7 / D14）。

覆盖：三表 + 11 索引 + items 三列 + 5 枚举 + 权限 + 三菜单、
qty=1 回填 / qty>1 与重复号跳过、幂等重跑、verify、rollback。
"""

import importlib
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

_MIGRATION = importlib.import_module('meta.migrations.v202__serial_number_model')

_SCHEMA = """
CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT, org_id INTEGER);
CREATE TABLE batches (
    id INTEGER PRIMARY KEY, batch_no TEXT, item_id INTEGER, org_id INTEGER
);
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY, receipt_no TEXT, org_id INTEGER,
    inventory_org_id INTEGER, deliver_to_location_id INTEGER,
    actual_arrival_date TEXT, status TEXT
);
CREATE TABLE receipt_lines (
    id INTEGER PRIMARY KEY, receipt_id INTEGER, item_id INTEGER,
    serial_no TEXT, qty_received REAL, qty_rejected REAL DEFAULT 0,
    lot_no TEXT
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY, delivery_no TEXT, ship_from_location_id INTEGER,
    actual_ship_date TEXT, status TEXT
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY, delivery_id INTEGER, item_id INTEGER,
    serial_no TEXT, qty REAL
);
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
"""


def _build_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.executescript("""
        INSERT INTO items (id, code) VALUES (900, 'ITM-900');
        INSERT INTO orgs (id, code) VALUES (1, 'SH'), (2, 'RCV');
        INSERT INTO locations (id, name, org_id) VALUES (7, 'SHIP', 1),
                                                       (8, 'STORE', 2);
        INSERT INTO batches (id, batch_no, item_id, org_id)
            VALUES (5, 'LOT-1', 900, 2);
        INSERT INTO receipts (id, receipt_no, org_id, inventory_org_id,
                              deliver_to_location_id, actual_arrival_date, status)
            VALUES (1, 'RC-1', 2, 2, 8, '2026-10-01', 'posted');
        INSERT INTO receipt_lines (id, receipt_id, item_id, serial_no,
                                   qty_received, qty_rejected, lot_no)
            VALUES (11, 1, 900, 'SN-R1', 1, 0, 'LOT-1'),
                   (12, 1, 900, 'SN-R1', 1, 0, NULL),
                   (13, 1, 900, 'SN-MULTI', 3, 0, NULL),
                   (14, 1, 900, 'SN-CSV,SN-CSV2', 1, 0, NULL);
        INSERT INTO shipments (id, delivery_no, ship_from_location_id,
                               actual_ship_date, status)
            VALUES (21, 'DN-1', 7, '2026-10-05', 'shipped');
        INSERT INTO shipment_lines (id, delivery_id, item_id, serial_no, qty)
            VALUES (31, 21, 900, 'SN-S1', 1),
                   (32, 21, 900, 'SN-SMULTI', 2);
        INSERT INTO permission_sets (id, code, is_active)
            VALUES (1, 'admin', 1), (2, 'default', 1);
        INSERT INTO menus (menu_code, menu_name, menu_path, sort_order,
                           parent_menu, is_active, show_in_sidebar,
                           auto_generated)
            VALUES ('master-data', '主数据', '/master-data', 100, '', 1, 1, 0),
                   ('procurement', '采购', '/procurement', 5, '', 1, 1, 0);
    """)
    conn.commit()
    conn.close()


def _rows(path, sql, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, list(params)).fetchall()
    finally:
        conn.close()


def _migrated_db(tmp_path):
    path = tmp_path / 'v202.db'
    _build_db(path)
    assert _MIGRATION.migrate(path) is True
    return path


def test_migrate_creates_model_enums_permissions_and_menus(tmp_path):
    path = _migrated_db(tmp_path)

    for table, _ddl in _MIGRATION.TABLES:
        assert _rows(path, "SELECT 1 FROM sqlite_master WHERE type='table' "
                           'AND name=?', (table,))
    for _table, name, _sql in _MIGRATION.INDEXES:
        assert _rows(path, "SELECT 1 FROM sqlite_master WHERE type='index' "
                           'AND name=?', (name,))
    columns = {row[1] for row in _rows(path, 'PRAGMA table_info(items)')}
    assert {'serial_tracked', 'require_on_receipt', 'require_on_issue'} <= columns

    assert len(_rows(path, 'SELECT id FROM enum_types')) == 5
    assert len(_rows(path, 'SELECT id FROM enum_values')) == 27
    assert len(_rows(path, 'SELECT code FROM permissions')) == 8

    menus = {row[0]: row[1] for row in _rows(
        path, 'SELECT menu_code, parent_menu FROM menus')}
    assert menus['serial-number-list'] == 'master-data'
    assert menus['serial-transaction-list'] == 'procurement'
    assert menus['document-serial-link-list'] == 'procurement'
    assert _rows(path, "SELECT sort_order FROM menus "
                       "WHERE menu_code='serial-number-list'")[0][0] == 107

    assert _MIGRATION.verify(path) is True


def test_migrate_backfills_only_single_qty_and_skips_duplicates(tmp_path):
    path = _migrated_db(tmp_path)

    serials = {row[0]: row for row in _rows(
        path, 'SELECT serial_no, usage_status, org_id, current_location_id, '
              'batch_id FROM serial_numbers')}
    assert set(serials) == {'SN-R1', 'SN-S1'}
    assert serials['SN-R1'][1:] == ('in_stores', 2, 8, 5)
    assert serials['SN-S1'][1:] == ('shipped', 1, None, None)

    links = _rows(path, 'SELECT doc_type, doc_id, line_id, direction '
                        'FROM document_serial_links ORDER BY doc_type')
    assert [(row[0], row[2], row[3]) for row in links] == [
        ('receipt', 11, 'in'), ('shipment', 31, 'out'),
    ]
    events = _rows(path, 'SELECT txn_type FROM serial_transactions ORDER BY id')
    assert [row[0] for row in events] == ['receive', 'ship']


def test_migrate_is_idempotent(tmp_path):
    path = _migrated_db(tmp_path)
    counts = {
        'serial_numbers': len(_rows(path, 'SELECT 1 FROM serial_numbers')),
        'links': len(_rows(path, 'SELECT 1 FROM document_serial_links')),
        'events': len(_rows(path, 'SELECT 1 FROM serial_transactions')),
        'permissions': len(_rows(path, 'SELECT 1 FROM permissions')),
        'menus': len(_rows(path, 'SELECT 1 FROM menus')),
    }

    assert _MIGRATION.migrate(path) is True

    assert len(_rows(path, 'SELECT 1 FROM serial_numbers')) == \
        counts['serial_numbers']
    assert len(_rows(path, 'SELECT 1 FROM document_serial_links')) == \
        counts['links']
    assert len(_rows(path, 'SELECT 1 FROM serial_transactions')) == \
        counts['events']
    assert len(_rows(path, 'SELECT 1 FROM permissions')) == \
        counts['permissions']
    assert len(_rows(path, 'SELECT 1 FROM menus')) == counts['menus']
    assert _MIGRATION.verify(path) is True


def test_rollback_removes_model_and_keep_item_columns_zeroed(tmp_path):
    path = _migrated_db(tmp_path)

    assert _MIGRATION.rollback(path) is True
    assert _MIGRATION.verify(path) is False

    for table, _ddl in _MIGRATION.TABLES:
        assert not _rows(path, "SELECT 1 FROM sqlite_master WHERE type='table' "
                               'AND name=?', (table,))
    assert len(_rows(path, 'SELECT 1 FROM permissions')) == 0
    menus = {row[0] for row in _rows(path, 'SELECT menu_code FROM menus')}
    assert not ({'serial-number-list', 'serial-transaction-list',
                 'document-serial-link-list'} & menus)

    columns = {row[1] for row in _rows(path, 'PRAGMA table_info(items)')}
    assert {'serial_tracked', 'require_on_receipt', 'require_on_issue'} <= columns


def test_migrate_returns_false_when_db_missing(tmp_path):
    assert _MIGRATION.migrate(tmp_path / 'missing.db') is False
