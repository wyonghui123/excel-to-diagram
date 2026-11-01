# -*- coding: utf-8 -*-
"""统一资源模型匹配 / 产能服务测试 (P2c)

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      FR-003 资源能力与技能 / FR-005 产能与可用性 / FR-008 资源分配

测试策略:
  · 内存 SQLite 真 SQL: 日历优先级、班次展开、能力有效期、时间窗重叠
    都必须用真表真 SQL 才可验证。
"""
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from datetime import date

import pytest

pytestmark = pytest.mark.unit

from meta.services.resource_matching_service import (
    ACTIVE_ASSIGNMENT_STATUSES,
    TIME_CAPACITY_CATEGORIES,
    ResourceMatchingError,
    availability_overrides,
    available_minutes,
    capacity_by_category,
    match_resources,
    resolve_resource_calendar,
    shift_windows_for_date,
    validate_assignment,
)

_SCHEMA = """
CREATE TABLE calendars (
    id INTEGER PRIMARY KEY,
    status TEXT DEFAULT 'active',
    day_mask_mon INTEGER DEFAULT 1,
    day_mask_tue INTEGER DEFAULT 1,
    day_mask_wed INTEGER DEFAULT 1,
    day_mask_thu INTEGER DEFAULT 1,
    day_mask_fri INTEGER DEFAULT 1,
    day_mask_sat INTEGER DEFAULT 1,
    day_mask_sun INTEGER DEFAULT 1
);
CREATE TABLE calendar_days (
    id INTEGER PRIMARY KEY,
    calendar_id INTEGER,
    date TEXT,
    day_type TEXT
);
CREATE TABLE shifts (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    start_time TEXT,
    end_time TEXT,
    crosses_midnight INTEGER DEFAULT 0,
    break_minutes INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE calendar_shifts (
    id INTEGER PRIMARY KEY,
    calendar_id INTEGER,
    shift_id INTEGER,
    seq INTEGER DEFAULT 1,
    capacity_factor REAL DEFAULT 1.0,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    calendar_id INTEGER
);
CREATE TABLE resources (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    resource_kind TEXT DEFAULT 'person',
    calendar_id INTEGER,
    location_id INTEGER,
    capacity_units REAL DEFAULT 1,
    utilization_pct REAL DEFAULT 100,
    capacity_per_day REAL,
    capacity_uom_id INTEGER,
    is_active INTEGER DEFAULT 1,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE resource_groups (
    id INTEGER PRIMARY KEY,
    code TEXT,
    calendar_id INTEGER,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE resource_group_members (
    id INTEGER PRIMARY KEY,
    group_id INTEGER,
    resource_id INTEGER,
    priority INTEGER,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE resource_capabilities (
    id INTEGER PRIMARY KEY,
    resource_id INTEGER,
    skill_id INTEGER,
    level INTEGER,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE resource_capacities (
    id INTEGER PRIMARY KEY,
    resource_id INTEGER,
    resource_group_id INTEGER,
    capacity_category TEXT,
    capacity_uom_id INTEGER,
    capacity_per_day REAL,
    capacity_units REAL DEFAULT 1,
    utilization_pct REAL DEFAULT 100,
    valid_from TEXT,
    valid_to TEXT
);
CREATE TABLE work_order_operations (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER,
    resource_group_id INTEGER,
    required_skill_id INTEGER
);
CREATE TABLE resource_assignments (
    id INTEGER PRIMARY KEY,
    work_order_operation_id INTEGER,
    resource_id INTEGER,
    planned_start TEXT,
    planned_end TEXT,
    planned_qty REAL,
    status TEXT DEFAULT 'planned',
    source TEXT DEFAULT 'manual'
);
CREATE TABLE resource_availabilities (
    id INTEGER PRIMARY KEY,
    resource_id INTEGER,
    availability_type TEXT DEFAULT 'unavailable',
    start_at TEXT,
    end_at TEXT,
    reason TEXT,
    source TEXT DEFAULT 'manual'
);
"""


