# -*- coding: utf-8 -*-
"""项目侧 G14：工时记录 `time_entry` 元模型 + 服务层校验（R-TE-1 … R-TE-6）

依据:
  docs/specs/tasks-project-g14-labor-view-2026-11-01.md §3 P1-1 / P1-2 / P4-1

【本文件守什么】
  TE-1 `time_entry` 字段 / 必填 / 5 索引 / 5 条真外键
  TE-2 labor_service 六条校验规则各 1 用例
  TE-3 成功落行：回填 work_order_id、默认 entry_type / billable、时间戳

建库一律走内存 SQLite 骨架表；需裸 SQL 时显式置 ALLOW_RAW_SQL。
"""
import logging
import os
import sqlite3
import sys
from datetime import date, timedelta

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.services.labor_service import LaborError, LaborService  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")
GENERATED_SQL = os.path.join(SCHEMA_DIR, "generated_schema.sql")

pytestmark = pytest.mark.unit


def _load_raw(bo_id):
    with open(os.path.join(SCHEMA_DIR, bo_id + ".yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get("fields") or []:
        if f.get("id") == field_id:
            return f
    return None


def _index(schema, name):
    for i in schema.get("indexes") or []:
        if i.get("name") == name:
            return i
    return None


def _reload_quietly():
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


# ─────────────────────────────────────────────────────────────────────────────
# TE-1 元模型
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeEntrySchema:

    def test_object_identity(self):
        raw = _load_raw('time_entry')
        assert raw['id'] == 'time_entry'
        assert raw['table_name'] == 'time_entries'
        assert raw['aspects'] == ['audit_aspect']
        assert raw['ui_view_config']['skip_auto_menu'] is True

    def test_required_and_nullable_fields(self):
        raw = _load_raw('time_entry')
        for fid in ('work_date', 'resource_id', 'minutes', 'entry_type', 'billable'):
            assert _field(raw, fid)['required'] is True, fid
        for fid in ('project_task_id', 'work_order_id', 'work_order_operation_id',
                    'resource_assignment_id', 'note'):
            assert _field(raw, fid)['nullable'] is True, fid

    def test_minutes_constraint(self):
        minutes = _field(_load_raw('time_entry'), 'minutes')
        assert minutes['type'] == 'integer'
        constraint = minutes['constraints'][0]
        assert constraint['type'] == 'numeric_range'
        assert constraint['gt'] == 0
        assert constraint['lte'] == 1440
        assert constraint['decimal_places'] == 0

    def test_five_indexes(self):
        raw = _load_raw('time_entry')
        expected = {
            'idx_time_entry_task_date': ['project_task_id', 'work_date'],
            'idx_time_entry_resource_date': ['resource_id', 'work_date'],
            'idx_time_entry_wo': ['work_order_id'],
            'idx_time_entry_operation': ['work_order_operation_id'],
            'idx_time_entry_assignment': ['resource_assignment_id'],
        }
        for name, fields in expected.items():
            index = _index(raw, name)
            assert index is not None, name
            assert index['fields'] == fields, name

    def test_five_true_foreign_keys(self):
        raw = _load_raw('time_entry')
        relations = {r['target']: r for r in raw.get('relations') or []}
        assert set(relations) == {
            'resource', 'project_task', 'work_order',
            'work_order_operation', 'resource_assignment'}
        for target, relation in relations.items():
            assert relation['type'] == 'reference'
            assert relation['source_field'] == '%s_id' % target

    def test_ddl_has_all_columns_and_foreign_keys(self):
        _reload_quietly()
        mo = registry.get('time_entry')
        assert mo is not None and mo.table_name == 'time_entries'
        sql = SchemaGenerator("sqlite").generate_create_table(mo)
        assert 'CREATE TABLE IF NOT EXISTS time_entries' in sql
        for column in ('work_date DATETIME NOT NULL', 'resource_id INTEGER NOT NULL',
                       'minutes INTEGER NOT NULL', 'project_task_id INTEGER',
                       'work_order_id INTEGER', 'work_order_operation_id INTEGER',
                       'resource_assignment_id INTEGER',
                       "entry_type VARCHAR(200) NOT NULL DEFAULT 'manual'",
                       'billable INTEGER NOT NULL DEFAULT 1', 'note VARCHAR(200)'):
            assert column in sql, column
        for fk in ('FOREIGN KEY (resource_id) REFERENCES resources(id)',
                   'FOREIGN KEY (project_task_id) REFERENCES project_tasks(id)',
                   'FOREIGN KEY (work_order_id) REFERENCES work_orders(id)',
                   'FOREIGN KEY (work_order_operation_id) '
                   'REFERENCES work_order_operations(id)',
                   'FOREIGN KEY (resource_assignment_id) '
                   'REFERENCES resource_assignments(id)'):
            assert fk in sql, fk

    def test_generated_schema_has_table_and_indexes(self):
        with open(GENERATED_SQL, "r", encoding="utf-8") as f:
            sql = f.read()
        assert 'CREATE TABLE IF NOT EXISTS time_entries' in sql
        for name in ('idx_time_entry_task_date', 'idx_time_entry_resource_date',
                     'idx_time_entry_wo', 'idx_time_entry_operation',
                     'idx_time_entry_assignment'):
            assert 'INDEX IF NOT EXISTS ' + name in sql, name


# ─────────────────────────────────────────────────────────────────────────────
# TE-2 / TE-3 服务层校验
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE resources (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    task_no TEXT,
    name TEXT
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
"""


class _MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cursor = self.conn.execute(sql, params or [])
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    conn.executescript("""
        INSERT INTO resources (id, code, name, is_active)
        VALUES (1, 'R-1', '张工', 1), (2, 'R-2', '停用资源', 0);
        INSERT INTO project_tasks (id, project_id, task_no, name)
        VALUES (11, 7, 'T-01', '任务A'), (12, 8, 'T-02', '任务B');
        INSERT INTO work_orders (id, work_order_no, project_id)
        VALUES (21, 'WO-01', 7), (22, 'WO-02', 8), (23, 'WO-03', NULL);
        INSERT INTO work_order_operations (id, work_order_id, operation_name)
        VALUES (31, 21, '安装'), (32, 22, '维修'), (33, 23, '巡检');
        INSERT INTO resource_assignments (id, work_order_operation_id, resource_id)
        VALUES (41, 31, 1), (42, 32, 2);
    """)
    return conn


def _svc(conn):
    return LaborService(_MemDS(conn))


def _today():
    return date.today()


def _payload(**over):
    payload = {
        'work_date': (_today() - timedelta(days=1)).strftime('%Y-%m-%d'),
        'resource_id': 1,
        'minutes': 60,
        'project_task_id': 11,
    }
    payload.update(over)
    return payload


def _row(conn, entry_id):
    cursor = conn.execute('SELECT * FROM time_entries WHERE id = ?', [entry_id])
    columns = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


class TestLaborServiceRules:

    def test_r_te_1_anchor_required(self):
        conn = _db()
        with pytest.raises(LaborError) as err:
            _svc(conn).record_time({
                'work_date': _payload()['work_date'],
                'resource_id': 1,
                'minutes': 60,
            })
        assert err.value.rule == 'ST_TIME_ENTRY_ANCHOR_REQUIRED'
        assert err.value.field_name == 'project_task_id'

    def test_r_te_2_project_mismatch(self):
        conn = _db()
        with pytest.raises(LaborError) as err:
            _svc(conn).record_time(_payload(project_task_id=12,
                                            work_order_operation_id=31))
        assert err.value.rule == 'ST_PROJECT_MISMATCH'
        assert err.value.details['task_project_id'] == 8
        assert err.value.details['work_order_project_id'] == 7

    def test_r_te_2_null_work_order_project_uses_task(self):
        conn = _db()
        result = _svc(conn).record_time(
            _payload(project_task_id=11, work_order_operation_id=33))
        assert result['id'] > 0

    def test_r_te_3_backfills_and_rejects_conflicting_work_order(self):
        conn = _db()
        result = _svc(conn).record_time(_payload(work_order_operation_id=31))
        row = _row(conn, result['id'])
        assert row['work_order_id'] == 21
        assert row['work_order_operation_id'] == 31

        with pytest.raises(LaborError) as err:
            _svc(conn).record_time(_payload(work_order_operation_id=31,
                                            work_order_id=22))
        assert err.value.rule == 'ST_WORK_ORDER_MISMATCH'
        assert err.value.field_name == 'work_order_id'

    def test_r_te_4_assignment_mismatch(self):
        conn = _db()
        with pytest.raises(LaborError) as err:
            _svc(conn).record_time(_payload(work_order_operation_id=31,
                                            resource_id=1,
                                            resource_assignment_id=42))
        assert err.value.rule == 'ST_ASSIGNMENT_MISMATCH'

        result = _svc(conn).record_time(_payload(work_order_operation_id=31,
                                                 resource_id=1,
                                                 resource_assignment_id=41))
        assert _row(conn, result['id'])['resource_assignment_id'] == 41

    def test_r_te_5_minutes_and_work_date(self):
        conn = _db()
        tomorrow = (_today() + timedelta(days=1)).strftime('%Y-%m-%d')
        for bad in ({'minutes': 0}, {'minutes': 1441},
                    {'minutes': 30.5}, {'minutes': 'abc'},
                    {'work_date': tomorrow}, {'work_date': '2026-13-01'}):
            with pytest.raises(LaborError) as err:
                _svc(conn).record_time(_payload(**bad))
            assert err.value.rule == 'ST_TIME_INVALID', bad

    def test_r_te_6_resource_must_be_active(self):
        conn = _db()
        with pytest.raises(LaborError) as err:
            _svc(conn).record_time(_payload(resource_id=2,
                                            work_order_operation_id=32))
        assert err.value.rule == 'ST_RESOURCE_INACTIVE'
        assert err.value.field_name == 'resource_id'

    def test_success_defaults_and_timestamps(self):
        conn = _db()
        result = _svc(conn).record_time(
            _payload(note='现场补录', project_task_id=11))
        row = _row(conn, result['id'])
        assert row['entry_type'] == 'manual'
        assert row['billable'] == 1
        assert row['note'] == '现场补录'
        assert row['created_at'] and row['updated_at']
        assert row['work_date'] == _payload()['work_date']
        assert row['minutes'] == 60
