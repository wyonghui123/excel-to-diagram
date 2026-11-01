# -*- coding: utf-8 -*-
"""项目侧 G14：工时回聚三视图（Phase 2）

依据:
  docs/specs/tasks-project-g14-labor-view-2026-11-01.md §4 视图 SQL 草案 / §5 验收出口

【本文件守什么】
  LV-1 空库可建三视图、可 SELECT
  LV-2 种子（项目 A 两任务 + 项目 B 一任务 + 只挂工单的工时）聚合数字正确
  LV-3 任务级 / 项目级 / 资源日级口径一致，且「任务 + 同项目工序」只计一次
  LV-4 v182 迁移：建表 / 视图可查 / 幂等 / verify / rollback 后视图消失且权限保留
"""
import os
import sqlite3
import sys

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.migrations import v182__time_entry_labor_view as v182  # noqa: E402

pytestmark = pytest.mark.unit

_BASE_SCHEMA = """
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
CREATE TABLE resources (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    is_active INTEGER DEFAULT 1
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
"""

_META_SCHEMA = """
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT,
    resource_type TEXT,
    action TEXT
);
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code TEXT UNIQUE NOT NULL,
    menu_name TEXT,
    menu_path TEXT,
    page_type TEXT,
    object_types TEXT,
    primary_object_type TEXT,
    bo_bindings TEXT,
    required_permissions TEXT,
    parent_menu TEXT,
    icon TEXT,
    color TEXT,
    description TEXT,
    sort_order INTEGER,
    is_active INTEGER,
    show_in_sidebar INTEGER,
    auto_generated INTEGER
);
CREATE TABLE menu_permissions (
    menu_code TEXT PRIMARY KEY,
    menu_name TEXT,
    menu_path TEXT,
    required_permissions TEXT,
    required_any_permission INTEGER,
    parent_menu TEXT,
    icon TEXT,
    sort_order INTEGER,
    is_active INTEGER,
    data_permission_hint TEXT
);
"""


def _seed(conn):
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
    # e1 / e2 / e3：只挂任务；e4：只挂工单（项目 A）；e5：任务 + 同项目工序；
    # e6：只挂工单（项目 B）。e5 若被双计，项目 A 的分钟数会变成 300。
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


def _view_rows(conn, view, **filters):
    where = ''
    if filters:
        where = ' WHERE ' + ' AND '.join('%s = ?' % k for k in filters)
    cursor = conn.execute('SELECT * FROM %s%s' % (view, where),
                          list(filters.values()))
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


class TestLaborViewsAggregation:

    def _conn(self):
        conn = sqlite3.connect(':memory:')
        conn.executescript(_BASE_SCHEMA)
        _seed(conn)
        v182.create_views(conn)
        return conn

    def test_empty_db_creates_queryable_views(self):
        conn = sqlite3.connect(':memory:')
        conn.executescript(_BASE_SCHEMA)
        v182.create_views(conn)
        for name, _sql in v182.VIEW_DEFINITIONS:
            assert conn.execute(
                'SELECT * FROM %s LIMIT 1' % name).fetchall() == []

    def test_task_level_numbers(self):
        conn = self._conn()
        rows = _view_rows(conn, 'v_project_task_labor')
        by_task = {row['project_task_id']: row for row in rows}
        assert set(by_task) == {101, 102, 201}

        task = by_task[101]
        assert task['project_id'] == 10
        assert task['task_no'] == '1.1'
        assert task['task_name'] == '任务A1'
        assert task['status'] == 'in_progress'
        assert task['actual_minutes'] == 165
        assert task['actual_hours'] == pytest.approx(2.75)
        assert task['billable_minutes'] == 165
        assert task['entry_count'] == 2
        assert task['resource_count'] == 2
        assert task['first_work_date'] == '2026-10-30'
        assert task['last_work_date'] == '2026-10-31'

        assert by_task[102]['actual_minutes'] == 60
        assert by_task[201]['actual_minutes'] == 90
        assert by_task[201]['billable_minutes'] == 0

    def test_project_level_numbers_and_work_order_only_entry(self):
        conn = self._conn()
        rows = _view_rows(conn, 'v_project_labor')
        by_project = {row['project_id']: row for row in rows}

        project_a = by_project[10]
        assert project_a['project_no'] == 'PA'
        assert project_a['project_name'] == '项目A'
        # 120 + 60 + 30(只挂工单) + 45(任务+同项目工序，只计一次) = 255
        assert project_a['actual_minutes'] == 255
        assert project_a['actual_hours'] == pytest.approx(4.25)
        assert project_a['billable_minutes'] == 255
        assert project_a['task_count'] == 2
        assert project_a['resource_count'] == 2
        assert project_a['entry_count'] == 4
        assert project_a['last_work_date'] == '2026-10-31'

        project_b = by_project[20]
        # 90(任务) + 15(只挂工单) = 105；90 非计费
        assert project_b['actual_minutes'] == 105
        assert project_b['actual_hours'] == pytest.approx(1.75)
        assert project_b['billable_minutes'] == 15
        assert project_b['task_count'] == 1
        assert project_b['resource_count'] == 1
        assert project_b['entry_count'] == 2
        assert project_b['last_work_date'] == '2026-10-31'

    def test_task_and_operation_entry_counted_once(self):
        """e5 同时挂任务 101 与工单 301（同项目 10），项目级只计一次。"""
        conn = self._conn()
        project_a = _view_rows(conn, 'v_project_labor', project_id=10)[0]
        task_rows = _view_rows(conn, 'v_project_task_labor', project_id=10)
        task_minutes = sum(row['actual_minutes'] for row in task_rows)
        assert task_minutes == 225
        assert project_a['actual_minutes'] == task_minutes + 30
        assert project_a['entry_count'] == 4

    def test_resource_daily_numbers(self):
        conn = self._conn()
        rows = _view_rows(conn, 'v_resource_labor_daily')
        by_key = {(row['resource_id'], row['work_date']): row for row in rows}

        assert by_key[(1, '2026-10-30')]['actual_minutes'] == 120
        assert by_key[(1, '2026-10-30')]['entry_count'] == 1
        assert by_key[(1, '2026-10-30')]['project_count'] == 1

        assert by_key[(1, '2026-10-31')]['actual_minutes'] == 30
        assert by_key[(1, '2026-10-31')]['billable_minutes'] == 30

        assert by_key[(2, '2026-10-31')]['actual_minutes'] == 105
        assert by_key[(2, '2026-10-31')]['billable_minutes'] == 105
        assert by_key[(2, '2026-10-31')]['entry_count'] == 2
        assert by_key[(2, '2026-10-31')]['project_count'] == 1

        assert by_key[(3, '2026-10-30')]['actual_minutes'] == 15
        assert by_key[(3, '2026-10-30')]['project_count'] == 1
        assert by_key[(3, '2026-10-31')]['actual_minutes'] == 90
        assert by_key[(3, '2026-10-31')]['billable_minutes'] == 0

    def test_resource_daily_equals_project_totals(self):
        conn = self._conn()
        daily_total = sum(
            row['actual_minutes'] for row in _view_rows(conn, 'v_resource_labor_daily'))
        project_total = sum(
            row['actual_minutes'] for row in _view_rows(conn, 'v_project_labor'))
        entry_total = conn.execute(
            'SELECT SUM(minutes) FROM time_entries').fetchone()[0]
        assert daily_total == project_total == entry_total == 360


