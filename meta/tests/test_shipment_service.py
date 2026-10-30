# -*- coding: utf-8 -*-
"""交货单服务测试（Spec §10.2 / §10.3 / §10.4 / §10.10 B1 验收 9 条）

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
      §10.2 对象模型 / §10.3 状态机与规则 R-DN-0~8 / §10.4 D10 派生扩展 / §10.10 验收

测试策略:
  · 服务层：内存 SQLite 真 SQL（超交聚合、计划行回写都靠真 SQL 才能验）
  · D10 接线：断言 ship confirm 后交付量与计划行状态，再交给
    SalesOrderFulfillmentService 派生 `fulfillment_status`（INV-1 唯一写入口）
"""

import os
import sqlite3

# 与 test_sales_order_fulfillment_status 同口径：只用内存库，不触碰真实库
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.sales_order_fulfillment_service import (
    FULFILL_DONE,
    FULFILL_NOT_STARTED,
    FULFILL_PARTIAL,
    SalesOrderFulfillmentService,
)
from meta.services.shipment_service import (
    ShipmentError,
    ShipmentService,
)

_SHIPMENTS_TABLE = 'shipments'
_ORDER_ID = 10
_ORDER_LINE_ID = 100
_SCHEDULE_ID = 1

_SCHEMA = """
CREATE TABLE orgs (
    id INTEGER PRIMARY KEY,
    code TEXT
);
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
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""


class _MemDS:
    """sqlite3 连接 → DataSource 形状（execute 返回 cursor 以取 lastrowid）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    return conn


def _add_org(conn, oid=1, code='SH'):
    conn.execute('INSERT INTO orgs (id, code) VALUES (?, ?)', [oid, code])


def _add_order(conn, oid=_ORDER_ID, org_id=1, order_date='2026-10-20',
               address='上海市浦东新区世纪大道 100 号', party_id=500):
    conn.execute(
        'INSERT INTO sales_orders (id, order_no, org_id, order_date, status, '
        'ship_to_party_id, ship_to_address_text) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        [oid, 'SO-0001', org_id, order_date, 'confirmed', party_id, address])


def _add_order_line(conn, lid=_ORDER_LINE_ID, oid=_ORDER_ID):
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, item_id, uom_id, status) '
        'VALUES (?, ?, ?, ?, ?)', [lid, oid, 900, 3, 'open'])


def _add_schedule(conn, sid=_SCHEDULE_ID, oid=_ORDER_ID,
                  lid=_ORDER_LINE_ID, kind='delivery', plant=7,
                  promised_date='2026-11-05', promised_qty=100.0,
                  delivered=0.0, status='planned'):
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, plant_location_id, promised_date, promised_qty, '
        'delivered_qty, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [sid, oid, lid, kind, plant, promised_date, promised_qty, delivered,
         status])


def _value(conn, sql, params=None):
    return conn.execute(sql, list(params or [])).fetchone()[0]


def _full_flow(svc, delivery_id):
    svc.release(delivery_id)
    svc.stage(delivery_id)


def _make_shipment(conn, qty=100.0, schedule_id=_SCHEDULE_ID, header=None,
                   lines=None):
    svc = ShipmentService(_MemDS(conn))
    payload = {'order_id': _ORDER_ID}
    if header:
        payload.update(header)
    rows = lines if lines is not None else [
        {'schedule_id': schedule_id, 'qty': qty}]
    result = svc.create_shipment(payload, rows)
    return svc, result


# ---------------- 创建：R-DN-0 / R-DN-1 ----------------

def test_create_requires_existing_order():
    conn = _db()
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment({'order_id': 999})
    assert exc.value.rule == 'DN_ORDER_NOT_FOUND'
    assert exc.value.field_name == 'order_id'


def test_create_applies_header_defaults_from_order_and_schedule():
    """地址/收货方/发货库位/计划发运日/编号均由订单 + 计划行派生。"""
    conn = _db()
    _add_org(conn, code='SH')
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_date='2026-11-05')
    svc, result = _make_shipment(conn)

    assert result['delivery_no'] == 'SH-DN-202610-0001'
    assert result['status'] == 'draft'
    header = _MemDS(conn).query(
        'SELECT * FROM shipments WHERE id = ?', [result['id']])[0]
    assert header['ship_to_party_id'] == 500
    assert header['ship_to_address_text'] == '上海市浦东新区世纪大道 100 号'
    assert header['ship_from_location_id'] == 7
    assert header['planned_ship_date'] == '2026-11-05'


