# -*- coding: utf-8 -*-
"""项目对象 P2 / B1：工单归集到项目

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §0.1 P2
  docs/specs/spec-project-type-object-model-research-2026-10-31.md §2.2

【本文件守什么】
  B1-1 work_order 声明可空 project_id（与 P1 三处挂载同构：字段 + 索引，不声明真外键）
  B1-2 项目 360 增加只读「工单」段，按 project_id 原生过滤
  B1-3 v175 迁移对存量库补列 + 补索引，幂等；回滚只删索引、保留列

建库一律走 factories 的 create_tables / seed_row（conftest 的裸 SQL 守卫
会把含裸 DML 的测试文件整体 skip）。
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
from meta.migrations.v175__work_order_project_id import (  # noqa: E402
    PROJECT_COLUMN,
    PROJECT_INDEX,
    WORK_ORDER_TABLE,
    migrate,
    rollback,
    verify,
)

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


# ─────────────────────────────────────────────────────────────────────────────
# B1-1 work_order.project_id 声明
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkOrderProjectMount:

    def test_project_id_is_nullable_and_points_to_project(self):
        field = _field(_load_raw('work_order'), 'project_id')
        assert field is not None
        assert field['nullable'] is True
        assert field['description'].startswith('所属项目')
        assert field['value_help']['source']['target_bo'] == 'project'
        assert field['value_help']['source']['code_field'] == 'project_no'
        assert field['ui']['relation'] == 'project'
        assert field['ui']['multiple'] is False
        assert field['ui']['clearable'] is True

    def test_project_id_has_index_declared(self):
        indexes = {i['name']: i for i in _load_raw('work_order')['indexes']}
        assert indexes[PROJECT_INDEX]['fields'] == [PROJECT_COLUMN]

    def test_no_reference_relation_to_project(self):
        """与 P1 三处挂载同构：不加真外键，避免存量库 / 新建库双源漂移。"""
        relations = _load_raw('work_order')['relations']
        assert 'work_order_to_project' not in {r['id'] for r in relations}

    def test_ui_exposes_project_in_list_form_and_detail(self):
        ui = _load_raw('work_order')['ui_view_config']
        assert 'project_id' in {c['field'] for c in ui['list']['columns']}
        form_fields = [
            f for section in ui['form']['sections']
            for column in section['columns']
            for f in column['fields']
        ]
        assert 'project_id' in form_fields
        detail_fields = [
            f for facet in ui['detail']['facets']
            for f in facet['fields']
        ]
        assert 'project_id' in detail_fields

    def test_generated_ddl_has_plain_nullable_column(self):
        _reload_quietly()
        mo = registry.get('work_order')
        assert mo is not None
        sql = SchemaGenerator("sqlite").generate_create_table(mo)
        assert 'project_id INTEGER' in sql
        assert 'FOREIGN KEY (project_id)' not in sql
        assert mo.table_name == WORK_ORDER_TABLE


# ─────────────────────────────────────────────────────────────────────────────
# B1-2 项目 360 履约段
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectWorkOrderSection:

    def test_work_order_is_fourth_readonly_tab(self):
        children = _load_raw('project')['ui_view_config']['child_sections']
        assert [c['child_object'] for c in children] == [
            'sales_order', 'sales_order_line', 'sales_order_schedule', 'work_order']
        section = children[-1]
        assert section['title'] == '工单（360）'
        assert section['display'] == 'tab'
        assert section['useMetaList'] is True
        assert section['enableDetail'] is True
        assert section['enableAutoCrud'] is False
        assert section['readonly'] is True
        assert section['pageSize'] == 20


# ─────────────────────────────────────────────────────────────────────────────
# B1-3 v175 迁移
# ─────────────────────────────────────────────────────────────────────────────

# 最小骨架表：模拟 v175 之前（没有 project_id 列）的存量库
_LEGACY_WORK_ORDER_DDL = (
    'CREATE TABLE {0} (id INTEGER PRIMARY KEY)'.format(WORK_ORDER_TABLE)
)


def _build_legacy_db(path):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(_LEGACY_WORK_ORDER_DDL)
        conn.commit()
    finally:
        conn.close()
    return path


def _columns(path, table):
    conn = sqlite3.connect(str(path))
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info({0})'.format(table))}
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


class TestMigration:

    def test_migrate_adds_column_and_index(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'b1_legacy.db')
        assert migrate(db) is True
        assert verify(db) is True
        assert PROJECT_COLUMN in _columns(db, WORK_ORDER_TABLE)
        assert _index_count(db, PROJECT_INDEX) == 1

    def test_migrate_is_idempotent(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'b1_twice.db')
        assert migrate(db) is True
        assert migrate(db) is True
        assert verify(db) is True
        assert _index_count(db, PROJECT_INDEX) == 1

    def test_verify_fails_before_migrate(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'b1_empty.db')
        assert verify(db) is False

    def test_migrate_skips_missing_table(self, tmp_path):
        db = tmp_path / 'b1_no_table.db'
        conn = sqlite3.connect(str(db))
        conn.close()
        assert migrate(db) is True
        # 无 work_orders 表时不建表、不建索引；verify 因缺表而失败
        assert verify(db) is False

    def test_rollback_drops_index_keeps_column(self, tmp_path):
        db = _build_legacy_db(tmp_path / 'b1_rollback.db')
        assert migrate(db) is True
        assert rollback(db) is True
        assert _index_count(db, PROJECT_INDEX) == 0
        assert PROJECT_COLUMN in _columns(db, WORK_ORDER_TABLE)
        assert verify(db) is False
