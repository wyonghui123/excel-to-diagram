# -*- coding: utf-8 -*-
"""采购订单履约状态派生测试。

依据: docs/specs/spec-receipt-object-model-2026-11-01.md §6 步 4 / §8.1
      docs/specs/spec-purchase-order-object-model-2026-11-01.md §3 / §4 / §10.4

策略：内存 SQLite 真 SQL，验证派生口径与幂等；不触碰真实库。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.purchase_order_fulfillment_service import (
    FULFILL_CLOSED,
    FULFILL_DONE,
    FULFILL_OPEN,
    FULFILL_PARTIAL,
    PurchaseOrderFulfillmentService,
)

_SCHEMA = """
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    delivery_relevant INTEGER DEFAULT 1
);
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY,
    status TEXT,
    fulfillment_status TEXT,
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE purchase_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_type_id INTEGER,
    qty REAL,
    status TEXT,
    fulfillment_status TEXT,
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE purchase_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    promised_qty REAL,
    received_qty REAL DEFAULT 0,
    status TEXT,
    updated_at TEXT
);
"""


class _DS:
    """最小数据源：query 返回 dict 行，execute 提交。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        self.conn.execute(sql, params or [])
        self.conn.commit()


@pytest.fixture()
def db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO type_definitions (id, delivery_relevant) VALUES (1, 1)")
    conn.execute("INSERT INTO type_definitions (id, delivery_relevant) VALUES (2, 0)")
    conn.commit()
    ds = _DS(conn)
    yield ds
    conn.close()


def _order(ds, status='confirmed', fulfillment=None):
    ds.execute('INSERT INTO purchase_orders (id, status, fulfillment_status) '
               'VALUES (1, ?, ?)', [status, fulfillment])


def _line(ds, line_id=11, qty=10, status='open', type_id=1, fulfillment=None):
    ds.execute(
        'INSERT INTO purchase_order_lines '
        '(id, order_id, line_type_id, qty, status, fulfillment_status) '
        'VALUES (?, 1, ?, ?, ?, ?)',
        [line_id, type_id, qty, status, fulfillment])


def _schedule(ds, schedule_id, line_id, promised, received, status):
    ds.execute(
        'INSERT INTO purchase_order_schedules '
        '(id, order_id, line_id, schedule_kind, promised_qty, received_qty, status) '
        'VALUES (?, 1, ?, ?, ?, ?, ?)',
        [schedule_id, line_id, 'delivery', promised, received, status])


def test_line_partial_when_received_below_qty(db):
    _order(db)
    _line(db)
    _schedule(db, 1, 11, 10, 4, 'confirmed')
    status = PurchaseOrderFulfillmentService(db).recompute_line(11)
    assert status == FULFILL_PARTIAL


def test_line_received_when_received_reaches_qty(db):
    _order(db)
    _line(db)
    _schedule(db, 1, 11, 10, 10, 'confirmed')
    status = PurchaseOrderFulfillmentService(db).recompute_line(11)
    assert status == FULFILL_DONE


def test_line_received_on_short_close(db):
    """短收结案：计划行 completed 且无 pending，行按实结案为 received。"""
    _order(db)
    _line(db, qty=10)
    _schedule(db, 1, 11, 10, 7, 'completed')
    status = PurchaseOrderFulfillmentService(db).recompute_line(11)
    assert status == FULFILL_DONE


def test_line_closed_for_non_delivery_relevant_without_schedules(db):
    _order(db)
    _line(db, type_id=2)
    status = PurchaseOrderFulfillmentService(db).recompute_line(11)
    assert status == FULFILL_CLOSED


def test_line_open_for_delivery_relevant_without_schedules(db):
    _order(db)
    _line(db)
    status = PurchaseOrderFulfillmentService(db).recompute_line(11)
    assert status == FULFILL_OPEN


def test_cancelled_line_closed(db):
    _order(db)
    _line(db, status='cancelled')
    _schedule(db, 1, 11, 10, 3, 'cancelled')
    status = PurchaseOrderFulfillmentService(db).recompute_line(11)
    assert status == FULFILL_CLOSED


def test_order_partial_then_received(db):
    _order(db)
    _line(db, line_id=11, qty=10)
    _line(db, line_id=12, qty=5)
    _schedule(db, 1, 11, 10, 10, 'confirmed')
    _schedule(db, 2, 12, 5, 2, 'confirmed')
    svc = PurchaseOrderFulfillmentService(db)
    assert svc.recompute_order(1) == FULFILL_PARTIAL

    db.execute('UPDATE purchase_order_schedules SET received_qty = 5, status = ? '
               'WHERE id = 2', ['completed'])
    assert svc.recompute_order(1) == FULFILL_DONE


def test_order_closed_when_header_closed(db):
    _order(db, status='closed')
    _line(db, qty=10)
    _schedule(db, 1, 11, 10, 10, 'completed')
    assert PurchaseOrderFulfillmentService(db).recompute_order(1) == FULFILL_CLOSED


def test_recompute_all_idempotent(db):
    _order(db)
    _line(db, qty=10)
    _schedule(db, 1, 11, 10, 3, 'confirmed')
    svc = PurchaseOrderFulfillmentService(db)
    first = svc.recompute_all()
    second = svc.recompute_all()
    assert first['lines_written'] == 1
    assert first['orders_written'] == 1
    assert second['lines_written'] == 0
    assert second['orders_written'] == 0
