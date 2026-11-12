# -*- coding: utf-8 -*-
"""到货计划行守卫测试（M3 / spec §10 / §14.1 R-SCH-0 ~ R-SCH-4）

测试策略：内存 SQLite 真 SQL，断言守卫错误规则码与副作用
（schedule_no 自增、作废冲销分配）。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.purchase_order_guard_service import (
    PurchaseOrderGuardError,
    PurchaseOrderGuardService,
)

_SCHEMA = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, status TEXT, document_type_id INTEGER,
    purchase_org_id INTEGER, purchase_legal_entity_id INTEGER,
    supplier_party_id INTEGER, currency_id INTEGER,
    exchange_rate REAL, exchange_rate_type TEXT, exchange_rate_date TEXT,
    approval_status TEXT
);
CREATE TABLE purchase_order_lines (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_no TEXT, line_type_id INTEGER,
    item_id INTEGER, uom_id INTEGER, qty REAL, unit_price REAL, tax_code_id INTEGER,
    tax_rate_percent REAL, tax_recoverable INTEGER DEFAULT 1,
    parent_line_id INTEGER, pricing_mode TEXT,
    status TEXT DEFAULT 'open'
);
CREATE TABLE purchase_order_schedules (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_id INTEGER, schedule_no INTEGER,
    schedule_kind TEXT DEFAULT 'delivery', promised_date TEXT, promised_qty REAL,
    received_qty REAL, status TEXT DEFAULT 'planned'
);
CREATE TABLE demand_allocations (
    id INTEGER PRIMARY KEY, demand_bo TEXT, demand_id INTEGER, demand_line_id INTEGER,
    target_bo TEXT, target_id INTEGER, target_line_id INTEGER,
    target_schedule_id INTEGER, qty REAL, status TEXT, reversed_at TEXT
);
"""


class _MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    connection.executescript(_SCHEMA)
    yield connection
    connection.close()


@pytest.fixture
def ds(conn):
    return _MemDS(conn)


def _expect_rule(call, rule):
    with pytest.raises(PurchaseOrderGuardError) as caught:
        call()
    assert caught.value.rule == rule


def _insert_order(conn, order_id=1):
    conn.execute(
        "INSERT INTO purchase_orders (id, order_no, status) VALUES (?, 'PO-001', 'draft')",
        [order_id])


def _insert_line(conn, line_id=10, order_id=1, qty=10.0):
    conn.execute(
        'INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, '
        'item_id, uom_id, qty, pricing_mode) '
        "VALUES (?, ?, '10', 111, 100, 1, ?, 'standalone')",
        [line_id, order_id, qty])


def _schedule(**overrides):
    row = {
        'id': None, 'order_id': 1, 'line_id': 10, 'schedule_no': None,
        'schedule_kind': 'delivery', 'promised_date': '2026-11-10',
        'promised_qty': 2.0, 'status': 'planned',
    }
    row.update(overrides)
    return row


def _insert_schedule(conn, schedule_id, line_id=10, order_id=1, schedule_no=1,
                     promised_qty=2.0, status='planned'):
    conn.execute(
        'INSERT INTO purchase_order_schedules (id, order_id, line_id, schedule_no, '
        'schedule_kind, promised_date, promised_qty, status) '
        "VALUES (?, ?, ?, ?, 'delivery', '2026-11-10', ?, ?)",
        [schedule_id, order_id, line_id, schedule_no, promised_qty, status])


# ---------------- 序号 ----------------

def test_schedule_no_auto_increment(conn, ds):
    _insert_line(conn)
    guard = PurchaseOrderGuardService(ds)
    data = _schedule()
    guard.validate_schedule_write(data, is_create=True)
    assert data['schedule_no'] == 1

    _insert_schedule(conn, schedule_id=1, schedule_no=1)
    second = _schedule()
    guard.validate_schedule_write(second, is_create=True)
    assert second['schedule_no'] == 2


