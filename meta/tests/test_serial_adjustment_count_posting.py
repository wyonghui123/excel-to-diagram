# -*- coding: utf-8 -*-
"""P6b 调整单 / 盘点单序列号过账测试（spec FR-002 ~ FR-006）。

覆盖：状态转移切质量轴、减少 / 报废终态、增加建档、盘盈建档、盘亏报废。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v202__serial_number_model as v202
from meta.services.inventory_guard_service import InventoryError
from meta.services.serial_number_service import (
    SerialNumberError,
    SerialNumberService,
)
from meta.tests import inventory_adjustment_doubles as adj
from meta.tests import inventory_test_doubles as inv

_STOCK_TABLES = ('inventory_adjustment_lines', 'inventory_count_lines')


def _rows(conn, sql, params=None):
    return inv.MemDS(conn).query(sql, params or [])


def _install(conn):
    v202._do_tables(conn)
    v202._do_indexes(conn)
    v202._do_item_columns(conn)
    for table in _STOCK_TABLES:
        if 'serial_no' not in inv._columns(conn, table):
            conn.execute('ALTER TABLE %s ADD COLUMN serial_no TEXT' % table)
    conn.execute('UPDATE items SET serial_tracked = 1 WHERE id = ?',
                 [inv.ITEM_ID])
    conn.commit()
    return conn


def _add_serial(conn, serial_no, quality='unrestricted', usage='in_stores'):
    service = SerialNumberService(inv.MemDS(conn))
    serial = service.create_serial({
        'item_id': inv.ITEM_ID, 'org_id': inv.ORG_ID,
        'serial_no': serial_no, 'source_type': 'opening',
        'current_location_id': inv.LOCATION_ID,
        'quality_status': quality})
    conn.execute(
        'UPDATE serial_numbers SET usage_status = ? WHERE id = ?',
        [usage, serial['id']])
    conn.commit()
    return serial['id']


def _set_line_serial(conn, table, line_id, serial_no):
    conn.execute('UPDATE %s SET serial_no = ? WHERE id = ?' % table,
                 [serial_no, line_id])
    conn.commit()


def _serial(conn, serial_no):
    rows = _rows(conn, 'SELECT * FROM serial_numbers WHERE serial_no = ?',
                 [serial_no])
    return rows[0] if rows else None


def _create(conn, adj_type, qty=1, lines=None):
    service = adj.adjustment_service(conn)
    header = service.prepare_create({
        'adjustment_type': adj_type, 'org_id': inv.ORG_ID,
        'location_id': inv.LOCATION_ID, 'posting_date': adj.DEFAULT_DATE,
    })
    header_id = adj.insert_adjustment(conn, header)
    specs = lines or [{}]
    line_ids = []
    for spec in specs:
        spec = dict(spec)
        spec.setdefault('qty', qty)
        if adj_type in ('qty_increase', 'opening'):
            spec.setdefault('to_stock_status', 'unrestricted')
        elif adj_type in ('qty_decrease', 'scrap'):
            spec.setdefault('from_stock_status', 'unrestricted')
        line_ids.append(adj.add_adjustment_line(conn, header_id, **spec))
    return header_id, line_ids, service


# ---------------- 调整单 ----------------

def test_status_transfer_changes_quality_only():
    conn = _install(adj.build_adjustment_db())
    adj.post_balance(conn, 1)
    serial_id = _add_serial(conn, 'SN-1')
    header_id, line_ids, service = _create(
        conn, 'status_transfer', 1,
        [{'from_stock_status': 'unrestricted',
          'to_stock_status': 'inspection'}])
    _set_line_serial(conn, 'inventory_adjustment_lines', line_ids[0], 'SN-1')

    service.release(header_id)
    service.post(header_id)

    serial = _rows(conn, 'SELECT * FROM serial_numbers WHERE id = ?',
                   [serial_id])[0]
    assert serial['quality_status'] == 'inspection'
    assert serial['usage_status'] == 'in_stores'
    events = _rows(conn,
                   'SELECT * FROM serial_transactions WHERE serial_id = ? '
                   'ORDER BY id DESC', [serial_id])
    assert events[0]['txn_type'] == 'status_change'
    assert events[0]['quality_from'] == 'unrestricted'
    assert events[0]['quality_to'] == 'inspection'


def test_qty_decrease_scraps_serial():
    conn = _install(adj.build_adjustment_db())
    adj.post_balance(conn, 1)
    serial_id = _add_serial(conn, 'SN-1')
    header_id, line_ids, service = _create(conn, 'qty_decrease', 1)
    _set_line_serial(conn, 'inventory_adjustment_lines', line_ids[0], 'SN-1')

    service.release(header_id)
    service.post(header_id)

    serial = _rows(conn, 'SELECT * FROM serial_numbers WHERE id = ?',
                   [serial_id])[0]
    assert serial['usage_status'] == 'scrapped'
    assert serial['scrapped_at']
    events = _rows(conn,
                   'SELECT * FROM serial_transactions WHERE serial_id = ? '
                   'ORDER BY id DESC', [serial_id])
    assert events[0]['txn_type'] == 'scrap'
    assert events[0]['usage_to'] == 'scrapped'


def test_qty_increase_creates_missing_serial():
    conn = _install(adj.build_adjustment_db())
    header_id, line_ids, service = _create(conn, 'qty_increase', 1)
    _set_line_serial(conn, 'inventory_adjustment_lines', line_ids[0], 'NEW-1')

    service.release(header_id)
    service.post(header_id)

    serial = _serial(conn, 'NEW-1')
    assert serial['usage_status'] == 'in_stores'
    assert serial['source_type'] == 'opening'
    events = _rows(conn,
                   'SELECT * FROM serial_transactions WHERE serial_id = ? '
                   'ORDER BY id', [serial['id']])
    assert [event['txn_type'] for event in events] == ['create', 'adjust']
    links = _rows(conn, 'SELECT * FROM document_serial_links WHERE line_id = ?',
                  [line_ids[0]])
    assert len(links) == 1 and links[0]['direction'] == 'in'


def test_qty_decrease_requires_serial_selection():
    conn = _install(adj.build_adjustment_db())
    adj.post_balance(conn, 1)
    header_id, _line_ids, service = _create(conn, 'qty_decrease', 1)
    service.release(header_id)

    with pytest.raises(InventoryError) as exc:
        service.post(header_id)
    assert '序列号数量必须等于单据数量' in str(exc.value)


def test_scrapped_serial_cannot_change_quality():
    conn = _install(adj.build_adjustment_db())
    serial_id = _add_serial(conn, 'SN-9', usage='scrapped')

    with pytest.raises(SerialNumberError) as exc:
        SerialNumberService(inv.MemDS(conn)).change_quality_status(
            serial_id, 'blocked')
    assert exc.value.rule == 'SERIAL_STATUS_TRANSITION_INVALID'


# ---------------- 盘点单 ----------------

def _count_with_variance(conn, counted, serial_no):
    adj.post_balance(conn, 1)
    service = adj.count_service(conn)
    data = service.prepare_create({
        'org_id': inv.ORG_ID, 'location_id': inv.LOCATION_ID,
        'tolerance_qty_abs': 5})
    count_id = adj.insert_count(conn, data)
    service.start(count_id)
    line = _rows(conn, 'SELECT * FROM inventory_count_lines WHERE count_id = ?',
                 [count_id])[0]
    conn.execute(
        'UPDATE inventory_count_lines SET counted_qty = ?, serial_no = ? '
        'WHERE id = ?', [counted, serial_no, line['id']])
    conn.commit()
    service.submit(count_id)
    return count_id, line['id'], service


def test_count_surplus_creates_and_receives_serial():
    conn = _install(adj.build_adjustment_db())
    count_id, line_id, service = _count_with_variance(conn, 2, 'CNT-NEW')

    result = service.post(count_id)

    assert result['status'] == 'posted'
    serial = _serial(conn, 'CNT-NEW')
    assert serial['usage_status'] == 'in_stores'
    assert serial['source_type'] == 'opening'
    events = _rows(conn,
                   'SELECT * FROM serial_transactions WHERE serial_id = ? '
                   'ORDER BY id', [serial['id']])
    assert [event['txn_type'] for event in events] == ['create', 'adjust']
    links = _rows(conn, 'SELECT * FROM document_serial_links WHERE line_id = ?',
                  [line_id])
    assert len(links) == 1 and links[0]['direction'] == 'in'


def test_count_shortage_scraps_serial():
    conn = _install(adj.build_adjustment_db())
    serial_id = _add_serial(conn, 'SN-1')
    count_id, line_id, service = _count_with_variance(conn, 0, 'SN-1')

    service.post(count_id)

    serial = _rows(conn, 'SELECT * FROM serial_numbers WHERE id = ?',
                   [serial_id])[0]
    assert serial['usage_status'] == 'scrapped'
    events = _rows(conn,
                   'SELECT * FROM serial_transactions WHERE serial_id = ? '
                   'ORDER BY id DESC', [serial_id])
    assert events[0]['txn_type'] == 'scrap'
    assert events[0]['doc_type'] == 'inventory_count'
    links = _rows(conn, 'SELECT * FROM document_serial_links WHERE line_id = ?',
                  [line_id])
    assert len(links) == 1 and links[0]['direction'] == 'out'
