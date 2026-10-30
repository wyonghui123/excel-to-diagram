# -*- coding: utf-8 -*-
"""销售订单履约状态派生测试（Spec §9 验收 1~24 + §4.8 不变式 INV-1~5）

依据: docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md v0.6
      §4.2 行派生 / §4.3 抬头派生 / §4.6 Close 前置 / §4.8 不变式

测试策略:
  · 服务层：内存 SQLite 真 SQL（派生 SQL 与迁移回填 SQL 逐字同构，用真库才能验证 INV-5）
  · 守卫层：_GuardDS 按 SQL 特征片段分流（不依赖真实库）
  · INV-1：静态源码扫描（唯一写入方）
  · INV-3：直接调用 v145 迁移的 _check_inv3
"""

import importlib.util
import os
import sqlite3
from pathlib import Path

# 本文件用内存 SQLite（:memory:）验证派生 SQL 与迁移回填 SQL 同构，
# 不触碰真实库；因此绕开 conftest 的 raw SQL 拦截
# （与 test_sales_order_expand / test_sales_order_header_discount 同口径）。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.services.sales_order_fulfillment_service import (
    FULFILL_DONE,
    FULFILL_NA,
    FULFILL_NOT_STARTED,
    FULFILL_PARTIAL,
    FULFILL_VOIDED,
    SalesOrderFulfillmentService,
)
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------- 内存库 ----------------

_SCHEMA = """
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT,
    level TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    status TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_type_id INTEGER,
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
    promised_date TEXT,
    promised_qty REAL,
    delivered_qty REAL DEFAULT 0,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY,
    object_type TEXT,
    object_id INTEGER,
    action TEXT,
    parent_object_type TEXT,
    parent_object_id INTEGER,
    created_at TEXT
);
"""


