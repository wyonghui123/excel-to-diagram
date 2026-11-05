# -*- coding: utf-8 -*-
"""交货单数据错误冲销（R1 全量回滚）验收

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.1 / D6（评审修正版）

覆盖:
  AC-24 正向交货 shipped → reversed：库存反冲、边红字、计划行回滚、幂等
  AC-25 退货交货 delivered → reversed：RETURN_IN 反冲为 REVERSAL 出库，
        边按退货规则红字，计划行不回写
  AC-26 仅 shipped / delivered 可冲销，draft 拒绝
  AC-27 预留反向核销：fulfilled → open，qty_fulfilled 归零
  AC-28 冲销后不可再签收 / 再发运
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_rule_store import upsert_rules
from meta.migrations import v214__doc_flow_shipment_issue_rule as v214
from meta.migrations import v222__doc_flow_return_shipment_rule as v222
from meta.services.shipment_service import ShipmentError, ShipmentService
from meta.tests import inventory_test_doubles as inv

_ORDER_ID = 10
_ORDER_LINE_ID = 100
_SCHEDULE_ID = 1
_RETURN_TYPE_ID = 2

_SHIPMENT_DDL = """
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    org_id INTEGER,
    order_date TEXT,
    status TEXT,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT,
    document_type_id INTEGER,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    project_task_id INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
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
    delivery_id INTEGER,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    scope_bo TEXT,
    level TEXT,
    document_category TEXT,
    status TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1
);
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    delivery_no TEXT,
    order_id INTEGER,
    document_type_id INTEGER,
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
    reversed_at TEXT,
    reversal_reason TEXT,
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


class _ShipDS(inv.MemDS):
    def insert(self, table, data):
        cols = list(data)
        cur = self.conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (table, ', '.join(cols), ', '.join('?' * len(cols))),
            [data[c] for c in cols])
        return cur.lastrowid


def _db():
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_SHIPMENT_DDL)
    conn.execute(v214.EDGE_TABLE_DDL)
    for _, ddl in v214.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v214.CONSUMED_VIEW_DDL)
    conn.execute(v214.RULE_TABLE_DDL)
    ds = _ShipDS(conn)
    upsert_rules(ds, [dict(v214.RULE), dict(v222.RETURN_RULE)])
    conn.execute(
        "INSERT INTO type_definitions (id, code, name, scope_bo, level, "
        "document_category, status) VALUES "
        "(1, 'STD', '标准交货单', 'shipment', 'header', 'standard', 'active'), "
        "(2, 'RETURN', '退货交货单', 'shipment', 'header', 'return', 'active')")
    conn.commit()
    return conn


def _seed_return_type(conn):
    if conn.execute(
            "SELECT 1 FROM inventory_transaction_types WHERE code='RETURN_IN'"
    ).fetchone():
        return
    conn.execute(
        'INSERT INTO inventory_transaction_types '
        '(code, name, category, direction, affects_on_hand, status, sort_order, '
        'description, created_at) '
        "VALUES ('RETURN_IN', '销售退货入库', 'receipt', 'in', 1, 'active', 70, "
        "'退货交货入库', '2026-11-05')")
    conn.commit()


def _add_order(conn):
    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        'ship_to_party_id, ship_to_address_text) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [_ORDER_ID, 'SO-0001', inv.ORG_ID, '2026-10-20', 'confirmed', 500,
         '上海市浦东新区世纪大道 100 号'])


def _add_order_line(conn):
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, '
        'project_task_id, status) VALUES (?, ?, ?, ?, 0, ?)',
        [_ORDER_LINE_ID, _ORDER_ID, inv.ITEM_ID, inv.UOM_ID, 'open'])


def _add_schedule(conn, promised_qty=100.0):
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, plant_location_id, promised_date, promised_qty, '
        'delivered_qty, status) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)',
        [_SCHEDULE_ID, _ORDER_ID, _ORDER_LINE_ID, 'delivery', inv.LOCATION_ID,
         '2026-11-05', promised_qty, 'planned'])


def _seed_balance(conn, qty=100.0):
    conn.execute(
        'INSERT INTO inventory_balances (org_id, location_id, item_id, batch_id, '
        'stock_status, stock_segment_type, project_id, project_task_id, '
        'sales_order_line_id, owner_party_id, qty_on_hand, qty_reserved) '
        "VALUES (?, ?, ?, 0, 'unrestricted', 'owned', 0, 0, 0, 0, ?, 0)",
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID, qty])


def _ship(conn, qty=10.0, document_type_id=None):
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=ds)
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    header = {'order_id': _ORDER_ID}
    if document_type_id is not None:
        header['document_type_id'] = document_type_id
    created = svc.create_shipment(
        header, [{'schedule_id': _SCHEDULE_ID, 'qty': qty}])
    svc.release(created['id'])
    svc.stage(created['id'])
    result = svc.ship_confirm(created['id'])
    return svc, created, result


def _qty_on_hand(conn):
    return conn.execute(
        'SELECT qty_on_hand FROM inventory_balances WHERE org_id=? AND '
        'location_id=? AND item_id=?',
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID]).fetchone()[0]


def _txns(conn):
    return conn.execute(
        'SELECT tt.code, t.direction, t.qty, t.source_event_key, '
        't.reversal_of_transaction_id '
        'FROM inventory_transactions t JOIN inventory_transaction_types tt '
        'ON tt.id = t.transaction_type_id ORDER BY t.id').fetchall()


def _edges(conn):
    # 边表 17 列无 ref_id 审计位：业务锚（红字单 ID）写入 derive_key 'red:...' 后缀
    return conn.execute(
        'SELECT rule_id, quantity_sign, status, derive_key FROM doc_flow_edges '
        'ORDER BY rowid').fetchall()


