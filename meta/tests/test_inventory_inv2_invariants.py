# -*- coding: utf-8 -*-
"""INV-2 不变量（规格 §8 第 11-13 条）：预留投影 / 根任务 / 单一事实边界。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.inventory_reservation_service import (
    InventoryReservationService,
)
from meta.services.stock_segment_service import StockSegmentService
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


def _conn(with_balance=10):
    conn = seed(build_db())
    if with_balance:
        InventoryPostingService(MemDS(conn)).post([{
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
            'source_event_key': 'seed-inv2',
        })
    return conn


def _payload(key, qty):
    return {
        'reservation_key': key,
        'org_id': ORG_ID,
        'item_id': ITEM_ID,
        'uom_id': UOM_ID,
        'location_id': LOCATION_ID,
        'batch_id': BATCH_ID,
        'qty_reserved': qty,
        'peg_type': 'soft',
        'demand_object_type': 'sales_order_line',
        'demand_object_id': SO_LINE_ID,
        'demand_line_id': SO_LINE_ID,
        'source_doc_type': 'sales_order',
        'source_doc_id': 1,
        'source_line_id': SO_LINE_ID,
    }


def _balance_reserved(conn):
    rows = conn.execute(
        'SELECT qty_reserved FROM inventory_balances '
        'WHERE org_id = ? AND item_id = ? AND location_id = ?',
        (ORG_ID, ITEM_ID, LOCATION_ID)).fetchall()
    return sum(float(r[0] or 0) for r in rows)


def test_i9_qty_reserved_is_projection_of_reservations():
    """I9：qty_reserved = 活跃预留汇总；释放后归零。"""
    conn = _conn()
    service = InventoryReservationService(MemDS(conn))

    created = service.create_reservation(_payload('RSV-I9', 4))
    assert created['created'] is True
    assert _balance_reserved(conn) == pytest.approx(4)

    service.release_reservation(
        created['reservation']['id'], '测试释放')
    assert _balance_reserved(conn) == pytest.approx(0)


def test_i10_ensure_root_task_is_idempotent_and_project_scoped():
    """I10：无任务项目自动建根任务；重复调用复用；跨项目不复用。"""
    conn = build_db()
    conn.execute(
        'CREATE TABLE IF NOT EXISTS project_tasks ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, '
        'task_no TEXT, name TEXT, task_type TEXT, status TEXT, '
        'parent_task_id INTEGER)')
    service = StockSegmentService(MemDS(conn))

    first = service.ensure_root_task(1)
    second = service.ensure_root_task(1)
    other = service.ensure_root_task(2)

    assert first > 0
    assert second == first
    assert other > 0 and other != first
    count = conn.execute(
        'SELECT COUNT(*) FROM project_tasks WHERE project_id = 1').fetchone()[0]
    assert count == 1