class _MemDS:
    """把 sqlite3 连接适配成 DataSource 的 query / execute。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        self.conn.execute(sql, list(params or []))


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    return conn


def _add_type(conn, tid=1, code='STD', relevant=1, category='material'):
    conn.execute(
        'INSERT INTO type_definitions (id, code, level, line_category, '
        'delivery_relevant) VALUES (?, ?, ?, ?, ?)',
        [tid, code, 'line', category, relevant])


def _add_order(conn, oid, status='confirmed', fulfillment=FULFILL_NOT_STARTED):
    conn.execute(
        'INSERT INTO sales_orders (id, status, fulfillment_status) '
        'VALUES (?, ?, ?)', [oid, status, fulfillment])


def _add_line(conn, lid, order_id, type_id=1, status='open',
              fulfillment=FULFILL_NOT_STARTED):
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, line_type_id, status, '
        'fulfillment_status) VALUES (?, ?, ?, ?, ?)',
        [lid, order_id, type_id, status, fulfillment])


def _add_schedule(conn, sid, order_id, line_id, kind='delivery',
                  status='planned', qty=1.0, date='2026-11-01',
                  delivered=0.0):
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, promised_date, promised_qty, delivered_qty, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [sid, order_id, line_id, kind, date, qty, delivered, status])


def _value(conn, sql, params=None):
    return conn.execute(sql, list(params or [])).fetchone()[0]


def _audit_time(conn, offset=''):
    """生产口径：audit.created_at 是**本地时间**明文（框架 datetime.now().isoformat）。"""
    if offset:
        return _value(conn, "SELECT datetime('now','localtime','%s')" % offset)
    return _value(conn, "SELECT datetime('now','localtime')")


def _derived_time(conn, offset=''):
    """服务层口径：fulfillment_derived_at 是 **UTC** 明文（datetime('now')）。"""
    if offset:
        return _value(conn, "SELECT datetime('now','%s')" % offset)
    return _value(conn, "SELECT datetime('now')")


def _add_audit(conn, audit_id, object_type, object_id, created_at,
               action='UPDATE', parent_type=None, parent_id=None):
    conn.execute(
        'INSERT INTO audit_logs (id, object_type, object_id, action, '
        'parent_object_type, parent_object_id, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        [audit_id, object_type, object_id, action, parent_type, parent_id,
         created_at])


# ---------------- §4.2 行派生（验收 1~4） ----------------

def test_line_without_schedule_is_not_started():
    """验收 1：无 delivery 计划行 → not_started。"""
    conn = _db()
    _add_line(conn, 100, 10)
    status = SalesOrderFulfillmentService(_MemDS(conn)).recompute_line(100)
    assert status == FULFILL_NOT_STARTED
    assert _value(conn, 'SELECT fulfillment_status FROM sales_order_lines '
                        'WHERE id = 100') == FULFILL_NOT_STARTED


def test_line_all_completed_is_fulfilled():
    """验收 2：全部 completed → fulfilled。"""
    conn = _db()
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    _add_schedule(conn, 2, 10, 100, status='completed')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_line(100) \
        == FULFILL_DONE


def test_line_mixed_status_is_partial():
    """验收 3：completed + planned/confirmed → partial。"""
    conn = _db()
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    _add_schedule(conn, 2, 10, 100, status='confirmed')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_line(100) \
        == FULFILL_PARTIAL


def test_cancelled_and_billing_schedules_not_counted():
    """验收 4：cancelled 计划行 / billing 计划行不计入聚合。"""
    conn = _db()
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='cancelled')
    _add_schedule(conn, 2, 10, 100, kind='billing', status='completed')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_line(100) \
        == FULFILL_NOT_STARTED


def test_line_partially_delivered_is_partial():
    """§10.4 D10：无 completed 但 delivered_qty > 0 → partial。"""
    conn = _db()
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='confirmed', qty=100.0,
                  delivered=60.0)
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_line(100) \
        == FULFILL_PARTIAL
    assert _value(conn, 'SELECT fulfillment_status FROM sales_order_lines '
                        'WHERE id = 100') == FULFILL_PARTIAL


def test_line_zero_delivered_stays_not_started():
    """§10.4 D10 回归：delivered_qty 为 0 / 空 → 仍 not_started。"""
    conn = _db()
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='planned', qty=100.0,
                  delivered=0.0)
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_line(100) \
        == FULFILL_NOT_STARTED


# ---------------- §4.3 抬头派生（验收 5~7 + 21） ----------------

def test_order_all_lines_fulfilled():
    """验收 5：所有行 fulfilled → 抬头 fulfilled。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_line(conn, 101, 10)
    for sid, lid in ((1, 100), (2, 101)):
        _add_schedule(conn, sid, 10, lid, status='completed')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(10) \
        == FULFILL_DONE
    assert _value(conn, 'SELECT fulfillment_status FROM sales_orders '
                        'WHERE id = 10') == FULFILL_DONE


def test_order_mixed_lines_is_partial():
    """验收 6：一行 fulfilled、一行 partial → 抬头 partial。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_line(conn, 101, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    _add_schedule(conn, 2, 10, 101, status='completed')
    _add_schedule(conn, 3, 10, 101, status='planned')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(10) \
        == FULFILL_PARTIAL


def test_order_all_lines_cancelled_is_voided():
    """验收 7 / INV-4：所有行 cancelled → voided。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10, status='cancelled')
    _add_line(conn, 101, 10, status='cancelled')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(10) \
        == FULFILL_VOIDED


