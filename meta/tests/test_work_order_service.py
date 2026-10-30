# -*- coding: utf-8 -*-
"""服务工单 / SLA 服务测试（B6 验收第 1-6、8 条）

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
      §10.5 对象模型 / §10.6 状态机与 SLA 规则 / §10.7 接线 / §10.10 B6 验收

测试策略:
  · 内存 SQLite 真 SQL：SLA 里程碑、暂停顺延、结算回写都依赖真 SQL 才能验
  · 业务日历用 `calendars`（周模式）+ `calendar_days`（例外日）两张真表
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.work_order_service import (
    MILESTONE_FIRST_RESPONSE,
    MILESTONE_RESOLUTION,
    SERVICE_STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    STATUS_WAITING,
    WorkOrderError,
    WorkOrderService,
)

_ORDER_ID = 10
_ORDER_LINE_ID = 100
_SCHEDULE_ID = 1

_SCHEMA = """
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    promised_date TEXT,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    fulfillment_status TEXT DEFAULT 'not_started',
    updated_at TEXT
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


def _svc(conn):
    return WorkOrderService(_MemDS(conn))


def _add_schedule(conn, sid=_SCHEDULE_ID, oid=_ORDER_ID,
                  lid=_ORDER_LINE_ID, kind='service', status='planned'):
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        'schedule_kind, promised_date, status) VALUES (?, ?, ?, ?, ?, ?)',
        [sid, oid, lid, kind, '2026-10-30', status])


def _add_order_line(conn, lid=_ORDER_LINE_ID, oid=_ORDER_ID,
                    fulfillment_status='not_started'):
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, fulfillment_status) '
        'VALUES (?, ?, ?)', [lid, oid, fulfillment_status])


def _add_calendar(conn, cid=1, sat=0, sun=0):
    conn.execute(
        'INSERT INTO calendars (id, day_mask_sat, day_mask_sun) VALUES (?, ?, ?)',
        [cid, sat, sun])


def _add_calendar_day(conn, cid=1, date='', day_type='holiday'):
    conn.execute(
        'INSERT INTO calendar_days (calendar_id, date, day_type) VALUES (?, ?, ?)',
        [cid, date, day_type])


def _add_coverage(conn, cid=1, calendar_id=None, name=None,
                  active=1, start=None, end=None, org_id=None):
    conn.execute(
        'INSERT INTO sla_coverages (id, name, org_id, calendar_id, '
        'start_date, end_date, active) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [cid, name or '覆盖 %s' % cid, org_id, calendar_id, start, end, active])
    return cid


def _add_rule(conn, rid=1, coverage_id=1, severity='high', channel=None,
              first=60, first_warn=15, resolution=480, resolution_warn=60,
              seq=0):
    conn.execute(
        'INSERT INTO sla_coverage_rules (id, coverage_id, severity, channel, '
        'first_response_minutes, first_response_warn_minutes, '
        'resolution_minutes, resolution_warn_minutes, seq) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [rid, coverage_id, severity, channel, first, first_warn,
         resolution, resolution_warn, seq])
    return rid


def _with_rule(conn, **rule):
    """服务计划行 + 日历 + 单条覆盖规则的标准夹具。"""
    _add_schedule(conn)
    _add_calendar(conn, 1)
    cov = _add_coverage(conn, calendar_id=1)
    _add_rule(conn, coverage_id=cov, **rule)
    return cov


def _value(conn, sql, params=None):
    row = conn.execute(sql, list(params or [])).fetchone()
    return row[0] if row else None


def _milestones(conn, wo_id):
    rows = conn.execute(
        'SELECT milestone_type, state, due_at, warn_at, paused_total_minutes '
        'FROM sla_milestones WHERE work_order_id = ?', [wo_id]).fetchall()
    return {row[0]: {'state': row[1], 'due_at': row[2], 'warn_at': row[3],
                     'paused_total_minutes': row[4]} for row in rows}


def _events(conn, wo_id):
    return [row[0] for row in conn.execute(
        'SELECT event_type FROM service_events WHERE work_order_id = ? '
        'ORDER BY id', [wo_id]).fetchall()]


def _create(svc, **over):
    payload = {'schedule_id': _SCHEDULE_ID, 'severity': 'high',
               'opened_at': '2026-10-30 09:00:00'}
    payload.update(over)
    return svc.create_work_order(payload)


# ---------------- R-ST-0 挂载点 ----------------

