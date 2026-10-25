# -*- coding: utf-8 -*-
"""W1-C 往来单位地址：YAML 声明 / 真建表 / 真外键 / 默认唯一性

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §5.2 / §5.4 / §5.5

【本文件守什么】
  1. 对象已注册、`table_name` / `parent_object` 正确，`skip_auto_menu` 生效
  2. 按 yaml 真建表，两条外键逐条存在（防 `source_field` 写错而推错列）
  3. `(party_id, address_id, role)` 唯一 + 同角色至多一条启用默认（部分唯一，W1-R13）
  4. 必填列 NOT NULL、`description` 可空
  5. UI 挂载面是 `party_archive`（父键推断依赖 `ui.relation`）
  6. 订单抬头两个地址字段可空、有真外键、进表单
  7. 地址库删除保护覆盖往来单位地址与订单引用

测试隔离同 `test_customer_sales_org_schema.py`：内存 SQLite + registry 重载 + 真建表；
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
from meta.tests.factories._pricing_p2_helpers import (  # noqa: E402
    create_tables,
    seed_row,
)

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

# 建表顺序：先 FK 目标表，再子表
TABLES = ["region", "address", "party", "party_address"]

EXPECTED_FKS = [
    ("party_id", "parties", "id"),
    ("address_id", "addresses", "id"),
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


class TestDeclaration:

    def test_object_registered(self):
        _reload_quietly()
        mo = registry.get("party_address")
        assert mo is not None
        assert mo.table_name == "party_addresses"

    def test_parent_and_menu(self):
        schema = _load_raw("party_address")
        assert schema["parent_object"] == "party"
        assert schema["ui_view_config"]["skip_auto_menu"] is True

    def test_required_fields(self):
        schema = _load_raw("party_address")
        for field_id in ("party_id", "address_id", "role", "is_default", "status"):
            assert _field(schema, field_id)["required"] is True
        assert _field(schema, "description")["nullable"] is True

    def test_role_enum(self):
        schema = _load_raw("party_address")
        role = _field(schema, "role")
        assert [v["value"] for v in role["enum_values"]] == \
            ["sold_to", "ship_to", "bill_to"]

    def test_is_default_switch(self):
        schema = _load_raw("party_address")
        is_default = _field(schema, "is_default")
        assert is_default["type"] == "boolean"
        assert is_default["default"] is False

    def test_indexes_declared(self):
        schema = _load_raw("party_address")
        by_name = {i.get("name"): i for i in schema["indexes"]}
        triple = by_name["uidx_party_address_party_addr_role"]
        assert triple["unique"] is True
        assert triple["fields"] == ["party_id", "address_id", "role"]
        default = by_name["uidx_party_address_default"]
        assert default["unique"] is True
        assert default["type"] == "partial"
        assert "is_default" in default["condition"]

    def test_party_id_ui_face(self):
        schema = _load_raw("party_address")
        party_id = _field(schema, "party_id")
        assert party_id["value_help"]["source"]["target_bo"] == "party_archive"
        assert party_id["ui"]["relation"] == "party_archive"

    def test_party_detail_child_section(self):
        schema = _load_raw("party_archive")
        children = (schema.get("ui_view_config") or {}).get("child_sections") or []
        match = [c for c in children if c.get("child_object") == "party_address"]
        assert match, "业务伙伴详情未挂载 party_address"
        assert match[0]["display"] == "tab"

    def test_order_address_fields(self):
        schema = _load_raw("sales_order")
        for field_id in ("ship_to_address_id", "bill_to_address_id"):
            f = _field(schema, field_id)
            assert f["nullable"] is True
            assert f["value_help"]["source"]["target_bo"] == "address"
        sections = schema["ui_view_config"]["form"]["sections"]
        rendered = [c.get("fields") for s in sections for c in s.get("columns") or []]
        assert ["ship_to_address_id", "bill_to_address_id"] in rendered

    def test_order_address_relations(self):
        schema = _load_raw("sales_order")
        refs = {r["id"]: r for r in schema["relations"]}
        assert refs["sales_order_to_ship_to_address"]["target"] == "address"
        assert refs["sales_order_to_ship_to_address"]["source_field"] == \
            "ship_to_address_id"
        assert refs["sales_order_to_bill_to_address"]["target"] == "address"

    def test_address_deletion_guard(self):
        schema = _load_raw("address")
        restricted = {(r["table"], r["foreign_key"])
                      for r in schema["deletion_policy"]["restrict_on"]}
        assert ("party_addresses", "address_id") in restricted
        assert ("sales_orders", "ship_to_address_id") in restricted
        assert ("sales_orders", "bill_to_address_id") in restricted


class TestTable:

    def test_table_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "party_addresses" in names

    def test_foreign_keys(self, conn):
        got = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(party_addresses)")}
        assert got == set(EXPECTED_FKS)

    def test_indexes_created(self, conn):
        rows = {r[0]: r[1] for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name='party_addresses'")}
        assert "UNIQUE" in rows["uidx_party_address_party_addr_role"].upper()
        default_sql = rows["uidx_party_address_default"].upper()
        assert "UNIQUE" in default_sql and "WHERE" in default_sql

    def test_not_null_and_nullable(self, conn):
        info = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(party_addresses)")}
        for field_id in ("party_id", "address_id", "role", "is_default", "status"):
            assert info[field_id][3] == 1
        assert info["description"][3] == 0

    def test_dangling_reference_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "party_addresses",
                     party_id=999, address_id=999, role="ship_to")
        assert "FOREIGN KEY" in str(exc.value).upper()

    def test_second_default_rejected(self, conn):
        """W1-R13：同一往来单位同一角色至多一条启用默认地址。"""
        seed_row(conn, "addresses", id=11, country_id=1, code="A11")
        seed_row(conn, "addresses", id=12, country_id=1, code="A12")
        seed_row(conn, "parties", id=11, code="P11")
        seed_row(conn, "party_addresses", party_id=11, address_id=11,
                 role="ship_to", is_default=1)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "party_addresses", party_id=11, address_id=12,
                     role="ship_to", is_default=1)

    def test_duplicate_triple_rejected(self, conn):
        seed_row(conn, "addresses", id=21, country_id=1, code="A21")
        seed_row(conn, "parties", id=21, code="P21")
        seed_row(conn, "party_addresses", party_id=21, address_id=21,
                 role="bill_to", is_default=0)
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, "party_addresses", party_id=21, address_id=21,
                     role="bill_to", is_default=0)
