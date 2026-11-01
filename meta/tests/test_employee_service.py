# -*- coding: utf-8 -*-
"""员工主服务测试（统一资源模型 P3 / FR-015）

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §FR-015

口径:
  · 内存 SQLite 真 SQL：资源↔员工按 person 求交、在职唯一、主管成环、
    排班星期掩码 / 生效区间 / 跨天班、HR 排班覆盖日历 + 请假例外扣减，
    都必须用真表真 SQL 才可验证。
"""
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.employee_service import (
    MAX_MANAGER_DEPTH,
    employee_shift_warnings,
    employee_shift_windows,
    resolve_resource_employee,
    shift_overlap_warnings,
    validate_employee,
)
from meta.services.resource_matching_service import (
    ResourceMatchingError,
    availability_overrides,
    available_minutes,
)

_SCHEMA = """
CREATE TABLE resources (
    id INTEGER PRIMARY KEY,
    code TEXT,
    person_ref INTEGER,
    calendar_id INTEGER,
    location_id INTEGER,
    capacity_units REAL DEFAULT 1,
    utilization_pct REAL DEFAULT 100,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    employee_no TEXT,
    name TEXT,
    person_profile_id INTEGER,
    user_id INTEGER,
    org_id INTEGER,
    location_id INTEGER,
    position TEXT,
    job_grade TEXT,
    employment_type TEXT DEFAULT 'full_time',
    status TEXT DEFAULT 'active',
    hire_date TEXT,
    termination_date TEXT,
    manager_employee_id INTEGER
);
CREATE TABLE employee_shift_assignments (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER,
    shift_id INTEGER,
    day_mask_mon INTEGER DEFAULT 1,
    day_mask_tue INTEGER DEFAULT 1,
    day_mask_wed INTEGER DEFAULT 1,
    day_mask_thu INTEGER DEFAULT 1,
    day_mask_fri INTEGER DEFAULT 1,
    day_mask_sat INTEGER DEFAULT 1,
    day_mask_sun INTEGER DEFAULT 1,
    seq INTEGER DEFAULT 1,
    effective_from TEXT,
    effective_to TEXT,
    work_center_id INTEGER,
    note TEXT
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
CREATE TABLE calendars (
    id INTEGER PRIMARY KEY,
    status TEXT DEFAULT 'active'
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


def _employee(conn, employee_id=None, **values):
    defaults = dict(employee_no='E{0}'.format(employee_id or 'X'), name='员工',
                    person_profile_id=employee_id or 1, org_id=0,
                    status='active', hire_date='2026-01-01')
    defaults.update(values)
    if employee_id is not None:
        defaults['id'] = employee_id
    return _insert(conn, 'employees', **defaults)


def _codes(result):
    return [error['code'] for error in result['errors']]


# ============================================================================
# 资源 ↔ 员工（按 person 求交）
# ============================================================================

def test_resolve_resource_employee_by_person():
    conn = _connect()
    _employee(conn, 7, employee_no='E7', name='张三', person_profile_id=101,
              hire_date='2026-01-01')
    _insert(conn, 'resources', id=1, code='R1', person_ref=101)
    employee = resolve_resource_employee(conn, 1, as_of='2026-11-01')
    assert employee['id'] == 7
    assert employee['employee_no'] == 'E7'
    assert employee['person_profile_id'] == 101
    assert employee['status'] == 'active'


def test_resolve_resource_employee_returns_none_without_person():
    conn = _connect()
    _insert(conn, 'resources', id=1, code='R1')          # 非人资源, 无 person_ref
    _insert(conn, 'resources', id=2, code='R2', person_ref=202)  # 无在职员工
    _employee(conn, 9, person_profile_id=202, status='terminated',
              hire_date='2020-01-01', termination_date='2021-01-01')
    assert resolve_resource_employee(conn, 1) is None
    assert resolve_resource_employee(conn, 2) is None


def test_resolve_resource_employee_unknown_resource_raises():
    conn = _connect()
    with pytest.raises(ResourceMatchingError) as exc:
        resolve_resource_employee(conn, 404)
    assert exc.value.code == 'RESOURCE_NOT_FOUND'


# ============================================================================
# 校验（不写库）
# ============================================================================

def test_validate_terminated_requires_termination_date():
    conn = _connect()
    result = validate_employee(conn, {
        'employee_no': 'E100', 'person_profile_id': 100,
        'status': 'terminated', 'hire_date': '2026-01-01'})
    assert 'TERMINATION_DATE_REQUIRED' in _codes(result)

    result = validate_employee(conn, {
        'employee_no': 'E101', 'person_profile_id': 101,
        'status': 'terminated', 'hire_date': '2026-06-01',
        'termination_date': '2026-01-01'})
    assert 'TERMINATION_BEFORE_HIRE' in _codes(result)


def test_validate_employee_no_conflict_only_for_active():
    conn = _connect()
    _employee(conn, 1, employee_no='E1', person_profile_id=101, status='active')
    result = validate_employee(conn, {
        'employee_no': 'E1', 'person_profile_id': 999, 'status': 'active',
        'hire_date': '2026-11-01'})
    assert 'EMPLOYEE_NO_CONFLICT' in _codes(result)

    _employee(conn, 2, employee_no='E-OLD', person_profile_id=102,
              status='terminated', hire_date='2020-01-01',
              termination_date='2021-01-01')
    result = validate_employee(conn, {
        'employee_no': 'E-OLD', 'person_profile_id': 999, 'status': 'active',
        'hire_date': '2026-11-01'})
    assert 'EMPLOYEE_NO_CONFLICT' not in _codes(result)


def test_validate_person_profile_conflict():
    conn = _connect()
    _employee(conn, 1, employee_no='E1', person_profile_id=101, status='active')
    result = validate_employee(conn, {
        'employee_no': 'E9', 'person_profile_id': 101, 'status': 'active',
        'hire_date': '2026-11-01'})
    assert 'PERSON_PROFILE_CONFLICT' in _codes(result)


def test_validate_manager_self_reference_and_cycle():
    conn = _connect()
    _employee(conn, 1, manager_employee_id=3)
    _employee(conn, 2, manager_employee_id=1)
    _employee(conn, 3, manager_employee_id=2)

    result = validate_employee(conn, {'manager_employee_id': 1}, employee_id=1)
    assert 'MANAGER_SELF_REFERENCE' in _codes(result)

    result = validate_employee(conn, {'manager_employee_id': 2}, employee_id=1)
    assert 'MANAGER_CYCLE' in _codes(result)
    assert MAX_MANAGER_DEPTH == 20


# ============================================================================
# 员工排班窗口 (FR-015)
# ============================================================================

def test_employee_shift_windows_respect_weekday_mask():
    conn = _connect()
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00', break_minutes=60)
    _employee(conn, 1)
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=shift_id, effective_from='2026-01-01', day_mask_sun=0)

    # 2026-11-01 是周日 -> 掩码关闭
    assert employee_shift_windows(conn, 1, '2026-11-01') == []

    windows = employee_shift_windows(conn, 1, '2026-11-02')
    assert len(windows) == 1
    window = windows[0]
    assert window['net_minutes'] == 420
    assert window['effective_minutes'] == 420.0
    assert window['capacity_factor'] == 1.0
    assert window['calendar_shift_id'] is None
    assert window['employee_id'] == 1
    assert window['employee_shift_assignment_id'] is not None


def test_employee_shift_windows_respect_effective_range():
    conn = _connect()
    shift_id = _insert(conn, 'shifts', code='DAY', name='白班',
                       start_time='08:00', end_time='16:00')
    _employee(conn, 1)
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=shift_id, effective_from='2026-11-05',
            effective_to='2026-11-20')

    assert employee_shift_windows(conn, 1, '2026-11-03') == []
    assert len(employee_shift_windows(conn, 1, '2026-11-10')) == 1


def test_employee_shift_windows_cross_midnight_and_inactive():
    conn = _connect()
    night_id = _insert(conn, 'shifts', code='NIGHT', name='夜班',
                       start_time='22:00', end_time='06:00',
                       crosses_midnight=1, break_minutes=60)
    inactive_id = _insert(conn, 'shifts', code='OLD', name='停用班',
                          start_time='08:00', end_time='12:00', is_active=0)
    _employee(conn, 1)
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=night_id, effective_from='2026-01-01')
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=inactive_id, effective_from='2026-01-01')

    windows = employee_shift_windows(conn, 1, '2026-11-03')
    assert len(windows) == 1
    window = windows[0]
    assert window['shift_code'] == 'NIGHT'
    assert window['crosses_midnight'] is True
    assert window['gross_minutes'] == 480
    assert window['net_minutes'] == 420
    assert window['effective_minutes'] == 420.0


# ============================================================================
# HR 可用性分支 (FR-015)
# ============================================================================

def test_available_minutes_employee_shift_overrides_calendar_with_leave():
    conn = _connect()
    _insert(conn, 'calendars', id=5)
    calendar_shift = _insert(conn, 'shifts', code='CAL_DAY', name='日历白班',
                             start_time='08:00', end_time='16:00',
                             break_minutes=0)
    _insert(conn, 'calendar_shifts', calendar_id=5, shift_id=calendar_shift)

    employee_shift = _insert(conn, 'shifts', code='EMP_EARLY', name='员工早班',
                             start_time='08:00', end_time='12:00')
    _employee(conn, 1, employee_no='E1', person_profile_id=101,
              hire_date='2026-01-01')
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=employee_shift, effective_from='2026-01-01')
    _insert(conn, 'resources', id=1, code='R1', person_ref=101, calendar_id=5)

    # 员工排班 240 分钟覆盖日历 480 分钟（不叠加）
    assert available_minutes(conn, 1, '2026-11-03') == 240.0

    _insert(conn, 'resource_availabilities', resource_id=1,
            availability_type='unavailable',
            start_at='2026-11-03 09:00:00', end_at='2026-11-03 10:00:00',
            reason='请假', source='hr')

    # 请假 60 分钟仍作用在员工排班窗口上: 240 - 60 = 180
    assert available_minutes(conn, 1, '2026-11-03') == 180.0
    result = availability_overrides(conn, 1, '2026-11-03')
    assert result['unavailable_minutes'] == 60.0
    assert result['available_minutes'] == 180.0
    assert result['calendar_id'] == 5


# ============================================================================
# 同日排班重叠告警 (FR-015 验收 / TBD-14)
# ============================================================================

def test_shift_overlap_warnings_detects_same_day_overlap():
    conn = _connect()
    day_id = _insert(conn, 'shifts', code='DAY', name='白班',
                     start_time='08:00', end_time='16:00', break_minutes=60)
    swing_id = _insert(conn, 'shifts', code='SWING', name='中班',
                       start_time='12:00', end_time='20:00', break_minutes=60)
    _employee(conn, 1)
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=day_id, effective_from='2026-01-01')
    _insert(conn, 'employee_shift_assignments', employee_id=1,
            shift_id=swing_id, effective_from='2026-01-01')

    # 08:00-16:00 与 12:00-20:00 重叠 240 分钟(按 gross 时间窗求交, 不扣休息)
    warnings = employee_shift_warnings(conn, 1, '2026-11-02')
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning['code'] == 'ASSIGNMENT_OVERLAP'
    assert warning['employee_id'] == 1
    assert warning['date'] == '2026-11-02'
    assert warning['overlap_minutes'] == 240
    assert len(warning['assignment_ids']) == 2
    assert set(warning['shift_ids']) == {day_id, swing_id}


def test_shift_overlap_warnings_ignores_adjacent_windows():
    windows = [
        {'shift_id': 1, 'shift_code': 'A', 'start_time': '08:00',
         'gross_minutes': 240, 'employee_id': 9,
         'employee_shift_assignment_id': 11},
        {'shift_id': 2, 'shift_code': 'B', 'start_time': '12:00',
         'gross_minutes': 240, 'employee_id': 9,
         'employee_shift_assignment_id': 12},
    ]
    # 首尾相接(08:00-12:00 与 12:00-16:00)不算重叠
    assert shift_overlap_warnings(windows, '2026-11-02') == []
