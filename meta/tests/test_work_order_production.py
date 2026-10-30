# -*- coding: utf-8 -*-
"""生产工单 / 组件展开测试（批次 4a：T4.1 / T4.2 / T4.3）

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
      §10.15 作业层统一契约 / §10.16 生产 → 出库 → 发运对象链

测试策略:
  · 内存 SQLite 真 SQL：组件展开依赖真 SQL（ORDER BY / DELETE / 有效期过滤）
  · 生产路径断言「无 SLA 副作用」：不写 sla_milestones / service_events，
    change_events 只写 1 条；不推进 fulfillment_status（INV-1）
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.work_order_service import (
    WorkOrderError,
    WorkOrderService,
)

_SCHEMA = """
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    promised_date TEXT,
    promised_qty REAL,
    status TEXT,
    delivered_qty REAL DEFAULT 0,
    updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    item_id INTEGER,
    qty REAL,
    fulfillment_status TEXT DEFAULT 'not_started',
    updated_at TEXT
);
CREATE TABLE sales_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    order_date TEXT,
    customer_account_id INTEGER
);
CREATE TABLE customer_accounts (
    id INTEGER PRIMARY KEY,
    name TEXT
);
CREATE TABLE calendars (
    id INTEGER PRIMARY KEY,
    day_mask_mon INTEGER DEFAULT 1,
    day_mask_tue INTEGER DEFAULT 1,
    day_mask_wed INTEGER DEFAULT 1,
    day_mask_thu INTEGER DEFAULT 1,
    day_mask_fri INTEGER DEFAULT 1,
    day_mask_sat INTEGER DEFAULT 0,
    day_mask_sun INTEGER DEFAULT 0
);
CREATE TABLE calendar_days (
    id INTEGER PRIMARY KEY,
    calendar_id INTEGER,
    date TEXT,
    day_type TEXT
);
CREATE TABLE sla_coverages (
    id INTEGER PRIMARY KEY,
    name TEXT,
    org_id INTEGER,
    calendar_id INTEGER,
    start_date TEXT,
    end_date TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE sla_coverage_rules (
    id INTEGER PRIMARY KEY,
    coverage_id INTEGER,
    severity TEXT,
    channel TEXT,
    first_response_minutes INTEGER,
    first_response_warn_minutes INTEGER,
    resolution_minutes INTEGER,
    resolution_warn_minutes INTEGER,
    seq INTEGER DEFAULT 0
);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no TEXT,
    order_type TEXT,
    schedule_id INTEGER,
    order_id INTEGER,
    order_line_id INTEGER,
    customer_account_id INTEGER,
    severity TEXT,
    channel TEXT,
    status TEXT,
    coverage_id INTEGER,
    asset_ref TEXT,
    source_demand_type TEXT,
    source_demand_id INTEGER,
    opened_at TEXT,
    first_response_at TEXT,
    resolved_at TEXT,
    closed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE work_order_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER,
    structure_id INTEGER,
    structure_line_id INTEGER,
    component_item_id INTEGER,
    line_no INTEGER,
    qty_per REAL,
    fixed_qty REAL,
    scrap_rate REAL,
    qty_required REAL,
    optional_flag INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE item_structures (
    id INTEGER PRIMARY KEY,
    item_id INTEGER,
    usage TEXT,
    alternative_no INTEGER DEFAULT 1,
    revision TEXT,
    base_qty REAL DEFAULT 1,
    status TEXT DEFAULT 'active',
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE item_structure_lines (
    id INTEGER PRIMARY KEY,
    structure_id INTEGER,
    line_no INTEGER,
    component_item_id INTEGER,
    qty_per REAL,
    fixed_qty REAL,
    scrap_rate REAL DEFAULT 0,
    optional_flag INTEGER DEFAULT 0,
    default_qty REAL,
    min_qty REAL,
    max_qty REAL,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE sla_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER,
    milestone_type TEXT,
    state TEXT,
    due_at TEXT,
    warn_at TEXT,
    started_at TEXT,
    paused_total_minutes INTEGER DEFAULT 0,
    completed_at TEXT,
    warned_at TEXT,
    breached_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE service_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER,
    event_type TEXT,
    occurred_at TEXT,
    actor TEXT,
    payload TEXT,
    note TEXT,
    created_at TEXT
);
CREATE TABLE change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT,
    object_id INTEGER,
    event_type TEXT,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    status TEXT,
    created_at TEXT
);
"""


class _MemDS:
    """sqlite3 内存库透传（query 返回 list[dict]，execute 返回 cursor）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cursor = self.conn.execute(sql, params or [])
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO sales_orders (id, order_no, order_date, customer_account_id) "
        "VALUES (10, 'SO-001', '2026-10-01', 7)")
    conn.execute("INSERT INTO customer_accounts (id, name) VALUES (7, '测试客户')")
    conn.execute(
        "INSERT INTO sales_order_lines (id, order_id, item_id, qty, fulfillment_status) "
        "VALUES (100, 10, NULL, NULL, 'not_started')")
    return conn


