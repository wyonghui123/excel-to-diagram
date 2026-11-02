# -*- coding: utf-8 -*-
"""项目侧 G14：工时聚合查询服务（P3-1）与只读 API（P3-2）

依据:
  docs/specs/tasks-project-g14-labor-view-2026-11-01.md §3 P3-1 / P3-2 / §4 P4-3

【本文件守什么】
  LQ-1 `project_task_labor` / `project_labor` 过滤 + 排序（读 Phase 2 三视图）
  LQ-2 `resource_utilization`：班次 480 + 实际 600 → 加班 120 / 利用率 125.0
  LQ-3 请假例外扣减后 available 下降（复用 available_minutes，不另写班次逻辑）
  LQ-4 无日历资源 actual>0 → available=0 + capacity_missing
  LQ-5 三个只读端点 200 + 关键字段；鉴权 / 参数错误走统一响应契约

建库一律走内存 SQLite 骨架 + v182.create_views()，尽量贴近真 SQL。
"""
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import meta.api.labor_api as labor_api  # noqa: E402
import meta.services.auth_middleware as auth_mw  # noqa: E402
from meta.migrations import v182__time_entry_labor_view as v182  # noqa: E402
from meta.services.labor_service import LaborError, LaborService  # noqa: E402

pytestmark = pytest.mark.unit

_SCHEMA = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    project_no TEXT,
    name TEXT
);
CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    task_no TEXT,
    name TEXT,
    status TEXT
);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY,
    work_order_no TEXT,
    project_id INTEGER
);
CREATE TABLE work_order_operations (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER,
    operation_name TEXT
);
CREATE TABLE resource_assignments (
    id INTEGER PRIMARY KEY,
    work_order_operation_id INTEGER,
    resource_id INTEGER
);
CREATE TABLE time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date TEXT,
    resource_id INTEGER,
    minutes INTEGER,
    project_task_id INTEGER,
    work_order_id INTEGER,
    work_order_operation_id INTEGER,
    resource_assignment_id INTEGER,
    entry_type TEXT DEFAULT 'manual',
    billable INTEGER DEFAULT 1,
    note TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 产能侧骨架（available_minutes / 日历 / 班次 / 例外）
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
    person_ref INTEGER,
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


