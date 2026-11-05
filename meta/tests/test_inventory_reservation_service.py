# -*- coding: utf-8 -*-
"""INV-2 S2：预留幂等 / 状态机 / 硬钉 / ATP / 销售订单同步。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.inventory_guard_service import InventoryError
from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.inventory_reservation_service import (
    InventoryReservationService,
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
PROJECT_ID = 301
TASK_ID = 201


def _conn(with_balance=10):
    conn = seed(build_db())
    if with_balance:
        posting = InventoryPostingService(MemDS(conn))
        posting.post([{
            'transaction_type': 'RCV_PO',
            'transaction_date': '2026-11-04',
            'org_id': ORG_ID,
            'location_id': LOCATION_ID,
            'item_id': ITEM_ID,
            'uom_id': UOM_ID,
            'qty': with_balance,
            'batch_id': BATCH_ID,
            'stock_status': 'unrestricted',
            'source_line_id': 1,
        }], {
            'source_doc_type': 'test',
            'source_doc_id': 1,
            'source_event_key': 'seed-balance',
        })
    return conn


def _payload(key, qty, peg_type='soft', demand_id=SO_LINE_ID, **extra):
    payload = {
        'reservation_key': key,
        'org_id': ORG_ID,
        'item_id': ITEM_ID,
        'uom_id': UOM_ID,
        'location_id': LOCATION_ID,
        'batch_id': BATCH_ID,
        'qty_reserved': qty,
        'peg_type': peg_type,
        'demand_object_type': 'sales_order_line',
        'demand_object_id': demand_id,
        'demand_line_id': demand_id,
        'source_doc_type': 'sales_order',
        'source_doc_id': 1,
        'source_line_id': demand_id,
    }
    payload.update(extra)
    return payload


def _service(conn):
    return InventoryReservationService(MemDS(conn))


def test_create_is_idempotent_by_key():
    conn = _conn()
    service = _service(conn)
    first = service.create_reservation(_payload('RSV-A', 4))
    assert first['created'] is True
    assert first['reservation']['reservation_no'].startswith('RSV-')
    assert first['reservation']['status'] == 'open'

    second = service.create_reservation(_payload('RSV-A', 4))
    assert second['created'] is False
    assert second['reservation']['id'] == first['reservation']['id']
    assert conn.execute(
        'SELECT COUNT(*) FROM inventory_reservations').fetchone()[0] == 1


def test_available_on_hand_after_create_and_release():
    conn = _conn(10)
    service = _service(conn)
    query = {'org_id': ORG_ID, 'item_id': ITEM_ID}
    assert service.available_on_hand(query)['available_on_hand'] == pytest.approx(10)

    created = service.create_reservation(_payload('RSV-B', 4))
    atp = service.available_on_hand(query)
    assert atp['on_hand'] == pytest.approx(10)
    assert atp['reserved'] == pytest.approx(4)
    assert atp['available_on_hand'] == pytest.approx(6)

    released = service.release_reservation(created['reservation']['id'],
                                           reason='测试释放')
    assert released['status'] == 'cancelled'
    assert service.available_on_hand(query)['available_on_hand'] == pytest.approx(10)

    with pytest.raises(InventoryError) as exc:
        service.release_reservation(created['reservation']['id'])
    assert exc.value.code == 'INV_RESERVATION_STATE_INVALID'


def test_fulfill_partial_then_full_and_over_fulfill():
    conn = _conn(10)
    service = _service(conn)
    created = service.create_reservation(_payload('RSV-C', 5))
    rid = created['reservation']['id']

    partial = service.fulfill_reservation(rid, 2)
    assert partial['status'] == 'partially_fulfilled'
    assert float(partial['qty_fulfilled']) == pytest.approx(2)
    atp = service.available_on_hand({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(3)

    done = service.fulfill_reservation(rid, 3)
    assert done['status'] == 'fulfilled'
    assert service.available_on_hand(
        {'org_id': ORG_ID, 'item_id': ITEM_ID}
    )['available_on_hand'] == pytest.approx(10)

    with pytest.raises(InventoryError) as exc:
        service.fulfill_reservation(rid, 1)
    assert exc.value.code == 'INV_RESERVATION_STATE_INVALID'


def test_over_fulfill_single_call_raises_qty_exceeded():
    conn = _conn(10)
    service = _service(conn)
    rid = service.create_reservation(_payload('RSV-D', 3))['reservation']['id']
    with pytest.raises(InventoryError) as exc:
        service.fulfill_reservation(rid, 4)
    assert exc.value.code == 'INV_RESERVATION_QTY_EXCEEDED'


def test_hard_peg_conflict_and_soft_overbooking():
    conn = _conn(10)
    service = _service(conn)
    service.create_reservation(_payload('RSV-H1', 8, peg_type='hard',
                                       demand_id=1))
    with pytest.raises(InventoryError) as exc:
        service.create_reservation(_payload('RSV-H2', 8, peg_type='hard',
                                           demand_id=2))
    assert exc.value.code == 'INV_HARD_PEG_CONFLICT'

    soft = service.create_reservation(_payload('RSV-S1', 12, demand_id=3))
    assert soft['created'] is True


def test_expire_reservations():
    conn = _conn()
    service = _service(conn)
    created = service.create_reservation(
        _payload('RSV-E', 2, valid_to='2026-01-01 00:00:00'))
    assert service.expire_reservations(now='2026-06-01 00:00:00') == 1
    row = service._load(created['reservation']['id'])
    assert row['status'] == 'expired'
    assert service.expire_reservations(now='2026-06-01 00:00:00') == 0


def test_atp_include_inbound_unsupported():
    conn = _conn(10)
    service = _service(conn)
    with pytest.raises(InventoryError) as exc:
        service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID},
                    include_inbound=True)
    assert exc.value.code == 'ATP_INBOUND_UNSUPPORTED'


def test_manual_reservation_exceeding_demand_rejected():
    conn = _conn(10)
    _create_so_tables(conn)
    service = _service(conn)
    service.create_reservation(_payload('RSV-D1', 8))
    with pytest.raises(InventoryError) as exc:
        service.create_reservation(_payload('RSV-D2', 4))
    assert exc.value.code == 'INV_RESERVATION_EXCEEDS_DEMAND'


def test_unknown_demand_qty_warns_and_allows(caplog):
    conn = _conn()
    service = _service(conn)
    with caplog.at_level('WARNING'):
        created = service.create_reservation(_payload('RSV-U1', 12,
                                                      demand_id=999))
    assert created['created'] is True
    assert 'INV_DEMAND_QTY_UNKNOWN' in caplog.text


def test_close_reservation_keeps_fulfilled_and_releases_rest():
    conn = _conn(10)
    service = _service(conn)
    rid = service.create_reservation(_payload('RSV-CL', 5))['reservation']['id']
    service.fulfill_reservation(rid, 2)

    closed = service.close_reservation(rid, reason='终止履行')
    assert closed['status'] == 'closed'
    assert float(closed['qty_fulfilled']) == pytest.approx(2)
    atp = service.available_on_hand({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(0)
    assert atp['available_on_hand'] == pytest.approx(10)

    with pytest.raises(InventoryError) as exc:
        service.fulfill_reservation(rid, 1)
    assert exc.value.code == 'INV_RESERVATION_CLOSED'
    with pytest.raises(InventoryError) as exc:
        service.release_reservation(rid)
    assert exc.value.code == 'INV_RESERVATION_CLOSED'


def _create_so_tables(conn, so_flag=0):
    conn.execute('CREATE TABLE IF NOT EXISTS sales_orders '
                 '(id INTEGER PRIMARY KEY, status TEXT, org_id INTEGER, '
                 'sales_org_id INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS sales_order_lines '
                 '(id INTEGER PRIMARY KEY, order_id INTEGER, item_id INTEGER, '
                 'uom_id INTEGER, qty REAL, status TEXT, '
                 'plant_location_id INTEGER, project_id INTEGER, '
                 'project_task_id INTEGER)')
    conn.execute("INSERT INTO sales_orders (id, status, org_id) "
                 "VALUES (1, 'open', ?)", [ORG_ID])
    conn.execute("INSERT INTO sales_order_lines (id, order_id, item_id, "
                 "uom_id, qty, status, plant_location_id, project_id) "
                 "VALUES (?, 1, ?, ?, 10, 'open', ?, NULL)",
                 [SO_LINE_ID, ITEM_ID, UOM_ID, LOCATION_ID])
    conn.execute('UPDATE items SET so_segment_enabled = ?, '
                 'hard_peg_default = 0 WHERE id = ?', [so_flag, ITEM_ID])
    conn.commit()


def test_sync_sales_order_line_create_and_resize():
    conn = _conn(10)
    _create_so_tables(conn)
    service = _service(conn)
    result = service.sync_sales_order_line(SO_LINE_ID)
    assert result['created'] is True
    reservation = result['reservation']
    assert reservation['stock_segment_type'] == 'owned'
    assert float(reservation['qty_reserved']) == pytest.approx(10)

    conn.execute('UPDATE sales_order_lines SET qty = 12 WHERE id = ?',
                 [SO_LINE_ID])
    conn.commit()
    synced = service.sync_sales_order_line(SO_LINE_ID)
    assert synced['updated'] is True
    assert float(synced['reservation']['qty_reserved']) == pytest.approx(12)

    conn.execute("UPDATE sales_order_lines SET status = 'cancelled' "
                 'WHERE id = ?', [SO_LINE_ID])
    conn.commit()
    released = service.sync_sales_order_line(SO_LINE_ID)
    assert released['released'] == 1
    row = service._load(reservation['id'])
    assert row['status'] == 'cancelled'


def test_sync_sales_order_line_with_segment_flag():
    conn = _conn(10)
    _create_so_tables(conn, so_flag=1)
    service = _service(conn)
    result = service.sync_sales_order_line(SO_LINE_ID)
    assert result['created'] is True
    assert result['reservation']['stock_segment_type'] == 'sales_order_line'
    assert result['reservation']['sales_order_line_id'] == SO_LINE_ID


def test_sync_sales_order_line_with_project_task_segment():
    """G15 P2：任务行落 project_task 段；取消后释放预留。"""
    conn = _conn(10)
    _create_so_tables(conn)
    conn.execute('UPDATE sales_order_lines SET project_id = ?, '
                 'project_task_id = ? WHERE id = ?',
                 [PROJECT_ID, TASK_ID, SO_LINE_ID])
    conn.commit()
    service = _service(conn)

    result = service.sync_sales_order_line(SO_LINE_ID)
    assert result['created'] is True
    reservation = result['reservation']
    assert reservation['stock_segment_type'] == 'project_task'
    assert reservation['project_id'] == PROJECT_ID
    assert reservation['project_task_id'] == TASK_ID
    assert reservation['sales_order_line_id'] == 0

    conn.execute("UPDATE sales_order_lines SET status = 'cancelled' "
                 'WHERE id = ?', [SO_LINE_ID])
    conn.commit()
    released = service.sync_sales_order_line(SO_LINE_ID)
    assert released['released'] == 1
    row = service._load(reservation['id'])
    assert row['status'] == 'cancelled'
