# -*- coding: utf-8 -*-
"""INV-2 S2：按段 ATP / 库位与批次作用域。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.inventory_reservation_service import (
    InventoryReservationService,
)
from meta.services.stock_segment_service import (
    DEFAULT_SEGMENT,
    SEGMENT_SALES_ORDER_LINE,
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


def _post(conn, qty, segment, event, line_id=1):
    entry = {
        'transaction_type': 'RCV_PO',
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
    InventoryPostingService(MemDS(conn)).post([entry], {
        'source_doc_type': 'test',
        'source_doc_id': 1,
        'source_event_key': event,
    })


def _so_segment():
    return {'stock_segment_type': SEGMENT_SALES_ORDER_LINE,
            'project_id': 0, 'project_task_id': 0,
            'sales_order_line_id': SO_LINE_ID, 'owner_party_id': 0}


def _reservation(conn, key, qty, demand_id, **extra):
    payload = {
        'reservation_key': key,
        'org_id': ORG_ID,
        'item_id': ITEM_ID,
        'uom_id': UOM_ID,
        'batch_id': BATCH_ID,
        'qty_reserved': qty,
        'demand_object_type': 'sales_order_line',
        'demand_object_id': demand_id,
        'demand_line_id': demand_id,
    }
    payload.update(extra)
    return InventoryReservationService(MemDS(conn)).create_reservation(payload)


def test_atp_is_segment_scoped():
    conn = seed(build_db())
    conn.execute('UPDATE items SET so_segment_enabled = 1 WHERE id = ?',
                 [ITEM_ID])
    conn.commit()
    _post(conn, 10, DEFAULT_SEGMENT, 'owned-in')
    _post(conn, 6, _so_segment(), 'so-in', line_id=2)

    service = InventoryReservationService(MemDS(conn))
    owned = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert owned['on_hand'] == pytest.approx(10)

    so = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID,
                      'stock_segment_type': SEGMENT_SALES_ORDER_LINE,
                      'sales_order_line_id': SO_LINE_ID})
    assert so['on_hand'] == pytest.approx(6)


def test_atp_location_scope_counts_unpinned_reservations():
    conn = seed(build_db())
    _post(conn, 10, DEFAULT_SEGMENT, 'owned-in')
    _reservation(conn, 'RSV-ATP-1', 4, 1)  # 不限定库位/批次

    service = InventoryReservationService(MemDS(conn))
    scoped = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID,
                          'location_id': LOCATION_ID, 'batch_id': BATCH_ID})
    assert scoped['on_hand'] == pytest.approx(10)
    assert scoped['available_on_hand'] == pytest.approx(6)

    other_batch = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID,
                               'location_id': LOCATION_ID, 'batch_id': 0})
    assert other_batch['reserved'] == pytest.approx(4)


def test_pinned_reservation_not_counted_in_other_batch():
    conn = seed(build_db())
    _post(conn, 10, DEFAULT_SEGMENT, 'owned-in')
    _reservation(conn, 'RSV-ATP-2', 5, 2, location_id=LOCATION_ID,
                 batch_id=BATCH_ID)

    service = InventoryReservationService(MemDS(conn))
    other_batch = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID,
                               'batch_id': BATCH_ID + 1})
    assert other_batch['on_hand'] == pytest.approx(0)
    assert other_batch['reserved'] == pytest.approx(0)

    same_batch = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID,
                              'batch_id': BATCH_ID})
    assert same_batch['available_on_hand'] == pytest.approx(5)


def test_expired_reservation_excluded_without_expire_job():
    conn = seed(build_db())
    _post(conn, 10, DEFAULT_SEGMENT, 'owned-in')
    _reservation(conn, 'RSV-ATP-3', 4, 3,
                 valid_to='2026-01-01 00:00:00')

    service = InventoryReservationService(MemDS(conn))
    atp = service.atp({'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['reserved'] == pytest.approx(0)
    assert atp['available_on_hand'] == pytest.approx(10)
    assert atp['shortage'] == pytest.approx(0)


def test_soft_overbooking_reports_shortage():
    conn = seed(build_db())
    _post(conn, 10, DEFAULT_SEGMENT, 'owned-in')
    _reservation(conn, 'RSV-ATP-4', 12, 4)

    atp = InventoryReservationService(MemDS(conn)).atp(
        {'org_id': ORG_ID, 'item_id': ITEM_ID})
    assert atp['available_on_hand'] == pytest.approx(-2)
    assert atp['shortage'] == pytest.approx(2)