def _connect():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    return conn


def _insert(conn, table, **values):
    columns = ', '.join(values.keys())
    placeholders = ', '.join('?' for _ in values)
    cursor = conn.execute(
        'INSERT INTO {0} ({1}) VALUES ({2})'.format(
            table, columns, placeholders), tuple(values.values()))
    return cursor.lastrowid


def _calendar(conn, calendar_id, weekend_off=False):
    masks = {}
    for field in ('day_mask_mon', 'day_mask_tue', 'day_mask_wed',
                  'day_mask_thu', 'day_mask_fri', 'day_mask_sat',
                  'day_mask_sun'):
        masks[field] = 0 if (weekend_off and field in ('day_mask_sat',
                                                        'day_mask_sun')) else 1
    _insert(conn, 'calendars', id=calendar_id, **masks)


# ============================================================================
# 日历优先级 (FR-005)
# ============================================================================

def test_resolve_calendar_precedence_resource_group_location_default():
    conn = _connect()
    for calendar_id in (1, 2, 3, 4, 5):
        _calendar(conn, calendar_id)
    _insert(conn, 'locations', id=10, calendar_id=3)
    _insert(conn, 'resource_groups', id=20, code='CREW_A', calendar_id=2)
    _insert(conn, 'resource_groups', id=21, code='CREW_B', calendar_id=4)
    _insert(conn, 'resources', id=1, code='R1', calendar_id=1, location_id=10)
    _insert(conn, 'resource_group_members', group_id=20, resource_id=1,
            priority=5)
    _insert(conn, 'resource_group_members', group_id=21, resource_id=1,
            priority=1)

    assert resolve_resource_calendar(conn, 1, default_calendar_id=5) == 1

    conn.execute('UPDATE resources SET calendar_id = NULL WHERE id = 1')
    # 组按 priority 升序: CREW_B(priority=1) 优先于 CREW_A(priority=5)
    assert resolve_resource_calendar(conn, 1, default_calendar_id=5) == 4

    conn.execute('UPDATE resource_groups SET calendar_id = NULL '
                 'WHERE id IN (20, 21)')
    assert resolve_resource_calendar(conn, 1, default_calendar_id=5) == 3

    conn.execute('UPDATE locations SET calendar_id = NULL WHERE id = 10')
    assert resolve_resource_calendar(conn, 1, default_calendar_id=5) == 5

    assert resolve_resource_calendar(conn, 1, default_calendar_id=None) is None


def test_resolve_calendar_skips_expired_group_membership():
    conn = _connect()
    _calendar(conn, 2)
    _calendar(conn, 3)
    _insert(conn, 'resource_groups', id=20, code='CREW_A', calendar_id=2)
    _insert(conn, 'locations', id=10, calendar_id=3)
    _insert(conn, 'resources', id=1, code='R1', location_id=10)
    _insert(conn, 'resource_group_members', group_id=20, resource_id=1,
            valid_to='2026-06-30')

    assert resolve_resource_calendar(conn, 1, as_of='2026-11-01') == 3


# ============================================================================
# 班次展开 (FR-014 / FR-005)
# ============================================================================

def test_shift_windows_respect_weekday_mask_and_exceptions():
    conn = _connect()
    _calendar(conn, 10, weekend_off=True)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='09:00', end_time='18:00', break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=10, shift_id=shift_id)

    # 2026-11-01 是周日, 周掩码关闭 -> 无窗口
    assert shift_windows_for_date(conn, 10, '2026-11-01') == []

    _insert(conn, 'calendar_days', calendar_id=10, date='2026-11-02',
            day_type='holiday')
    assert shift_windows_for_date(conn, 10, '2026-11-02') == []

    _insert(conn, 'calendar_days', calendar_id=10, date='2026-11-07',
            day_type='workday')
    windows = shift_windows_for_date(conn, 10, '2026-11-07')
    assert len(windows) == 1
    assert windows[0]['day_type'] == 'workday'
    assert windows[0]['net_minutes'] == 480

    windows = shift_windows_for_date(conn, 10, '2026-11-03')
    assert len(windows) == 1
    assert windows[0]['gross_minutes'] == 540
    assert windows[0]['break_minutes'] == 60
    assert windows[0]['effective_minutes'] == 480


