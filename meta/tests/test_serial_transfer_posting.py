# -*- coding: utf-8 -*-
"""P6b 调拨收发序列号过账测试（spec FR-001 / FR-002）。

覆盖：发货号数 / 组织 / 状态校验、transfer_out 事件、TO 收货 transfer_in 与组织迁移。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v202__serial_number_model as v202
from meta.services.serial_number_service import (
    SerialNumberError,
    SerialNumberService,
)
from meta.services.transfer_order_service import TransferOrderError
from meta.tests import transfer_order_test_doubles as d

_INV_TX_SCHEMA = """
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_key TEXT,
    source_line_id INTEGER
);
"""


def _install_serial(conn):
    v202._do_tables(conn)
    v202._do_indexes(conn)
    v202._do_item_columns(conn)
    conn.execute('ALTER TABLE transfer_order_lines ADD COLUMN serial_no TEXT')
    conn.executescript(_INV_TX_SCHEMA)
    conn.execute('UPDATE items SET serial_tracked = 1 WHERE id = 900')
    conn.commit()


def _add_serial(conn, status='in_stores', org_id=2, location_id=9):
    service = SerialNumberService(d.MemDS(conn))
    serial = service.create_serial({
        'item_id': 900, 'org_id': org_id, 'serial_no': 'SN-1',
        'source_type': 'opening', 'current_location_id': location_id})
    conn.execute(
        'UPDATE serial_numbers SET usage_status = ?, current_location_id = ? '
        'WHERE id = ?', [status, location_id, serial['id']])
    conn.execute(
        'UPDATE transfer_order_lines SET serial_no = ? WHERE id = 100',
        ['SN-1'])
    conn.commit()
    return serial['id']


def _setup(status='in_stores'):
    conn = d.seeded_db(line_qtys=(1.0,))
    _install_serial(conn)
    serial_id = _add_serial(conn, status=status)
    d.release_transfer_order(conn, 1)
    return conn, serial_id


def _serial(conn, serial_id):
    return d.MemDS(conn).query(
        'SELECT * FROM serial_numbers WHERE id = ?', [serial_id])[0]


def _txns(conn, serial_id):
    return d.MemDS(conn).query(
        'SELECT * FROM serial_transactions WHERE serial_id = ? ORDER BY id',
        [serial_id])


def test_transfer_ship_registers_transfer_out(monkeypatch):
    conn, serial_id = _setup()
    service = d.to_service(conn)
    monkeypatch.setattr(service, '_post_ship_inventory',
                        lambda *args, **kwargs: None)

    result = service.ship(1, [{'line_id': 100, 'qty': 1}])

    assert result['id'] == 1
    serial = _serial(conn, serial_id)
    assert serial['usage_status'] == 'in_transit'
    assert serial['current_location_id'] is None
    events = [e for e in _txns(conn, serial_id)
              if e['txn_type'] == 'transfer_out']
    assert len(events) == 1
    assert events[0]['doc_type'] == 'transfer_order'
    assert events[0]['usage_to'] == 'in_transit'
    links = d.MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE doc_type = ?', ['transfer_order'])
    assert len(links) == 1
    assert links[0]['direction'] == 'out'


def test_transfer_ship_requires_serial_count(monkeypatch):
    conn, _serial_id = _setup()
    conn.execute('UPDATE transfer_order_lines SET serial_no = NULL WHERE id = 100')
    conn.commit()
    service = d.to_service(conn)
    monkeypatch.setattr(service, '_post_ship_inventory',
                        lambda *args, **kwargs: None)

    with pytest.raises(TransferOrderError) as exc:
        service.ship(1, [{'line_id': 100, 'qty': 1}])
    assert exc.value.rule == 'SERIAL_TRANSFER_COUNT_MISMATCH'
    shipped = d.MemDS(conn).query(
        'SELECT qty_shipped FROM transfer_order_lines WHERE id = 100')[0]
    assert shipped['qty_shipped'] == 0


def test_transfer_ship_rejects_serial_not_in_stores(monkeypatch):
    conn, _serial_id = _setup(status='defined')
    service = d.to_service(conn)
    monkeypatch.setattr(service, '_post_ship_inventory',
                        lambda *args, **kwargs: None)

    with pytest.raises(TransferOrderError) as exc:
        service.ship(1, [{'line_id': 100, 'qty': 1}])
    assert exc.value.rule == 'SERIAL_NOT_AVAILABLE'


def test_transfer_receipt_moves_in_transit_to_target_org(monkeypatch):
    conn, serial_id = _setup()
    service = d.to_service(conn)
    monkeypatch.setattr(service, '_post_ship_inventory',
                        lambda *args, **kwargs: None)
    service.ship(1, [{'line_id': 100, 'qty': 1}])

    conn.execute(
        'INSERT INTO receipts (id, receipt_no, receipt_date, source_doc_type, '
        'source_doc_id, org_id, inventory_org_id, deliver_to_location_id, '
        "status) VALUES (1, 'RCV-001', '2026-11-04', 'transfer_order', 1, 3, 3, 7, 'draft')")
    conn.execute(
        'INSERT INTO receipt_lines (id, receipt_id, line_no, source_line_id, '
        'item_id, qty_received, qty_rejected, status) '
        "VALUES (200, 1, '10', 100, 900, 1, 0, 'open')")
    conn.commit()

    serial_service = SerialNumberService(d.MemDS(conn))
    serial_service.precheck_transfer_receipt(1, 1)
    result = serial_service.register_transfer_receipt(1, 1)

    assert result['registered'] == 1
    serial = _serial(conn, serial_id)
    assert serial['org_id'] == 3
    assert serial['usage_status'] == 'in_stores'
    assert serial['current_location_id'] == 7
    events = [e for e in _txns(conn, serial_id)
              if e['txn_type'] == 'transfer_in']
    assert len(events) == 1
    assert events[0]['org_from_id'] == 2
    assert events[0]['org_to_id'] == 3


def test_transfer_receipt_requires_in_transit_serial():
    conn, serial_id = _setup(status='in_stores')
    conn.execute(
        'INSERT INTO receipts (id, receipt_no, receipt_date, source_doc_type, '
        'source_doc_id, org_id, inventory_org_id, deliver_to_location_id, '
        "status) VALUES (1, 'RCV-001', '2026-11-04', 'transfer_order', 1, 3, 3, 7, 'draft')")
    conn.execute(
        'INSERT INTO receipt_lines (id, receipt_id, line_no, source_line_id, '
        'item_id, qty_received, qty_rejected, status) '
        "VALUES (200, 1, '10', 100, 900, 1, 0, 'open')")
    conn.execute(
        'INSERT INTO document_serial_links (doc_type, doc_id, line_id, '
        'serial_id, direction) VALUES (?, 1, 100, ?, ?)',
        ['transfer_order', serial_id, 'out'])
    conn.commit()

    with pytest.raises(SerialNumberError) as exc:
        SerialNumberService(d.MemDS(conn)).precheck_transfer_receipt(1, 1)
    assert exc.value.rule == 'SERIAL_NOT_AVAILABLE'