def test_order_not_voided_when_active_line_exists():
    """INV-4 反向：只要还有 active 行（open）就不为 voided。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10, status='cancelled')
    _add_line(conn, 101, 10, status='open')
    assert SalesOrderFulfillmentService(_MemDS(conn)).recompute_order(10) \
        != FULFILL_VOIDED


# ---------------- §4.6 Close 前置（验收 9 / 17） ----------------

class _GuardDS:
    """按 SQL 特征片段分流。顺序敏感：履约状态查询必须先于通用订单查询。"""

    def __init__(self, fulfillment=None, line=None, order=None,
                 delivery_sum=0.0):
        self.fulfillment = fulfillment
        self.line = line
        self.order = order
        self.delivery_sum = delivery_sum

    def query(self, sql, params=None):
        if 'SELECT fulfillment_status FROM sales_orders' in sql:
            if self.fulfillment is None:
                return []
            return [{'fulfillment_status': self.fulfillment}]
        if 'FROM sales_order_lines l' in sql:
            return [self.line] if self.line else []
        if 'COALESCE(SUM(promised_qty)' in sql:
            return [{'qty': self.delivery_sum}]
        if 'FROM sales_orders WHERE id' in sql:
            return [self.order] if self.order else []
        raise AssertionError('unexpected sql: %s' % sql)


def _close(order_fulfillment):
    SalesOrderGuardService(
        _GuardDS(fulfillment=order_fulfillment)).validate_order_write(
            {'id': 1, 'status': 'closed'},
            old_data={'status': 'confirmed'}, is_create=False)


def test_close_rejected_when_not_fulfilled():
    """验收 9：履约未完成的订单不得关闭。"""
    for status in (FULFILL_NOT_STARTED, FULFILL_PARTIAL):
        with pytest.raises(SalesOrderGuardError) as exc:
            _close(status)
        assert exc.value.rule == 'ORDER_NOT_FULFILLED'
        assert exc.value.field_name == 'fulfillment_status'


@pytest.mark.parametrize('status', [FULFILL_DONE, FULFILL_VOIDED, FULFILL_NA])
def test_close_allowed_for_terminal_fulfillment(status):
    """验收 9 / 17：fulfilled / voided / not_applicable 放行（FR-006）。"""
    _close(status)


def test_close_fail_open_when_read_fails():
    """读不到履约状态时 fail-open，不阻断关闭。"""
    _close(None)


def test_service_line_not_applicable_does_not_block_close():
    """验收 17：纯服务行（delivery_relevant=false）派生 not_applicable。"""
    conn = _db()
    _add_type(conn, tid=1, code='SVC', relevant=0, category='service')
    _add_order(conn, 10)
    _add_line(conn, 100, 10, type_id=1)
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    assert svc.recompute_line(100) == FULFILL_NA
    # 抬头：唯一的 active 行 not_applicable → 抬头 not_applicable
    assert svc.recompute_order(10) == FULFILL_NA
    _close(FULFILL_NA)


# ---------------- R-SCH-16 交货相关性（验收 15 / 16） ----------------

def _schedule_guard(line):
    return SalesOrderGuardService(_GuardDS(
        order={'id': 10, 'status': 'draft'}, line=line))


def _schedule_payload():
    return {
        'schedule_no': 10,
        'line_id': 100,
        'order_id': 10,
        'schedule_kind': 'delivery',
        'promised_date': '2026-11-01',
        'promised_qty': 3,
        'plant_location_id': 900,
        'status': 'planned',
    }


def test_delivery_schedule_rejected_for_not_delivery_relevant_line():
    """验收 15：delivery_relevant=false 的行不得建 delivery 计划行。"""
    line = {'id': 100, 'order_id': 10, 'qty': 10, 'uom_id': 8,
            'plant_location_id': 900, 'delivery_relevant': 0}
    with pytest.raises(SalesOrderGuardError) as exc:
        _schedule_guard(line).validate_schedule_write(_schedule_payload())
    assert exc.value.rule == 'SCHEDULE_NOT_DELIVERY_RELEVANT'


def test_delivery_schedule_allowed_for_delivery_relevant_line():
    """验收 16：delivery_relevant=true 的行正常放行。"""
    line = {'id': 100, 'order_id': 10, 'qty': 10, 'uom_id': 8,
            'plant_location_id': 900, 'delivery_relevant': 1}
    _schedule_guard(line).validate_schedule_write(_schedule_payload())


# ---------------- INV-5 / 验收 10 / 11 / 19 ----------------

def test_recompute_all_is_idempotent():
    """验收 10：连续两次全量重算，第二次零写入。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_line(conn, 101, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))

    first = svc.recompute_all()
    assert first['orders'] == 1
    # 行 101 无计划行 → 派生值与默认值 same（not_started），不落库
    assert first['lines_written'] == 1
    assert first['orders_written'] == 1

    second = svc.recompute_all()
    assert second['lines_written'] == 0
    assert second['orders_written'] == 0


