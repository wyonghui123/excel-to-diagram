# -*- coding: utf-8 -*-
"""G12：工单工序补作业定义溯源

依据:
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §3 G12 / D4
  docs/specs/tasks-project-g12-g13-execution-boundary-2026-11-01.md P1

【本文件守什么】
  P1-1 work_order_operation 声明可空 work_definition_id / work_definition_operation_id
       （字段 + 索引，不声明真外键；空值 = 手填工序）
  P1-2 表单 / 详情可见工艺溯源
  P1-3 v184 迁移对存量库补列 + 补索引，幂等；回滚只删索引、保留列
  P1-4 工序**不新增** project_task_id（§8.2 红线 2 不被 G12 破坏）
"""
import logging
import os
import sqlite3
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.migrations import v184__work_order_operation_definition_trace as v184  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

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


def _columns(db_path, table):
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute('PRAGMA table_info({0})'.format(table))}
    finally:
        conn.close()


def _index_count(db_path, name):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT COUNT(1) FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()[0]
    finally:
        conn.close()


def _build_legacy_operation_db(path):
    """最小骨架表：模拟 v184 之前（无溯源列）的存量库。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute('CREATE TABLE {0} (id INTEGER PRIMARY KEY, '
                     'work_order_id INTEGER, seq INTEGER)'.format(
                         v184.OPERATION_TABLE))
        conn.commit()
    finally:
        conn.close()
    return path


class TestDefinitionTraceSchema:
    def test_trace_fields_declared_nullable(self):
        raw = _load_raw('work_order_operation')
        for fid in (v184.DEFINITION_COLUMN, v184.DEFINITION_OP_COLUMN):
            field = _field(raw, fid)
            assert field is not None
            assert field['nullable'] is True
            assert field['semantics']['display']['type'] == 'association'

    def test_no_true_foreign_key_for_trace(self):
        raw = _load_raw('work_order_operation')
        relations = {r['id'] for r in raw['relations']}
        assert 'work_order_operation_to_work_definition' not in relations
        indexes = {i['name'] for i in raw['indexes']}
        assert v184.INDEXES[0][0] in indexes
        assert v184.INDEXES[1][0] in indexes

    def test_red_line_operation_has_no_project_task_id(self):
        raw = _load_raw('work_order_operation')
        assert _field(raw, 'project_task_id') is None

    def test_ui_exposes_trace_in_form_and_detail(self):
        ui = _load_raw('work_order_operation')['ui_view_config']
        form_fields = [
            f for section in ui['form']['sections']
            for column in section['columns']
            for f in column['fields']
        ]
        assert v184.DEFINITION_COLUMN in form_fields
        assert v184.DEFINITION_OP_COLUMN in form_fields
        detail_fields = [f for facet in ui['detail']['facets'] for f in facet['fields']]
        assert v184.DEFINITION_COLUMN in detail_fields
        assert v184.DEFINITION_OP_COLUMN in detail_fields

    def test_generated_ddl_has_plain_nullable_columns(self):
        _reload_quietly()
        mo = registry.get('work_order_operation')
        assert mo is not None
        sql = SchemaGenerator("sqlite").generate_create_table(mo)
        assert 'work_definition_id INTEGER' in sql
        assert 'work_definition_operation_id INTEGER' in sql
        assert 'FOREIGN KEY (work_definition_id)' not in sql


class TestDefinitionTraceMigration:
    def test_migration_adds_columns_and_indexes(self, tmp_path):
        db = _build_legacy_operation_db(tmp_path / 'g12_trace.db')
        assert v184.verify(db) is False
        assert v184.migrate(db) is True
        assert v184.verify(db) is True
        columns = _columns(db, v184.OPERATION_TABLE)
        assert v184.DEFINITION_COLUMN in columns
        assert v184.DEFINITION_OP_COLUMN in columns
        assert _index_count(db, v184.INDEXES[0][0]) == 1
        assert _index_count(db, v184.INDEXES[1][0]) == 1

    def test_migration_is_idempotent(self, tmp_path):
        db = _build_legacy_operation_db(tmp_path / 'g12_trace_twice.db')
        assert v184.migrate(db) is True
        assert v184.migrate(db) is True
        assert v184.verify(db) is True
        assert _index_count(db, v184.INDEXES[0][0]) == 1

    def test_rollback_drops_indexes_keeps_columns(self, tmp_path):
        db = _build_legacy_operation_db(tmp_path / 'g12_trace_rollback.db')
        assert v184.migrate(db) is True
        assert v184.rollback(db) is True
        assert _index_count(db, v184.INDEXES[0][0]) == 0
        assert _index_count(db, v184.INDEXES[1][0]) == 0
        columns = _columns(db, v184.OPERATION_TABLE)
        assert v184.DEFINITION_COLUMN in columns