def _svc(conn):
    return WorkOrderService(_MemDS(conn))


def _set_line_item(conn, lid=100, item_id=500, qty=5):
    """订单行补物料 / 数量（组件展开由需求来源自动推导）。"""
    conn.execute(
        "UPDATE sales_order_lines SET item_id = ?, qty = ? WHERE id = ?",
        [item_id, qty, lid])


def _add_schedule(conn, sid=1, oid=10, lid=100, kind='delivery',
                  status='planned', promised='2026-11-05', promised_qty=None):
    conn.execute(
        "INSERT INTO sales_order_schedules "
        "(id, order_id, line_id, schedule_kind, promised_date, promised_qty, "
        "status, delivered_qty, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, '2026-10-01')",
        [sid, oid, lid, kind, promised, promised_qty, status])


def _add_sla_rule(conn, severity='high'):
    conn.execute(
        "INSERT INTO sla_coverages (id, name, active) VALUES (1, '默认SLA', 1)")
    conn.execute(
        "INSERT INTO sla_coverage_rules "
        "(id, coverage_id, severity, channel, first_response_minutes, "
        "first_response_warn_minutes, resolution_minutes, "
        "resolution_warn_minutes, seq) VALUES (1, 1, ?, NULL, 60, 10, 480, 60, 1)",
        [severity])


def _add_structure(conn, sid=1, item_id=500, usage='production',
                   alternative_no=1, revision='A', status='active',
                   valid_from='2026-01-01', valid_to=None):
    conn.execute(
        "INSERT INTO item_structures "
        "(id, item_id, usage, alternative_no, revision, base_qty, status, "
        "valid_from, valid_to) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
        [sid, item_id, usage, alternative_no, revision, status,
         valid_from, valid_to])


def _add_line(conn, lid, structure_id, component_item_id, qty_per=None,
              fixed_qty=None, scrap_rate=0, optional_flag=0,
              default_qty=None, min_qty=None, max_qty=None,
              line_no=None, valid_from=None, valid_to=None):
    conn.execute(
        "INSERT INTO item_structure_lines "
        "(id, structure_id, line_no, component_item_id, qty_per, fixed_qty, "
        "scrap_rate, optional_flag, default_qty, min_qty, max_qty, "
        "valid_from, valid_to) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [lid, structure_id, line_no if line_no is not None else lid,
         component_item_id, qty_per, fixed_qty, scrap_rate, optional_flag,
         default_qty, min_qty, max_qty, valid_from, valid_to])


def _row(conn, sql, params=()):
    rows = conn.execute(sql, list(params)).fetchall()
    return rows


def _count(conn, table, where='', params=()):
    sql = 'SELECT COUNT(*) FROM %s' % table
    if where:
        sql += ' WHERE ' + where
    return conn.execute(sql, list(params)).fetchone()[0]


def _create(conn, **over):
    payload = {'order_type': 'production',
               'source_demand_type': 'sales_order_line',
               'source_demand_id': 100}
    payload.update(over)
    return _svc(conn).create_work_order(payload)


# --------------------------------------------------------------- service 回归


def test_service_path_behavior_unchanged():
    conn = _db()
    _add_schedule(conn, kind='service')
    _add_sla_rule(conn)

    result = _svc(conn).create_work_order({
        'schedule_id': 1, 'severity': 'high',
        'opened_at': '2026-10-30 09:00:00'})

    assert result['sla']['code'] is None
    assert len(result['sla']['milestones']) == 2
    row = _row(conn, 'SELECT * FROM work_orders WHERE id = ?', [result['id']])[0]
    columns = ('id', 'work_order_no', 'order_type', 'schedule_id', 'order_id',
               'order_line_id', 'customer_account_id', 'severity', 'channel',
               'status', 'coverage_id', 'asset_ref', 'source_demand_type',
               'source_demand_id', 'opened_at', 'first_response_at',
               'resolved_at', 'closed_at', 'created_at', 'updated_at')
    record = dict(zip(columns, row))
    assert record['order_type'] == 'service'
    assert record['schedule_id'] == 1
    assert record['source_demand_type'] is None
    assert record['source_demand_id'] is None
    assert _count(conn, 'sla_milestones') == 2
    assert _count(conn, 'service_events') >= 1
    assert _count(conn, 'change_events') == 1


