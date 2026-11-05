# -*- coding: utf-8 -*-
"""阶段 A 单一事实模型测试（P0 / AC-SF-01~05）

依据: docs/specs/spec-phaseA-doc-flow-single-fact-2026-11-06.md

覆盖:
  T1 事务边界：后置步骤异常 → 库存 / 边 / 状态 / 计划行全量回滚
  T2 过账 fail-closed：post() 被跳过 → DN_ISSUE_NOT_POSTED，状态不推进
  T3 过账关闭：显式降级 inventory_mode='disabled'，不写边
  T4 补偿边：不改原边、聚合归零、同 ref 幂等、超额拒绝
  T5 冲销补偿：原边与红字子边均保持 active，聚合归零
  T6 计划行重算：30 → 50 → 30，按行事实重算而非增量算术
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_attach import reverse_edges_by_source
from meta.core.doc_flow_derive_engine import DocFlowDeriveError
from meta.core.doc_flow_reversal import compensate_edge
from meta.migrations import v214__doc_flow_shipment_issue_rule as v214
from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.shipment_service import ShipmentError, ShipmentService
from meta.tests import inventory_test_doubles as inv

RULE_ID = v214.RULE_ID

_ORDER_ID = 10
_ORDER_LINE_ID = 100
_SCHEDULE_ID = 1

_SHIPMENT_DDL = """
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    org_id INTEGER,
    order_date TEXT,
    status TEXT,
    ship_to_party_id INTEGER,
    ship_to_address_text TEXT,
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
    level TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1
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
    reversed_at TEXT,
    reversal_reason TEXT,
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


def _db(with_rule=True):
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_SHIPMENT_DDL)
    conn.execute(v214.EDGE_TABLE_DDL)
    for _, ddl in v214.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v214.CONSUMED_VIEW_DDL)
    if with_rule:
        conn.execute(v214.RULE_TABLE_DDL)
        from meta.core.doc_flow_rule_store import upsert_rules
        upsert_rules(_ShipDS(conn), [dict(v214.RULE)])
    conn.commit()
    return conn


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


def _staged_shipment(conn, qty=10):
    ds = _ShipDS(conn)
    svc = ShipmentService(ds, platform_data_source=ds)
    created = svc.create_shipment(
        {'order_id': _ORDER_ID}, [{'schedule_id': _SCHEDULE_ID, 'qty': qty}])
    svc.release(created['id'])
    svc.stage(created['id'])
    return svc, created


def _base_db(posting=True, with_rule=True):
    conn = _db(with_rule=with_rule)
    inv.enable_posting(conn, posting)
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    return conn


def _schedule_qty(conn):
    return conn.execute(
        'SELECT delivered_qty FROM sales_order_schedules WHERE id = ?',
        [_SCHEDULE_ID]).fetchone()[0]


def _header_status(conn, delivery_id):
    return conn.execute(
        'SELECT status FROM shipments WHERE id = ?', [delivery_id]).fetchone()[0]


def _count(conn, table, where='1=1', params=None):
    if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            [table]).fetchone():
        return 0
    return conn.execute(
        'SELECT COUNT(*) FROM %s WHERE %s' % (table, where),
        list(params or [])).fetchone()[0]


def _insert_edge(conn, edge_id, *, sign='normal', qty=100.0,
                 rule_id=RULE_ID, source_id='900', derive_key='',
                 target_id='txn-1'):
    conn.execute(
        'INSERT INTO doc_flow_edges (id, source_bo, source_id, source_item, '
        'target_bo, target_id, target_item, quantity, amount, currency, unit, '
        'quantity_sign, rule_id, derived_at, derived_by, status, pool, '
        'source_instance_id, target_instance_id, derive_key, edge_kind, '
        'reverses_edge_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, '
        "?, 'active', ?, '', '', ?, 'normal', '')",
        [edge_id, 'shipment_line', source_id, '', 'inventory_transaction',
         target_id, '', qty, '', '', sign, rule_id, '2026-11-06 10:00:00',
         'test', 'inventory_issue', derive_key])
    conn.commit()


# ---------------------------------------------------------------- T1 事务边界

def test_ship_confirm_rolls_back_everything_on_post_step_failure(monkeypatch):
    conn = _base_db(posting=True)
    _seed_balance(conn, 100.0)
    svc, created = _staged_shipment(conn, qty=10)

    def _boom(self, *args, **kwargs):
        raise RuntimeError('inject failure after posting')

    monkeypatch.setattr(ShipmentService, '_write_issue_edges', _boom)
    with pytest.raises(RuntimeError):
        svc.ship_confirm(created['id'])

    assert _header_status(conn, created['id']) == 'staged'
    assert _count(conn, 'inventory_transactions') == 0
    assert _schedule_qty(conn) == 0
    balance = conn.execute(
        'SELECT qty_on_hand FROM inventory_balances WHERE item_id = ?',
        [inv.ITEM_ID]).fetchone()[0]
    assert balance == 100.0


