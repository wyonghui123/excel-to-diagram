# -*- coding: utf-8 -*-
"""INV-2 S3：供应—需求 trace 链接 / 上限 / 关闭 / 端到端追溯。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.demand_trace_service import DemandTraceService
from meta.services.inventory_guard_service import InventoryError
from meta.tests.inventory_test_doubles import MemDS, build_db, seed

SO_LINE_ID = 501
PO_LINE_ID = 601
SHIPMENT_ID = 701


def _conn():
    conn = seed(build_db())
    conn.execute('CREATE TABLE sales_order_lines '
                 '(id INTEGER PRIMARY KEY, qty REAL)')
    conn.execute('INSERT INTO sales_order_lines (id, qty) VALUES (?, 10)',
                 [SO_LINE_ID])
    conn.commit()
    return conn


def _link(conn, supply, demand, qty, trace_type='allocation', **extra):
    payload = {
        'supply_object_type': supply[0],
        'supply_object_id': supply[1],
        'supply_line_id': supply[2],
        'demand_object_type': demand[0],
        'demand_object_id': demand[1],
        'demand_line_id': demand[2],
        'trace_type': trace_type,
        'allocated_qty': qty,
    }
    payload.update(extra)
    return DemandTraceService(MemDS(conn)).link_supply_demand(payload)


def test_link_idempotent_and_qty_cap():
    conn = _conn()
    service = DemandTraceService(MemDS(conn))
    supply = ('purchase_order_line', PO_LINE_ID, 0)
    demand = ('sales_order_line', SO_LINE_ID, SO_LINE_ID)

    first = _link(conn, supply, demand, 5)
    assert first['created'] is True
    again = _link(conn, supply, demand, 5)
    assert again['created'] is False and again['updated'] is False

    changed = _link(conn, supply, demand, 8)
    assert changed['updated'] is True
    assert float(changed['link']['allocated_qty']) == pytest.approx(8)

    with pytest.raises(InventoryError) as exc:
        _link(conn, supply, demand, 12)
    assert exc.value.code == 'INV_TRACE_QTY_EXCEEDED'

    with pytest.raises(InventoryError):
        _link(conn, ('purchase_order_line', PO_LINE_ID, 1), demand, 4)


def test_unlink_then_relink():
    conn = _conn()
    service = DemandTraceService(MemDS(conn))
    supply = ('purchase_order_line', PO_LINE_ID, 0)
    demand = ('sales_order_line', SO_LINE_ID, SO_LINE_ID)
    link = _link(conn, supply, demand, 5)
    closed = service.unlink(link['link']['id'], reason='重链')
    assert closed['valid_to'] is not None

    again = _link(conn, supply, demand, 5)
    assert again['created'] is True
    assert again['link']['id'] != link['link']['id']


def test_trace_end_demand_multi_hop():
    conn = _conn()
    supply = ('purchase_order_line', PO_LINE_ID, 0)
    shipment = ('shipment', SHIPMENT_ID, 0)
    demand = ('sales_order_line', SO_LINE_ID, SO_LINE_ID)
    _link(conn, supply, shipment, 5, trace_type='pegging')
    _link(conn, shipment, demand, 5, trace_type='reservation')

    result = DemandTraceService(MemDS(conn)).trace_end_demand({
        'object_type': 'purchase_order_line', 'object_id': PO_LINE_ID,
    })
    assert result['hops'] >= 2
    assert len(result['demands']) == 1
    terminal = result['demands'][0]
    assert terminal['object_type'] == 'sales_order_line'
    assert terminal['object_id'] == SO_LINE_ID
    assert terminal['allocated_qty'] == pytest.approx(5)


def test_trace_unknown_node_type_rejected():
    conn = _conn()
    with pytest.raises(InventoryError) as exc:
        _link(conn, ('martian_supply', 1, 0),
              ('sales_order_line', SO_LINE_ID, SO_LINE_ID), 1)
    assert exc.value.code == 'INV_TRACE_NODE_INVALID'


def test_hard_pegging_inventory_segment_rejected():
    """R15：库存段行的数量只能由预留陈述，hard pegging 不得再记量。"""
    conn = _conn()
    demand = ('sales_order_line', SO_LINE_ID, SO_LINE_ID)
    with pytest.raises(InventoryError) as exc:
        _link(conn, ('inventory_balance', 1, 0), demand, 5,
              trace_type='pegging', peg_type='hard')
    assert exc.value.code == 'TRACE_SUPPLY_DOUBLE_COUNT'


def test_trace_does_not_duplicate_demand_allocation_project_task():
    """I11 边界：采购行的项目任务归属只留在 demand_allocation，trace 不双写。"""
    conn = _conn()
    conn.execute(
        'CREATE TABLE demand_allocations ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, demand_bo VARCHAR(200), '
        'demand_id INTEGER, demand_line_id INTEGER, project_id INTEGER, '
        'project_task_id INTEGER, target_bo VARCHAR(200), target_id INTEGER, '
        'target_line_id INTEGER, qty REAL)')
    conn.execute(
        'INSERT INTO demand_allocations (demand_bo, demand_id, demand_line_id, '
        'project_id, project_task_id, target_bo, target_id, target_line_id, qty) '
        "VALUES ('purchase_order_line', ?, 0, 11, 21, 'purchase_order_line', ?, 0, 5)",
        [PO_LINE_ID, PO_LINE_ID])
    conn.commit()

    _link(conn, ('purchase_order_line', PO_LINE_ID, 0),
          ('sales_order_line', SO_LINE_ID, SO_LINE_ID), 5, trace_type='pegging')

    allocations = conn.execute(
        'SELECT demand_bo, demand_line_id, project_id, project_task_id, qty '
        'FROM demand_allocations').fetchall()
    assert allocations == [('purchase_order_line', 0, 11, 21, 5)]
    assert conn.execute(
        'SELECT count(*) FROM demand_trace_links').fetchone()[0] == 1
    columns = {row[1] for row in conn.execute(
        'PRAGMA table_info(demand_trace_links)').fetchall()}
    assert 'project_task_id' not in columns


def test_inherit_from_document_shipment_line():
    conn = _conn()
    result = DemandTraceService(MemDS(conn)).inherit_from_document({
        'doc_type': 'shipment',
        'doc_id': SHIPMENT_ID,
        'lines': [{
            'line_id': 11,
            'qty': 5,
            'source_doc_type': 'sales_order',
            'source_doc_id': 1,
            'source_line_id': SO_LINE_ID,
        }],
    })
    assert result['created'] == 1
    rows = conn.execute(
        'SELECT supply_object_type, supply_object_id, supply_line_id, '
        'demand_object_type, demand_object_id FROM demand_trace_links').fetchall()
    assert rows == [('shipment', SHIPMENT_ID, 11,
                     'sales_order_line', SO_LINE_ID)]
