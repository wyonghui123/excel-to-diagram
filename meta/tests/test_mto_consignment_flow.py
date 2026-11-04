# -*- coding: utf-8 -*-
"""INV-2 S4/S5：MTO 预留闭环 + 供应商寄售收货/消耗转移。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.inventory_reservation_service import (
    InventoryReservationService,
)
from meta.services.stock_segment_service import (
    DEFAULT_SEGMENT,
    SEGMENT_SUPPLIER_CONSIGNMENT,
    StockSegmentService,
)
from meta.tests.inventory_test_doubles import (
    BATCH_ID,
    ITEM_ID,
    LOCATION_ID,
    ORG_ID,
    MemDS,
    build_db,
    seed,
)

UOM_ID = 3
SO_LINE_ID = 501
OWNER_ID = 88
PROJECT_ID = 301
TASK_ID = 201


def _env():
    conn = seed(build_db())
    conn.execute('CREATE TABLE sales_orders '
                 '(id INTEGER PRIMARY KEY, status TEXT, org_id INTEGER)')
    conn.execute('CREATE TABLE sales_order_lines '
                 '(id INTEGER PRIMARY KEY, order_id INTEGER, item_id INTEGER, '
                 'uom_id INTEGER, qty REAL, status TEXT, '
                 'plant_location_id INTEGER, project_id INTEGER, '
                 'project_task_id INTEGER)')
    conn.execute("INSERT INTO sales_orders (id, status, org_id) "
                 "VALUES (1, 'open', ?)", [ORG_ID])
    conn.execute("INSERT INTO sales_order_lines (id, order_id, item_id, "
                 "uom_id, qty, status, plant_location_id, project_id, "
                 "project_task_id) VALUES (?, 1, ?, ?, 10, 'open', ?, NULL, 0)",
                 [SO_LINE_ID, ITEM_ID, UOM_ID, LOCATION_ID])
    for code, name, direction in (
            ('SEG_TRANSFER_OUT', '段转出', 'out'),
            ('SEG_TRANSFER_IN', '段转入', 'in')):
        conn.execute(
            'INSERT OR IGNORE INTO inventory_transaction_types '
            '(code, name, category, direction, affects_on_hand, status, '
            "sort_order, created_at) VALUES (?, ?, 'transfer', ?, 1, "
            "'active', 9, datetime('now'))", [code, name, direction])
    conn.commit()
    return conn


def _post(conn, qty, segment, direction='in', event='evt', line_id=1):
    entry = {
        'transaction_type': 'RCV_PO' if direction == 'in' else 'ISSUE_TO_SHIP',
        'transaction_date': '2026-11-04',
        'org_id': ORG_ID,
        'location_id': LOCATION_ID,
        'item_id': ITEM_ID,
        'uom_id': UOM_ID,
        'qty': qty,
        'batch_id': BATCH_ID,
        'stock_status': 'unrestricted',
        'source_line_id': line_id,
    }
    entry.update(segment)
    return InventoryPostingService(MemDS(conn)).post([entry], {
        'source_doc_type': 'test',
        'source_doc_id': 1,
        'source_event_key': event,
    })


def test_mto_soft_reservation_to_shipment_closure():
    conn = _env()
    reservations = InventoryReservationService(MemDS(conn))
    created = reservations.sync_sales_order_line(SO_LINE_ID)
    assert created['reservation']['stock_segment_type'] == 'owned'
    assert created['reservation']['peg_type'] == 'soft'

    query = {'org_id': ORG_ID, 'item_id': ITEM_ID}
    assert reservations.available_on_hand(query)['available_on_hand'] \
        == pytest.approx(-10)

    _post(conn, 10, DEFAULT_SEGMENT, event='mto-receipt')
    assert reservations.available_on_hand(query)['available_on_hand'] \
        == pytest.approx(0)

    fulfilled = reservations.fulfill_by_demand('sales_order_line',
                                               SO_LINE_ID, 10)
    assert fulfilled['fulfilled'] == pytest.approx(10)
    row = conn.execute(
        'SELECT status FROM inventory_reservations WHERE id = ?',
        [created['reservation']['id']]).fetchone()
    assert row[0] == 'fulfilled'
    assert reservations.available_on_hand(query)['available_on_hand'] \
        == pytest.approx(10)

    _post(conn, 10, DEFAULT_SEGMENT, direction='out', event='mto-ship')
    assert reservations.available_on_hand(query)['on_hand'] \
        == pytest.approx(0)


def test_consignment_receipt_and_consume_transfer():
    conn = _env()
    conn.execute('UPDATE items SET consignment_enabled = 1 WHERE id = ?',
                 [ITEM_ID])
    conn.commit()
    consignment = {'stock_segment_type': SEGMENT_SUPPLIER_CONSIGNMENT,
                   'project_id': 0, 'project_task_id': 0,
                   'sales_order_line_id': 0, 'owner_party_id': OWNER_ID}
    _post(conn, 6, consignment, event='consign-receipt')

    segments = StockSegmentService(MemDS(conn))
    result = segments.consume_consignment({
        'from_segment': consignment,
        'to_segment': dict(DEFAULT_SEGMENT),
        'org_id': ORG_ID,
        'location_id': LOCATION_ID,
        'item_id': ITEM_ID,
        'uom_id': UOM_ID,
        'batch_id': BATCH_ID,
        'qty': 4,
        'source_event_key': 'consign-consume-1',
        'source_doc_type': 'work_order',
        'source_doc_id': 1,
    })
    assert result['result']['created'] == 2

    posting = InventoryPostingService(MemDS(conn))
    assert posting.on_hand(ORG_ID, LOCATION_ID, ITEM_ID, BATCH_ID,
                           segment=consignment) == pytest.approx(2)
    assert posting.on_hand(ORG_ID, LOCATION_ID, ITEM_ID, BATCH_ID,
                           segment=DEFAULT_SEGMENT) == pytest.approx(4)

    rows = conn.execute(
        "SELECT remark FROM inventory_transactions WHERE source_event_key = ? "
        "ORDER BY id", ['consign-consume-1']).fetchall()
    assert len(rows) == 2
    assert all('寄售消耗' in (row[0] or '') for row in rows)