# ------------------------------------------------------------ 正向交货冲销

def test_reverse_shipped_restores_stock_edges_and_schedule():
    conn = _db()
    inv.enable_posting(conn, True)
    _seed_balance(conn, 100.0)
    svc, created, result = _ship(conn, qty=10.0)
    assert result['status'] == 'shipped'
    assert _qty_on_hand(conn) == 90.0

    reversed_result = svc.reverse(created['id'], reason='数量录错')
    assert reversed_result['status'] == 'reversed'
    assert _qty_on_hand(conn) == 100.0

    txns = _txns(conn)
    assert len(txns) == 2
    assert txns[0][0] == 'ISSUE_TO_SHIP' and txns[0][1] == 'out'
    assert txns[1][0] == 'REVERSAL' and txns[1][1] == 'in'
    assert txns[1][4] is not None
    assert txns[1][3] == 'shipment:%s:ship_reverse' % created['id']

    edges = _edges(conn)
    # 单一事实模型：原边保持 active，冲销以 #rev 补偿边追加（不改历史）
    assert [e[0].split('#rev:')[0] for e in edges] == [v214.RULE_ID, v214.RULE_ID]
    assert edges[0][1] == 'normal' and edges[0][2] == 'active'
    assert edges[1][1] == 'red' and edges[1][2] == 'active'
    assert edges[1][0].endswith('#rev:%s' % created['id'])
    assert str(edges[1][3]).startswith('rev:')
    assert str(edges[1][3]).endswith(str(created['id']))

    header = conn.execute(
        'SELECT status, reversed_at, reversal_reason FROM shipments WHERE id=?',
        [created['id']]).fetchone()
    assert header[0] == 'reversed'
    assert header[1]
    assert header[2] == '数量录错'

    line_status = conn.execute(
        'SELECT status FROM shipment_lines WHERE delivery_id=?',
        [created['id']]).fetchone()[0]
    assert line_status == 'reversed'

    sched = conn.execute(
        'SELECT delivered_qty, status, delivery_id FROM sales_order_schedules '
        'WHERE id=?', [_SCHEDULE_ID]).fetchone()
    assert sched[0] == 0.0
    assert sched[1] == 'confirmed'
    assert sched[2] is None

    # 幂等：再次冲销不产生新事务 / 新边
    again = svc.reverse(created['id'], reason='重复提交')
    assert again['idempotent'] is True
    assert len(_txns(conn)) == 2
    assert len(_edges(conn)) == 2


# ------------------------------------------------------------ 退货交货冲销

def test_reverse_return_shipment_reds_return_in_and_keeps_schedule():
    conn = _db()
    inv.enable_posting(conn, True)
    _seed_return_type(conn)
    svc, created, result = _ship(conn, qty=10.0,
                                 document_type_id=_RETURN_TYPE_ID)
    assert result['status'] == 'shipped'
    txns = _txns(conn)
    assert txns[0][0] == 'RETURN_IN' and txns[0][1] == 'in'

    svc.reverse(created['id'], reason='退货数量录错')
    txns = _txns(conn)
    assert len(txns) == 2
    assert txns[1][0] == 'REVERSAL' and txns[1][1] == 'out'
    assert txns[1][3] == 'shipment:%s:return_reverse' % created['id']

    edges = _edges(conn)
    assert ([e[0].split('#rev:')[0] for e in edges]
            == [v222.RETURN_RULE['rule_id']] * 2)
    assert edges[0][2] == 'active' and edges[1][1] == 'red'
    assert edges[1][2] == 'active'

    sched = conn.execute(
        'SELECT delivered_qty, status FROM sales_order_schedules WHERE id=?',
        [_SCHEDULE_ID]).fetchone()
    assert sched[0] == 0.0  # 退货方向发运本来就不回写计划行


# ------------------------------------------------------------ 状态守卫

def test_reverse_requires_shipped_or_delivered():
    conn = _db()
    inv.enable_posting(conn, False)
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=ds)
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    created = svc.create_shipment(
        {'order_id': _ORDER_ID}, [{'schedule_id': _SCHEDULE_ID, 'qty': 10}])
    with pytest.raises(ShipmentError) as exc:
        svc.reverse(created['id'], reason='未发运')
    assert exc.value.rule == 'DN_STATE_INVALID'


def test_reverse_unfulfills_reserved_demand():
    conn = _db()
    inv.enable_posting(conn, True)
    _seed_balance(conn, 100.0)
    conn.execute(
        "INSERT INTO inventory_reservations (reservation_no, org_id, item_id, "
        "uom_id, demand_object_type, demand_object_id, demand_line_id, "
        "qty_reserved, qty_fulfilled, status, reservation_key) VALUES "
        "('RES-1', ?, ?, ?, 'sales_order_line', ?, 0, 10, 10, 'fulfilled', "
        "'so_line:' || ?)",
        [inv.ORG_ID, inv.ITEM_ID, inv.UOM_ID, _ORDER_LINE_ID,
         _ORDER_LINE_ID])
    conn.commit()

    svc, created, _result = _ship(conn, qty=10.0)
    svc.reverse(created['id'], reason='数据错误')

    row = conn.execute(
        'SELECT status, qty_fulfilled FROM inventory_reservations WHERE id=1'
    ).fetchone()
    assert row[0] == 'open'
    assert row[1] == 0.0


def test_reversed_delivery_cannot_receive_or_reship():
    conn = _db()
    inv.enable_posting(conn, False)
    _seed_balance(conn, 100.0)
    svc, created, _result = _ship(conn, qty=10.0)
    svc.reverse(created['id'], reason='数据错误')

    with pytest.raises(ShipmentError):
        svc.receive(created['id'])
    with pytest.raises(ShipmentError):
        svc.ship_confirm(created['id'])