# --------------------------------------------------------------- 生产守卫


def test_production_requires_source_demand():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _svc(conn).create_work_order({'order_type': 'production'})
    assert err.value.rule == 'ST_SOURCE_DEMAND_REQUIRED'

    with pytest.raises(WorkOrderError) as err:
        _create(conn, source_demand_type='purchase_order')
    assert err.value.rule == 'ST_SOURCE_DEMAND_REQUIRED'


def test_production_rejects_asset_and_sla():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _create(conn, asset_ref='SN-001')
    assert err.value.rule == 'ST_ASSET_NOT_ALLOWED'

    with pytest.raises(WorkOrderError) as err:
        _create(conn, coverage_id=1)
    assert err.value.rule == 'ST_SLA_NOT_ALLOWED'


def test_production_rejects_unknown_demand():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _create(conn, source_demand_id=999)
    assert err.value.rule == 'ST_SOURCE_DEMAND_INVALID'


def test_production_rejects_service_schedule_demand():
    conn = _db()
    _add_schedule(conn, sid=2, kind='service')
    with pytest.raises(WorkOrderError) as err:
        _create(conn, source_demand_type='sales_order_schedule',
                source_demand_id=2)
    assert err.value.rule == 'ST_SCHEDULE_INVALID'


# --------------------------------------------------------------- 生产建单


def test_production_creates_without_sla_side_effects():
    conn = _db()
    result = _create(conn)

    assert result['order_type'] == 'production'
    assert result['schedule_id'] is None
    assert result['source_demand_type'] == 'sales_order_line'
    assert result['source_demand_id'] == 100
    # 订单行无物料 / 数量 → 推导不出，记 no_structure 且不阻断建单
    assert result['component_expansion']['code'] == 'no_structure'
    assert result['component_expansion']['reason'] == 'missing_item_or_qty'

    row = _row(conn, 'SELECT * FROM work_orders WHERE id = ?', [result['id']])[0]
    columns = ('id', 'work_order_no', 'order_type', 'schedule_id', 'order_id',
               'order_line_id', 'customer_account_id', 'severity', 'channel',
               'status', 'coverage_id', 'asset_ref', 'source_demand_type',
               'source_demand_id', 'opened_at', 'first_response_at',
               'resolved_at', 'closed_at', 'created_at', 'updated_at')
    record = dict(zip(columns, row))
    assert record['order_type'] == 'production'
    assert record['order_id'] == 10
    assert record['order_line_id'] == 100
    assert record['customer_account_id'] == 7
    assert record['severity'] is None
    assert record['coverage_id'] is None
    assert record['asset_ref'] is None
    assert record['status'] == 'New'

    # P-3：无 SLA 副作用
    assert _count(conn, 'sla_milestones') == 0
    assert _count(conn, 'service_events') == 0
    assert _count(conn, 'change_events') == 1
    # INV-1：不推进履约状态
    status = conn.execute(
        "SELECT fulfillment_status FROM sales_order_lines WHERE id = 100"
    ).fetchone()[0]
    assert status == 'not_started'


def test_production_schedule_demand_backfills_order_line():
    conn = _db()
    _add_schedule(conn, sid=3, kind='delivery', lid=100)
    result = _create(conn, source_demand_type='sales_order_schedule',
                     source_demand_id=3)
    row = _row(conn, 'SELECT order_id, order_line_id FROM work_orders WHERE id = ?',
               [result['id']])[0]
    assert row[0] == 10
    assert row[1] == 100


# --------------------------------------------------------------- 组件展开


def test_production_creation_expands_components():
    conn = _db()
    _add_structure(conn, sid=1, item_id=500)
    _add_line(conn, 11, 1, 501, qty_per=2, fixed_qty=1, scrap_rate=0.1, line_no=10)
    _add_line(conn, 12, 1, 502, optional_flag=1, default_qty=3, min_qty=1,
              max_qty=5, scrap_rate=0, line_no=20)
    # 订单行带物料 / 数量 → 建单时由需求来源自动推导并展开（无需 payload 传参）
    _set_line_item(conn, item_id=500, qty=5)

    result = _create(conn)

    assert result['item_id'] == 500
    assert result['qty'] == 5
    assert result['component_expansion']['code'] == 'expanded'
    assert result['component_expansion']['count'] == 2
    assert result['component_expansion']['structure_id'] == 1

    rows = {
        row[0]: row[1]
        for row in conn.execute(
            'SELECT component_item_id, qty_required FROM work_order_components '
            'WHERE work_order_id = ?', [result['id']]).fetchall()
    }
    # (2 × 5 + 1) × 1.1 = 12.1；optional 行取 default_qty=3
    assert rows[501] == pytest.approx(12.1)
    assert rows[502] == pytest.approx(3.0)