def test_shift_windows_cross_midnight_and_capacity_factor():
    conn = _connect()
    _calendar(conn, 11)
    shift_id = _insert(conn, 'shifts', code='NIGHT', name='夜班',
                       start_time='22:00', end_time='06:00',
                       crosses_midnight=1, break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=11, shift_id=shift_id,
            capacity_factor=0.5)

    windows = shift_windows_for_date(conn, 11, '2026-11-03')
    assert len(windows) == 1
    window = windows[0]
    assert window['crosses_midnight'] is True
    assert window['gross_minutes'] == 480
    assert window['net_minutes'] == 420
    assert window['capacity_factor'] == 0.5
    assert window['effective_minutes'] == 210


def test_shift_windows_skip_inactive_or_expired_shift():
    conn = _connect()
    _calendar(conn, 12)
    active_id = _insert(conn, 'shifts', code='A', name='A',
                        start_time='08:00', end_time='12:00')
    _insert(conn, 'shifts', id=99, code='B', name='B',
            start_time='13:00', end_time='17:00', is_active=0)
    _insert(conn, 'shifts', id=98, code='C', name='C',
            start_time='18:00', end_time='20:00', valid_to='2026-06-30')
    _insert(conn, 'calendar_shifts', calendar_id=12, shift_id=active_id)
    _insert(conn, 'calendar_shifts', calendar_id=12, shift_id=99)
    _insert(conn, 'calendar_shifts', calendar_id=12, shift_id=98)

    windows = shift_windows_for_date(conn, 12, '2026-11-03')
    assert [w['shift_code'] for w in windows] == ['A']


def test_shift_windows_unknown_calendar_raises():
    conn = _connect()
    with pytest.raises(ResourceMatchingError) as exc:
        shift_windows_for_date(conn, 404, '2026-11-03')
    assert exc.value.code == 'CALENDAR_NOT_FOUND'


# ============================================================================
# 可用产能 (FR-005 公式)
# ============================================================================

def test_available_minutes_uses_units_and_utilization():
    conn = _connect()
    _calendar(conn, 13)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00', break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=13, shift_id=shift_id)
    _insert(conn, 'resources', id=2, code='R2', calendar_id=13,
            capacity_units=2, utilization_pct=150)

    # 净 420 分钟 × 2 单元 × 150% = 1260
    assert available_minutes(conn, 2, '2026-11-03') == 1260.0


def test_available_minutes_returns_zero_without_calendar():
    conn = _connect()
    _insert(conn, 'resources', id=3, code='R3')
    assert available_minutes(conn, 3, '2026-11-03') == 0.0


def test_available_minutes_unknown_resource_raises():
    conn = _connect()
    with pytest.raises(ResourceMatchingError) as exc:
        available_minutes(conn, 404, '2026-11-03')
    assert exc.value.code == 'RESOURCE_NOT_FOUND'


# ============================================================================
# 可用性例外 (FR-005 / P2c)
# ============================================================================

def test_availability_unavailable_leave_deducts_capacity():
    """请假 4 小时落在班次内 ⇒ 扣减 240 分钟。"""
    conn = _connect()
    _calendar(conn, 14)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00', break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=14, shift_id=shift_id)
    _insert(conn, 'resources', id=40, code='R40', calendar_id=14)
    _insert(conn, 'resource_availabilities', resource_id=40,
            availability_type='unavailable',
            start_at='2026-11-03 09:00:00', end_at='2026-11-03 13:00:00',
            reason='请假', source='hr')

    result = availability_overrides(conn, 40, '2026-11-03')
    assert result['unavailable_minutes'] == 240.0
    assert result['overtime_minutes'] == 0.0
    assert len(result['entries']) == 1
    assert result['entries'][0]['availability_type'] == 'unavailable'
    # 班次净 420 分钟 - 240 = 180
    assert result['available_minutes'] == 180.0
    assert available_minutes(conn, 40, '2026-11-03') == 180.0


