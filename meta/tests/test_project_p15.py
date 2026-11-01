# -*- coding: utf-8 -*-
"""项目侧 P1.5：计划层 `project_task` + 依赖边（AC-09 / G11）

依据:
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §2.5 / AC-09
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P1.5

【本文件守什么】
  P15-1 `project_task` 可独立创建 / 关闭（字段 + 声明式状态机，不生成 tasks）
  P15-2 `project_task_dependency` 只表达 FS/SS/FF/SF + lag（lag 可正可负）
  P15-3 `source_demand_type='project_task'` 时 `source_demand_id` 必填
  P15-4 该任务必须归属同一 `project_id`（缺省时从任务回填）
  P15-5 v179 迁移：建表 / 索引 / 权限 / 菜单，幂等；回滚删表保留权限
  P15-6 `generated_schema.sql` 与 registry 生成 DDL 一致（无外键漂移）

建库一律走内存 SQLite 骨架表；需裸 SQL 时显式置 ALLOW_RAW_SQL。
"""
import logging
import os
import sqlite3
import sys

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.migrations import v179__project_task_p15 as v179  # noqa: E402
from meta.services.work_order_service import (  # noqa: E402
    WorkOrderError,
    WorkOrderService,
)

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


def _reload_quietly():
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


def _index(schema, name):
    for i in schema.get("indexes") or []:
        if i.get("name") == name:
            return i
    return None


# ─────────────────────────────────────────────────────────────────────────────
# P15-1 project_task 声明与状态机
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectTaskSchema:

    def test_core_fields_declared(self):
        raw = _load_raw('project_task')
        project = _field(raw, 'project_id')
        assert project['required'] is True
        assert project['semantics']['display']['target_type'] == 'project'
        parent = _field(raw, 'parent_task_id')
        assert parent['nullable'] is True
        assert parent['semantics']['hierarchy_field'] == 'parent'
        task_no = _field(raw, 'task_no')
        assert task_no['max_length'] == 30
        assert _field(raw, 'name')['max_length'] == 200
        assert _field(raw, 'owner_user_id')['nullable'] is True

    def test_status_machine_is_declarative(self):
        raw = _load_raw('project_task')
        status = _field(raw, 'status')
        assert {e['value'] for e in status['enum_values']} == {
            'draft', 'planned', 'in_progress', 'done', 'cancelled'}
        rules = raw['rules']
        assert {r['type'] for r in rules} == {'state_transition'}
        assert {r['state_field'] for r in rules} == {'status'}
        transitions = {
            (r['id'], tuple(r['from_states']), r['to_state']) for r in rules
        }
        assert transitions == {
            ('plan_task', ('draft',), 'planned'),
            ('start_task', ('planned',), 'in_progress'),
            ('complete_task', ('in_progress',), 'done'),
            ('cancel_task', ('draft', 'planned', 'in_progress'), 'cancelled'),
        }

    def test_plan_does_not_create_actions(self):
        """红线：计划只产需求不产动作——不生成 tasks、不挂工序。"""
        raw = _load_raw('project_task')
        field_ids = {f['id'] for f in raw['fields']}
        assert 'task_id' not in field_ids
        assert 'work_order_operation_id' not in field_ids
        assert 'operation_id' not in field_ids

    def test_task_no_unique_within_project(self):
        raw = _load_raw('project_task')
        index = _index(raw, 'uidx_project_task_no')
        assert index['fields'] == ['project_id', 'task_no']
        assert index['unique'] is True

    def test_project_relation_and_ddl(self):
        raw = _load_raw('project_task')
        relations = {r['id'] for r in raw['relations']}
        assert 'project_task_to_project' in relations
        _reload_quietly()
        mo = registry.get('project_task')
        assert mo is not None and mo.table_name == v179.TASK_TABLE
        sql = SchemaGenerator("sqlite").generate_create_table(mo)
        assert 'project_tasks' in sql
        assert 'parent_task_id INTEGER' in sql
        assert 'FOREIGN KEY (project_id) REFERENCES projects(id)' in sql

    def test_ui_exposes_plan_fields(self):
        ui = _load_raw('project_task')['ui_view_config']
        list_fields = {c['field'] for c in ui['list']['columns']}
        assert {'task_no', 'status', 'planned_start', 'percent_complete'} <= list_fields
        form_fields = [
            f for section in ui['form']['sections']
            for column in section['columns']
            for f in column['fields']
        ]
        for fid in ('project_id', 'parent_task_id', 'task_no', 'status'):
            assert fid in form_fields