def test_create_requires_address_snapshot():
    conn = _db()
    _add_order(conn, address=None)
    _add_order_line(conn)
    _add_schedule(conn, plant=None)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID}, [{'schedule_id': _SCHEDULE_ID, 'qty': 1}])
    assert exc.value.rule == 'DN_ADDRESS_REQUIRED'


def test_create_requires_location():
    conn = _db()
    _add_order(conn)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment({'order_id': _ORDER_ID})
    assert exc.value.rule == 'DN_LOCATION_REQUIRED'


def test_create_line_on_billing_schedule_rejected():
    """R-DN-0：交货行只能挂 delivery 计划行。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, kind='billing', plant=7)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID},
            [{'schedule_id': _SCHEDULE_ID, 'qty': 10}])
    assert exc.value.rule == 'DN_SCHEDULE_INVALID'
    assert exc.value.field_name == 'schedule_id'


@pytest.mark.parametrize('schedule_status', ['completed', 'cancelled'])
def test_create_line_on_unavailable_schedule_rejected(schedule_status):
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, status=schedule_status)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID},
            [{'schedule_id': _SCHEDULE_ID, 'qty': 10}])
    assert exc.value.rule == 'DN_SCHEDULE_INVALID'


def test_create_line_schedule_of_other_order_rejected():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, oid=999)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID},
            [{'schedule_id': _SCHEDULE_ID, 'qty': 10}])
    assert exc.value.rule == 'DN_SCHEDULE_INVALID'


def test_create_line_order_line_mismatch_rejected():
    """冗余列 order_line_id 与计划行反查不一致 → 拒绝。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID},
            [{'schedule_id': _SCHEDULE_ID, 'qty': 10, 'order_line_id': 999}])
    assert exc.value.rule == 'DN_SCHEDULE_INVALID'
    assert exc.value.field_name == 'order_line_id'


@pytest.mark.parametrize('qty', [0, -5])
def test_create_line_qty_must_be_positive(qty):
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID}, [{'schedule_id': _SCHEDULE_ID, 'qty': qty}])
    assert exc.value.rule == 'DN_QTY_EXCEED'


