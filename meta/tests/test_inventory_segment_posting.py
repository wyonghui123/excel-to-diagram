# -*- coding: utf-8 -*-
"""INV-2 S1：段化过账 / 段转移 / 余额投影回归。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.migrations.v201__inventory_foundation import BAL_TABLE, TX_TABLE
from meta.services.inventory_guard_service import InventoryError
from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.inventory_reservation_service import (
    InventoryReservationService,
)
from meta.services.stock_segment_service import (
    DEFAULT_SEGMENT,
    INV_CONSIGNMENT_OWNER_REQUIRED,
    SEGMENT_CUSTOMER_OWNED,
    SEGMENT_PROJECT_TASK,
    SEGMENT_SALES_ORDER_LINE,
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

PROJECT_ID = 301
TASK_ID = 201
SO_LINE_ID = 501
OWNER_ID = 88


def _env():
    conn = seed(build_db())
    conn.execute(
        'CREATE TABLE IF NOT EXISTS project_tasks ('
        'id INTEGER PRIMARY KEY, project_id INTEGER, parent_task_id INTEGER, '
        'task_no TEXT, name TEXT, task_type TEXT, status TEXT)')
    conn.execute(
        'INSERT OR IGNORE INTO project_tasks '
        '(id, project_id, parent_task_id, task_no, name, task_type, status) '
        "VALUES (?, ?, NULL, 'T201', '任务201', 'activity', 'active')",
        [TASK_ID, PROJECT_ID])
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


def _post(conn, qty, direction='in', segment=None, line_id=1,
          event='evt-1'):
    service = InventoryPostingService(MemDS(conn))
    entry = {
        'transaction_type': 'RCV_PO' if direction == 'in' else 'ISSUE_TO_SHIP',
        'transaction_date': '2026-11-04',
        'org_id': ORG_ID,
        'location_id': LOCATION_ID,
        'item_id': ITEM_ID,
        'uom_id': 3,
        'qty': qty,
        'batch_id': BATCH_ID,
        'stock_status': 'unrestricted',
        'source_line_id': line_id,
    }
    entry.update(segment or DEFAULT_SEGMENT)
    return service.post([entry], {
        'source_doc_type': 'test',
        'source_doc_id': 1,
        'source_event_key': event,
        'transaction_date': '2026-11-04',
    })


def _on_hand(conn, segment):
    return InventoryPostingService(MemDS(conn)).on_hand(
        ORG_ID, LOCATION_ID, ITEM_ID, BATCH_ID, segment=segment)


def test_project_task_segment_post_and_isolate():
    conn = _env()
    project = {'stock_segment_type': SEGMENT_PROJECT_TASK,
               'project_id': PROJECT_ID, 'project_task_id': TASK_ID,
               'sales_order_line_id': 0, 'owner_party_id': 0}
    _post(conn, 10, segment=project, event='in-1')
    assert _on_hand(conn, project) == pytest.approx(10)
    assert _on_hand(conn, DEFAULT_SEGMENT) == pytest.approx(0)

    _post(conn, 4, direction='out', segment=project, line_id=2, event='out-1')
    assert _on_hand(conn, project) == pytest.approx(6)


def test_sales_order_segment_requires_item_flag():
    conn = _env()
    segment = {'stock_segment_type': SEGMENT_SALES_ORDER_LINE,
               'project_id': 0, 'project_task_id': 0,
               'sales_order_line_id': SO_LINE_ID, 'owner_party_id': 0}
    with pytest.raises(InventoryError) as exc:
        _post(conn, 5, segment=segment)
    assert exc.value.code == 'INV_SO_SEGMENT_DISABLED'

    conn.execute('UPDATE items SET so_segment_enabled = 1 WHERE id = ?',
                 [ITEM_ID])
    conn.commit()
    _post(conn, 5, segment=segment, event='in-so')
    assert _on_hand(conn, segment) == pytest.approx(5)


def test_consignment_requires_owner_and_flag():
    conn = _env()
    missing_owner = {'stock_segment_type': SEGMENT_SUPPLIER_CONSIGNMENT,
                     'project_id': 0, 'project_task_id': 0,
                     'sales_order_line_id': 0, 'owner_party_id': 0}
    with pytest.raises(InventoryError) as exc:
        _post(conn, 5, segment=missing_owner)
    assert exc.value.code == INV_CONSIGNMENT_OWNER_REQUIRED

    segment = {'stock_segment_type': SEGMENT_SUPPLIER_CONSIGNMENT,
               'project_id': 0, 'project_task_id': 0,
               'sales_order_line_id': 0, 'owner_party_id': OWNER_ID}
    with pytest.raises(InventoryError) as exc:
        _post(conn, 5, segment=segment, event='in-consign-0')
    assert exc.value.code == 'INV_SEGMENT_INVALID'

    conn.execute('UPDATE items SET consignment_enabled = 1 WHERE id = ?',
                 [ITEM_ID])
    conn.commit()
    _post(conn, 5, segment=segment, event='in-consign')
    assert _on_hand(conn, segment) == pytest.approx(5)
    assert _on_hand(conn, DEFAULT_SEGMENT) == pytest.approx(0)


def test_customer_owned_segment_rejected():
    conn = _env()
    segment = {'stock_segment_type': SEGMENT_CUSTOMER_OWNED,
               'project_id': 0, 'project_task_id': 0,
               'sales_order_line_id': 0, 'owner_party_id': 0}
    with pytest.raises(InventoryError) as exc:
        _post(conn, 1, segment=segment)
    assert exc.value.code == 'INV_SEGMENT_INVALID'


def test_segment_transfer_keeps_total_and_pairs():
    conn = _env()
    _post(conn, 20, event='in-owned')
    project = {'stock_segment_type': SEGMENT_PROJECT_TASK,
               'project_id': PROJECT_ID, 'project_task_id': TASK_ID,
               'sales_order_line_id': 0, 'owner_party_id': 0}
    result = StockSegmentService(MemDS(conn)).transfer_segment({
        'from_segment': DEFAULT_SEGMENT,
        'to_segment': project,
        'org_id': ORG_ID,
        'location_id': LOCATION_ID,
        'item_id': ITEM_ID,
        'uom_id': 3,
        'batch_id': BATCH_ID,
        'qty': 5,
        'source_event_key': 'seg-transfer-1',
        'source_doc_type': 'test',
        'source_doc_id': 1,
    })
    assert result['qty'] == 5
    assert result['result']['created'] == 2
    assert _on_hand(conn, DEFAULT_SEGMENT) == pytest.approx(15)
    assert _on_hand(conn, project) == pytest.approx(5)
    rows = conn.execute(
        'SELECT transfer_group_id, COUNT(*) FROM %s '
        'WHERE source_event_key = ? GROUP BY transfer_group_id'
        % TX_TABLE, ['seg-transfer-1']).fetchall()
    assert len(rows) == 1 and rows[0][1] == 2


def test_transfer_negative_stock_is_per_segment():
    conn = _env()
    _post(conn, 3, event='in-owned')
    project = {'stock_segment_type': SEGMENT_PROJECT_TASK,
               'project_id': PROJECT_ID, 'project_task_id': TASK_ID,
               'sales_order_line_id': 0, 'owner_party_id': 0}
    with pytest.raises(InventoryError) as exc:
        StockSegmentService(MemDS(conn)).transfer_segment({
            'from_segment': DEFAULT_SEGMENT, 'to_segment': project,
            'org_id': ORG_ID, 'location_id': LOCATION_ID,
            'item_id': ITEM_ID, 'uom_id': 3, 'batch_id': BATCH_ID,
            'qty': 5, 'source_event_key': 'seg-transfer-2',
        })
    assert exc.value.code == 'INV_NEGATIVE_STOCK'


def test_ensure_root_task_reuses_and_creates():
    conn = _env()
    service = StockSegmentService(MemDS(conn))
    assert service.ensure_root_task(PROJECT_ID) == TASK_ID

    first = service.ensure_root_task(PROJECT_ID + 1)
    second = service.ensure_root_task(PROJECT_ID + 1)
    assert first > 0
    assert second == first
    row = conn.execute(
        "SELECT task_no FROM project_tasks WHERE id = ?", [first]).fetchone()
    assert row[0] == 'ROOT'

    with pytest.raises(InventoryError) as exc:
        service.validate_segment({
            'stock_segment_type': SEGMENT_PROJECT_TASK,
            'project_id': PROJECT_ID + 1,
            'project_task_id': TASK_ID,
        })
    assert exc.value.code == 'INV_SEGMENT_PARTNER_MISMATCH'


def test_reservation_projection_written_to_balance():
    conn = _env()
    _post(conn, 10, event='in-owned')
    service = InventoryReservationService(MemDS(conn))
    created = service.create_reservation({
        'reservation_key': 'RSV-KEY-1',
        'org_id': ORG_ID,
        'item_id': ITEM_ID,
        'uom_id': 3,
        'location_id': LOCATION_ID,
        'batch_id': BATCH_ID,
        'qty_reserved': 4,
        'demand_object_type': 'sales_order_line',
        'demand_object_id': SO_LINE_ID,
        'demand_line_id': SO_LINE_ID,
        'source_doc_type': 'sales_order',
        'source_doc_id': 1,
        'source_line_id': SO_LINE_ID,
    })
    assert created['created'] is True
    row = conn.execute(
        "SELECT qty_reserved FROM %s WHERE org_id=? AND location_id=? "
        "AND item_id=? AND batch_id=? AND stock_status='unrestricted'"
        % BAL_TABLE, [ORG_ID, LOCATION_ID, ITEM_ID, BATCH_ID]).fetchone()
    assert row and float(row[0]) == pytest.approx(4)

    service.release_reservation(created['reservation']['id'], reason='测试释放')
    row = conn.execute(
        "SELECT qty_reserved FROM %s WHERE org_id=? AND location_id=? "
        "AND item_id=? AND batch_id=? AND stock_status='unrestricted'"
        % BAL_TABLE, [ORG_ID, LOCATION_ID, ITEM_ID, BATCH_ID]).fetchone()
    assert row and float(row[0]) == pytest.approx(0)