def test_availability_overtime_outside_shift_counts():
    """加班 2 小时全部落在班次外 ⇒ 加班分钟计入, 产能不变。"""
    conn = _connect()
    _calendar(conn, 15)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00')
    _insert(conn, 'calendar_shifts', calendar_id=15, shift_id=shift_id)
    _insert(conn, 'resources', id=41, code='R41', calendar_id=15)
    _insert(conn, 'resource_availabilities', resource_id=41,
            availability_type='overtime',
            start_at='2026-11-03T18:00:00', end_at='2026-11-03T20:00:00',
            reason='赶工', source='manual')

    result = availability_overrides(conn, 41, '2026-11-03')
    assert result['overtime_minutes'] == 120.0
    assert result['unavailable_minutes'] == 0.0
    assert result['available_minutes'] == 480.0
    assert available_minutes(conn, 41, '2026-11-03') == 480.0


def test_available_minutes_unchanged_without_availability_entries():
    """无例外行时与 P2b 旧口径完全一致(净 480 × 2 单元 × 150%)。"""
    conn = _connect()
    _calendar(conn, 16)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='09:00', end_time='18:00', break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=16, shift_id=shift_id)
    _insert(conn, 'resources', id=42, code='R42', calendar_id=16,
            capacity_units=2, utilization_pct=150)

    assert available_minutes(conn, 42, '2026-11-03') == 1440.0
    result = availability_overrides(conn, 42, '2026-11-03')
    assert result['entries'] == []
    assert result['unavailable_minutes'] == 0.0
    assert result['overtime_minutes'] == 0.0
    assert result['available_minutes'] == 1440.0


# ============================================================================
# 技能匹配 (FR-003)
# ============================================================================

def test_match_resources_filters_level_and_expired_capability():
    conn = _connect()
    _insert(conn, 'resources', id=1, code='R1')
    _insert(conn, 'resources', id=2, code='R2')
    _insert(conn, 'resources', id=3, code='R3')
    _insert(conn, 'resources', id=4, code='R4', is_active=0)
    _insert(conn, 'resource_capabilities', resource_id=1, skill_id=1, level=4,
            valid_from='2026-01-01')
    _insert(conn, 'resource_capabilities', resource_id=2, skill_id=1, level=2,
            valid_from='2026-01-01')
    _insert(conn, 'resource_capabilities', resource_id=3, skill_id=1, level=5,
            valid_from='2026-01-01', valid_to='2026-06-30')
    _insert(conn, 'resource_capabilities', resource_id=4, skill_id=1, level=4,
            valid_from='2026-01-01')

    matched = match_resources(conn, skill_id=1, min_level=3,
                              as_of='2026-11-01')
    assert [row['resource_id'] for row in matched] == [1]

    # 2026-06-01 时 R3 尚未过期, 按等级降序排在首位
    matched = match_resources(conn, skill_id=1, as_of='2026-06-01',)
    assert [row['resource_id'] for row in matched] == [3, 1, 2]

    assert match_resources(conn, skill_id=1, as_of='2026-11-01') == \
        match_resources(conn, skill_id=1, as_of=date(2026, 11, 1))


def test_match_resources_group_and_kind_filters():
    conn = _connect()
    _insert(conn, 'resources', id=1, code='R1', resource_kind='person')
    _insert(conn, 'resources', id=2, code='R2', resource_kind='machine')
    _insert(conn, 'resource_groups', id=20, code='CREW')
    _insert(conn, 'resource_group_members', group_id=20, resource_id=1)
    _insert(conn, 'resource_group_members', group_id=20, resource_id=2)

    matched = match_resources(conn, group_id=20, as_of='2026-11-01')
    assert [row['resource_id'] for row in matched] == [1, 2]

    matched = match_resources(conn, group_id=20, resource_kind='person',
                              as_of='2026-11-01')
    assert [row['resource_id'] for row in matched] == [1]