def test_schedule_id_required():
    conn = _db()
    with pytest.raises(WorkOrderError) as exc:
        WorkOrderService(_MemDS(conn)).create_work_order({'severity': 'high'})
    assert exc.value.rule == 'ST_SCHEDULE_INVALID'
    assert exc.value.field_name == 'schedule_id'


def test_schedule_must_be_service_kind():
    conn = _db()
    _add_schedule(conn, kind='delivery')
    with pytest.raises(WorkOrderError) as exc:
        _create(_svc(conn))
    assert exc.value.rule == 'ST_SCHEDULE_INVALID'


def test_severity_required():
    conn = _db()
    _add_schedule(conn)
    with pytest.raises(WorkOrderError) as exc:
        _create(_svc(conn), severity=None)
    assert exc.value.rule == 'SLA_SEVERITY_REQUIRED'


# ---------------- 1. 单规则命中 ----------------

def test_single_rule_creates_two_milestones():
    conn = _db()
    cov = _with_rule(conn)
    result = _create(_svc(conn))

    assert result['sla']['code'] is None
    assert result['sla']['coverage_id'] == cov
    milestones = {m['milestone_type']: m for m in result['sla']['milestones']}
    assert set(milestones) == {MILESTONE_FIRST_RESPONSE, MILESTONE_RESOLUTION}
    assert milestones[MILESTONE_FIRST_RESPONSE]['due_at'] == '2026-10-30 10:00:00'
    assert milestones[MILESTONE_FIRST_RESPONSE]['warn_at'] == '2026-10-30 09:45:00'
    assert milestones[MILESTONE_RESOLUTION]['due_at'] == '2026-10-30 17:00:00'
    assert _value(conn,
                  'SELECT coverage_id FROM work_orders WHERE id = ?',
                  [result['id']]) == cov


# ---------------- 2. 多规则 / 无规则 → 歧义 ----------------

def test_multiple_rule_hits_are_ambiguous():
    conn = _db()
    _add_schedule(conn)
    cov_a = _add_coverage(conn, 1)
    _add_rule(conn, rid=1, coverage_id=cov_a)
    cov_b = _add_coverage(conn, 2)
    _add_rule(conn, rid=2, coverage_id=cov_b)

    result = _create(_svc(conn))

    assert result['sla']['code'] == 'SLA_RULE_AMBIGUOUS'
    assert result['sla']['reason'] == 'multiple_rules'
    assert result['sla']['milestones'] == []
    assert len(result['sla']['candidates']) == 2
    assert _value(conn,
                  'SELECT coverage_id FROM work_orders WHERE id = ?',
                  [result['id']]) is None
    assert 'sla_trace' in _events(conn, result['id'])


def test_no_rule_hit_is_ambiguous():
    conn = _db()
    _add_schedule(conn)
    cov = _add_coverage(conn, 1)
    _add_rule(conn, coverage_id=cov, severity='low')

    result = _create(_svc(conn))

    assert result['sla']['code'] == 'SLA_RULE_AMBIGUOUS'
    assert result['sla']['reason'] == 'no_rule'
    assert result['sla']['milestones'] == []
    assert 'sla_trace' in _events(conn, result['id'])


# ---------------- 3. 警告阈值 ----------------

def test_warn_threshold_becomes_warned_then_breached():
    conn = _db()
    _with_rule(conn)
    svc = _svc(conn)
    result = _create(svc)
    wo_id = result['id']

    svc.recompute_milestones(wo_id, now='2026-10-30 09:50:00')
    milestones = _milestones(conn, wo_id)
    # 首响 warn_at 09:45 已过、due_at 10:00 未到 → Warned
    assert milestones[MILESTONE_FIRST_RESPONSE]['state'] == 'Warned'
    # 解决 warn_at 16:00 未到 → 仍 Running
    assert milestones[MILESTONE_RESOLUTION]['state'] == 'Running'

    svc.recompute_milestones(wo_id, now='2026-10-30 10:05:00')
    assert _milestones(conn, wo_id)[MILESTONE_FIRST_RESPONSE]['state'] == 'Breached'


# ---------------- 4. 暂停 / 恢复顺延 ----------------

