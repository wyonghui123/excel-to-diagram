# -*- coding: utf-8 -*-
"""统一资源模型 P3（员工 / 员工排班）：YAML 声明 / 真建表 / 真外键 / 部分唯一索引

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §FR-015

【本文件守什么】
  1. employee / employee_shift_assignment 已注册，table_name 正确，skip_auto_menu 生效
  2. employee **不含 resource_id**（资源与员工按 person 求交，不建资源外键）
  3. 两组枚举取值与 Spec 一致，value_help 指向平台枚举字典
  4. 2 条部分唯一索引：employee_no / person_profile_id 仅 status='active' 唯一
  5. 按 yaml 真建表：外键逐条存在，且悬空引用抛 IntegrityError
  6. 部分唯一索引在 DB 层真生效：在职重复被拒、历史离职行可同号
  7. 必填 / 可空列；restrict 声明（employee / employee_shift_assignment / person_profile）

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

# 建表顺序：先 FK 目标表，再员工 / 排班
TABLES = ["org", "location", "user", "person_profile", "shift",
          "resource_group", "employee", "employee_shift_assignment"]

EXPECTED_FKS = {
    "employees": {
        ("person_profile_id", "person_profiles", "id"),
        ("user_id", "users", "id"),
        ("org_id", "orgs", "id"),
        ("location_id", "locations", "id"),
        ("manager_employee_id", "employees", "id"),
    },
    "employee_shift_assignments": {
        ("employee_id", "employees", "id"),
        ("shift_id", "shifts", "id"),
        ("work_center_id", "resource_groups", "id"),
    },
}

PARTIAL_UNIQUE_INDEXES = [
    ("uq_employee_active_no", ["employee_no"]),
    ("uq_employee_active_person", ["person_profile_id"]),
]

NORMAL_INDEXES = [
    ("idx_employee_org", ["org_id"]),
    ("idx_employee_status", ["status"]),
    ("uq_employee_shift_assignment",
     ["employee_id", "shift_id", "seq", "effective_from"]),
    ("idx_employee_shift_assignment_employee", ["employee_id"]),
    ("idx_employee_shift_assignment_shift", ["shift_id"]),
]

NOT_NULL_COLUMNS = {
    "employees": ("employee_no", "name", "person_profile_id", "org_id",
                  "employment_type", "status", "hire_date"),
    "employee_shift_assignments": (
        "employee_id", "shift_id", "day_mask_mon", "day_mask_tue",
        "day_mask_wed", "day_mask_thu", "day_mask_fri", "day_mask_sat",
        "day_mask_sun", "seq", "effective_from"),
}

NULLABLE_COLUMNS = {
    "employees": ("user_id", "location_id", "position", "job_grade",
                  "termination_date", "manager_employee_id"),
    "employee_shift_assignments": ("effective_to", "work_center_id", "note"),
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

    def test_objects_registered(self):
        _reload_quietly()
        for bo_id, table in (("employee", "employees"),
                             ("employee_shift_assignment",
                              "employee_shift_assignments")):
            mo = registry.get(bo_id)
            assert mo is not None, "{0} 未注册".format(bo_id)
            assert mo.table_name == table
            assert mo.aspects and "audit_aspect" in mo.aspects

    def test_skip_auto_menu(self):
        for bo_id in ("employee", "employee_shift_assignment"):
            assert _load_raw(bo_id)["ui_view_config"]["skip_auto_menu"] is True

    def test_employee_is_thin_without_resource_id(self):
        """FR-015：employee 是 person 之上的雇佣关系，不得含 resource_id 字段。"""
        ids = {f["id"] for f in _load_raw("employee")["fields"]}
        assert "resource_id" not in ids
        assert "person_profile_id" in ids
        assert "employee_no" in ids

    def test_enum_values_and_type_ids(self):
        expected = {
            "employment_type": ["full_time", "part_time", "contractor",
                                "intern", "dispatched"],
            "status": ["active", "inactive", "terminated"],
        }
        type_ids = {
            "employment_type": "employment_type",
            "status": "employment_status",
        }
        for field_id, values in expected.items():
            field = _field(_load_raw("employee"), field_id)
            assert field is not None, "employee.{0} 缺失".format(field_id)
            assert [v["value"] for v in field["enum_values"]] == values
            assert all("label" in v for v in field["enum_values"])
            assert field["value_help"]["source"]["type"] == "enum"
            assert field["value_help"]["source"]["enum_type_id"] == \
                type_ids[field_id]

    def test_employment_defaults(self):
        employment_type = _field(_load_raw("employee"), "employment_type")
        status = _field(_load_raw("employee"), "status")
        assert employment_type["required"] is True
        assert employment_type["default"] == "full_time"
        assert status["required"] is True
        assert status["default"] == "active"

    def test_partial_unique_indexes_declared(self):
        indexes = {i.get("name"): i for i in _load_raw("employee")["indexes"]}
        for name, fields in PARTIAL_UNIQUE_INDEXES:
            assert name in indexes, "缺部分唯一索引 {0}".format(name)
            index = indexes[name]
            assert index["unique"] is True
            assert index["type"] == "partial"
            assert index["condition"] == "status = 'active'"
            assert index["fields"] == fields

    def test_normal_indexes_declared(self):
        employee_indexes = {i.get("name"): list(i["fields"])
                            for i in _load_raw("employee")["indexes"]}
        for name, fields in (("idx_employee_org", ["org_id"]),
                             ("idx_employee_status", ["status"])):
            assert employee_indexes.get(name) == fields, \
                "employee 缺索引 {0}".format(name)
        assignment_indexes = {
            i.get("name"): list(i["fields"])
            for i in _load_raw("employee_shift_assignment")["indexes"]}
        for name, fields in NORMAL_INDEXES[2:]:
            assert assignment_indexes.get(name) == fields, \
                "employee_shift_assignment 缺索引 {0}".format(name)
        assert assignment_indexes["uq_employee_shift_assignment"] == [
            "employee_id", "shift_id", "seq", "effective_from"]

    def test_reference_fields_declare_strict_value_help(self):
        for bo_id, field_id, target_bo in (
                ("employee", "person_profile_id", "person_profile"),
                ("employee", "user_id", "user"),
                ("employee", "org_id", "org"),
                ("employee", "location_id", "location"),
                ("employee", "manager_employee_id", "employee"),
                ("employee_shift_assignment", "employee_id", "employee"),
                ("employee_shift_assignment", "shift_id", "shift"),
                ("employee_shift_assignment", "work_center_id",
                 "resource_group")):
            field = _field(_load_raw(bo_id), field_id)
            assert field is not None, "{0}.{1} 缺失".format(bo_id, field_id)
            source = field["value_help"]["source"]
            assert source["type"] == "bo"
            assert source["target_bo"] == target_bo
            assert source["value_field"] == "id"
            assert source["apply_target_permissions"] is True
            assert field["value_help"]["behavior"]["binding_strength"] == "strict"
            assert field["value_help"]["presentation"]["result_type"] == "dialog"

    def test_day_masks(self):
        schema = _load_raw("employee_shift_assignment")
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            field = _field(schema, "day_mask_" + day)
            assert field is not None, "day_mask_{0} 缺失".format(day)
            assert field["type"] == "boolean"
            assert field["required"] is True
            assert field["default"] is True

    def test_restrict_declarations(self):
        employee = _load_raw("employee")["deletion_policy"]
        assert employee["mode"] == "restrict"
        assert {(r["table"], r["foreign_key"]) for r in employee["restrict_on"]} == {
            ("employee_shift_assignments", "employee_id"),
            ("employees", "manager_employee_id"),
        }
        assignment = _load_raw("employee_shift_assignment")["deletion_policy"]
        assert assignment["mode"] == "restrict"
        assert assignment["restrict_on"] == []
        person = _load_raw("person_profile")["deletion_policy"]["restrict_on"]
        assert ("employees", "person_profile_id") in {
            (r["table"], r["foreign_key"]) for r in person}

    def test_audit_timestamps_declared(self):
        for bo_id in ("employee", "employee_shift_assignment"):
            ids = {f["id"] for f in _load_raw(bo_id)["fields"]}
            assert "created_at" in ids and "updated_at" in ids


class TestTable:

    def test_tables_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in NOT_NULL_COLUMNS:
            assert table in names, "缺表 {0}".format(table)

    def test_foreign_keys(self, conn):
        for table, fks in EXPECTED_FKS.items():
            assert _fk_set(conn, table) == fks, "{0} 外键不符".format(table)

    def test_partial_unique_indexes_created(self, conn):
        for name, _fields in PARTIAL_UNIQUE_INDEXES:
            sql = _index_sql(conn, name) or ""
            assert "UNIQUE" in sql.upper(), "{0} 不是唯一索引".format(name)
            assert "WHERE" in sql.upper(), "{0} 不是部分索引".format(name)
            assert "'active'" in sql, "{0} 条件不含 status='active'".format(name)

    def test_normal_indexes_created(self, conn):
        for name, _fields in NORMAL_INDEXES:
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

    def test_dangling_person_profile_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "employees", employee_no="E-ORPHAN", name="孤儿员工",
                     person_profile_id=999, org_id=0,
                     hire_date="2026-01-01 00:00:00")
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_shift_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "employee_shift_assignments", employee_id=999,
                     shift_id=999, effective_from="2026-01-01")
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_active_employee_no_unique(self, conn):
        seed_row(conn, "employees", employee_no="E-DUP", name="甲",
                 person_profile_id=1, org_id=0, status="active",
                 hire_date="2026-01-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "employees", employee_no="E-DUP", name="乙",
                     person_profile_id=2, org_id=0, status="active",
                     hire_date="2026-02-01")

    def test_terminated_employee_no_can_repeat(self, conn):
        """历史离职行可同号（再入职沿用原号）⇒ 部分唯一索引不应拦截。"""
        seed_row(conn, "employees", employee_no="E-REHIRE", name="甲",
                 person_profile_id=3, org_id=0, status="terminated",
                 hire_date="2020-01-01", termination_date="2021-01-01")
        seed_row(conn, "employees", employee_no="E-REHIRE", name="甲",
                 person_profile_id=3, org_id=0, status="terminated",
                 hire_date="2022-01-01", termination_date="2023-01-01")
        seed_row(conn, "employees", employee_no="E-REHIRE", name="甲",
                 person_profile_id=3, org_id=0, status="active",
                 hire_date="2026-01-01")

    def test_active_person_profile_unique(self, conn):
        seed_row(conn, "employees", employee_no="E-P1", name="甲",
                 person_profile_id=7, org_id=0, status="active",
                 hire_date="2026-01-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "employees", employee_no="E-P2", name="甲",
                     person_profile_id=7, org_id=0, status="active",
                     hire_date="2026-02-01")
        # 离职行与在职行同 person 允许（历史雇佣）
        seed_row(conn, "employees", employee_no="E-P3", name="甲",
                 person_profile_id=7, org_id=0, status="terminated",
                 hire_date="2020-01-01", termination_date="2021-01-01")

    def test_duplicate_assignment_key_rejected(self, conn):
        seed_row(conn, "employee_shift_assignments", employee_id=11,
                 shift_id=12, seq=1, effective_from="2026-01-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "employee_shift_assignments", employee_id=11,
                     shift_id=12, seq=1, effective_from="2026-01-01")