def test_match_resources_min_level_requires_skill():
    conn = _connect()
    with pytest.raises(ResourceMatchingError) as exc:
        match_resources(conn, min_level=3)
    assert exc.value.code == 'INVALID_ARGUMENT'


# ============================================================================
# 分配校验 (FR-008)
# ============================================================================

def test_validate_assignment_rejects_resource_outside_group():
    conn = _connect()
    _insert(conn, 'resource_groups', id=20, code='CREW')
    _insert(conn, 'resources', id=5, code='R5')
    _insert(conn, 'work_order_operations', id=100, work_order_id=1,
            resource_group_id=20)

    with pytest.raises(ResourceMatchingError) as exc:
        validate_assignment(conn, 100, 5, '2026-11-03 09:00:00',
                            '2026-11-03 12:00:00')
    assert exc.value.code == 'RESOURCE_NOT_IN_GROUP'


def test_validate_assignment_rejects_overlapping_window():
    conn = _connect()
    _insert(conn, 'resource_groups', id=20, code='CREW')
    _insert(conn, 'resources', id=6, code='R6')
    _insert(conn, 'resource_group_members', group_id=20, resource_id=6)
    _insert(conn, 'work_order_operations', id=100, work_order_id=1,
            resource_group_id=20)
    _insert(conn, 'resource_assignments', work_order_operation_id=100,
            resource_id=6, planned_start='2026-11-03 09:00:00',
            planned_end='2026-11-03 12:00:00', status='planned')

    with pytest.raises(ResourceMatchingError) as exc:
        validate_assignment(conn, 100, 6, '2026-11-03 10:00:00',
                            '2026-11-03 11:00:00')
    assert exc.value.code == 'ASSIGNMENT_OVERLAP'

    # 取消的分配不占用时间窗
    conn.execute("UPDATE resource_assignments SET status = 'canceled'")
    result = validate_assignment(conn, 100, 6, '2026-11-03 10:00:00',
                                 '2026-11-03 11:00:00')
    assert result['ok'] is True
    assert result['planned_start'] == '2026-11-03 10:00:00'
    assert 'planned' in ACTIVE_ASSIGNMENT_STATUSES


def test_validate_assignment_qty_and_window_rules():
    conn = _connect()
    _insert(conn, 'resources', id=7, code='R7')
    _insert(conn, 'work_order_operations', id=101, work_order_id=1)

    with pytest.raises(ResourceMatchingError) as exc:
        validate_assignment(conn, 101, 7, '2026-11-03 09:00:00',
                            '2026-11-03 12:00:00', planned_qty=5, max_qty=3)
    assert exc.value.code == 'QTY_EXCEEDS_OPERATION'

    with pytest.raises(ResourceMatchingError) as exc:
        validate_assignment(conn, 101, 7, '2026-11-03 09:00:00',
                            '2026-11-03 12:00:00', planned_qty=0)
    assert exc.value.code == 'INVALID_QTY'

    with pytest.raises(ResourceMatchingError) as exc:
        validate_assignment(conn, 101, 7, '2026-11-03 12:00:00',
                            '2026-11-03 09:00:00')
    assert exc.value.code == 'INVALID_WINDOW'

    with pytest.raises(ResourceMatchingError) as exc:
        validate_assignment(conn, 404, 7, '2026-11-03 09:00:00',
                            '2026-11-03 12:00:00')
    assert exc.value.code == 'OPERATION_NOT_FOUND'