# ------------------------------------------------------------ T2 fail-closed

def test_ship_confirm_rejects_when_posting_skipped(monkeypatch):
    conn = _base_db(posting=True)
    _seed_balance(conn, 100.0)
    svc, created = _staged_shipment(conn, qty=10)

    monkeypatch.setattr(
        InventoryPostingService, 'post',
        lambda self, entries, source: {'skipped': True})
    with pytest.raises(ShipmentError) as exc:
        svc.ship_confirm(created['id'])
    assert exc.value.rule == 'DN_ISSUE_NOT_POSTED'

    assert _header_status(conn, created['id']) == 'staged'
    assert _count(conn, 'inventory_transactions') == 0
    assert _schedule_qty(conn) == 0


# -------------------------------------------------------- T3 过账关闭显式降级

def test_ship_confirm_reports_degraded_mode_when_posting_disabled():
    conn = _base_db(posting=False)
    svc, created = _staged_shipment(conn, qty=10)

    result = svc.ship_confirm(created['id'])
    assert result['status'] == 'shipped'
    assert result['inventory_mode'] == 'disabled'
    assert _count(conn, 'doc_flow_edges') == 0


# ------------------------------------------------------------ T4 补偿边原语

def test_compensate_edge_appends_and_is_idempotent():
    conn = _db()
    ds = _ShipDS(conn)
    _insert_edge(conn, 'orig-1', sign='normal', qty=100.0)

    first = compensate_edge(ds, 'orig-1', ref_id='REV-1', derived_by='test')
    assert first.kind == 'compensation' and first.replay is False

    replay = compensate_edge(ds, 'orig-1', ref_id='REV-1', derived_by='test')
    assert replay.replay is True and replay.edge_id == first.edge_id

    orig = conn.execute(
        'SELECT status, edge_kind FROM doc_flow_edges WHERE id = ?',
        ['orig-1']).fetchone()
    assert orig[0] == 'active'

    comp = conn.execute(
        'SELECT quantity, quantity_sign, edge_kind, reverses_edge_id, rule_id '
        'FROM doc_flow_edges WHERE id = ?', [first.edge_id]).fetchone()
    assert comp == (100.0, 'red', 'reversal', 'orig-1', RULE_ID + '#rev:REV-1')

    consumed = conn.execute(
        "SELECT SUM(consumed_qty) FROM v_doc_flow_consumed_qty "
        "WHERE source_bo = 'shipment_line'").fetchone()[0]
    assert consumed == 0

    with pytest.raises(DocFlowDeriveError) as exc:
        compensate_edge(ds, 'orig-1', ref_id='REV-2')
    assert exc.value.code == 'COMPENSATE_OVER_ORIGINAL'


# --------------------------------------------------- T5 冲销保留红字历史

def test_reverse_compensates_red_child_without_touching_history():
    conn = _db()
    ds = _ShipDS(conn)
    _insert_edge(conn, 'orig-2', sign='normal', qty=100.0, source_id='901')
    _insert_edge(conn, 'red-2', sign='red', qty=20.0, source_id='901',
                 rule_id=RULE_ID + '#red:REDX',
                 derive_key='red:orig-2:REDX')

    count = reverse_edges_by_source(
        ds, RULE_ID, 'shipment_line', '901', ref_id='DEL-9',
        derived_by='shipment_reverse')
    assert count == 1

    rows = conn.execute(
        'SELECT id, status, quantity_sign FROM doc_flow_edges '
        'WHERE status = ?', ['active']).fetchall()
    statuses = {row[0]: (row[1], row[2]) for row in rows}
    assert statuses['orig-2'] == ('active', 'normal')
    assert statuses['red-2'] == ('active', 'red')

    reversals = conn.execute(
        'SELECT quantity_sign, reverses_edge_id FROM doc_flow_edges '
        'WHERE edge_kind = ? ORDER BY reverses_edge_id', ['reversal']).fetchall()
    assert reversals == [('red', 'orig-2'), ('normal', 'red-2')]

    consumed = conn.execute(
        "SELECT SUM(consumed_qty) FROM v_doc_flow_consumed_qty "
        "WHERE source_bo = 'shipment_line' AND source_id = '901'").fetchone()[0]
    assert consumed == 0


# ------------------------------------------------------ T6 计划行同事务重算

def test_schedule_delivered_qty_is_recomputed_from_lines():
    conn = _base_db(posting=True)
    _seed_balance(conn, 100.0)

    svc1, created1 = _staged_shipment(conn, qty=30)
    svc1.ship_confirm(created1['id'])
    assert _schedule_qty(conn) == 30

    svc2, created2 = _staged_shipment(conn, qty=20)
    svc2.ship_confirm(created2['id'])
    assert _schedule_qty(conn) == 50

    svc2.reverse(created2['id'], reason='数量录错')
    assert _schedule_qty(conn) == 30
    assert _header_status(conn, created2['id']) == 'reversed'