def test_recompute_all_repairs_drift():
    """验收 11 / 19：派生值被篡改后，全量重算能发现并修复。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    conn.execute("UPDATE sales_order_lines SET fulfillment_status = 'partial' "
                 'WHERE id = 100')
    conn.execute("UPDATE sales_orders SET fulfillment_status = 'not_started' "
                 'WHERE id = 10')

    stats = svc.recompute_all()
    assert stats['lines_written'] == 1
    assert stats['orders_written'] == 1
    assert _value(conn, 'SELECT fulfillment_status FROM sales_order_lines '
                        'WHERE id = 100') == FULFILL_DONE
    assert _value(conn, 'SELECT fulfillment_status FROM sales_orders '
                        'WHERE id = 10') == FULFILL_DONE


def test_check_drift_clean_data_reports_nothing():
    """验收 11：干净数据巡检零漂移。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    report = svc.check_drift()
    assert report['lines'] == []
    assert report['orders'] == []
    assert report['scanned'] == {'orders': 1, 'lines': 1}


def test_check_drift_reports_tampered_line_and_order():
    """验收 11：人为篡改行 / 抬头后，巡检报出不一致且不改库。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    conn.execute("UPDATE sales_order_lines SET fulfillment_status = 'partial' "
                 'WHERE id = 100')
    conn.execute("UPDATE sales_orders SET fulfillment_status = 'not_started' "
                 'WHERE id = 10')

    report = svc.check_drift()
    assert report['lines'] == [{'line_id': 100, 'order_id': 10,
                               'stored': FULFILL_PARTIAL,
                               'expected': FULFILL_DONE}]
    assert report['orders'] == [{'order_id': 10,
                                 'stored': FULFILL_NOT_STARTED,
                                 'expected': FULFILL_DONE}]
    # 只读：巡检后库中仍是篡改值
    assert _value(conn, 'SELECT fulfillment_status FROM sales_order_lines '
                        'WHERE id = 100') == FULFILL_PARTIAL
    assert _value(conn, 'SELECT fulfillment_status FROM sales_orders '
                        'WHERE id = 10') == FULFILL_NOT_STARTED


def test_check_drift_scoped_to_single_order():
    """验收 11：指定 order_id 只扫该订单。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    _add_order(conn, 20)
    _add_line(conn, 200, 20)
    _add_schedule(conn, 2, 20, 200, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    conn.execute("UPDATE sales_order_lines SET fulfillment_status = 'partial' "
                 'WHERE id IN (100, 200)')

    report = svc.check_drift(order_id=10)
    assert [x['line_id'] for x in report['lines']] == [100]
    assert report['scanned'] == {'orders': 1, 'lines': 1}


# ---------------- FR-011 派生时间戳 / 陈旧判定 ----------------

def test_recompute_refreshes_derived_at_even_without_value_change():
    """FR-011：派生值未变也刷新 fulfillment_derived_at（只动时间戳，不动状态）。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    conn.execute("UPDATE sales_order_lines SET fulfillment_derived_at = "
                 "'2000-01-01 00:00:00' WHERE id = 100")
    conn.execute("UPDATE sales_orders SET fulfillment_derived_at = "
                 "'2000-01-01 00:00:00' WHERE id = 10")

    stats = SalesOrderFulfillmentService(_MemDS(conn)).recompute_all()

    # 状态值本就一致 → 不落状态；但时间戳被刷新
    assert stats['lines_written'] == 0
    assert stats['orders_written'] == 0
    assert _value(conn, 'SELECT fulfillment_derived_at FROM sales_order_lines '
                        'WHERE id = 100') != '2000-01-01 00:00:00'
    assert _value(conn, 'SELECT fulfillment_derived_at FROM sales_orders '
                        'WHERE id = 10') != '2000-01-01 00:00:00'


def test_check_drift_flags_stale_line_and_order():
    """FR-011：派生之后又有审计变更 → 行 / 抬头判为陈旧，且不与漂移混淆。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    old = _derived_time(conn, '-1 hour')
    conn.execute('UPDATE sales_order_lines SET fulfillment_derived_at = ? '
                 'WHERE id = 100', [old])
    conn.execute('UPDATE sales_orders SET fulfillment_derived_at = ? '
                 'WHERE id = 10', [old])
    _add_audit(conn, 1, 'sales_order_line', 100, _audit_time(conn),
               parent_type='sales_order', parent_id=10)

    report = svc.check_drift()

    assert [x['line_id'] for x in report['stale']['lines']] == [100]
    assert [x['order_id'] for x in report['stale']['orders']] == [10]
    assert report['stale']['lines'][0]['order_id'] == 10
    # 陈旧 ≠ 漂移：状态值本身一致
    assert report['lines'] == []
    assert report['orders'] == []


def test_check_drift_not_stale_when_derived_after_change():
    """FR-011：审计变更早于派生确认 → 不判陈旧。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    _add_audit(conn, 1, 'sales_order_line', 100, _audit_time(conn, '-2 hours'),
               parent_type='sales_order', parent_id=10)

    report = svc.check_drift()
    assert report['stale'] == {'lines': [], 'orders': []}


def test_check_drift_stale_from_delivery_schedule_change():
    """FR-011：delivery 计划行变更也计入其所属行的水位。"""
    conn = _db()
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='planned')
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    old = _derived_time(conn, '-1 hour')
    conn.execute('UPDATE sales_order_lines SET fulfillment_derived_at = ? '
                 'WHERE id = 100', [old])
    conn.execute('UPDATE sales_orders SET fulfillment_derived_at = ? '
                 'WHERE id = 10', [old])
    _add_audit(conn, 1, 'sales_order_schedule', 1, _audit_time(conn),
               action='CREATE', parent_type='sales_order', parent_id=10)

    report = svc.check_drift()
    assert [x['line_id'] for x in report['stale']['lines']] == [100]
    assert [x['order_id'] for x in report['stale']['orders']] == [10]


def test_check_drift_stale_degrades_when_audit_missing():
    """审计表缺失时陈旧判定降级为空，漂移巡检不受影响。"""
    conn = _db()
    conn.execute('DROP TABLE audit_logs')
    _add_order(conn, 10)
    _add_line(conn, 100, 10)
    svc = SalesOrderFulfillmentService(_MemDS(conn))
    svc.recompute_all()

    report = svc.check_drift()
    assert report['stale'] == {'lines': [], 'orders': []}
    assert report['scanned'] == {'orders': 1, 'lines': 1}


# ---------------- INV-1 唯一写入方（验收 18） ----------------

def _scan_set_fulfillment():
    """扫描 meta/ 下（排除 tests / migrations）的 `SET fulfillment_status`。"""
    hits = set()
    for path in (REPO_ROOT / 'meta').rglob('*.py'):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if '/tests/' in '/' + rel or '/migrations/' in '/' + rel:
            continue
        text = path.read_text(encoding='utf-8')
        if 'SET fulfillment_status' in text:
            hits.add(rel)
    return hits


def test_inv1_single_writer():
    """验收 18 / INV-1：fulfillment_status 只有服务层一个写入方。"""
    assert _scan_set_fulfillment() == {
        'meta/services/sales_order_fulfillment_service.py'}


# ---------------- INV-3（验收 20） ----------------

def _load_v145():
    path = REPO_ROOT / 'meta/migrations/v145__sales_order_fulfillment_status.py'
    spec = importlib.util.spec_from_file_location('v145_fulfillment', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inv3_flags_delivery_schedule_on_not_delivery_relevant_line():
    """验收 20 / INV-3：delivery_relevant=0 的行存在 delivery 计划行 → 报出。"""
    v145 = _load_v145()
    conn = _db()
    _add_type(conn, tid=1, code='SVC', relevant=0, category='service')
    _add_line(conn, 100, 10, type_id=1)
    _add_schedule(conn, 1, 10, 100, kind='delivery', status='planned')
    assert v145._check_inv3(conn) != []


def test_inv3_passes_for_clean_data():
    """INV-3 干净数据（不交货相关的行只有 billing 计划行）不报出。"""
    v145 = _load_v145()
    conn = _db()
    _add_type(conn, tid=1, code='SVC', relevant=0, category='service')
    _add_line(conn, 100, 10, type_id=1)
    _add_schedule(conn, 1, 10, 100, kind='billing', status='planned')
    assert v145._check_inv3(conn) == []


# ---------------- 审计排除（验收 22） ----------------

@pytest.mark.parametrize('name', ['sales_order.yaml', 'sales_order_line.yaml'])
def test_audit_update_excludes_fulfillment_status(name):
    """验收 22 / FR-011：派生字段不进审计（事实源在计划行审计）。"""
    data = yaml.safe_load(
        (REPO_ROOT / 'meta/schemas' / name).read_text(encoding='utf-8'))
    exclude = data['audit']['update']['exclude']
    assert 'fulfillment_status' in exclude
    assert 'fulfillment_derived_at' in exclude


# ---------------- 取消级联 FR-014（验收 23 / 24） ----------------

def test_cascade_cancel_cancels_lines_and_pending_schedules():
    """验收 23：取消订单 → 行与未终态 delivery 计划行置 cancelled，抬头 voided。"""
    conn = _db()
    _add_order(conn, 10, status='confirmed')
    _add_line(conn, 100, 10)
    _add_line(conn, 101, 10)
    _add_schedule(conn, 1, 10, 100, status='planned')
    _add_schedule(conn, 2, 10, 101, status='confirmed')
    _add_schedule(conn, 3, 10, 101, kind='billing', status='planned')

    result = SalesOrderFulfillmentService(_MemDS(conn)).cascade_cancel(10)

    assert result['lines_cancelled'] == 2
    assert result['schedules_cancelled'] == 2
    assert result['fulfillment_status'] == FULFILL_VOIDED
    assert _value(conn, "SELECT COUNT(*) FROM sales_order_lines "
                        "WHERE order_id = 10 AND status = 'cancelled'") == 2
    # delivery 计划行全部 cancelled；billing 计划行不受影响
    assert _value(conn, "SELECT COUNT(*) FROM sales_order_schedules "
                        "WHERE order_id = 10 AND schedule_kind = 'delivery' "
                        "AND status <> 'cancelled'") == 0
    assert _value(conn, "SELECT status FROM sales_order_schedules "
                        'WHERE id = 3') == 'planned'
    assert _value(conn, 'SELECT fulfillment_status FROM sales_orders '
                        'WHERE id = 10') == FULFILL_VOIDED


def test_cascade_cancel_keeps_completed_schedules():
    """验收 24：已 completed 的 delivery 计划行保持 completed（交付事实不可改写）。"""
    conn = _db()
    _add_order(conn, 10, status='confirmed')
    _add_line(conn, 100, 10)
    _add_schedule(conn, 1, 10, 100, status='completed')
    _add_schedule(conn, 2, 10, 100, status='planned')

    SalesOrderFulfillmentService(_MemDS(conn)).cascade_cancel(10)

    assert _value(conn, 'SELECT status FROM sales_order_schedules '
                        'WHERE id = 1') == 'completed'
    assert _value(conn, 'SELECT status FROM sales_order_schedules '
                        'WHERE id = 2') == 'cancelled'
