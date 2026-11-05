# -*- coding: utf-8 -*-
"""包装容器测试替身（P6a-2 §11）。

只建服务真正读写的表；HU 三表直接复用迁移 v211 的 DDL / 索引，
保证测试与生产约束一致（含部分唯一索引与 CHECK）。
"""

import importlib
import sqlite3

from meta.tests.receipt_test_doubles import MemDS

_MIGRATION = importlib.import_module('meta.migrations.v211__handling_unit')
_STATUS_MIGRATION = importlib.import_module(
    'meta.migrations.v217__handling_unit_status')

SCHEMA = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    name TEXT,
    serial_tracked INTEGER DEFAULT 0,
    require_on_receipt INTEGER DEFAULT 0,
    require_on_issue INTEGER DEFAULT 0
);
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT, name TEXT);
CREATE TABLE locations (
    id INTEGER PRIMARY KEY, code TEXT, name TEXT, org_id INTEGER,
    status TEXT DEFAULT 'active'
);
CREATE TABLE batches (
    id INTEGER PRIMARY KEY, batch_no TEXT, item_id INTEGER, org_id INTEGER
);
CREATE TABLE serial_numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER, org_id INTEGER, serial_no TEXT, batch_id INTEGER,
    usage_status TEXT DEFAULT 'defined',
    quality_status TEXT DEFAULT 'unrestricted',
    current_location_id INTEGER, shipped_at TEXT,
    created_at TEXT, updated_at TEXT,
    UNIQUE (item_id, org_id, serial_no)
);
CREATE TABLE serial_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, serial_id INTEGER,
    inventory_transaction_id INTEGER, txn_type TEXT, txn_date TEXT,
    org_from_id INTEGER, org_to_id INTEGER,
    location_from_id INTEGER, location_to_id INTEGER,
    batch_from_id INTEGER, batch_to_id INTEGER,
    usage_from TEXT, usage_to TEXT, quality_from TEXT, quality_to TEXT,
    doc_type TEXT, doc_id INTEGER, line_id INTEGER,
    remark TEXT, created_by TEXT, created_at TEXT
);
CREATE TABLE document_serial_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL, doc_id INTEGER NOT NULL, line_id INTEGER NOT NULL,
    serial_id INTEGER NOT NULL, direction TEXT NOT NULL,
    created_at TEXT,
    UNIQUE (doc_type, line_id, serial_id)
);
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_no TEXT, org_id INTEGER,
    inventory_org_id INTEGER, deliver_to_location_id INTEGER, status TEXT,
    receipt_date DATETIME
);
CREATE TABLE receipt_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_id INTEGER, line_no TEXT,
    item_id INTEGER, uom_id INTEGER, qty_received REAL,
    qty_rejected REAL DEFAULT 0, serial_no TEXT, lot_no TEXT,
    putaway_location_id INTEGER, hu_no TEXT, hu_type TEXT, status TEXT
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_no TEXT,
    ship_from_location_id INTEGER, status TEXT,
    planned_ship_date DATETIME, actual_ship_date DATETIME
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id INTEGER, item_id INTEGER,
    qty REAL, serial_no TEXT, hu_no TEXT, status TEXT
);
CREATE TABLE transfer_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, transfer_order_no TEXT,
    from_org_id INTEGER, to_org_id INTEGER,
    from_location_id INTEGER, to_location_id INTEGER, status TEXT,
    transfer_date DATETIME
);
CREATE TABLE transfer_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, transfer_order_id INTEGER,
    line_no TEXT, item_id INTEGER, uom_id INTEGER, qty REAL,
    qty_shipped REAL DEFAULT 0, serial_no TEXT, hu_no TEXT, hu_type TEXT,
    status TEXT
);
"""


def build_db(with_hu: bool = True):
    conn = sqlite3.connect(':memory:', isolation_level=None)
    conn.executescript(SCHEMA)
    if with_hu:
        for _table, ddl in _MIGRATION.TABLES:
            conn.executescript(ddl)
        for _table, _name, ddl in _MIGRATION.INDEXES:
            conn.execute(ddl)
        # v217：测试库同样升到 6 态（planned / in_transit）
        _STATUS_MIGRATION._rebuild(conn, _STATUS_MIGRATION.NEW_DDL)
    conn.execute("INSERT INTO orgs (id, code, name) VALUES (1, 'ORG1', '组织一')")
    conn.execute("INSERT INTO orgs (id, code, name) VALUES (2, 'ORG2', '组织二')")
    conn.execute(
        "INSERT INTO locations (id, code, name, org_id) VALUES (7, 'L7', '库位7', 1)")
    conn.execute(
        "INSERT INTO locations (id, code, name, org_id) VALUES (8, 'L8', '库位8', 1)")
    conn.execute(
        "INSERT INTO locations (id, code, name, org_id) VALUES (9, 'L9', '库位9', 2)")
    conn.commit()
    return conn


def add_item(conn, item_id=900, name='物料900'):
    conn.execute('INSERT INTO items (id, name) VALUES (?, ?)', [item_id, name])


def add_serial(conn, serial_no='SN-001', item_id=900, org_id=1,
               location_id=7, status='in_stores', batch_id=None):
    cursor = conn.execute(
        'INSERT INTO serial_numbers (item_id, org_id, serial_no, batch_id, '
        'usage_status, current_location_id) VALUES (?, ?, ?, ?, ?, ?)',
        [item_id, org_id, serial_no, batch_id, status, location_id])
    return cursor.lastrowid


def link_receipt_serial(conn, receipt_id, line_id, serial_id):
    conn.execute(
        'INSERT INTO document_serial_links (doc_type, doc_id, line_id, '
        "serial_id, direction) VALUES ('receipt', ?, ?, ?, 'in')",
        [receipt_id, line_id, serial_id])


def ds(conn):
    return MemDS(conn)


def service(conn):
    from meta.services.handling_unit_service import HandlingUnitService
    return HandlingUnitService(MemDS(conn))