class _MemDS:
    """最小数据源：query / execute + 原生 conn（available_minutes 要用）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cursor = self.conn.execute(sql, params or [])
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])


def _seed_projects(conn):
    """项目 A 两任务 + 项目 B 一任务 + 只挂工单 / 任务+工序的工时。"""
    conn.executescript("""
        INSERT INTO projects (id, project_no, name)
        VALUES (10, 'PA', '项目A'), (20, 'PB', '项目B');
        INSERT INTO project_tasks (id, project_id, task_no, name, status)
        VALUES (101, 10, '1.1', '任务A1', 'in_progress'),
               (102, 10, '1.2', '任务A2', 'planned'),
               (201, 20, '2.1', '任务B1', 'draft');
        INSERT INTO work_orders (id, work_order_no, project_id)
        VALUES (301, 'WO-A', 10), (302, 'WO-B', 20);
        INSERT INTO work_order_operations (id, work_order_id, operation_name)
        VALUES (401, 301, '安装'), (402, 302, '维修');
        INSERT INTO resources (id, code, name, is_active)
        VALUES (1, 'R-1', '张工', 1), (2, 'R-2', '李工', 1), (3, 'R-3', '王工', 1);
    """)
    entries = (
        (1, '2026-10-30', 1, 120, 101, None, None, 1, 'manual', 1),
        (2, '2026-10-31', 2, 60, 102, None, None, None, 'manual', 1),
        (3, '2026-10-31', 3, 90, 201, None, None, None, 'manual', 0),
        (4, '2026-10-31', 1, 30, None, 301, None, None, 'manual', 1),
        (5, '2026-10-31', 2, 45, 101, 301, 401, None, 'manual', 1),
        (6, '2026-10-30', 3, 15, None, 302, 402, None, 'manual', 1),
    )
    conn.executemany(
        'INSERT INTO time_entries (id, work_date, resource_id, minutes, '
        'project_task_id, work_order_id, work_order_operation_id, '
        'resource_assignment_id, entry_type, billable) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', entries)


def _seed_utilization(conn):
    """班次 08:00–17:00（休息 60）净 480；资源 2 当天请假 4h；资源 3 无日历。"""
    conn.executescript("""
        INSERT INTO calendars (id, status) VALUES (1, 'active'), (2, 'active');
        INSERT INTO shifts (id, code, name, start_time, end_time,
                            break_minutes, is_active)
        VALUES (11, 'DAY', '白班', '08:00', '17:00', 60, 1);
        INSERT INTO calendar_shifts (id, calendar_id, shift_id, seq, capacity_factor)
        VALUES (1, 1, 11, 1, 1.0), (2, 2, 11, 1, 1.0);
        INSERT INTO resources (id, code, name, calendar_id, capacity_units,
                               utilization_pct, is_active)
        VALUES (1, 'R-1', '张工', 1, 1, 100, 1),
               (2, 'R-2', '李工', 2, 1, 100, 1),
               (3, 'R-3', '王工', NULL, 1, 100, 1);
        INSERT INTO resource_availabilities
            (id, resource_id, availability_type, start_at, end_at, reason, source)
        VALUES (1, 2, 'unavailable', '2026-11-03 09:00:00',
                '2026-11-03 13:00:00', '请假', 'hr');
    """)
    entries = (
        (1, '2026-11-03', 1, 300, 101, None, None, None, 'manual', 1),
        (2, '2026-11-03', 1, 300, 101, None, None, None, 'manual', 1),
        (3, '2026-11-03', 2, 300, 101, None, None, None, 'manual', 1),
        (4, '2026-11-03', 3, 60, 101, None, None, None, 'manual', 1),
    )
    conn.executemany(
        'INSERT INTO time_entries (id, work_date, resource_id, minutes, '
        'project_task_id, work_order_id, work_order_operation_id, '
        'resource_assignment_id, entry_type, billable) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', entries)


def _db(seed):
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    seed(conn)
    v182.create_views(conn)
    return conn


@contextmanager
def _service(seed):
    conn = _db(seed)
    try:
        yield LaborService(_MemDS(conn))
    finally:
        conn.close()


# ======================================================================
# P3-1 聚合查询：过滤 + 排序
# ======================================================================
class TestLaborAggregateQueries:

    def test_project_task_labor_all_rows_sorted(self):
        with _service(_seed_projects) as svc:
            rows = svc.project_task_labor()
        assert [r['project_task_id'] for r in rows] == [101, 201, 102]
        assert rows[0]['actual_minutes'] == 165
        assert rows[1]['actual_minutes'] == 90
        assert rows[2]['actual_minutes'] == 60
        assert rows[0]['project_id'] == 10
        assert rows[0]['task_name'] == '任务A1'

    def test_project_task_labor_filters(self):
        with _service(_seed_projects) as svc:
            by_project = svc.project_task_labor(project_id=10)
            by_task = svc.project_task_labor(task_id=102)
        assert [r['project_task_id'] for r in by_project] == [101, 102]
        assert [r['project_task_id'] for r in by_task] == [102]
        assert by_task[0]['actual_minutes'] == 60

    def test_project_labor_all_and_filtered(self):
        with _service(_seed_projects) as svc:
            rows = svc.project_labor()
            only_b = svc.project_labor(project_id=20)
        assert [r['project_id'] for r in rows] == [10, 20]
        assert rows[0]['actual_minutes'] == 255
        assert rows[0]['task_count'] == 2
        assert rows[1]['actual_minutes'] == 105
        assert len(only_b) == 1
        assert only_b[0]['project_no'] == 'PB'
        assert only_b[0]['actual_minutes'] == 105


# ======================================================================
# P3-1 资源利用率（复用 available_minutes）
# ======================================================================
class TestResourceUtilization:

    def test_overtime_and_utilization_from_shift_480(self):
        with _service(_seed_utilization) as svc:
            result = svc.resource_utilization(1, '2026-11-03', '2026-11-03')
        assert result['days'] == 1
        assert result['actual_minutes'] == 600
        assert result['available_minutes'] == 480.0
        assert result['utilization_pct'] == 125.0
        assert result['overtime_minutes'] == 120.0
        day = result['daily'][0]
        assert day['work_date'] == '2026-11-03'
        assert day['actual_minutes'] == 600
        assert day['available_minutes'] == 480.0
        assert day['overtime_minutes'] == 120.0
        assert day['capacity_missing'] is False

    def test_date_range_includes_both_ends(self):
        with _service(_seed_utilization) as svc:
            result = svc.resource_utilization(
                1, date(2026, 11, 2), '2026-11-03')
        assert result['start_date'] == '2026-11-02'
        assert result['end_date'] == '2026-11-03'
        assert result['days'] == 2
        assert result['actual_minutes'] == 600
        assert result['available_minutes'] == 960.0
        assert result['utilization_pct'] == 62.5
        assert result['daily'][0]['actual_minutes'] == 0
        assert result['daily'][0]['available_minutes'] == 480.0
        assert result['daily'][1]['actual_minutes'] == 600

    def test_leave_deduction_lowers_available(self):
        with _service(_seed_utilization) as svc:
            result = svc.resource_utilization(2, '2026-11-03', '2026-11-03')
        day = result['daily'][0]
        # 班次净 480 − 请假 240 = 240
        assert day['available_minutes'] == 240.0
        assert day['available_minutes'] < 480.0
        assert day['actual_minutes'] == 300
        assert day['utilization_pct'] == 125.0
        assert day['overtime_minutes'] == 60.0

    def test_resource_without_calendar_flags_capacity_missing(self):
        with _service(_seed_utilization) as svc:
            result = svc.resource_utilization(3, '2026-11-03', '2026-11-03')
        day = result['daily'][0]
        assert day['available_minutes'] == 0.0
        assert day['actual_minutes'] == 60
        assert day['capacity_missing'] is True
        assert day['utilization_pct'] == 0.0

    def test_start_after_end_raises_time_invalid(self):
        with _service(_seed_utilization) as svc:
            with pytest.raises(LaborError) as exc:
                svc.resource_utilization(1, '2026-11-03', '2026-11-02')
        assert exc.value.rule == 'ST_TIME_INVALID'

    def test_unknown_resource_raises_not_found(self):
        with _service(_seed_utilization) as svc:
            with pytest.raises(LaborError) as exc:
                svc.resource_utilization(404, '2026-11-03', '2026-11-03')
        assert exc.value.rule == 'RESOURCE_NOT_FOUND'


# ======================================================================
# P3-2 只读 API
# ======================================================================
class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {'user_id': '1', 'username': 'admin', 'token_version': 0,
                'permissions': ['*']}


AUTH = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'}


def _client(monkeypatch, seed):
    from flask import Flask
    conn = _db(seed)
    labor_api.init_service(_MemDS(conn))
    monkeypatch.setattr(auth_mw, 'token_blacklist_service', _FakeBlacklist())
    monkeypatch.setattr(auth_mw, 'TokenService', _FakeTokenService)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(labor_api.labor_bp)
    # 与 app_builder.with_blueprints() 同口径：/api/labor 无版本别名
    app.register_blueprint(labor_api.labor_bp, url_prefix='/api/labor',
                           name='labor_compat')
    return app.test_client(), conn


@pytest.fixture()
def agg_client(monkeypatch):
    client, conn = _client(monkeypatch, _seed_projects)
    yield client
    conn.close()
    labor_api._service = None


@pytest.fixture()
def util_client(monkeypatch):
    client, conn = _client(monkeypatch, _seed_utilization)
    yield client
    conn.close()
    labor_api._service = None


class TestLaborApi:

    def test_project_tasks_endpoint(self, agg_client):
        resp = agg_client.get('/api/v1/labor/project-tasks', headers=AUTH)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['total'] == 3
        items = body['data']['items']
        assert [row['project_task_id'] for row in items] == [101, 201, 102]
        assert items[0]['actual_minutes'] == 165

    def test_project_tasks_filter_and_legacy_path(self, agg_client):
        resp = agg_client.get(
            '/api/labor/projects?project_id=10', headers=AUTH)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['total'] == 1
        row = body['data']['items'][0]
        assert row['project_id'] == 10
        assert row['actual_minutes'] == 255
        assert row['project_name'] == '项目A'

    def test_resource_utilization_endpoint(self, util_client):
        resp = util_client.get(
            '/api/v1/labor/resources/utilization?resource_id=1'
            '&start_date=2026-11-03&end_date=2026-11-03', headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['resource_id'] == 1
        assert data['actual_minutes'] == 600
        assert data['available_minutes'] == 480.0
        assert data['utilization_pct'] == 125.0
        assert data['overtime_minutes'] == 120.0
        assert data['days'] == 1

    def test_resource_utilization_requires_resource_id(self, util_client):
        resp = util_client.get(
            '/api/v1/labor/resources/utilization', headers=AUTH)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert body['code'] == 'INVALID_PARAMETER'

    def test_resource_utilization_invalid_range(self, util_client):
        resp = util_client.get(
            '/api/v1/labor/resources/utilization?resource_id=1'
            '&start_date=2026-11-03&end_date=2026-11-02', headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'ST_TIME_INVALID'

    def test_endpoint_requires_login(self, agg_client):
        resp = agg_client.get('/api/v1/labor/project-tasks')
        assert resp.status_code == 401
