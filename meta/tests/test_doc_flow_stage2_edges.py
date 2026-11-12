# -*- coding: utf-8 -*-
"""DOC_FLOW 阶段 2 存量链路补边验收

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.2~§5.7 / §6 阶段 2

覆盖:
  · v215 迁移注册 6 条规则且重跑幂等
  · attach 工具：规则在线写边 + 7 元组幂等；规则缺失降级为 False 不抛错
  · 交货单创建：销售订单计划行 → 交货行，自动写边（代表链路接线验收）
"""

import os
import sqlite3

# 与项目测试同口径：只用内存库，不触碰真实库
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_attach import attach_edge
from meta.core.doc_flow_rule_store import upsert_rules
from meta.core.models import registry
from meta.migrations import v215__doc_flow_stage2_rules as v215
from meta.services.shipment_service import ShipmentService
from meta.tests import inventory_test_doubles as inv

_SHIPMENT_DDL = """
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    org_id INTEGER,
    order_date TEXT,
    status TEXT,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    status TEXT
);
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    plant_location_id INTEGER,
    promised_date TEXT,
    promised_qty REAL,
    delivered_qty REAL DEFAULT 0,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    delivery_no TEXT,
    order_id INTEGER,
    ship_from_location_id INTEGER,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT,
    carrier_name TEXT,
    tracking_no TEXT,
    waybill_no TEXT,
    planned_ship_date TEXT,
    actual_ship_date TEXT,
    actual_arrival_date TEXT,
    signature_ref TEXT,
    status TEXT,
    source TEXT,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE shipment_lines (
    id INTEGER PRIMARY KEY,
    delivery_id INTEGER,
    schedule_id INTEGER,
    order_line_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL,
    lot_no TEXT,
    serial_no TEXT,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""


class _DS(inv.MemDS):
    def insert(self, table, data):
        cols = list(data)
        cur = self.conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (table, ', '.join(cols), ', '.join('?' * len(cols))),
            [data[c] for c in cols])
        return cur.lastrowid


def _flow_tables(conn):
    conn.execute(v215.RULE_TABLE_DDL)
    conn.execute(v215.EDGE_TABLE_DDL)
    for _, ddl in v215.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v215.CONSUMED_VIEW_DDL)


def _create_bo_table(conn, bo):
    """按 BO 元数据建测试表（含 aspect 审计列，derive 会显式取列）。"""
    obj = registry.get(bo)
    cols = []
    for field in obj.get_persistent_fields():
        if field.db_column == 'id':
            cols.append('id INTEGER PRIMARY KEY')
        else:
            cols.append('"%s" TEXT' % field.db_column)
    conn.execute('CREATE TABLE %s (%s)' % (obj.table_name, ', '.join(cols)))


def _count(conn, table, where='1=1', params=None):
    return conn.execute(
        'SELECT COUNT(*) FROM %s WHERE %s' % (table, where),
        list(params or [])).fetchone()[0]


# ---------------------------------------------------------------- 迁移

def test_v215_migration_registers_six_rules_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / 'mig.db')
    sqlite3.connect(db_path).close()

    v215.migrate(db_path)
    v215.migrate(db_path)  # 重跑必须幂等

    conn = sqlite3.connect(db_path)
    try:
        rules = conn.execute(
            'SELECT rule_id, source_bo, target_bo, source_qty_field, pool, '
            'status FROM doc_flow_rule ORDER BY rule_id').fetchall()
        assert len(rules) == len(v215.RULES)
        got = {row[0]: row[1:] for row in rules}
        assert got['requisition_line_to_po_line'] == (
            'requisition_line', 'purchase_order_line', 'qty', 'purchasing', 'active')
        assert got['po_schedule_to_receipt_line'] == (
            'purchase_order_schedule', 'receipt_line', 'promised_qty',
            'purchasing', 'active')
        assert got['receipt_line_to_inventory_txn'] == (
            'receipt_line', 'inventory_transaction', 'qty_received',
            'inventory_receipt', 'active')
        assert got['so_schedule_to_shipment_line'] == (
            'sales_order_schedule', 'shipment_line', 'promised_qty',
            'sales_delivery', 'active')
        assert got['allocation_to_transfer_line'] == (
            'demand_allocation', 'transfer_order_line', 'qty', 'transfer', 'active')
        assert got['transfer_order_line_to_issue_txn'] == (
            'transfer_order_line', 'inventory_transaction', 'qty',
            'transfer_move', 'active')
        assert v215.verify(db_path)['ok'] is True
    finally:
        conn.close()


# ---------------------------------------------------------------- attach 工具

def test_attach_edge_writes_once_and_degrades_without_rule():
    conn = sqlite3.connect(':memory:')
    try:
        _flow_tables(conn)
        _create_bo_table(conn, 'requisition_line')
        _create_bo_table(conn, 'purchase_order_line')
        conn.execute('INSERT INTO requisition_lines (id, qty, uom_id) VALUES (1, 10, 3)')
        conn.execute('INSERT INTO purchase_order_lines (id, qty, uom_id) VALUES (2, 4, 3)')
        ds = _DS(conn)
        upsert_rules(ds, [dict(v215.RULES[0])])

        assert attach_edge(ds, ds, 'requisition_line_to_po_line',
                           1, 2, 4, derived_by='test') is True
        # 同源同目标同规则 → 7 元组幂等，不新增
        assert attach_edge(ds, ds, 'requisition_line_to_po_line',
                           1, 2, 4, derived_by='test') is True
        assert _count(conn, 'doc_flow_edges') == 1
        edge = conn.execute(
            'SELECT source_bo, target_bo, quantity, pool, status '
            'FROM doc_flow_edges').fetchone()
        assert edge == ('requisition_line', 'purchase_order_line', 4.0,
                        'purchasing', 'active')

        # 规则未注册 → 降级 False，不抛错、不写边
        assert attach_edge(ds, ds, 'missing_rule', 1, 2, 4) is False
        assert _count(conn, 'doc_flow_edges') == 1
    finally:
        conn.close()


# --------------------------------------------------------- 交货单创建接线

def test_create_shipment_writes_so_schedule_edge():
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_SHIPMENT_DDL)
    _flow_tables(conn)
    ds = _DS(conn)
    upsert_rules(ds, [dict(rule) for rule in v215.RULES
                      if rule['rule_id'] == 'so_schedule_to_shipment_line'])

    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        'ship_to_party_id, ship_to_address_text) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [10, 'SO-0001', inv.ORG_ID, '2026-11-05', 'confirmed', 500, '上海'])
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, '
        'project_task_id, status) VALUES (?, ?, ?, ?, ?, ?)',
        [100, 10, inv.ITEM_ID, inv.UOM_ID, 0, 'open'])
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, plant_location_id, promised_date, promised_qty, '
        'delivered_qty, status, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)',
        [1, 10, 100, 'delivery', inv.LOCATION_ID, '2026-11-05', 100.0,
         'planned', '2026-11-05 10:00:00', '2026-11-05 10:00:00'])
    conn.commit()

    svc = ShipmentService(ds, platform_data_source=ds)
    created = svc.create_shipment({'order_id': 10}, [{'schedule_id': 1, 'qty': 10}])
    shipment_line_id = conn.execute(
        'SELECT id FROM shipment_lines WHERE delivery_id = ?',
        [created['id']]).fetchone()[0]

    edges = conn.execute(
        'SELECT source_bo, source_id, target_bo, target_item, quantity, '
        'rule_id, derived_by FROM doc_flow_edges').fetchall()
    assert len(edges) == 1
    source_bo, source_id, target_bo, target_item, qty, rule_id, derived_by = edges[0]
    assert source_bo == 'sales_order_schedule'
    assert source_id == '1'
    assert target_bo == 'shipment_line'
    assert target_item == str(shipment_line_id)
    assert qty == 10.0
    assert rule_id == 'so_schedule_to_shipment_line'
    assert derived_by == 'shipment_service'


# ------------------------------------------------- 端到端链路数量一致（AC-15）

def test_end_to_end_chain_quantity_consistent():
    """销售计划行 → 交货行 → 出库事务：相邻两跳消耗量可加总一致。"""
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_SHIPMENT_DDL)
    _flow_tables(conn)
    ds = _DS(conn)
    upsert_rules(ds, [
        dict(rule) for rule in v215.RULES
        if rule['rule_id'] == 'so_schedule_to_shipment_line'
    ] + [{
        'rule_id': 'shipment_line_to_issue_txn', 'source_bo': 'shipment_line',
        'target_bo': 'inventory_transaction', 'source_qty_field': 'qty',
        'pool': 'inventory_issue',
    }])

    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        'ship_to_party_id, ship_to_address_text) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [10, 'SO-0001', inv.ORG_ID, '2026-11-05', 'confirmed', 500, '上海'])
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, '
        'project_task_id, status) VALUES (?, ?, ?, ?, ?, ?)',
        [100, 10, inv.ITEM_ID, inv.UOM_ID, 0, 'open'])
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, plant_location_id, promised_date, promised_qty, '
        'delivered_qty, status, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)',
        [1, 10, 100, 'delivery', inv.LOCATION_ID, '2026-11-05', 100.0,
         'planned', '2026-11-05 10:00:00', '2026-11-05 10:00:00'])
    conn.commit()

    created = ShipmentService(ds, platform_data_source=ds).create_shipment(
        {'order_id': 10}, [{'schedule_id': 1, 'qty': 10}])
    shipment_line_id = conn.execute(
        'SELECT id FROM shipment_lines WHERE delivery_id = ?',
        [created['id']]).fetchone()[0]

    conn.execute(
        'INSERT INTO inventory_transactions (id, transaction_no, '
        'transaction_type_id, transaction_date, org_id, location_id, item_id, '
        'uom_id, qty, base_qty, direction, stock_status, stock_segment_type, '
        'project_id, project_task_id, sales_order_line_id, owner_party_id, '
        'source_doc_type, source_doc_id, source_line_id, source_event_key) '
        'VALUES (900, ?, 1, ?, ?, ?, ?, ?, 10, 10, ?, ?, ?, 0, 0, 0, 0, ?, ?, '
        '0, ?)',
        ['IT-900', '2026-11-05', inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID,
         inv.UOM_ID, 'out', 'unrestricted', 'owned', 'shipment',
         created['id'], 'shipment:900:ship'])

    assert attach_edge(ds, ds, 'shipment_line_to_issue_txn',
                       shipment_line_id, 900, 10,
                       target_item=str(shipment_line_id)) is True

    consumed = dict(
        (row[0], row[1]) for row in conn.execute(
            'SELECT source_bo, consumed_qty FROM v_doc_flow_consumed_qty '
            "WHERE source_bo IN ('sales_order_schedule', 'shipment_line')"
        ).fetchall())
    assert consumed['sales_order_schedule'] == pytest.approx(10.0)
    assert consumed['shipment_line'] == pytest.approx(10.0)
    assert consumed['sales_order_schedule'] == consumed['shipment_line']
