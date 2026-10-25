# -*- coding: utf-8 -*-
"""区域 + 销售员区域分配（W2-E）：YAML 声明 / 真建表 / 真外键 / 唯一索引

依据: docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md
      §7.2（对象）/ §7.3（菜单与权限）/ §7.4（R-TER-2）

【本文件守什么】
  1. 两个对象已注册、table_name / parent_object 正确，skip_auto_menu 生效
  2. 字段必填 / 可空与 status 枚举符合 Spec
  3. 按 yaml 真建表，外键逐条存在（含 parent_id 自引用）
  4. DB 级 FK 是真约束：悬空引用抛 IntegrityError
  5. code 全局唯一；(salesperson_id, territory_id, effective_from) 唯一
  6. 同销售员同生效日至多一条主区域（R-TER-2，部分唯一索引）
  7. 销售员详情已挂负责区域子表

测试隔离同 `test_salesperson_schema.py`：内存 SQLite + registry 重载 + 真建表；
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
TABLES = ["party", "user", "org", "salesperson",
          "territory", "salesperson_territory_assignment"]

TERRITORY_FKS = [
    ("parent_id", "territories", "id"),
    ("owner_org_id", "orgs", "id"),
]

ASSIGNMENT_FKS = [
    ("salesperson_id", "salespersons", "id"),
    ("territory_id", "territories", "id"),
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


class TestDeclaration:

    def test_objects_registered(self):
        _reload_quietly()
        ter = registry.get("territory")
        assign = registry.get("salesperson_territory_assignment")
        assert ter is not None and ter.table_name == "territories"
        assert assign is not None
        assert assign.table_name == "salesperson_territory_assignments"

    def test_parent_and_menu(self):
        assign = _load_raw("salesperson_territory_assignment")
        assert assign["parent_object"] == "salesperson"
        assert assign["ui_view_config"]["skip_auto_menu"] is True
        assert _load_raw("territory")["ui_view_config"]["skip_auto_menu"] is True

    def test_required_and_optional_fields(self):
        ter = _load_raw("territory")
        for field_id in ("code", "name", "status"):
            assert _field(ter, field_id)["required"] is True
        for field_id in ("parent_id", "level", "owner_org_id", "description"):
            assert _field(ter, field_id).get("nullable") is True
        assign = _load_raw("salesperson_territory_assignment")
        for field_id in ("salesperson_id", "territory_id", "is_primary"):
            assert _field(assign, field_id)["required"] is True
        for field_id in ("effective_from", "effective_to"):
            assert _field(assign, field_id).get("nullable") is True

    def test_status_enum(self):
        status = _field(_load_raw("territory"), "status")
        assert status["default"] == "active"
        assert [v["value"] for v in status["enum_values"]] == ["active", "inactive"]

    def test_hierarchy_and_exclude_self(self):
        parent = _field(_load_raw("territory"), "parent_id")
        assert parent["value_help"]["source"]["target_bo"] == "territory"
        assert parent["value_help"]["source"]["hierarchy"]["enabled"] is True
        assert parent["value_help"]["source"]["hierarchy"]["parent_field"] == "parent_id"
        assert parent["value_help"]["behavior"]["exclude_self"] is True
        assert parent["semantics"]["hierarchy_level"]["max_depth"] == 10

    def test_indexes_declared(self):
        ter = {i["name"]: i for i in _load_raw("territory")["indexes"]}
        assert ter["uq_territory_code"]["unique"] is True
        assert ter["uq_territory_code"]["fields"] == ["code"]
        assert "idx_territory_parent" in ter
        assert "idx_territory_owner_org" in ter
        assert "idx_territory_status" in ter

        assign = {i["name"]: i for i in
                  _load_raw("salesperson_territory_assignment")["indexes"]}
        triple = assign["uq_sta_triple"]
        assert triple["unique"] is True
        assert triple["fields"] == ["salesperson_id", "territory_id",
                                    "effective_from"]
        primary = assign["uq_sta_primary"]
        assert primary["unique"] is True and primary["type"] == "partial"
        assert "is_primary = 1" in primary["condition"]

    def test_salesperson_child_section(self):
        schema = _load_raw("salesperson")
        children = (schema.get("ui_view_config") or {}).get("child_sections") or []
        match = [c for c in children
                 if c.get("child_object") == "salesperson_territory_assignment"]
        assert match, "销售员详情未挂载 salesperson_territory_assignment"
        assert match[0]["display"] == "tab"

    def test_deletion_protection(self):
        schema = _load_raw("territory")
        tables = {(r["table"], r["foreign_key"])
                  for r in schema["deletion_policy"]["restrict_on"]}
        assert ("territories", "parent_id") in tables
        assert ("salesperson_territory_assignments", "territory_id") in tables


class TestTable:

    def test_tables_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "territories" in names
        assert "salesperson_territory_assignments" in names

    def test_foreign_keys(self, conn):
        ter = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(territories)")}
        assert ter == set(TERRITORY_FKS)
        assign = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(salesperson_territory_assignments)")}
        assert assign == set(ASSIGNMENT_FKS)

    def test_indexes_created(self, conn):
        code = _index_sql(conn, "uq_territory_code") or ""
        assert "UNIQUE" in code.upper()
        triple = _index_sql(conn, "uq_sta_triple") or ""
        assert "UNIQUE" in triple.upper()
        primary = _index_sql(conn, "uq_sta_primary") or ""
        assert "UNIQUE" in primary.upper()
        assert "WHERE" in primary.upper() and "IS_PRIMARY" in primary.upper()

    def test_not_null_and_nullable(self, conn):
        ter = {r[1]: r for r in conn.execute("PRAGMA table_info(territories)")}
        for column in ("code", "name", "status"):
            assert ter[column][3] == 1
        for column in ("parent_id", "level", "owner_org_id", "description"):
            assert ter[column][3] == 0

        assign = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(salesperson_territory_assignments)")}
        for column in ("salesperson_id", "territory_id", "is_primary"):
            assert assign[column][3] == 1
        for column in ("effective_from", "effective_to"):
            assert assign[column][3] == 0

    def test_dangling_parent_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "territories", code="T-ORPHAN", name="孤儿",
                     parent_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_owner_org_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "territories", code="T-ORPHAN2", name="孤儿2",
                     owner_org_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_assignment_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "salesperson_territory_assignments",
                     salesperson_id=999, territory_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_duplicate_code_rejected(self, conn):
        seed_row(conn, "territories", code="T-DUP", name="甲区")
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "territories", code="T-DUP", name="乙区")

    def test_duplicate_triple_rejected(self, conn):
        seed_row(conn, "salespersons", id=31, code="SPT31", name="戊")
        seed_row(conn, "territories", id=31, code="T31", name="三一区")
        seed_row(conn, "salesperson_territory_assignments",
                 salesperson_id=31, territory_id=31,
                 effective_from="2026-10-01", is_primary=0)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "salesperson_territory_assignments",
                     salesperson_id=31, territory_id=31,
                     effective_from="2026-10-01", is_primary=0)

    def test_second_primary_rejected(self, conn):
        seed_row(conn, "salespersons", id=41, code="SPT41", name="己")
        seed_row(conn, "territories", id=41, code="T41", name="四一区")
        seed_row(conn, "territories", id=42, code="T42", name="四二区")
        seed_row(conn, "salesperson_territory_assignments",
                 salesperson_id=41, territory_id=41,
                 effective_from="2026-10-01", is_primary=1)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "salesperson_territory_assignments",
                     salesperson_id=41, territory_id=42,
                     effective_from="2026-10-01", is_primary=1)

    def test_null_effective_from_not_constrained_on_primary(self, conn):
        # SQLite 唯一索引把 NULL 视为互不相等：无生效日的主区域不互斥
        seed_row(conn, "salespersons", id=51, code="SPT51", name="庚")
        seed_row(conn, "territories", id=51, code="T51", name="五一区")
        seed_row(conn, "territories", id=52, code="T52", name="五二区")
        seed_row(conn, "salesperson_territory_assignments",
                 salesperson_id=51, territory_id=51,
                 effective_from=None, is_primary=1)
        seed_row(conn, "salesperson_territory_assignments",
                 salesperson_id=51, territory_id=52,
                 effective_from=None, is_primary=1)
