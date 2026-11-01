# -*- coding: utf-8 -*-
"""统一资源模型 P2b（八个对象）：YAML 声明 / 真建表 / 真外键 / 唯一索引

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      §FR-014 / §9.2 目标架构 / §9.3 数据模型表

【本文件守什么】
  1. 八个对象已注册、table_name 正确、skip_auto_menu 生效
  2. 八组枚举取值与 Spec 一致，value_help 指向平台枚举字典（type id 对齐 v176）
  3. 按 yaml 真建表，外键逐条存在（含 work_order_operations 真表名）
  4. DB 级 FK 是真约束：悬空引用抛 IntegrityError
  5. 唯一键生效：shift.code / (code,revision) / (definition_id,seq)
     / capacity 四元组 / assignment 三元组 / territory 四元组
  6. 必填列 NOT NULL、可空列可空
  7. restrict 声明：shift / work_definition / work_definition_operation；
     资源与资源组追加了引用 P2b 子表的 restrict 规则

测试隔离同 `test_resource_domain_schema.py`：内存 SQLite + registry 重载 + 真建表；
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

# 建表顺序：先 FK 目标表，再子表（SQLite 允许先建子表，此处仍按依赖排序便于阅读）
TABLES = ["org", "calendar", "item_group", "uom_group", "uom", "item",
          "territory", "skill", "resource_group", "resource",
          "shift", "calendar_shift", "work_definition",
          "work_definition_sequence", "work_definition_operation",
          "operation_resource_requirement",
          "resource_capacity", "resource_territory_assignment",
          "work_order", "work_order_operation", "resource_assignment"]

EXPECTED_FKS = {
    "shifts": {("org_id", "orgs", "id")},
    "calendar_shifts": {("calendar_id", "calendars", "id"),
                        ("shift_id", "shifts", "id")},
    "work_definitions": {("item_id", "items", "id"),
                         ("org_id", "orgs", "id")},
    "work_definition_operations": {
        ("definition_id", "work_definitions", "id"),
        ("resource_group_id", "resource_groups", "id"),
        # P4a：sequence_id 可空，空 = 标准序列
        ("sequence_id", "work_definition_sequences", "id")},
    "operation_resource_requirements": {
        ("operation_id", "work_definition_operations", "id"),
        ("resource_group_id", "resource_groups", "id"),
        ("resource_id", "resources", "id"),
        ("required_skill_id", "skills", "id")},
    "resource_capacities": {
        ("resource_id", "resources", "id"),
        ("resource_group_id", "resource_groups", "id"),
        ("capacity_uom_id", "uoms", "id")},
    "resource_assignments": {
        ("work_order_operation_id", "work_order_operations", "id"),
        ("resource_id", "resources", "id")},
    "resource_territory_assignments": {
        ("resource_id", "resources", "id"),
        ("resource_group_id", "resource_groups", "id"),
        ("territory_id", "territories", "id")},
}

# (bo_id, 字段 id, 表名, 枚举字典 id, 取值)
ENUM_FIELDS = [
    ("shift", "shift_type", "shifts", "shift_type",
     ["regular", "overtime", "standby"]),
    ("calendar_shift", None, "calendar_shifts", None, None),
    ("work_definition", "definition_kind", "work_definitions",
     "definition_kind", ["routing", "service_template"]),
    ("work_definition", "status", "work_definitions",
     "work_definition_status", ["draft", "active", "obsolete"]),
    ("work_definition_operation", "status", "work_definition_operations",
     "work_definition_status", ["draft", "active", "obsolete"]),
    ("operation_resource_requirement", "role",
     "operation_resource_requirements", "requirement_role",
     ["machine", "labor", "tool", "vehicle", "external"]),
    ("resource_capacity", "capacity_category", "resource_capacities",
     "capacity_category", ["labor_hours", "machine_hours", "tool_count",
                           "vehicle_weight", "vehicle_volume",
                           "facility_capacity"]),
    ("resource_assignment", "status", "resource_assignments",
     "assignment_status", ["planned", "confirmed", "in_progress",
                           "completed", "canceled"]),
    ("resource_assignment", "source", "resource_assignments",
     "assignment_source", ["manual", "auto"]),
    ("resource_territory_assignment", "coverage_level",
     "resource_territory_assignments", "coverage_level",
     ["primary", "backup"]),
]

UNIQUE_INDEXES = [
    ("shifts", "uq_shift_code"),
    ("work_definitions", "uq_work_definition_code_revision"),
    ("work_definition_operations", "uq_work_definition_operation_seq"),
    ("resource_capacities", "uq_resource_capacity"),
    ("resource_assignments", "uq_resource_assignment"),
    ("resource_territory_assignments", "uq_resource_territory_assignment"),
]

NOT_NULL_COLUMNS = {
    "shifts": ("code", "name", "start_time", "end_time", "crosses_midnight",
               "break_minutes", "shift_type", "is_active"),
    "calendar_shifts": ("calendar_id", "shift_id", "day_mask_mon", "day_mask_tue",
                        "day_mask_wed", "day_mask_thu", "day_mask_fri",
                        "day_mask_sat", "day_mask_sun", "seq", "capacity_factor"),
    "work_definitions": ("code", "name", "definition_kind", "revision", "status"),
    "work_definition_operations": ("definition_id", "seq", "operation_name",
                                   "setup_minutes", "teardown_minutes",
                                   "run_minutes", "queue_minutes", "move_minutes",
                                   "travel_minutes", "qty_per", "status"),
    "operation_resource_requirements": ("operation_id", "role", "qty",
                                        "is_primary", "priority"),
    "resource_capacities": ("capacity_category", "capacity_units", "utilization_pct"),
    "resource_assignments": ("work_order_operation_id", "resource_id", "status",
                             "source"),
    "resource_territory_assignments": ("territory_id", "coverage_level"),
}

NULLABLE_COLUMNS = {
    "shifts": ("org_id", "valid_from", "valid_to"),
    "calendar_shifts": ("valid_from", "valid_to"),
    "work_definitions": ("item_id", "org_id", "description"),
    "work_definition_operations": ("resource_group_id",),
    "operation_resource_requirements": ("resource_group_id", "resource_id",
                                        "required_skill_id", "min_level",
                                        "lead_time_days"),
    "resource_capacities": ("resource_id", "resource_group_id", "capacity_uom_id",
                            "capacity_per_day", "valid_from", "valid_to"),
    "resource_assignments": ("planned_start", "planned_end", "planned_qty"),
    "resource_territory_assignments": ("resource_id", "resource_group_id",
                                       "effective_from", "effective_to"),
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
        expected = {
            "shift": "shifts",
            "calendar_shift": "calendar_shifts",
            "work_definition": "work_definitions",
            "work_definition_operation": "work_definition_operations",
            "operation_resource_requirement": "operation_resource_requirements",
            "resource_capacity": "resource_capacities",
            "resource_assignment": "resource_assignments",
            "resource_territory_assignment": "resource_territory_assignments",
        }
        for bo_id, table in expected.items():
            mo = registry.get(bo_id)
            assert mo is not None, "{0} 未注册".format(bo_id)
            assert mo.table_name == table
            assert mo.aspects and "audit_aspect" in mo.aspects

    def test_skip_auto_menu(self):
        for bo_id in ("shift", "calendar_shift", "work_definition",
                      "work_definition_operation",
                      "operation_resource_requirement", "resource_capacity",
                      "resource_assignment", "resource_territory_assignment"):
            assert _load_raw(bo_id)["ui_view_config"]["skip_auto_menu"] is True

    def test_shift_code_globally_unique(self):
        code = _field(_load_raw("shift"), "code")
        assert code["required"] is True and code["unique"] is True
        assert code["max_length"] == 40
        assert code["pattern"] == "^[A-Z][A-Z0-9_]*$"
        assert code["semantics"]["business_key"] is True

    def test_work_definition_code_not_field_unique(self):
        """code 与 revision 组合唯一 ⇒ 字段级不得再声明 unique（否则列级 UNIQUE 冲突）。"""
        code = _field(_load_raw("work_definition"), "code")
        assert code["required"] is True
        assert code.get("unique") is not True
        assert code["semantics"]["business_key"] is True

    def test_enum_values_and_type_ids(self):
        for bo_id, field_id, _table, enum_type_id, values in ENUM_FIELDS:
            if field_id is None:
                continue
            field = _field(_load_raw(bo_id), field_id)
            assert field is not None, "{0}.{1} 缺失".format(bo_id, field_id)
            assert [v["value"] for v in field["enum_values"]] == values
            assert all("label" in v for v in field["enum_values"])
            assert field["value_help"]["source"]["type"] == "enum"
            assert field["value_help"]["source"]["enum_type_id"] == enum_type_id

    def test_calendar_shift_masks(self):
        schema = _load_raw("calendar_shift")
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            field = _field(schema, "day_mask_" + day)
            assert field["required"] is True and field["default"] is True
            assert field["type"] == "boolean"

    def test_reference_fields_declare_strict_value_help(self):
        """引用字段统一 `source.type: bo` + `binding_strength: strict` + dialog。"""
        for bo_id, field_id, target_bo in (
                ("shift", "org_id", "org"),
                ("calendar_shift", "calendar_id", "calendar"),
                ("calendar_shift", "shift_id", "shift"),
                ("work_definition", "item_id", "item"),
                ("work_definition", "org_id", "org"),
                ("work_definition_operation", "definition_id", "work_definition"),
                ("work_definition_operation", "resource_group_id", "resource_group"),
                ("operation_resource_requirement", "operation_id",
                 "work_definition_operation"),
                ("operation_resource_requirement", "resource_group_id",
                 "resource_group"),
                ("operation_resource_requirement", "resource_id", "resource"),
                ("operation_resource_requirement", "required_skill_id", "skill"),
                ("resource_capacity", "resource_id", "resource"),
                ("resource_capacity", "resource_group_id", "resource_group"),
                ("resource_capacity", "capacity_uom_id", "uom"),
                ("resource_assignment", "work_order_operation_id",
                 "work_order_operation"),
                ("resource_assignment", "resource_id", "resource"),
                ("resource_territory_assignment", "resource_id", "resource"),
                ("resource_territory_assignment", "resource_group_id",
                 "resource_group"),
                ("resource_territory_assignment", "territory_id", "territory")):
            field = _field(_load_raw(bo_id), field_id)
            assert field is not None, "{0}.{1} 缺失".format(bo_id, field_id)
            source = field["value_help"]["source"]
            assert source["type"] == "bo"
            assert source["target_bo"] == target_bo
            assert source["value_field"] == "id"
            assert source["apply_target_permissions"] is True
            assert field["value_help"]["behavior"]["binding_strength"] == "strict"
            assert field["value_help"]["presentation"]["result_type"] == "dialog"

    def test_unique_indexes_declared(self):
        expected = {
            "shift": ("uq_shift_code", ["code"]),
            "work_definition": ("uq_work_definition_code_revision",
                               ["code", "revision"]),
            "work_definition_operation": ("uq_work_definition_operation_seq",
                                         ["definition_id", "seq"]),
            "resource_capacity": ("uq_resource_capacity",
                                  ["resource_id", "resource_group_id",
                                   "capacity_category", "valid_from"]),
            "resource_assignment": ("uq_resource_assignment",
                                    ["work_order_operation_id", "resource_id",
                                     "planned_start"]),
            "resource_territory_assignment": ("uq_resource_territory_assignment",
                                             ["resource_id", "resource_group_id",
                                              "territory_id", "effective_from"]),
        }
        for bo_id, (name, fields) in expected.items():
            found = [i for i in _load_raw(bo_id)["indexes"]
                     if i.get("name") == name]
            assert found, "{0} 缺唯一索引 {1}".format(bo_id, name)
            assert found[0]["unique"] is True
            assert found[0]["fields"] == fields

    def test_fk_columns_indexed(self):
        for table, fk_cols in (
                ("shifts", ["org_id"]),
                ("calendar_shifts", ["calendar_id", "shift_id"]),
                ("work_definitions", ["item_id", "org_id"]),
                ("work_definition_operations", ["resource_group_id"]),
                ("operation_resource_requirements",
                 ["operation_id", "resource_group_id", "resource_id",
                  "required_skill_id"]),
                ("resource_capacities",
                 ["resource_group_id", "capacity_uom_id"]),
                ("resource_assignments",
                 ["resource_id", "work_order_operation_id"]),
                ("resource_territory_assignments",
                 ["resource_group_id", "territory_id"])):
            bo_id = {"shifts": "shift", "calendar_shifts": "calendar_shift",
                     "work_definitions": "work_definition",
                     "work_definition_operations": "work_definition_operation",
                     "operation_resource_requirements":
                     "operation_resource_requirement",
                     "resource_capacities": "resource_capacity",
                     "resource_assignments": "resource_assignment",
                     "resource_territory_assignments":
                     "resource_territory_assignment"}[table]
            indexed = set()
            for idx in _load_raw(bo_id)["indexes"]:
                indexed.update(idx["fields"])
            for col in fk_cols:
                assert col in indexed, "{0}.{1} 未建索引".format(table, col)

    def test_valid_from_indexed(self):
        for bo_id in ("shift", "calendar_shift", "resource_capacity"):
            indexed = set()
            for idx in _load_raw(bo_id)["indexes"]:
                indexed.update(idx["fields"])
            assert "valid_from" in indexed

    def test_restrict_declarations(self):
        shift = _load_raw("shift")["deletion_policy"]["restrict_on"]
        assert {(r["table"], r["foreign_key"]) for r in shift} == {
            ("calendar_shifts", "shift_id")}
        wd = _load_raw("work_definition")["deletion_policy"]["restrict_on"]
        assert {(r["table"], r["foreign_key"]) for r in wd} == {
            ("work_definition_operations", "definition_id")}
        wdo = _load_raw("work_definition_operation")["deletion_policy"]["restrict_on"]
        assert {(r["table"], r["foreign_key"]) for r in wdo} == {
            ("operation_resource_requirements", "operation_id")}
        # 资源 / 资源组反向 restrict 已追加 P2b 子表
        resource = _load_raw("resource")["deletion_policy"]["restrict_on"]
        rules = {(r["table"], r["foreign_key"]) for r in resource}
        for rule in (("operation_resource_requirements", "resource_id"),
                     ("resource_capacities", "resource_id"),
                     ("resource_assignments", "resource_id"),
                     ("resource_territory_assignments", "resource_id")):
            assert rule in rules
        group = _load_raw("resource_group")["deletion_policy"]["restrict_on"]
        rules = {(r["table"], r["foreign_key"]) for r in group}
        for rule in (("operation_resource_requirements", "resource_group_id"),
                     ("resource_capacities", "resource_group_id"),
                     ("resource_territory_assignments", "resource_group_id")):
            assert rule in rules


class TestTable:

    def test_tables_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in NOT_NULL_COLUMNS:
            assert table in names, "缺表 {0}".format(table)

    def test_foreign_keys(self, conn):
        for table, fks in EXPECTED_FKS.items():
            assert _fk_set(conn, table) == fks, "{0} 外键不符".format(table)

    def test_unique_indexes_created(self, conn):
        for _table, name in UNIQUE_INDEXES:
            sql = _index_sql(conn, name) or ""
            assert "UNIQUE" in sql.upper(), "{0} 不是唯一索引".format(name)

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

    def test_dangling_shift_org_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "shifts", code="S-ORPHAN", name="孤儿班次",
                     start_time="08:00", end_time="17:00", org_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_work_definition_item_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "work_definitions", code="WD-ORPHAN", name="孤儿定义",
                     item_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_definition_operation_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "work_definition_operations", definition_id=999,
                     seq=1, operation_name="孤儿工序")
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_requirement_operation_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "operation_resource_requirements", operation_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_capacity_resource_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resource_capacities", resource_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_assignment_operation_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resource_assignments",
                     work_order_operation_id=999, resource_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_territory_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resource_territory_assignments",
                     resource_id=999, territory_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_duplicate_shift_code_rejected(self, conn):
        seed_row(conn, "shifts", code="S-DUP", name="甲班次",
                 start_time="08:00", end_time="17:00")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "shifts", code="S-DUP", name="乙班次",
                     start_time="08:00", end_time="17:00")

    def test_duplicate_definition_code_revision_rejected(self, conn):
        seed_row(conn, "work_definitions", code="WD-DUP", name="甲定义",
                 revision="A")
        seed_row(conn, "work_definitions", code="WD-DUP", name="乙定义",
                 revision="B")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "work_definitions", code="WD-DUP", name="丙定义",
                     revision="A")

    def test_duplicate_operation_seq_rejected(self, conn):
        seed_row(conn, "work_definitions", id=41, code="WD41", name="定义")
        seed_row(conn, "work_definition_operations", definition_id=41, seq=1,
                 operation_name="甲工序")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "work_definition_operations", definition_id=41, seq=1,
                     operation_name="乙工序")

    def test_duplicate_capacity_key_rejected(self, conn):
        seed_row(conn, "resource_capacities", resource_id=42,
                 resource_group_id=46, capacity_category="labor_hours",
                 valid_from="2026-11-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resource_capacities", resource_id=42,
                     resource_group_id=46, capacity_category="labor_hours",
                     valid_from="2026-11-01")

    def test_duplicate_assignment_key_rejected(self, conn):
        seed_row(conn, "resource_assignments", work_order_operation_id=43,
                 resource_id=43, planned_start="2026-11-01 08:00:00")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resource_assignments", work_order_operation_id=43,
                     resource_id=43, planned_start="2026-11-01 08:00:00")

    def test_duplicate_territory_key_rejected(self, conn):
        seed_row(conn, "resource_territory_assignments", resource_id=44,
                 resource_group_id=45, territory_id=44,
                 effective_from="2026-11-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resource_territory_assignments", resource_id=44,
                     resource_group_id=45, territory_id=44,
                     effective_from="2026-11-01")