def test_schedule_no_duplicated(conn, ds):
    _insert_line(conn)
    _insert_schedule(conn, schedule_id=1, schedule_no=1)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(schedule_no=1), is_create=True), 'PO_SCHEDULE_NO_DUPLICATED')


def test_schedule_no_must_be_integer(conn, ds):
    _insert_line(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(schedule_no='abc'), is_create=True), 'PO_SCHEDULE_NO_INVALID')


# ---------------- 父键 / 必填 ----------------

def test_schedule_order_must_match_line(conn, ds):
    _insert_line(conn, line_id=10, order_id=2)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(order_id=1), is_create=True), 'PO_SCHEDULE_ORDER_MISMATCH')


def test_schedule_requires_parent_line(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(line_id=None), is_create=True), 'PO_SCHEDULE_PARENT_REQUIRED')


def test_schedule_requires_promised_date(conn, ds):
    _insert_line(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(promised_date=None), is_create=True),
        'PO_SCHEDULE_DATE_REQUIRED')


def test_schedule_requires_positive_qty(conn, ds):
    _insert_line(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(promised_qty=0), is_create=True), 'PO_SCHEDULE_QTY_POSITIVE')


# ---------------- 数量上限 ----------------

def test_schedule_total_must_not_exceed_line_qty(conn, ds):
    _insert_line(conn, qty=10)
    _insert_schedule(conn, schedule_id=1, schedule_no=1, promised_qty=6)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        _schedule(schedule_no=2, promised_qty=5), is_create=True),
        'PO_SCHEDULE_QTY_EXCEEDED')


def test_schedule_update_excludes_self_from_cap(conn, ds):
    _insert_line(conn, qty=10)
    _insert_schedule(conn, schedule_id=1, schedule_no=1, promised_qty=6)
    guard = PurchaseOrderGuardService(ds)
    old = _schedule(id=1, schedule_no=1, promised_qty=6)
    guard.validate_schedule_write(
        dict(old, promised_qty=10), old_data=old, is_create=False)


# ---------------- 状态 ----------------

def test_schedule_status_transition(conn, ds):
    _insert_line(conn)
    old = _schedule(id=1, status='planned')
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_write(
        dict(old, status='completed'), old_data=old, is_create=False),
        'PO_SCHEDULE_STATUS_TRANSITION_INVALID')


def test_schedule_planned_can_be_cancelled(conn, ds):
    _insert_line(conn)
    old = _schedule(id=1, status='planned')
    guard = PurchaseOrderGuardService(ds)
    guard.validate_schedule_write(
        dict(old, status='cancelled'), old_data=old, is_create=False)


def test_schedule_delete_only_planned(conn, ds):
    _insert_line(conn)
    _insert_schedule(conn, schedule_id=1, status='confirmed')
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_delete(1),
                 'PO_SCHEDULE_DELETE_NOT_PLANNED')


def test_schedule_delete_blocked_by_active_allocation(conn, ds):
    _insert_line(conn)
    _insert_schedule(conn, schedule_id=1, status='planned')
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, target_schedule_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 1, 1, 'active')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_schedule_delete(1),
                 'PO_SCHEDULE_HAS_ACTIVE_ALLOCATION')


def test_scheduled_cancel_reverses_allocations(conn, ds):
    """R-PO-10：计划行作废 → 其 active 分配置 reversed 并写 reversed_at。"""
    _insert_line(conn)
    _insert_schedule(conn, schedule_id=1, schedule_no=1, status='planned')
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, target_schedule_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 1, 1, 'active')")
    guard = PurchaseOrderGuardService(ds)
    old = _schedule(id=1, schedule_no=1, status='planned')
    guard.validate_schedule_write(
        dict(old, status='cancelled'), old_data=old, is_create=False)

    row = ds.query('SELECT status, reversed_at FROM demand_allocations WHERE id = 1')[0]
    assert row['status'] == 'reversed'
    assert row['reversed_at']
