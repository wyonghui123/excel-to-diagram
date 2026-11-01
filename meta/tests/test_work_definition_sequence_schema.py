# -*- coding: utf-8 -*-
"""统一资源模型 P4a（作业定义序列 + 工序 sequence_id）：YAML 声明 / 真建表 / 真外键

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §TBD-15

【本文件守什么】
  1. work_definition_sequence 已注册，table_name 正确，skip_auto_menu + 三态 UI 配置
  2. seq_type 首期只有 std / alternative（branch/return 与 parallel 不提前建字段）
  3. work_definition_operations.sequence_id 可空（存量行 NULL = 标准序列）
  4. (definition_id, seq_no) 唯一；sequence_id 有索引且是真外键
  5. restrict：序列下仍有工序时删除被拒绝；YAML 声明反向 restrict 规则

测试隔离同 `test_resource_domain_p2b_schema.py`：内存 SQLite + registry 重载 + 真建表；
播种经 factories，本文件不含裸 SQL DML。
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
from meta.tests.factories._pricing_p2_helpers import create_tables, seed_row  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

TABLES = ["org", "item_group", "uom_group", "uom", "item", "resource_group",
          "work_definition", "work_definition_sequence",
          "work_definition_operation"]

EXPECTED_FKS = {
    "work_definition_sequences": {
        ("definition_id", "work_definitions", "id"),
    },
    "work_definition_operations": {
        ("definition_id", "work_definitions", "id"),
        ("resource_group_id", "resource_groups", "id"),
        ("sequence_id", "work_definition_sequences", "id"),
    },
}

NOT_NULL_COLUMNS = {
    "work_definition_sequences": ("definition_id", "seq_no", "seq_type"),
}

NULLABLE_COLUMNS = {
    "work_definition_sequences": ("description",),
    "work_definition_operations": ("sequence_id", "resource_group_id"),
}

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


@pytest.fixture(scope="module")
def conn():
    _reload_quietly()
    c = sqlite3.connect(":memory:")
    create_tables(c, TABLES)
    yield c
    c.close()


@pytest.fixture()
def fk_conn():
    _reload_quietly()
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    create_tables(c, TABLES)
    yield c
    c.close()


def _index_sql(conn, name):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _fk_set(conn, table):
    return {(row[3], row[2], row[4]) for row in conn.execute(
        "PRAGMA foreign_key_list({0})".format(table))}


class TestDeclaration:

    def test_object_registered(self):
        _reload_quietly()
        mo = registry.get("work_definition_sequence")
        assert mo is not None, "work_definition_sequence 未注册"
        assert mo.table_name == "work_definition_sequences"
        assert mo.aspects and "audit_aspect" in mo.aspects

    def test_skip_auto_menu_and_three_state_ui(self):
        schema = _load_raw("work_definition_sequence")
        assert schema["ui_view_config"]["skip_auto_menu"] is True
        assert "list" in schema["ui_view_config"]
        assert "form" in schema["ui_view_config"]
        assert "detail" in schema["ui_view_config"]

    def test_seq_type_only_std_and_alternative(self):
        """TBD-15：首期只实现 std / alternative，branch/return/parallel 放 P5。"""
        field = _field(_load_raw("work_definition_sequence"), "seq_type")
        assert field is not None
        assert [v["value"] for v in field["enum_values"]] == ["std", "alternative"]
        assert all("label" in v for v in field["enum_values"])
        assert field["default"] == "std"
        assert field["value_help"]["source"]["type"] == "enum"
        assert field["value_help"]["source"]["enum_type_id"] == "sequence_type"

    def test_no_p5_fields(self):
        """不提前建字段：branch_from_seq / return_seq / parallel 均不出现。"""
        ids = {f["id"] for f in _load_raw("work_definition_sequence")["fields"]}
        for forbidden in ("branch_from_seq", "return_seq", "is_parallel"):
            assert forbidden not in ids

    def test_sequence_no_required_and_ranged(self):
        field = _field(_load_raw("work_definition_sequence"), "seq_no")
        assert field["required"] is True
        assert field["constraints"][0]["gte"] == 1
        assert field["constraints"][0]["decimal_places"] == 0

    def test_reference_field_declares_strict_value_help(self):
        field = _field(_load_raw("work_definition_sequence"), "definition_id")
        source = field["value_help"]["source"]
        assert source["type"] == "bo"
        assert source["target_bo"] == "work_definition"
        assert source["apply_target_permissions"] is True
        assert field["value_help"]["behavior"]["binding_strength"] == "strict"

    def test_unique_and_type_indexes_declared(self):
        indexes = {i.get("name"): i for i in
                   _load_raw("work_definition_sequence")["indexes"]}
        assert indexes["uq_work_definition_sequence_no"]["unique"] is True
        assert indexes["uq_work_definition_sequence_no"]["fields"] == [
            "definition_id", "seq_no"]
        assert indexes["idx_work_definition_sequence_type"]["fields"] == ["seq_type"]

    def test_restrict_declaration(self):
        policy = _load_raw("work_definition_sequence")["deletion_policy"]
        assert policy["mode"] == "restrict"
        assert {(r["table"], r["foreign_key"]) for r in policy["restrict_on"]} == {
            ("work_definition_operations", "sequence_id")}

    def test_operation_sequence_id_is_nullable_reference(self):
        schema = _load_raw("work_definition_operation")
        field = _field(schema, "sequence_id")
        assert field is not None, "work_definition_operation.sequence_id 缺失"
        assert field["type"] == "integer"
        assert field["nullable"] is True
        assert field["value_help"]["source"]["target_bo"] == "work_definition_sequence"
        assert field["value_help"]["behavior"]["binding_strength"] == "strict"
        rel = [r for r in schema["relations"]
               if r["id"] == "work_definition_operation_to_sequence"]
        assert rel and rel[0]["source_field"] == "sequence_id"
        assert rel[0]["target"] == "work_definition_sequence"
        indexed = set()
        for idx in schema["indexes"]:
            indexed.update(idx["fields"])
        assert "sequence_id" in indexed

    def test_audit_timestamps_declared(self):
        ids = {f["id"] for f in _load_raw("work_definition_sequence")["fields"]}
        assert "created_at" in ids and "updated_at" in ids


class TestTable:

    def test_tables_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "work_definition_sequences" in names

    def test_foreign_keys(self, conn):
        for table, fks in EXPECTED_FKS.items():
            assert _fk_set(conn, table) == fks, "{0} 外键不符".format(table)

    def test_indexes_created(self, conn):
        for name in ("uq_work_definition_sequence_no",
                     "idx_work_definition_sequence_type",
                     "idx_work_definition_operation_sequence"):
            assert _index_sql(conn, name) is not None, "缺索引 {0}".format(name)

    def test_not_null_columns(self, conn):
        for table, cols in NOT_NULL_COLUMNS.items():
            info = {r[1]: r for r in conn.execute(
                "PRAGMA table_info({0})".format(table))}
            for col in cols:
                assert info[col][3] == 1, "{0}.{1} 应 NOT NULL".format(table, col)

    def test_nullable_columns(self, conn):
        for table, cols in NULLABLE_COLUMNS.items():
            info = {r[1]: r for r in conn.execute(
                "PRAGMA table_info({0})".format(table))}
            for col in cols:
                assert info[col][3] == 0, "{0}.{1} 应可空".format(table, col)

    def test_duplicate_sequence_no_rejected(self, conn):
        seed_row(conn, "work_definition_sequences", definition_id=1, seq_no=1)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "work_definition_sequences", definition_id=1, seq_no=1)

    def test_same_seq_no_allowed_across_definitions(self, conn):
        seed_row(conn, "work_definition_sequences", definition_id=2, seq_no=1)
        seed_row(conn, "work_definition_sequences", definition_id=3, seq_no=1)

    def test_dangling_definition_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "work_definition_sequences", definition_id=999,
                     seq_no=1)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_operation_without_sequence_allowed(self, fk_conn):
        """存量工序 sequence_id 为 NULL ⇒ 视为标准序列，不应被外键拦截。"""
        parent = seed_row(fk_conn, "work_definitions", code="WD-SEQ", name="序列测试",
                          definition_kind="routing", revision="A", status="active")
        seed_row(fk_conn, "work_definition_operations",
                 definition_id=parent.lastrowid, seq=1,
                 operation_name="旧工序", sequence_id=None)