def test_production_schedule_demand_uses_promised_qty():
    conn = _db()
    _set_line_item(conn, item_id=500, qty=3)
    _add_schedule(conn, sid=3, kind='delivery', lid=100, promised_qty=10)
    _add_structure(conn, sid=1, item_id=500)
    _add_line(conn, 11, 1, 501, qty_per=2, line_no=10)

    result = _create(conn, source_demand_type='sales_order_schedule',
                     source_demand_id=3)

    assert result['item_id'] == 500
    assert result['qty'] == 10
    assert result['component_expansion']['code'] == 'expanded'
    qty = conn.execute(
        'SELECT qty_required FROM work_order_components WHERE work_order_id = ?',
        [result['id']]).fetchone()[0]
    assert qty == pytest.approx(20.0)  # 2 × promised_qty 10


def test_production_schedule_demand_falls_back_to_line_qty():
    conn = _db()
    _set_line_item(conn, item_id=500, qty=4)
    _add_schedule(conn, sid=4, kind='delivery', lid=100)  # promised_qty 为空
    _add_structure(conn, sid=1, item_id=500)
    _add_line(conn, 11, 1, 501, qty_per=1, line_no=10)

    result = _create(conn, source_demand_type='sales_order_schedule',
                     source_demand_id=4)

    assert result['qty'] == 4
    assert result['component_expansion']['code'] == 'expanded'
    qty = conn.execute(
        'SELECT qty_required FROM work_order_components WHERE work_order_id = ?',
        [result['id']]).fetchone()[0]
    assert qty == pytest.approx(4.0)


def test_expand_components_prefers_lowest_alternative_and_latest_revision():
    conn = _db()
    _add_structure(conn, sid=1, item_id=500, alternative_no=1, revision='A')
    _add_structure(conn, sid=2, item_id=500, alternative_no=1, revision='B')
    _add_structure(conn, sid=3, item_id=500, alternative_no=2, revision='C')
    _add_line(conn, 11, 2, 501, qty_per=1, line_no=10)

    result = _svc(conn).expand_components(1, 500, 3, as_of='2026-10-30')
    assert result['code'] == 'expanded'
    assert result['structure_id'] == 2
    assert len(result['components']) == 1


def test_expand_components_ignores_inactive_usage_or_expired():
    conn = _db()
    _add_structure(conn, sid=1, item_id=500, status='inactive')
    _add_structure(conn, sid=2, item_id=500, usage='engineering')
    _add_structure(conn, sid=3, item_id=500, valid_to='2026-01-31')

    for as_of in ('2026-10-30',):
        result = _svc(conn).expand_components(1, 500, 5, as_of=as_of)
        assert result['code'] == 'no_structure'
        assert result['structure_id'] is None
        assert result['components'] == []
    assert _count(conn, 'work_order_components') == 0


def test_expand_components_is_idempotent():
    conn = _db()
    _add_structure(conn, sid=1, item_id=500)
    _add_line(conn, 11, 1, 501, qty_per=2, line_no=10)
    _add_line(conn, 12, 1, 502, qty_per=1, scrap_rate=0.2, line_no=20)

    svc = _svc(conn)
    first = svc.expand_components(1, 500, 4)
    second = svc.expand_components(1, 500, 4)

    assert first['code'] == 'expanded' and second['code'] == 'expanded'
    assert _count(conn, 'work_order_components', 'work_order_id = ?', [1]) == 2
    rows = conn.execute(
        'SELECT component_item_id, qty_required FROM work_order_components '
        'WHERE work_order_id = ? ORDER BY component_item_id', [1]).fetchall()
    assert rows[0][1] == pytest.approx(8.0)   # 2 × 4
    assert rows[1][1] == pytest.approx(4.8)   # 1 × 4 × 1.2


def test_expand_components_requires_item_and_qty():
    conn = _db()
    with pytest.raises(WorkOrderError) as err:
        _svc(conn).expand_components(1, None, 5)
    assert err.value.rule == 'ST_COMPONENT_INPUT_INVALID'

    with pytest.raises(WorkOrderError) as err:
        _svc(conn).expand_components(1, 500, 'abc')
    assert err.value.rule == 'ST_COMPONENT_INPUT_INVALID'
