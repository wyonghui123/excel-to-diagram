# -*- coding: utf-8 -*-
"""序列号过账钩子测试（spec §6.1 / D7）。

收货：qty=1 快捷录号自动建号与 link、qty=3 三号子表登记、
require_on_receipt 数量不符拒绝、qty>1 单值序列号拒绝、未启用物料拒绝行内录号。
发运：qty=1 快捷 link + shipped、qty=2 双 link、require_on_issue 数量不符、
非在库序列号拒绝发运。
"""

import importlib
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.receipt_service import ReceiptError, ReceiptService  # noqa: E402
from meta.services.serial_number_service import SerialNumberService  # noqa: E402
from meta.services.shipment_service import ShipmentError, ShipmentService  # noqa: E402
from meta.tests.receipt_test_doubles import MemDS, seeded_db  # noqa: E402

_MIGRATION = importlib.import_module('meta.migrations.v202__serial_number_model')

_ITEMS_DDL = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    serial_tracked INTEGER DEFAULT 0,
    require_on_receipt INTEGER DEFAULT 0,
    require_on_issue INTEGER DEFAULT 0
);
"""

_INV_TX_DDL = """
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_key TEXT,
    source_line_id INTEGER
);
"""

_HEADER = {
    'document_type_id': 1,
    'receipt_date': '2026-11-01',
    'source_doc_id': 1,
    'inventory_org_id': 2,
    'deliver_to_location_id': 8,
}

_SHIPMENT_SCHEMA = """
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT, org_id INTEGER);
CREATE TABLE items (
    id INTEGER PRIMARY KEY, serial_tracked INTEGER DEFAULT 0,
    require_on_receipt INTEGER DEFAULT 0, require_on_issue INTEGER DEFAULT 0
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, org_id INTEGER, order_date TEXT,
    status TEXT, ship_to_party_id INTEGER, ship_to_address_text TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT, updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_type_id INTEGER,
    item_id INTEGER, uom_id INTEGER, status TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT, updated_at TEXT
);
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_id INTEGER,
    schedule_kind TEXT, plant_location_id INTEGER, promised_date TEXT,
    promised_qty REAL, delivered_qty REAL DEFAULT 0, delivery_id INTEGER,
    status TEXT, updated_at TEXT
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY, code TEXT, level TEXT, line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY, delivery_no TEXT, order_id INTEGER,
    ship_from_location_id INTEGER, ship_to_party_id INTEGER,
    ship_to_address_text TEXT, carrier_name TEXT, tracking_no TEXT,
    waybill_no TEXT, planned_ship_date TEXT, actual_ship_date TEXT,
    actual_arrival_date TEXT, signature_ref TEXT, status TEXT, source TEXT,
    remark TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY, delivery_id INTEGER, schedule_id INTEGER,
    order_line_id INTEGER, item_id INTEGER, uom_id INTEGER, qty REAL,
    lot_no TEXT, serial_no TEXT, status TEXT, created_at TEXT, updated_at TEXT
);
"""


# ---------------- 收货 ----------------

def _receipt_db(tracked=1, require_receipt=1):
    conn = seeded_db()
    conn.executescript(_ITEMS_DDL)
    conn.executescript(_INV_TX_DDL)
    for _table, ddl in _MIGRATION.TABLES:
        conn.executescript(ddl)
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (900, ?, ?, 0)', [tracked, require_receipt])
    conn.commit()
    return conn


def _receipt_svc(conn):
    return ReceiptService(MemDS(conn))


def _serial_row(conn, serial_no):
    return MemDS(conn).query(
        'SELECT * FROM serial_numbers WHERE serial_no = ?', [serial_no])[0]


def _receipt_line_id(conn, receipt_id):
    return MemDS(conn).query(
        'SELECT id FROM receipt_lines WHERE receipt_id = ?', [receipt_id])[0]['id']


def test_qty_one_serial_no_creates_serial_and_link():
    conn = _receipt_db()
    svc = _receipt_svc(conn)
    receipt = svc.create_receipt(
        _HEADER, [{'schedule_id': 1, 'qty_received': 1, 'serial_no': 'SN-Q1'}])
    svc.post(receipt['id'])

    row = _serial_row(conn, 'SN-Q1')
    assert row['usage_status'] == 'in_stores'
    assert row['current_location_id'] == 8
    links = MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE doc_type = ? AND doc_id = ?',
        ['receipt', receipt['id']])
    assert len(links) == 1
    assert links[0]['direction'] == 'in'
    events = MemDS(conn).query(
        'SELECT * FROM serial_transactions WHERE serial_id = ? ORDER BY id',
        [row['id']])
    assert [e['txn_type'] for e in events] == ['create', 'receive']
    assert events[-1]['usage_to'] == 'in_stores'


def test_qty_three_requires_three_pre_registered_serials():
    conn = _receipt_db()
    svc = _receipt_svc(conn)
    receipt = svc.create_receipt(
        _HEADER, [{'schedule_id': 1, 'qty_received': 3}])
    line_id = _receipt_line_id(conn, receipt['id'])
    serial_service = SerialNumberService(MemDS(conn))
    for serial_no in ('SN-A', 'SN-B', 'SN-C'):
        serial = serial_service.create_serial(
            {'item_id': 900, 'org_id': 2, 'serial_no': serial_no})
        MemDS(conn).execute(
            'INSERT INTO document_serial_links (doc_type, doc_id, line_id, '
            'serial_id, direction) VALUES (?, ?, ?, ?, ?)',
            ['receipt', receipt['id'], line_id, serial['id'], 'in'])

    svc.post(receipt['id'])

    for serial_no in ('SN-A', 'SN-B', 'SN-C'):
        assert _serial_row(conn, serial_no)['usage_status'] == 'in_stores'
    assert len(MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE doc_type = ? AND line_id = ?',
        ['receipt', line_id])) == 3


def test_require_on_receipt_rejects_count_mismatch():
    conn = _receipt_db()
    svc = _receipt_svc(conn)
    receipt = svc.create_receipt(
        _HEADER, [{'schedule_id': 1, 'qty_received': 3}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'SERIAL_RECEIPT_COUNT_MISMATCH'
    assert exc.value.field_name == 'serial_no'


def test_qty_more_than_one_rejects_single_serial_no():
    conn = _receipt_db()
    svc = _receipt_svc(conn)
    receipt = svc.create_receipt(
        _HEADER, [{'schedule_id': 1, 'qty_received': 3, 'serial_no': 'SN-X'}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'SERIAL_SINGLE_VALUE_WITH_MULTI_QTY'


def test_untracked_item_rejects_line_serial_no():
    conn = _receipt_db(tracked=0, require_receipt=0)
    svc = _receipt_svc(conn)
    receipt = svc.create_receipt(
        _HEADER, [{'schedule_id': 1, 'qty_received': 1, 'serial_no': 'SN-X'}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'SERIAL_ITEM_NOT_TRACKED'


# ---------------- 发运 ----------------

def _shipment_db(tracked=1, require_issue=1):
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SHIPMENT_SCHEMA)
    for _table, ddl in _MIGRATION.TABLES:
        conn.executescript(ddl)
    conn.execute('INSERT INTO orgs (id, code) VALUES (1, ?)', ['SH'])
    conn.execute('INSERT INTO locations (id, name, org_id) VALUES (7, ?, 1)',
                 ['SHIP-LOC'])
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (900, ?, 0, ?)', [tracked, require_issue])
    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        "ship_to_party_id, ship_to_address_text) VALUES (10, 'SO-0001', 1, "
        "'2026-10-20', 'confirmed', 500, '上海市浦东新区世纪大道 100 号')")
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, status) '
        "VALUES (100, 10, 900, 3, 'open')")
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, plant_location_id, promised_date, promised_qty, '
        "delivered_qty, status) VALUES (1, 10, 100, 'delivery', 7, "
        "'2026-11-05', 100.0, 0.0, 'planned')")
    conn.commit()
    return conn


def _add_serial(conn, serial_no, status='in_stores'):
    cursor = conn.execute(
        'INSERT INTO serial_numbers (item_id, org_id, serial_no, usage_status, '
        'quality_status, current_location_id, source_type, created_at, updated_at) '
        "VALUES (900, 1, ?, ?, 'unrestricted', ?, 'received', "
        "datetime('now'), datetime('now'))",
        [serial_no, status, 7 if status == 'in_stores' else None])
    return cursor.lastrowid


def _prepare_shipment(conn, qty):
    svc = ShipmentService(MemDS(conn))
    result = svc.create_shipment(
        {'order_id': 10}, [{'schedule_id': 1, 'qty': qty}])
    svc.release(result['id'])
    svc.stage(result['id'])
    line_id = MemDS(conn).query(
        'SELECT id FROM shipment_lines WHERE delivery_id = ?',
        [result['id']])[0]['id']
    return svc, result['id'], line_id


def test_qty_one_quick_entry_creates_link_and_ships():
    conn = _shipment_db()
    svc, delivery_id, line_id = _prepare_shipment(conn, 1)
    MemDS(conn).execute(
        'UPDATE shipment_lines SET serial_no = ? WHERE id = ?',
        ['SN-S1', line_id])
    _add_serial(conn, 'SN-S1')

    svc.ship_confirm(delivery_id)

    row = MemDS(conn).query(
        'SELECT * FROM serial_numbers WHERE serial_no = ?', ['SN-S1'])[0]
    assert row['usage_status'] == 'shipped'
    assert row['current_location_id'] is None
    links = MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE doc_type = ? AND line_id = ?',
        ['shipment', line_id])
    assert len(links) == 1
    assert links[0]['direction'] == 'out'
    events = MemDS(conn).query(
        'SELECT * FROM serial_transactions WHERE serial_id = ? ORDER BY id',
        [row['id']])
    assert [e['txn_type'] for e in events] == ['ship']
    assert events[0]['usage_to'] == 'shipped'


def test_qty_two_requires_two_links_and_ships_both():
    conn = _shipment_db()
    svc, delivery_id, line_id = _prepare_shipment(conn, 2)
    for serial_no in ('SN-S2', 'SN-S3'):
        serial_id = _add_serial(conn, serial_no)
        MemDS(conn).execute(
            'INSERT INTO document_serial_links (doc_type, doc_id, line_id, '
            'serial_id, direction) VALUES (?, ?, ?, ?, ?)',
            ['shipment', delivery_id, line_id, serial_id, 'out'])

    svc.ship_confirm(delivery_id)

    for serial_no in ('SN-S2', 'SN-S3'):
        assert MemDS(conn).query(
            'SELECT usage_status FROM serial_numbers WHERE serial_no = ?',
            [serial_no])[0]['usage_status'] == 'shipped'


def test_require_on_issue_auto_creates_serials_when_none_selected():
    """P6b FR-007：仅发货管理模式未录号时按数量自动建档（替代 P6a 的拒绝口径）。"""
    conn = _shipment_db()
    svc, delivery_id, line_id = _prepare_shipment(conn, 2)

    svc.ship_confirm(delivery_id)

    rows = MemDS(conn).query(
        'SELECT * FROM serial_numbers ORDER BY serial_no')
    assert len(rows) == 2
    assert {row['usage_status'] for row in rows} == {'shipped'}
    assert {row['source_type'] for row in rows} == {'issue_created'}
    links = MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE doc_type = ? AND line_id = ?',
        ['shipment', line_id])
    assert len(links) == 2


def test_defined_serial_cannot_be_shipped():
    conn = _shipment_db()
    svc, delivery_id, line_id = _prepare_shipment(conn, 1)
    serial_id = _add_serial(conn, 'SN-DEF', status='defined')
    MemDS(conn).execute(
        'INSERT INTO document_serial_links (doc_type, doc_id, line_id, '
        'serial_id, direction) VALUES (?, ?, ?, ?, ?)',
        ['shipment', delivery_id, line_id, serial_id, 'out'])

    with pytest.raises(ShipmentError) as exc:
        svc.ship_confirm(delivery_id)
    assert exc.value.rule == 'SERIAL_NOT_AVAILABLE'
    assert MemDS(conn).query(
        'SELECT usage_status FROM serial_numbers WHERE serial_no = ?',
        ['SN-DEF'])[0]['usage_status'] == 'defined'
