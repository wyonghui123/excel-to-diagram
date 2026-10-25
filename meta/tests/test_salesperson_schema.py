# -*- coding: utf-8 -*-
"""销售员 + 客户销售员分配（W1-D）：YAML 声明 / 真建表 / 真外键 / 唯一索引

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §6.2 / §6.5

【本文件守什么】
  1. 两个对象已注册、table_name / parent_object 正确，skip_auto_menu 生效
  2. 按 yaml 真建表，外键逐条存在（防 source_field 写错而推错列）
  3. DB 级 FK 是真约束：悬空引用抛 IntegrityError
  4. `(customer_account_id, sales_org_id, salesperson_id)` 唯一
  5. 同客户同组织至多一条 active 主销售员（W1-R16）；NULL 组织的通用主销售员也唯一
  6. 客户档案详情已挂客户销售员分配子表；订单 salesperson_id 可空且进表单

测试隔离同 `test_party_address_schema.py`：内存 SQLite + registry 重载 + 真建表；
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
TABLES = ["party", "user", "org", "customer_account",
          "salesperson", "customer_salesperson_assignment"]

SALESPERSON_FKS = [
    ("party_id", "parties", "id"),
    ("user_id", "users", "id"),
]

ASSIGNMENT_FKS = [
    ("customer_account_id", "customer_accounts", "id"),
    ("sales_org_id", "orgs", "id"),
    ("salesperson_id", "salespersons", "id"),
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
        sp = registry.get("salesperson")
        assign = registry.get("customer_salesperson_assignment")
        assert sp is not None and sp.table_name == "salespersons"
        assert assign is not None
        assert assign.table_name == "customer_salesperson_assignments"

    def test_parent_and_menu(self):
        assign = _load_raw("customer_salesperson_assignment")
        assert assign["parent_object"] == "customer_account"
        assert assign["ui_view_config"]["skip_auto_menu"] is True
        assert _load_raw("salesperson")["ui_view_config"]["skip_auto_menu"] is True

    def test_required_and_optional_fields(self):
        sp = _load_raw("salesperson")
        for field_id in ("code", "name", "status"):
            assert _field(sp, field_id)["required"] is True
        for field_id in ("party_id", "user_id", "description"):
            assert _field(sp, field_id).get("nullable") is True
        assign = _load_raw("customer_salesperson_assignment")
        for field_id in ("customer_account_id", "salesperson_id",
                         "is_primary", "status"):
            assert _field(assign, field_id)["required"] is True
        for field_id in ("sales_org_id", "valid_from", "valid_to"):
            assert _field(assign, field_id).get("nullable") is True

    def test_salesperson_status_enum(self):
        status = _field(_load_raw("salesperson"), "status")
        assert status["default"] == "active"
        assert [v["value"] for v in status["enum_values"]] == ["active", "inactive"]

    def test_assignment_indexes_declared(self):
        schema = _load_raw("customer_salesperson_assignment")
        found = {i["name"]: i for i in schema["indexes"]}
        triple = found["uidx_customer_salesperson_assign"]
        assert triple["unique"] is True
        assert triple["fields"] == ["customer_account_id", "sales_org_id",
                                    "salesperson_id"]
        primary = found["uidx_customer_salesperson_primary"]
        assert primary["unique"] is True and primary["type"] == "partial"
        assert "is_primary = 1" in primary["condition"]
        all_org = found["uidx_customer_salesperson_primary_all_org"]
        assert all_org["unique"] is True and all_org["type"] == "partial"
        assert "sales_org_id IS NULL" in all_org["condition"]

    def test_account_child_section(self):
        schema = _load_raw("customer_account")
        children = (schema.get("ui_view_config") or {}).get("child_sections") or []
        match = [c for c in children
                 if c.get("child_object") == "customer_salesperson_assignment"]
        assert match, "客户档案详情未挂载 customer_salesperson_assignment"
        assert match[0]["display"] == "tab"

    def test_order_salesperson_field(self):
        schema = _load_raw("sales_order")
        field = _field(schema, "salesperson_id")
        assert field is not None
        assert field.get("nullable") is True
        assert field["value_help"]["source"]["target_bo"] == "salesperson"
        assert field["ui"]["relation"] == "salesperson"
        form = schema["ui_view_config"]["form"]
        flat = [f for section in form["sections"]
                for col in section["columns"] for f in col["fields"]]
        assert "salesperson_id" in flat

    def test_order_relation_declared(self):
        schema = _load_raw("sales_order")
        match = [r for r in schema["relations"]
                 if r.get("id") == "sales_order_to_salesperson"]
        assert match
        assert match[0]["source_field"] == "salesperson_id"
        assert match[0]["target"] == "salesperson"

    def test_deletion_protection(self):
        schema = _load_raw("salesperson")
        restrict = schema["deletion_policy"]["restrict_on"]
        tables = {(r["table"], r["foreign_key"]) for r in restrict}
        assert ("customer_salesperson_assignments", "salesperson_id") in tables
        assert ("sales_orders", "salesperson_id") in tables


class TestTable:

    def test_tables_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "salespersons" in names
        assert "customer_salesperson_assignments" in names

    def test_foreign_keys(self, conn):
        sp = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(salespersons)")}
        assert sp == set(SALESPERSON_FKS)
        assign = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(customer_salesperson_assignments)")}
        assert assign == set(ASSIGNMENT_FKS)

    def test_indexes_created(self, conn):
        assert "UNIQUE" in (_index_sql(conn, "uidx_salesperson_code") or "").upper()
        triple = _index_sql(conn, "uidx_customer_salesperson_assign") or ""
        assert "UNIQUE" in triple.upper()
        primary = _index_sql(conn, "uidx_customer_salesperson_primary") or ""
        assert "UNIQUE" in primary.upper()
        assert "WHERE" in primary.upper() and "IS_PRIMARY" in primary.upper()
        all_org = _index_sql(conn, "uidx_customer_salesperson_primary_all_org") or ""
        assert "SALES_ORG_ID IS NULL" in all_org.upper()

    def test_not_null_and_nullable(self, conn):
        sp = {r[1]: r for r in conn.execute("PRAGMA table_info(salespersons)")}
        for column in ("code", "name", "status"):
            assert sp[column][3] == 1
        for column in ("party_id", "user_id"):
            assert sp[column][3] == 0
        assign = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(customer_salesperson_assignments)")}
        for column in ("customer_account_id", "salesperson_id",
                       "is_primary", "status"):
            assert assign[column][3] == 1
        for column in ("sales_org_id", "valid_from", "valid_to"):
            assert assign[column][3] == 0

    def test_dangling_salesperson_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "salespersons", code="SPX", name="孤儿",
                     party_id=999, user_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_dangling_assignment_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "customer_salesperson_assignments",
                     customer_account_id=999, salesperson_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_second_primary_rejected(self, conn):
        seed_row(conn, "salespersons", code="SP11", name="甲")
        seed_row(conn, "salespersons", code="SP12", name="乙")
        seed_row(conn, "customer_salesperson_assignments",
                 customer_account_id=1, sales_org_id=318, salesperson_id=11,
                 is_primary=1)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "customer_salesperson_assignments",
                     customer_account_id=1, sales_org_id=318, salesperson_id=12,
                     is_primary=1)

    def test_second_all_org_primary_rejected(self, conn):
        seed_row(conn, "salespersons", code="SP21", name="丙")
        seed_row(conn, "salespersons", code="SP22", name="丁")
        seed_row(conn, "customer_salesperson_assignments",
                 customer_account_id=2, sales_org_id=None, salesperson_id=21,
                 is_primary=1)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "customer_salesperson_assignments",
                     customer_account_id=2, sales_org_id=None, salesperson_id=22,
                     is_primary=1)

    def test_duplicate_triple_rejected(self, conn):
        seed_row(conn, "salespersons", code="SP31", name="戊")
        seed_row(conn, "customer_salesperson_assignments",
                 customer_account_id=3, sales_org_id=318, salesperson_id=31,
                 is_primary=0)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "customer_salesperson_assignments",
                     customer_account_id=3, sales_org_id=318, salesperson_id=31,
                     is_primary=0)