def test_pause_and_resume_shifts_due_at():
    conn = _db()
    _with_rule(conn)
    svc = _svc(conn)
    result = _create(svc)
    wo_id = result['id']
    conn.execute('UPDATE work_orders SET status = ? WHERE id = ?',
                 [STATUS_IN_PROGRESS, wo_id])

    paused = svc.pause(wo_id, now='2026-10-30 10:30:00')
    assert paused['status'] == STATUS_WAITING
    for milestone in _milestones(conn, wo_id).values():
        assert milestone['state'] == 'Paused'

    resumed = svc.resume(wo_id, now='2026-10-30 11:00:00')
    assert resumed['paused_minutes'] == 30
    milestones = _milestones(conn, wo_id)
    first = milestones[MILESTONE_FIRST_RESPONSE]
    assert first['state'] == 'Running'
    assert first['paused_total_minutes'] == 30
    assert first['due_at'] == '2026-10-30 10:30:00'
    assert first['warn_at'] == '2026-10-30 10:15:00'
    assert _value(conn, 'SELECT status FROM work_orders WHERE id = ?',
                  [wo_id]) == STATUS_IN_PROGRESS


# ---------------- 5. resolve 结算 ----------------

def test_resolve_settles_milestone_and_completes_schedule():
    conn = _db()
    _with_rule(conn)
    svc = _svc(conn)
    result = _create(svc)
    wo_id = result['id']

    out = svc.resolve_event(wo_id, occurred_at='2026-10-30 12:00:00')

    assert out['status'] == STATUS_RESOLVED
    assert out['milestone_state'] == 'Met'
    assert out['schedule_status'] == 'completed'
    milestones = _milestones(conn, wo_id)
    assert milestones[MILESTONE_RESOLUTION]['state'] == 'Met'
    assert _value(conn, 'SELECT status FROM sales_order_schedules WHERE id = ?',
                  [_SCHEDULE_ID]) == 'completed'
    assert svc.derive_service_status(_ORDER_ID) == SERVICE_STATUS_COMPLETED
    assert 'resolve' in _events(conn, wo_id)
    assert _value(conn,
                  "SELECT COUNT(*) FROM change_events WHERE object_type = "
                  "'work_order' AND event_type = 'state_change'") >= 1

    again = svc.resolve_event(wo_id, occurred_at='2026-10-30 12:30:00')
    assert again['already_resolved'] is True


def test_resolve_after_due_is_breached():
    conn = _db()
    _with_rule(conn)
    svc = _svc(conn)
    result = _create(svc)

    out = svc.resolve_event(result['id'], occurred_at='2026-10-30 18:00:00')

    assert out['milestone_state'] == 'Breached'


# ---------------- 6. 正交断言 ----------------

def test_resolve_does_not_touch_fulfillment_status():
    conn = _db()
    _with_rule(conn)
    _add_order_line(conn, fulfillment_status='not_started')
    # 同订单行还有一条 delivery 计划行，resolve 不得改动它
    _add_schedule(conn, sid=2, kind='delivery', status='confirmed')
    svc = _svc(conn)
    result = _create(svc)

    svc.resolve_event(result['id'], occurred_at='2026-10-30 12:00:00')

    assert _value(conn,
                  'SELECT fulfillment_status FROM sales_order_lines WHERE id = ?',
                  [_ORDER_LINE_ID]) == 'not_started'
    assert _value(conn, 'SELECT status FROM sales_order_schedules WHERE id = ?',
                  [2]) == 'confirmed'
    # 服务维度已全部完成，履约维度仍 not_started（两个状态正交成立）
    assert svc.derive_service_status(_ORDER_ID) == SERVICE_STATUS_COMPLETED


# ---------------- 8. 跨周末 / 节假日 ----------------

def test_due_at_skips_weekend_and_holiday():
    conn = _db()
    _add_calendar(conn, 1)
    # 2026-10-31（周六）调休上班；2026-11-02（周一）法定假日
    _add_calendar_day(conn, 1, '2026-10-31', 'workday')
    _add_calendar_day(conn, 1, '2026-11-02', 'holiday')
    svc = _svc(conn)

    # 周五 09:00 起 1000 业务分钟：周五 480 + 周六 480 + 周日跳过 +
    # 周一假日跳过 → 周二 09:00 再推 40 分钟
    assert svc.compute_due_at('2026-10-30 09:00:00', 1000, 1) \
        == '2026-11-03 09:40:00'
    # 同一输入重复计算结果一致（无时区换算，业务时间恒为本地口径）
    assert svc.compute_due_at('2026-10-30 09:00:00', 1000, 1) \
        == '2026-11-03 09:40:00'
