# -*- coding: utf-8 -*-
"""SerialNumberService 单元测试（spec §5 / §3.5）。

覆盖：建档唯一键 / 初始状态 / 行级录号校验 / 状态白名单 / 反冲 / 按号追溯。
"""

import importlib
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.serial_number_service import (  # noqa: E402
    SerialNumberError,
    SerialNumberService,
)
from meta.tests.receipt_test_doubles import MemDS  # noqa: E402

_MIGRATION = importlib.import_module('meta.migrations.v202__serial_number_model')

_SCHEMA = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    serial_tracked INTEGER DEFAULT 0,
    require_on_receipt INTEGER DEFAULT 0,
    require_on_issue INTEGER DEFAULT 0
);
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT, org_id INTEGER);
CREATE TABLE batches (
    id INTEGER PRIMARY KEY, batch_no TEXT, item_id INTEGER, org_id INTEGER
);
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_no TEXT, org_id INTEGER,
    inventory_org_id INTEGER, deliver_to_location_id INTEGER,
    actual_arrival_date TEXT, status TEXT
);
CREATE TABLE receipt_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_id INTEGER, item_id INTEGER,
    qty_received REAL, qty_rejected REAL DEFAULT 0, serial_no TEXT,
    lot_no TEXT, putaway_location_id INTEGER, status TEXT
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_no TEXT,
    ship_from_location_id INTEGER, actual_ship_date TEXT, status TEXT
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id INTEGER, item_id INTEGER,
    qty REAL, serial_no TEXT, status TEXT
);
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source_event_key TEXT,
    source_line_id INTEGER
);
"""


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    for _table, ddl in _MIGRATION.TABLES:
        conn.executescript(ddl)
    conn.execute('INSERT INTO orgs (id, code) VALUES (1, ?)', ['ORG1'])
    conn.execute(
        'INSERT INTO locations (id, name, org_id) VALUES (7, ?, 1)', ['LOC7'])
    conn.commit()
    return conn


def _add_item(conn, item_id=900, tracked=1, receipt=0, issue=0):
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (?, ?, ?, ?)',
        [item_id, tracked, receipt, issue])


def _svc(conn):
    return SerialNumberService(MemDS(conn))


def _find(conn, serial_no):
    return MemDS(conn).query(
        'SELECT * FROM serial_numbers WHERE serial_no = ?', [serial_no])


def _txns(conn, serial_id):
    return MemDS(conn).query(
        'SELECT * FROM serial_transactions WHERE serial_id = ? ORDER BY id',
        [serial_id])


# ---------------- 建档 ----------------

def test_create_serial_writes_create_event():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    result = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})

    row = _find(conn, 'SN-001')[0]
    assert row['usage_status'] == 'defined'
    assert row['quality_status'] == 'unrestricted'
    assert row['source_type'] == 'received'
    events = _txns(conn, result['id'])
    assert [e['txn_type'] for e in events] == ['create']
    assert events[0]['usage_to'] == 'defined'


def test_create_serial_rejects_duplicate_key():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    service.create_serial({'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    with pytest.raises(SerialNumberError) as exc:
        service.create_serial(
            {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    assert exc.value.rule == 'SERIAL_DUPLICATE'


def test_create_serial_rejects_untracked_item():
    conn = _db()
    _add_item(conn, tracked=0)
    service = _svc(conn)
    with pytest.raises(SerialNumberError) as exc:
        service.create_serial(
            {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    assert exc.value.rule == 'SERIAL_ITEM_NOT_TRACKED'


# ---------------- 行级录号校验 ----------------

def test_validate_line_serials_requires_exact_count():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    service.create_serial({'item_id': 900, 'org_id': 1, 'serial_no': 'SN-1'})
    service.create_serial({'item_id': 900, 'org_id': 1, 'serial_no': 'SN-2'})
    with pytest.raises(SerialNumberError) as exc:
        service.validate_line_serials(900, 1, 3, ['SN-1', 'SN-2'], 'out')
    assert exc.value.rule == 'SERIAL_COUNT_MISMATCH'


def test_validate_line_serials_rejects_duplicates_in_line():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    service.create_serial({'item_id': 900, 'org_id': 1, 'serial_no': 'SN-1'})
    with pytest.raises(SerialNumberError) as exc:
        service.validate_line_serials(900, 1, 2, ['SN-1', 'SN-1'], 'in')
    assert exc.value.rule == 'SERIAL_DUPLICATE_IN_LINE'


def test_validate_line_serials_out_requires_in_store():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    service.create_serial({'item_id': 900, 'org_id': 1, 'serial_no': 'SN-1'})
    with pytest.raises(SerialNumberError) as exc:
        service.validate_line_serials(900, 1, 1, ['SN-1'], 'out')
    assert exc.value.rule == 'SERIAL_NOT_AVAILABLE'


def test_validate_line_serials_untracked_item_must_be_empty():
    conn = _db()
    _add_item(conn, tracked=0)
    service = _svc(conn)
    with pytest.raises(SerialNumberError) as exc:
        service.validate_line_serials(900, 1, 1, ['SN-1'], 'in')
    assert exc.value.rule == 'SERIAL_ITEM_NOT_TRACKED'


# ---------------- 状态白名单 ----------------

def test_change_status_follows_whitelist():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    serial = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    service.change_status(serial['id'], 'in_stores', '收货')
    service.change_status(serial['id'], 'issued', '领用')
    result = service.change_status(serial['id'], 'shipped', '发运')
    assert result['to_status'] == 'shipped'
    assert _find(conn, 'SN-001')[0]['shipped_at']


def test_change_status_rejects_illegal_jump():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    serial = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    with pytest.raises(SerialNumberError) as exc:
        service.change_status(serial['id'], 'shipped', '跳步')
    assert exc.value.rule == 'SERIAL_STATUS_TRANSITION_INVALID'


def test_scrapped_is_terminal():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    serial = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    service.change_status(serial['id'], 'scrapped', '报废')
    with pytest.raises(SerialNumberError) as exc:
        service.change_status(serial['id'], 'in_stores', '复活')
    assert exc.value.rule == 'SERIAL_STATUS_TRANSITION_INVALID'
    assert _find(conn, 'SN-001')[0]['scrapped_at']


# ---------------- 反冲 / 追溯 ----------------

def test_reverse_serial_event_rolls_back_status_without_deleting_link():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    serial = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    service.change_status(serial['id'], 'in_stores', '收货')
    conn.execute(
        'INSERT INTO inventory_transactions (id, source_event_key, source_line_id) '
        'VALUES (42, ?, 1)', ['receipt:1:post'])
    MemDS(conn).execute(
        'INSERT INTO serial_transactions (serial_id, inventory_transaction_id, '
        'txn_type, txn_date, location_to_id, usage_from, usage_to, doc_type, '
        'doc_id, line_id) VALUES (?, 42, ?, ?, 7, ?, ?, ?, 1, 1)',
        [serial['id'], 'receive', '2026-11-01 10:00:00', 'defined', 'in_stores',
         'receipt'])
    MemDS(conn).execute(
        'INSERT INTO document_serial_links (doc_type, doc_id, line_id, serial_id, '
        'direction) VALUES (?, 1, 1, ?, ?)',
        ['receipt', serial['id'], 'in'])

    result = service.reverse_serial_event(42)
    assert result['reversed'] == 1
    assert _find(conn, 'SN-001')[0]['usage_status'] == 'defined'
    assert MemDS(conn).query(
        'SELECT COUNT(*) AS cnt FROM document_serial_links')[0]['cnt'] == 1
    adjust = [e for e in _txns(conn, serial['id']) if e['txn_type'] == 'adjust']
    assert len(adjust) == 1
    assert adjust[0]['usage_to'] == 'defined'


def test_trace_serial_returns_timeline_and_documents_across_orgs():
    conn = _db()
    _add_item(conn)
    conn.execute('INSERT INTO orgs (id, code) VALUES (2, ?)', ['ORG2'])
    _svc(conn).create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    _svc(conn).create_serial(
        {'item_id': 900, 'org_id': 2, 'serial_no': 'SN-001'})

    result = _svc(conn).trace_serial('SN-001')
    assert result['serial_no'] == 'SN-001'
    assert {m['org_id'] for m in result['matches']} == {1, 2}
    assert all(len(m['transactions']) == 1 for m in result['matches'])

    scoped = _svc(conn).trace_serial('SN-001', org_id=1)
    assert [m['org_id'] for m in scoped['matches']] == [1]


# ---------------- P6b：质量状态 / 退货 / 仅发货建档 ----------------

def test_change_quality_status_only_touches_quality_axis():
    conn = _db()
    _add_item(conn)
    serial = _svc(conn).create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})

    result = _svc(conn).change_quality_status(
        serial['id'], 'inspection', '质检中')
    row = _find(conn, 'SN-001')[0]
    assert result['to'] == 'inspection'
    assert row['quality_status'] == 'inspection'
    assert row['usage_status'] == 'defined'

    events = [e for e in _txns(conn, serial['id'])
              if e['txn_type'] == 'status_change']
    assert events[-1]['quality_from'] == 'unrestricted'
    assert events[-1]['quality_to'] == 'inspection'


def test_change_quality_status_rejects_unknown_value_and_scrapped():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    serial = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})

    with pytest.raises(SerialNumberError) as exc:
        service.change_quality_status(serial['id'], 'frozen')
    assert exc.value.rule == 'SERIAL_QUALITY_STATUS_INVALID'

    service.change_status(serial['id'], 'scrapped', '报废')
    with pytest.raises(SerialNumberError) as exc:
        service.change_quality_status(serial['id'], 'unrestricted')
    assert exc.value.rule == 'SERIAL_STATUS_TRANSITION_INVALID'


def test_return_serial_moves_issued_to_returned_then_in_stores():
    conn = _db()
    _add_item(conn)
    service = _svc(conn)
    serial = service.create_serial(
        {'item_id': 900, 'org_id': 1, 'serial_no': 'SN-001'})
    service.change_status(serial['id'], 'in_stores', '入库')
    service.change_status(serial['id'], 'issued', '领用')

    returned = service.return_serial(serial['id'], reason='客户退回')
    assert returned['to_status'] == 'returned'
    assert _find(conn, 'SN-001')[0]['usage_status'] == 'returned'

    stored = service.return_serial(
        serial['id'], location_id=7, to_stores=True, reason='退回入库')
    assert stored['to_status'] == 'in_stores'
    assert _find(conn, 'SN-001')[0]['current_location_id'] == 7
    assert [e['txn_type'] for e in _txns(conn, serial['id'])][-2:] == [
        'return', 'return']


def test_issue_created_shipment_creates_serials_on_register():
    conn = _db()
    _add_item(conn, tracked=1, receipt=0, issue=1)
    conn.execute(
        'INSERT INTO shipments (id, delivery_no, ship_from_location_id, '
        "actual_ship_date, status) VALUES (1, ?, 7, ?, 'draft')",
        ['DN-001', '2026-11-04'])
    conn.execute(
        'INSERT INTO shipment_lines (id, delivery_id, item_id, qty, serial_no, '
        "status) VALUES (10, 1, 900, 2, NULL, 'open')")
    service = _svc(conn)

    service.precheck_shipment(1)  # 仅发货管理模式允许未录号
    result = service.register_shipment(1)

    rows = MemDS(conn).query(
        'SELECT * FROM serial_numbers ORDER BY serial_no')
    assert result['registered'] == 2
    assert len(rows) == 2
    assert {row['usage_status'] for row in rows} == {'shipped'}
    assert {row['source_type'] for row in rows} == {'issue_created'}
    assert MemDS(conn).query(
        'SELECT COUNT(*) AS cnt FROM document_serial_links')[0]['cnt'] == 2