# ─────────────────────────────────────────────────────────────────────────────
# LV-4 v182 迁移
# ─────────────────────────────────────────────────────────────────────────────

def _build_db(path):
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_BASE_SCHEMA)
        conn.executescript(_META_SCHEMA)
        # 视图依赖的骨架表已含；time_entries 由迁移创建
        conn.execute('DROP TABLE time_entries')
        conn.commit()
    finally:
        conn.close()
    return path


def _table_exists(path, table):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()[0] == 1
    finally:
        conn.close()


def _view_exists(path, view):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT COUNT(1) FROM sqlite_master WHERE type='view' AND name=?",
            (view,)).fetchone()[0] == 1
    finally:
        conn.close()


def _index_count(path, name):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT COUNT(1) FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()[0]
    finally:
        conn.close()


def _permission_codes(path):
    conn = sqlite3.connect(str(path))
    try:
        return {row[0] for row in conn.execute('SELECT code FROM permissions')}
    finally:
        conn.close()


def _menu_active(path, code):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute('SELECT is_active FROM menus WHERE menu_code=?',
                           (code,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


class TestMigration:

    def test_migrate_creates_table_indexes_permissions_menu_views(self, tmp_path):
        db = _build_db(tmp_path / 'g14.db')
        assert v182.verify(db) is False
        assert v182.migrate(db) is True
        assert v182.verify(db) is True
        assert _table_exists(db, v182.TIME_ENTRY_TABLE)
        for name, _table, _sql in v182.INDEXES:
            assert _index_count(db, name) == 1, name
        assert {p[0] for p in v182.PERMISSIONS} <= _permission_codes(db)
        assert _menu_active(db, v182.TIME_ENTRY_MENU['menu_code']) == 1
        for name, _sql in v182.VIEW_DEFINITIONS:
            assert _view_exists(db, name), name
            conn = sqlite3.connect(str(db))
            try:
                conn.execute('SELECT * FROM %s LIMIT 1' % name).fetchall()
            finally:
                conn.close()

    def test_migrate_is_idempotent(self, tmp_path):
        db = _build_db(tmp_path / 'g14_twice.db')
        assert v182.migrate(db) is True
        assert v182.migrate(db) is True
        assert v182.verify(db) is True
        for name, _table, _sql in v182.INDEXES:
            assert _index_count(db, name) == 1, name
        for name, _sql in v182.VIEW_DEFINITIONS:
            assert _view_exists(db, name), name

    def test_rollback_drops_views_table_menu_keeps_permissions(self, tmp_path):
        db = _build_db(tmp_path / 'g14_rollback.db')
        assert v182.migrate(db) is True
        assert v182.rollback(db) is True
        for name, _sql in v182.VIEW_DEFINITIONS:
            assert not _view_exists(db, name), name
        assert not _table_exists(db, v182.TIME_ENTRY_TABLE)
        for name, _table, _sql in v182.INDEXES:
            assert _index_count(db, name) == 0, name
        assert _menu_active(db, v182.TIME_ENTRY_MENU['menu_code']) is None
        assert {p[0] for p in v182.PERMISSIONS} <= _permission_codes(db)