def test_create_line_over_promised_rejected():
    """R-DN-1：qty > promised_qty − delivered_qty → DN_QTY_EXCEED。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0, delivered=60.0)
    with pytest.raises(ShipmentError) as exc:
        ShipmentService(_MemDS(conn)).create_shipment(
            {'order_id': _ORDER_ID},
            [{'schedule_id': _SCHEDULE_ID, 'qty': 41}])
    assert exc.value.rule == 'DN_QTY_EXCEED'
    assert exc.value.field_name == 'qty'


def test_create_line_null_promised_qty_is_unlimited():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=None)
    svc, result = _make_shipment(conn, qty=500)
    assert result['status'] == 'draft'


def test_delivery_no_sequence_increments():
    conn = _db()
    _add_org(conn, code='SH')
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    _first = _make_shipment(conn)[1]['delivery_no']
    _second = _make_shipment(conn)[1]['delivery_no']
    assert _first == 'SH-DN-202610-0001'
    assert _second == 'SH-DN-202610-0002'


# ---------------- 状态机：R-DN-2 / R-DN-3 / R-DN-4 ----------------

def test_ship_confirm_requires_staged():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn)
    with pytest.raises(ShipmentError) as exc:
        svc.ship_confirm(result['id'])
    assert exc.value.rule == 'DN_STATE_INVALID'
    assert _value(conn, 'SELECT status FROM shipments WHERE id = ?',
                  [result['id']]) == 'draft'


def test_ship_confirm_empty_shipment_rejected():
    """R-DN-4：0 行单据禁止发运确认。"""
    conn = _db()
    _add_order(conn)
    svc, result = _make_shipment(
        conn, header={'order_id': _ORDER_ID, 'ship_from_location_id': 7},
        lines=[])
    _full_flow(svc, result['id'])
    with pytest.raises(ShipmentError) as exc:
        svc.ship_confirm(result['id'])
    assert exc.value.rule == 'DN_EMPTY'
    assert _value(conn, 'SELECT status FROM shipments WHERE id = ?',
                  [result['id']]) == 'staged'


def test_ship_confirm_full_delivery_completes_schedule():
    """§10.10(1)：整单交付 → 计划行 completed + 订单行 fulfilled。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)
    svc, result = _make_shipment(conn, qty=100)
    _full_flow(svc, result['id'])
    shipped = svc.ship_confirm(result['id'])

    assert shipped['status'] == 'shipped'
    assert shipped['idempotent'] is False
    assert _value(conn, 'SELECT delivered_qty FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 100.0
    assert _value(conn, 'SELECT status FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 'completed'
    assert _value(conn, 'SELECT delivery_id FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == result['id']
    assert _value(conn, 'SELECT status FROM shipments WHERE id = ?',
                  [result['id']]) == 'shipped'
    assert _value(conn, 'SELECT status FROM shipment_lines WHERE delivery_id = ?',
                  [result['id']]) == 'shipped'

    # INV-1：履约派生仍由 fulfillment 服务唯一写入
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(
        _ORDER_ID) == FULFILL_DONE


def test_ship_confirm_partial_then_remainder_reaches_fulfilled():
    """§10.10(2)：60 + 40 两批交付；第一批后 partial，第二批后 fulfilled。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)

    svc, first = _make_shipment(conn, qty=60)
    _full_flow(svc, first['id'])
    svc.ship_confirm(first['id'])
    assert _value(conn, 'SELECT delivered_qty FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 60.0
    assert _value(conn, 'SELECT status FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 'confirmed'
    # §10.10(2)：第一批后**行** partial（D10 扩展生效）；抬头按 §4.3 规则
    # 「无 fulfilled 行 → not_started」仍为 not_started
    SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(_ORDER_ID)
    assert _value(conn, 'SELECT fulfillment_status FROM sales_order_lines '
                        'WHERE id = ?', [_ORDER_LINE_ID]) == FULFILL_PARTIAL

    svc2, second = _make_shipment(conn, qty=40)
    _full_flow(svc2, second['id'])
    svc2.ship_confirm(second['id'])
    assert _value(conn, 'SELECT delivered_qty FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 100.0
    assert _value(conn, 'SELECT status FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 'completed'
    assert _value(conn, 'SELECT delivery_id FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == second['id']
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(
        _ORDER_ID) == FULFILL_DONE


def test_ship_confirm_is_idempotent():
    """R-DN-3：已 shipped 再次确认直接返回，不重复累加 delivered_qty。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)
    svc, result = _make_shipment(conn, qty=100)
    _full_flow(svc, result['id'])
    svc.ship_confirm(result['id'])
    again = svc.ship_confirm(result['id'])
    assert again['idempotent'] is True
    assert again['status'] == 'shipped'
    assert _value(conn, 'SELECT delivered_qty FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 100.0


def test_ship_confirm_rechecks_over_delivery_across_drafts():
    """两张草稿叠加超交：创建时各自合法，发运时按计划行累计复核拒绝。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)
    svc, first = _make_shipment(conn, qty=60)
    svc2, second = _make_shipment(conn, qty=60)
    _full_flow(svc, first['id'])
    svc.ship_confirm(first['id'])
    _full_flow(svc2, second['id'])
    with pytest.raises(ShipmentError) as exc:
        svc2.ship_confirm(second['id'])
    assert exc.value.rule == 'DN_QTY_EXCEED'
    assert _value(conn, 'SELECT delivered_qty FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 60.0


def test_cancel_draft_does_not_touch_schedule():
    """§10.10(4)：draft 取消成功，计划行不受影响。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    cancelled = svc.cancel(result['id'])
    assert cancelled['status'] == 'cancelled'
    assert _value(conn, 'SELECT status FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 'planned'
    assert _value(conn, 'SELECT delivered_qty FROM sales_order_schedules '
                        'WHERE id = ?', [_SCHEDULE_ID]) == 0.0


def test_cancel_after_shipped_rejected():
    """§10.10(5) / R-DN-2：仅 draft/released 可取消。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    _full_flow(svc, result['id'])
    svc.ship_confirm(result['id'])
    with pytest.raises(ShipmentError) as exc:
        svc.cancel(result['id'])
    assert exc.value.rule == 'DN_STATE_INVALID'


def test_cancel_staged_rejected():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    _full_flow(svc, result['id'])
    with pytest.raises(ShipmentError) as exc:
        svc.cancel(result['id'])
    assert exc.value.rule == 'DN_STATE_INVALID'


def test_receive_marks_delivered_and_idempotent():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    _full_flow(svc, result['id'])
    svc.ship_confirm(result['id'])
    received = svc.receive(result['id'], signature_ref='SIG-001',
                           actual_arrival_date='2026-11-08 10:00:00')
    assert received['status'] == 'delivered'
    assert _value(conn, 'SELECT signature_ref FROM shipments WHERE id = ?',
                  [result['id']]) == 'SIG-001'
    assert _value(conn, 'SELECT status FROM shipment_lines WHERE delivery_id = ?',
                  [result['id']]) == 'delivered'
    again = svc.receive(result['id'])
    assert again['idempotent'] is True


def test_receive_before_ship_rejected():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    with pytest.raises(ShipmentError) as exc:
        svc.receive(result['id'])
    assert exc.value.rule == 'DN_STATE_INVALID'


# ---------------- 行编辑 / 删除 ----------------

def test_update_line_qty_in_draft():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)
    svc, result = _make_shipment(conn, qty=60)
    line_id = _value(conn, 'SELECT id FROM shipment_lines WHERE delivery_id = ?',
                     [result['id']])
    updated = svc.update_line(line_id, {'qty': 80})
    assert updated['qty'] == 80.0


def test_update_line_rejects_over_delivery():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)
    svc, result = _make_shipment(conn, qty=60)
    line_id = _value(conn, 'SELECT id FROM shipment_lines WHERE delivery_id = ?',
                     [result['id']])
    with pytest.raises(ShipmentError) as exc:
        svc.update_line(line_id, {'qty': 101})
    assert exc.value.rule == 'DN_QTY_EXCEED'


def test_update_line_rejects_when_header_not_editable():
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    _full_flow(svc, result['id'])
    line_id = _value(conn, 'SELECT id FROM shipment_lines WHERE delivery_id = ?',
                     [result['id']])
    with pytest.raises(ShipmentError) as exc:
        svc.update_line(line_id, {'qty': 5})
    assert exc.value.rule == 'DN_STATE_INVALID'


def test_update_line_locked_after_shipped():
    """R-DN-7：已发运行禁改 qty / schedule_id。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn, promised_qty=100.0)
    svc, result = _make_shipment(conn, qty=10)
    _full_flow(svc, result['id'])
    svc.ship_confirm(result['id'])
    line_id = _value(conn, 'SELECT id FROM shipment_lines WHERE delivery_id = ?',
                     [result['id']])
    with pytest.raises(ShipmentError) as exc:
        svc.update_line(line_id, {'qty': 5})
    assert exc.value.rule == 'DN_LINE_LOCKED'


def test_assert_deletable_blocks_shipped():
    """R-DN-8：已发运单据不可删除。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    svc, result = _make_shipment(conn, qty=10)
    svc.assert_deletable(result['id'])  # draft 放行
    _full_flow(svc, result['id'])
    svc.ship_confirm(result['id'])
    with pytest.raises(ShipmentError) as exc:
        svc.assert_deletable(result['id'])
    assert exc.value.rule == 'DN_DELETE_FORBIDDEN'


def test_ledger_schedule_stays_not_started_without_delivery():
    """D10 回归：未发生交付时派生仍为 not_started。"""
    conn = _db()
    _add_order(conn)
    _add_order_line(conn)
    _add_schedule(conn)
    _make_shipment(conn, qty=10)  # 仅建单，不发运
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(
        _ORDER_ID) == FULFILL_NOT_STARTED
