# -*- coding: utf-8 -*-
"""资源可用性例外（P2c）：YAML 声明 / 真建表 / 真外键 / 索引

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      §FR-005 产能与可用性 / §9.3 数据模型表

【本文件守什么】
  1. 对象已注册、table_name 正确、skip_auto_menu 生效
  2. 2 组枚举（7 个取值）与 v180 枚举种子一致，value_help 指向平台枚举字典
  3. 引用字段统一 bo + strict + dialog；relations 声明 N:1
  4. 按 yaml 真建表，外键逐条存在且是真约束（悬空引用抛 IntegrityError）
  5. 只建 2 条索引（resource_id / start_at），不建唯一键
  6. 必填列 NOT NULL、可空列可空
  7. resource.yaml 追加了对 resource_availabilities 的反向 restrict 声明

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

TABLES = ["org", "resource", "resource_availability"]

EXPECTED_FKS = {
    "resource_availabilities": {("resource_id", "resources", "id"),
                                ("org_id", "orgs", "id")},
}

ENUM_FIELDS = [
    ("availability_type", "availability_type",
     ["available", "unavailable", "overtime"]),
    ("source", "availability_source",
     ["manual", "hr", "maintenance", "other"]),
]

INDEXES = [
    ("idx_resource_availability_resource", ["resource_id"]),
    ("idx_resource_availability_window", ["start_at"]),
]

NOT_NULL_COLUMNS = ("resource_id", "availability_type", "start_at", "end_at", "source")
NULLABLE_COLUMNS = ("reason", "org_id")

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
        mo = registry.get("resource_availability")
        assert mo is not None, "resource_availability 未注册"
        assert mo.table_name == "resource_availabilities"
        assert mo.aspects and "audit_aspect" in mo.aspects

    def test_skip_auto_menu(self):
        assert _load_raw("resource_availability")["ui_view_config"]["skip_auto_menu"] is True

    def test_required_and_default_fields(self):
        schema = _load_raw("resource_availability")
        resource_id = _field(schema, "resource_id")
        assert resource_id["required"] is True
        availability_type = _field(schema, "availability_type")
        assert availability_type["required"] is True
        assert availability_type["default"] == "unavailable"
        source = _field(schema, "source")
        assert source["required"] is True
        assert source["default"] == "manual"
        for field_id in ("start_at", "end_at"):
            field = _field(schema, field_id)
            assert field["required"] is True
            assert field["type"] == "datetime"
        assert _field(schema, "reason")["nullable"] is True
        assert _field(schema, "org_id")["nullable"] is True

    def test_enum_values_and_type_ids(self):
        schema = _load_raw("resource_availability")
        for field_id, enum_type_id, values in ENUM_FIELDS:
            field = _field(schema, field_id)
            assert field is not None, "resource_availability.{0} 缺失".format(field_id)
            assert [v["value"] for v in field["enum_values"]] == values
            assert all("label" in v for v in field["enum_values"])
            assert field["value_help"]["source"]["type"] == "enum"
            assert field["value_help"]["source"]["enum_type_id"] == enum_type_id
            assert field["semantics"]["filter_type"] == "enum"

    def test_reference_fields_declare_strict_value_help(self):
        for field_id, target_bo in (("resource_id", "resource"),
                                    ("org_id", "org")):
            field = _field(_load_raw("resource_availability"), field_id)
            assert field is not None, "resource_availability.{0} 缺失".format(field_id)
            source = field["value_help"]["source"]
            assert source["type"] == "bo"
            assert source["target_bo"] == target_bo
            assert source["value_field"] == "id"
            assert source["apply_target_permissions"] is True
            assert field["value_help"]["behavior"]["binding_strength"] == "strict"
            assert field["value_help"]["presentation"]["result_type"] == "dialog"

    def test_indexes_declared_without_unique(self):
        declared = _load_raw("resource_availability")["indexes"]
        names = [idx["name"] for idx in declared]
        assert names == [name for name, _fields in INDEXES]
        for idx, (_name, fields) in zip(declared, INDEXES):
            assert idx["fields"] == fields
            assert idx.get("unique") is not True

    def test_relations_declared(self):
        relations = _load_raw("resource_availability")["relations"]
        pairs = {(r["source_field"], r["target"], r["cardinality"]) for r in relations}
        assert ("resource_id", "resource", "N:1") in pairs
        assert ("org_id", "org", "N:1") in pairs

    def test_deletion_policy_is_leaf(self):
        policy = _load_raw("resource_availability")["deletion_policy"]
        assert policy["mode"] == "restrict"
        assert policy["restrict_on"] == []

    def test_resource_restrict_on_covers_availability(self):
        rules = {
            (r["table"], r["foreign_key"])
            for r in _load_raw("resource")["deletion_policy"]["restrict_on"]
        }
        assert ("resource_availabilities", "resource_id") in rules


class TestTable:

    def test_table_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "resource_availabilities" in names

    def test_foreign_keys(self, conn):
        assert _fk_set(conn, "resource_availabilities") == \
            EXPECTED_FKS["resource_availabilities"]

    def test_indexes_created(self, conn):
        index_names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        for name, _fields in INDEXES:
            assert name in index_names, "缺索引 {0}".format(name)
            sql = _index_sql(conn, name) or ""
            assert "UNIQUE" not in sql.upper(), "{0} 不应是唯一索引".format(name)

    def test_not_null_columns(self, conn):
        info = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(resource_availabilities)")}
        for col in NOT_NULL_COLUMNS:
            assert info[col][3] == 1, "resource_availabilities.{0} 应 NOT NULL".format(col)

    def test_nullable_columns(self, conn):
        info = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(resource_availabilities)")}
        for col in NULLABLE_COLUMNS:
            assert info[col][3] == 0, "resource_availabilities.{0} 应可空".format(col)

    def test_dangling_resource_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resource_availabilities", resource_id=999,
                     availability_type="unavailable",
                     start_at="2026-11-03 09:00:00",
                     end_at="2026-11-03 12:00:00")
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_overlapping_entries_allowed(self, conn):
        seed_row(conn, "resource_availabilities", resource_id=7,
                 availability_type="unavailable",
                 start_at="2026-11-03 09:00:00", end_at="2026-11-03 12:00:00")
        seed_row(conn, "resource_availabilities", resource_id=7,
                 availability_type="overtime",
                 start_at="2026-11-03 10:00:00", end_at="2026-11-03 13:00:00")