def test_validate_assignment_warns_when_skill_missing():
    conn = _connect()
    _insert(conn, 'resources', id=8, code='R8')
    _insert(conn, 'work_order_operations', id=102, work_order_id=1,
            required_skill_id=1)

    result = validate_assignment(conn, 102, 8, '2026-11-03 09:00:00',
                                 '2026-11-03 12:00:00')
    assert result['warnings'] == ['SKILL_NOT_VERIFIED']

    _insert(conn, 'resource_capabilities', resource_id=8, skill_id=1, level=3,
            valid_from='2026-01-01')
    result = validate_assignment(conn, 102, 8, '2026-11-03 09:00:00',
                                 '2026-11-03 12:00:00')
    assert result['warnings'] == []


# ============================================================================
# 多口径产能 (FR-005)
# ============================================================================

def test_capacity_by_category_latest_valid_row_wins():
    conn = _connect()
    _calendar(conn, 30)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00', break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=30, shift_id=shift_id)
    _insert(conn, 'resources', id=30, code='R30', calendar_id=30)

    _insert(conn, 'resource_capacities', resource_id=30,
            capacity_category='labor_hours', capacity_uom_id=1,
            capacity_per_day=420, capacity_units=1, utilization_pct=100,
            valid_from='2026-01-01')
    _insert(conn, 'resource_capacities', resource_id=30,
            capacity_category='labor_hours', capacity_uom_id=1,
            capacity_per_day=420, capacity_units=2, utilization_pct=100,
            valid_from='2026-10-01')
    _insert(conn, 'resource_capacities', resource_id=30,
            capacity_category='machine_hours', capacity_uom_id=1,
            capacity_per_day=420, capacity_units=1, utilization_pct=100,
            valid_from='2026-01-01', valid_to='2026-06-30')

    result = capacity_by_category(conn, resource_id=30, the_date='2026-11-03')
    assert result['calendar_id'] == 30
    assert result['calendar_minutes'] == 420.0
    assert 'machine_hours' not in result['categories']
    labor = result['categories']['labor_hours']
    # 10-01 那行生效(units=2): 420 × 2 × 100% = 840
    assert labor['capacity_units'] == 2
    assert labor['effective_per_day'] == 840.0
    assert labor['scope'] == 'resource'
    assert 'labor_hours' in TIME_CAPACITY_CATEGORIES


def test_capacity_by_category_non_time_uses_declared_value():
    conn = _connect()
    _calendar(conn, 31)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00', break_minutes=60)
    _insert(conn, 'calendar_shifts', calendar_id=31, shift_id=shift_id)
    _insert(conn, 'resources', id=31, code='R31', calendar_id=31)
    _insert(conn, 'resource_capacities', resource_id=31,
            capacity_category='vehicle_weight', capacity_uom_id=2,
            capacity_per_day=1000, capacity_units=2, utilization_pct=80,
            valid_from='2026-01-01')

    result = capacity_by_category(conn, resource_id=31, the_date='2026-11-03')
    weight = result['categories']['vehicle_weight']
    # 非时间口径: 1000 × 2 × 80% = 1600, 不受日历 420 分钟影响
    assert weight['effective_per_day'] == 1600.0
    assert weight['declared_per_day'] == 1000


def test_capacity_by_category_group_scope_and_argument_check():
    conn = _connect()
    _calendar(conn, 32)
    _insert(conn, 'resource_groups', id=40, code='FLEET', calendar_id=32)
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='12:00')
    _insert(conn, 'calendar_shifts', calendar_id=32, shift_id=shift_id)
    _insert(conn, 'resource_capacities', resource_group_id=40,
            capacity_category='tool_count', capacity_per_day=5,
            capacity_units=1, utilization_pct=100,
            valid_from='2026-01-01')

    result = capacity_by_category(conn, group_id=40, the_date='2026-11-03')
    assert result['calendar_id'] == 32
    assert result['categories']['tool_count']['scope'] == 'group'
    assert result['categories']['tool_count']['effective_per_day'] == 5.0

    with pytest.raises(ResourceMatchingError) as exc:
        capacity_by_category(conn)
    assert exc.value.code == 'INVALID_ARGUMENT'
