# -*- coding: utf-8 -*-
"""统一资源模型 P2a（六个对象）：YAML 声明 / 真建表 / 真外键 / 唯一索引

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      §FR-001 ~ FR-004 / §FR-007 / §FR-011 / §9.3 数据模型表

【本文件守什么】
  1. 六个对象已注册，table_name / parent_object 正确，skip_auto_menu 生效
  2. code 全局唯一（regex + max_length + business_key）
  3. 枚举字段取值符合 Spec（含 value_help 指向平台枚举字典）
  4. 按 yaml 真建表，外键逐条存在（含自引用）
  5. DB 级 FK 是真约束：悬空引用抛 IntegrityError
  6. 唯一键生效：(group_id, resource_id) / (resource_id, skill_id, valid_from)
     / (resource_id, rate_purpose, valid_from)
  7. work_order_operation 已改名为 resource_group_id，并新增
     required_skill_id / teardown_minutes；旧 required_skill 只读保留

测试隔离同 `test_territory_schema.py`：内存 SQLite + registry 重载 + 真建表；
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

# 建表顺序：先 FK 目标表，再子表
TABLES = ["org", "party", "person_profile", "region", "calendar", "address",
          "location", "uom_group", "uom", "currency",
          "skill", "resource_group", "resource", "resource_group_member",
          "resource_capability", "resource_rate"]

RESOURCE_FKS = [
    ("org_id", "orgs", "id"),
    ("location_id", "locations", "id"),
    ("party_id", "parties", "id"),
    ("person_ref", "person_profiles", "id"),
    ("capacity_uom_id", "uoms", "id"),
    ("calendar_id", "calendars", "id"),
]

GROUP_FKS = [
    ("parent_group_id", "resource_groups", "id"),
    ("org_id", "orgs", "id"),
    ("org_unit_id", "orgs", "id"),
    ("location_id", "locations", "id"),
    ("calendar_id", "calendars", "id"),
]

MEMBER_FKS = [
    ("group_id", "resource_groups", "id"),
    ("resource_id", "resources", "id"),
]

CAPABILITY_FKS = [
    ("resource_id", "resources", "id"),
    ("skill_id", "skills", "id"),
]

RATE_FKS = [
    ("resource_id", "resources", "id"),
    ("resource_group_id", "resource_groups", "id"),
    ("org_id", "orgs", "id"),
    ("location_id", "locations", "id"),
    ("currency_id", "currencies", "id"),
    ("rate_uom_id", "uoms", "id"),
]

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
            "skill": "skills",
            "resource": "resources",
            "resource_group": "resource_groups",
            "resource_group_member": "resource_group_members",
            "resource_capability": "resource_capabilities",
            "resource_rate": "resource_rates",
        }
        for bo_id, table in expected.items():
            mo = registry.get(bo_id)
            assert mo is not None, "{0} 未注册".format(bo_id)
            assert mo.table_name == table

    def test_parent_objects(self):
        assert _load_raw("resource_group_member")["parent_object"] == "resource_group"
        assert _load_raw("resource_capability")["parent_object"] == "resource"
        assert _load_raw("resource_rate")["parent_object"] == "resource"
        for bo_id in ("skill", "resource", "resource_group",
                      "resource_group_member", "resource_capability",
                      "resource_rate"):
            assert _load_raw(bo_id)["ui_view_config"]["skip_auto_menu"] is True

    def test_code_global_unique(self):
        for bo_id in ("skill", "resource", "resource_group"):
            code = _field(_load_raw(bo_id), "code")
            assert code["required"] is True and code["unique"] is True
            assert code["max_length"] == 40
            assert code["pattern"] == "^[A-Z][A-Z0-9_]*$"
            assert code["semantics"]["business_key"] is True
            assert code["semantics"]["pattern"] == "^[A-Z][A-Z0-9_]*$"

    def test_skill_enums(self):
        skill = _load_raw("skill")
        category = _field(skill, "category")
        assert category["required"] is True and category["default"] == "trade"
        assert [v["value"] for v in category["enum_values"]] == [
            "trade", "certification", "language", "soft"]
        assert category["value_help"]["source"]["enum_type_id"] == "skill_category"
        status = _field(skill, "status")
        assert status["default"] == "active"
        assert [v["value"] for v in status["enum_values"]] == ["active", "inactive"]

    def test_resource_enums(self):
        resource = _load_raw("resource")
        kind = _field(resource, "resource_kind")
        assert kind["required"] is True and kind["default"] == "person"
        assert [v["value"] for v in kind["enum_values"]] == [
            "person", "machine", "vehicle", "tool", "facility", "site", "external"]
        assert kind["value_help"]["source"]["enum_type_id"] == "resource_kind"

    def test_group_enums(self):
        group = _load_raw("resource_group")
        kind = _field(group, "group_kind")
        assert [v["value"] for v in kind["enum_values"]] == [
            "work_center", "crew", "pool", "fleet", "site_group"]
        assert kind["default"] == "work_center"
        assert kind["value_help"]["source"]["enum_type_id"] == "resource_group_kind"
        agg = _field(group, "capacity_aggregation")
        assert agg["required"] is True and agg["default"] == "sum"
        assert [v["value"] for v in agg["enum_values"]] == [
            "sum", "max", "bottleneck"]
        assert agg["value_help"]["source"]["enum_type_id"] == "capacity_aggregation"
        mode = _field(group, "membership_mode")
        assert mode["required"] is True and mode["default"] == "members"
        assert [v["value"] for v in mode["enum_values"]] == ["members", "children"]
        assert mode["value_help"]["source"]["enum_type_id"] == "membership_mode"

    def test_rate_enums(self):
        rate = _load_raw("resource_rate")
        purpose = _field(rate, "rate_purpose")
        assert [v["value"] for v in purpose["enum_values"]] == [
            "cost", "billing", "overtime", "setup"]
        assert purpose["value_help"]["source"]["enum_type_id"] == "rate_purpose"
        basis = _field(rate, "rate_basis")
        assert [v["value"] for v in basis["enum_values"]] == [
            "per_hour", "per_use", "per_unit", "per_km", "per_kg"]
        assert basis["value_help"]["source"]["enum_type_id"] == "rate_basis"
        source = _field(rate, "rate_source")
        assert [v["value"] for v in source["enum_values"]] == [
            "internal", "external_contract", "standard"]
        assert source["value_help"]["source"]["enum_type_id"] == "resource_rate_source"

    def test_skill_hierarchy_depth(self):
        parent = _field(_load_raw("skill"), "parent_id")
        assert parent["value_help"]["source"]["target_bo"] == "skill"
        assert parent["value_help"]["source"]["hierarchy"]["enabled"] is True
        assert parent["value_help"]["behavior"]["exclude_self"] is True
        assert parent["semantics"]["hierarchy_level"]["max_depth"] == 3

    def test_group_hierarchy_depth(self):
        parent = _field(_load_raw("resource_group"), "parent_group_id")
        assert parent["value_help"]["source"]["target_bo"] == "resource_group"
        assert parent["value_help"]["source"]["hierarchy"]["parent_field"] == \
            "parent_group_id"
        assert parent["semantics"]["hierarchy_level"]["max_depth"] == 10

    def test_member_constraints(self):
        member = _load_raw("resource_group_member")
        alloc = _field(member, "allocation_pct")
        assert alloc["required"] is True and alloc["default"] == 100
        rule = alloc["constraints"][0]
        assert rule["gt"] == 0 and rule["lte"] == 100
        qty = _field(member, "quantity")
        assert qty["required"] is True and qty["default"] == 1
        assert qty["constraints"][0]["gte"] == 1

    def test_capability_level_range(self):
        level = _field(_load_raw("resource_capability"), "level")
        assert level["required"] is True and level["default"] == 1
        rule = level["constraints"][0]
        assert rule["gte"] == 1 and rule["lte"] == 5

    def test_indexes_declared(self):
        expected = {
            "skill": {"uq_skill_code", "idx_skill_parent",
                      "idx_skill_category", "idx_skill_status"},
            "resource": {"uq_resource_code", "idx_resource_kind",
                         "idx_resource_org", "idx_resource_location",
                         "idx_resource_party", "idx_resource_person",
                         "idx_resource_active"},
            "resource_group": {"uq_resource_group_code", "idx_resource_group_parent",
                               "idx_resource_group_org", "idx_resource_group_kind",
                               "idx_resource_group_active"},
            "resource_group_member": {"uq_resource_group_member",
                                      "idx_resource_group_member_resource",
                                      "idx_resource_group_member_group"},
            "resource_capability": {"uq_resource_capability",
                                    "idx_resource_capability_resource",
                                    "idx_resource_capability_skill"},
            "resource_rate": {"uq_resource_rate_resource", "uq_resource_rate_group",
                              "idx_resource_rate_purpose", "idx_resource_rate_org",
                              "idx_resource_rate_validity"},
        }
        for bo_id, names in expected.items():
            declared = {i["name"] for i in _load_raw(bo_id)["indexes"]}
            assert names <= declared, "{0} 缺索引 {1}".format(
                bo_id, names - declared)

    def test_work_order_operation_renamed(self):
        op = _load_raw("work_order_operation")
        assert _field(op, "work_center_id") is None
        rg = _field(op, "resource_group_id")
        assert rg["name"] == "资源组/工作中心"
        assert rg["value_help"]["source"]["target_bo"] == "resource_group"
        assert rg["value_help"]["behavior"]["binding_strength"] == "strict"
        skill = _field(op, "required_skill_id")
        assert skill["nullable"] is True
        assert skill["value_help"]["source"]["target_bo"] == "skill"
        teardown = _field(op, "teardown_minutes")
        assert teardown["default"] == 0
        legacy = _field(op, "required_skill")
        assert legacy["ui"]["editable"] is False
        assert legacy["ui"]["readonly"] is True
        assert legacy["semantics"]["readonly_always"] is True
        assert legacy["description"].startswith("已废弃")
        # [FIX 2026-11-08] G12 已新增 work_definition_id（来源作业定义，可空 =
        # 手填步骤），与 P2b 当时的"不新增"结论相反。
        wd = _field(op, "work_definition_id")
        assert wd is not None
        assert wd["nullable"] is True
        assert wd["semantics"]["display"]["target_type"] == "work_definition"

    def test_work_order_operation_indexes(self):
        names = {i["name"] for i in _load_raw("work_order_operation")["indexes"]}
        assert "idx_work_order_operation_resource_group" in names
        assert "idx_work_order_operation_required_skill" in names


class TestTable:

    def test_tables_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("skills", "resources", "resource_groups",
                      "resource_group_members", "resource_capabilities",
                      "resource_rates"):
            assert table in names

    def test_skill_foreign_key(self, conn):
        assert _fk_set(conn, "skills") == {("parent_id", "skills", "id")}

    def test_resource_foreign_keys(self, conn):
        assert _fk_set(conn, "resources") == set(RESOURCE_FKS)

    def test_group_foreign_keys(self, conn):
        assert _fk_set(conn, "resource_groups") == set(GROUP_FKS)

    def test_member_foreign_keys(self, conn):
        assert _fk_set(conn, "resource_group_members") == set(MEMBER_FKS)

    def test_capability_foreign_keys(self, conn):
        assert _fk_set(conn, "resource_capabilities") == set(CAPABILITY_FKS)

    def test_rate_foreign_keys(self, conn):
        assert _fk_set(conn, "resource_rates") == set(RATE_FKS)

    def test_unique_indexes_created(self, conn):
        for name in ("uq_skill_code", "uq_resource_code",
                     "uq_resource_group_code", "uq_resource_group_member",
                     "uq_resource_capability", "uq_resource_rate_resource",
                     "uq_resource_rate_group"):
            sql = _index_sql(conn, name) or ""
            assert "UNIQUE" in sql.upper(), "{0} 不是唯一索引".format(name)

    def test_not_null_and_nullable(self, conn):
        skill = {r[1]: r for r in conn.execute("PRAGMA table_info(skills)")}
        for column in ("code", "name", "category", "requires_certification",
                       "status"):
            assert skill[column][3] == 1
        for column in ("parent_id", "default_validity_months", "description"):
            assert skill[column][3] == 0

        resource = {r[1]: r for r in conn.execute("PRAGMA table_info(resources)")}
        for column in ("code", "name", "resource_kind", "capacity_units",
                       "utilization_pct", "is_active"):
            assert resource[column][3] == 1
        for column in ("org_id", "location_id", "cost_center_id", "party_id",
                       "person_ref", "capacity_uom_id", "capacity_per_day",
                       "calendar_id", "timezone", "valid_from", "valid_to"):
            assert resource[column][3] == 0

    def test_dangling_skill_parent_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "skills", code="SK-ORPHAN", name="孤儿技能",
                     parent_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_resource_party_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resources", code="R-ORPHAN", name="孤儿资源",
                     party_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_capability_skill_rejected(self, fk_conn):
        seed_row(fk_conn, "resources", code="R-OK", name="资源")
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resource_capabilities", resource_id=1,
                     skill_id=999, valid_from="2026-11-01")
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_member_resource_rejected(self, fk_conn):
        seed_row(fk_conn, "resource_groups", code="G-OK", name="组")
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "resource_group_members", group_id=1,
                     resource_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_duplicate_skill_code_rejected(self, conn):
        seed_row(conn, "skills", code="SK-DUP", name="甲技能")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "skills", code="SK-DUP", name="乙技能")

    def test_duplicate_resource_code_rejected(self, conn):
        seed_row(conn, "resources", code="R-DUP", name="甲资源")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resources", code="R-DUP", name="乙资源")

    def test_duplicate_member_rejected(self, conn):
        seed_row(conn, "resource_groups", id=31, code="G31", name="三一组")
        seed_row(conn, "resources", id=31, code="R31", name="三一资源")
        seed_row(conn, "resource_group_members", group_id=31, resource_id=31)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resource_group_members", group_id=31, resource_id=31)

    def test_duplicate_capability_triple_rejected(self, conn):
        seed_row(conn, "skills", id=32, code="SK32", name="三二技能")
        seed_row(conn, "resources", id=32, code="R32", name="三二资源")
        seed_row(conn, "resource_capabilities", resource_id=32, skill_id=32,
                 valid_from="2026-11-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resource_capabilities", resource_id=32, skill_id=32,
                     valid_from="2026-11-01")

    def test_duplicate_resource_rate_rejected(self, conn):
        seed_row(conn, "resources", id=33, code="R33", name="三三资源")
        seed_row(conn, "resource_rates", resource_id=33, rate=100.0,
                 rate_purpose="cost", valid_from="2026-11-01")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "resource_rates", resource_id=33, rate=200.0,
                     rate_purpose="cost", valid_from="2026-11-01")