# ─────────────────────────────────────────────────────────────────────────────
# P15-2 依赖边语义
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectTaskDependencySchema:

    def test_dependency_type_is_exactly_four_values(self):
        field = _field(_load_raw('project_task_dependency'), 'dependency_type')
        assert {e['value'] for e in field['enum_values']} == {
            'FS', 'SS', 'FF', 'SF'}

    def test_lag_minutes_signed(self):
        field = _field(_load_raw('project_task_dependency'), 'lag_minutes')
        assert field['type'] == 'integer'
        assert field['required'] is True
        constraint = field['constraints'][0]
        assert constraint['type'] == 'numeric_range'
        assert constraint['decimal_places'] == 0
        # 可正可负：下界必须允许负数（不得是 0 / 正值）
        assert constraint['gte'] < 0

    def test_edge_unique_three_columns(self):
        raw = _load_raw('project_task_dependency')
        index = _index(raw, 'uidx_ptd_edge')
        assert index['fields'] == [
            'predecessor_task_id', 'successor_task_id', 'dependency_type']
        assert index['unique'] is True
        relations = {r['id'] for r in raw['relations']}
        assert relations == {
            'project_task_dependency_to_predecessor',
            'project_task_dependency_to_successor',
        }

    def test_fk_to_project_task_in_ddl(self):
        _reload_quietly()
        mo = registry.get('project_task_dependency')
        assert mo is not None and mo.table_name == v179.DEPENDENCY_TABLE
        sql = SchemaGenerator("sqlite").generate_create_table(mo)
        assert 'project_task_dependencies' in sql
        assert 'lag_minutes INTEGER NOT NULL DEFAULT 0' in sql
        assert 'FOREIGN KEY (predecessor_task_id) REFERENCES project_tasks(id)' in sql
        assert 'FOREIGN KEY (successor_task_id) REFERENCES project_tasks(id)' in sql


# ─────────────────────────────────────────────────────────────────────────────
# P15-3 / P15-4 需求来源：project_task
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no TEXT,
    order_type TEXT,
    schedule_id INTEGER,
    order_id INTEGER,
    order_line_id INTEGER,
    customer_account_id INTEGER,
    project_id INTEGER,
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
CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    task_no TEXT,
    name TEXT
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
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cursor = self.conn.execute(sql, params or [])
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])


def _db(task_project_id=7, task_id=1):
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO project_tasks (id, project_id, task_no, name) "
        "VALUES (?, ?, 'T-01', '现场安装')", [task_id, task_project_id])
    return conn


def _svc(conn):
    return WorkOrderService(_MemDS(conn))


def _create(conn, **over):
    payload = {'order_type': 'production',
               'source_demand_type': 'project_task',
               'source_demand_id': 1}
    payload.update(over)
    return _svc(conn).create_work_order(payload)


def _saved_project_id(conn, work_order_id):
    row = conn.execute('SELECT project_id FROM work_orders WHERE id = ?',
                       [work_order_id]).fetchone()
    return row[0]


class TestProjectTaskDemand:

    def test_source_demand_id_required(self):
        conn = _db()
        with pytest.raises(WorkOrderError) as err:
            _svc(conn).create_work_order({
                'order_type': 'production',
                'source_demand_type': 'project_task'})
        assert err.value.rule == 'ST_SOURCE_DEMAND_REQUIRED'

    def test_missing_task_rejected(self):
        conn = _db()
        with pytest.raises(WorkOrderError) as err:
            _create(conn, source_demand_id=99)
        assert err.value.rule == 'ST_SOURCE_DEMAND_INVALID'

    def test_project_mismatch_rejected(self):
        conn = _db(task_project_id=7)
        with pytest.raises(WorkOrderError) as err:
            _create(conn, project_id=8)
        assert err.value.rule == 'ST_PROJECT_MISMATCH'
        assert err.value.field_name == 'project_id'

    def test_project_inherited_from_task(self):
        conn = _db(task_project_id=7)
        result = _create(conn)
        assert result['source_demand_type'] == 'project_task'
        assert result['source_demand_id'] == 1
        assert _saved_project_id(conn, result['id']) == 7
        assert result['component_expansion']['code'] == 'no_structure'

    def test_same_project_accepted(self):
        conn = _db(task_project_id=7)
        result = _create(conn, project_id=7)
        assert _saved_project_id(conn, result['id']) == 7

    def test_work_order_schema_lists_project_task_enum(self):
        field = _field(_load_raw('work_order'), 'source_demand_type')
        assert 'project_task' in {e['value'] for e in field['enum_values']}


# ─────────────────────────────────────────────────────────────────────────────
# P15-5 v179 迁移
# ─────────────────────────────────────────────────────────────────────────────

_MIGRATION_SCHEMA = """
CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT);
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


def _build_db(path, with_meta=True):
    conn = sqlite3.connect(str(path))
    try:
        if with_meta:
            conn.executescript(_MIGRATION_SCHEMA)
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

    def test_migrations_create_tables_indexes_permissions_menu(self, tmp_path):
        db = _build_db(tmp_path / 'p15.db')
        assert v179.verify(db) is False
        assert v179.migrate(db) is True
        assert v179.verify(db) is True
        assert _table_exists(db, v179.TASK_TABLE)
        assert _table_exists(db, v179.DEPENDENCY_TABLE)
        for name, _table, _sql in v179.INDEXES:
            assert _index_count(db, name) == 1, name
        assert {p[0] for p in v179.PERMISSIONS} <= _permission_codes(db)
        assert _menu_active(db, v179.TASK_MENU['menu_code']) == 1

    def test_migrate_is_idempotent(self, tmp_path):
        db = _build_db(tmp_path / 'p15_twice.db')
        assert v179.migrate(db) is True
        assert v179.migrate(db) is True
        assert v179.verify(db) is True
        for name, _table, _sql in v179.INDEXES:
            assert _index_count(db, name) == 1, name
        assert len(v179.PERMISSIONS) == len(
            {p[0] for p in v179.PERMISSIONS} & _permission_codes(db))

    def test_migrate_skips_meta_tables_when_absent(self, tmp_path):
        """最小库里没有 permissions / menus 时仍能建表（权限与菜单 fail-open）。"""
        db = _build_db(tmp_path / 'p15_plain.db', with_meta=False)
        assert v179.migrate(db) is True
        assert v179.verify(db) is True
        assert _table_exists(db, v179.TASK_TABLE)
        assert _table_exists(db, v179.DEPENDENCY_TABLE)

    def test_rollback_drops_tables_keeps_permissions(self, tmp_path):
        db = _build_db(tmp_path / 'p15_rollback.db')
        assert v179.migrate(db) is True
        assert v179.rollback(db) is True
        assert not _table_exists(db, v179.TASK_TABLE)
        assert not _table_exists(db, v179.DEPENDENCY_TABLE)
        for name, _table, _sql in v179.INDEXES:
            assert _index_count(db, name) == 0, name
        assert _menu_active(db, v179.TASK_MENU['menu_code']) is None
        assert {p[0] for p in v179.PERMISSIONS} <= _permission_codes(db)


# ─────────────────────────────────────────────────────────────────────────────
# P15-6 generated_schema.sql 与迁移 DDL 一致
# ─────────────────────────────────────────────────────────────────────────────

class TestGeneratedSchema:

    def test_generated_sql_has_both_tables_and_indexes(self):
        with open(GENERATED_SQL, "r", encoding="utf-8") as f:
            sql = f.read()
        assert 'CREATE TABLE IF NOT EXISTS project_tasks' in sql
        assert 'CREATE TABLE IF NOT EXISTS project_task_dependencies' in sql
        for name, _table, _sql in v179.INDEXES:
            assert 'INDEX IF NOT EXISTS ' + name in sql, name
        assert 'FOREIGN KEY (project_id) REFERENCES projects(id)' in sql
        assert 'FOREIGN KEY (predecessor_task_id) REFERENCES project_tasks(id)' in sql
