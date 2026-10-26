# -*- coding: utf-8 -*-
"""客户销售组织（W1-B）：YAML 声明 / 真建表 / 真外键 / 唯一索引

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §4.2 / §4.4

【本文件守什么】
  1. 对象已注册、`table_name` / `parent_object` 正确，`skip_auto_menu` 生效
  2. 按 yaml 真建表，五条外键**逐条**存在（防 `source_field` 写错而推错列）
  3. DB 级 FK 是真约束：悬空引用抛 IntegrityError
  4. `(customer_account_id, sales_org_id)` 唯一索引就位
  5. 必填列 NOT NULL、四个覆盖字段可空（空 = 沿用账户级）
  6. `sales_org_id` 候选集走 `org_sales_org` 视图，回显/跳转落 `org`
  7. 客户档案详情的 `child_sections` 已挂上该子表（tab 形态）

测试隔离同 `test_pricing_p2_schemas.py`：内存 SQLite + registry 重载 + 真建表；
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
TABLES = ["currency", "payment_term", "tax_classification", "org",
          "rate_table", "customer_account", "customer_sales_org"]

# (源列, 目标表, 目标列) —— 逐条断言
EXPECTED_FKS = [
    ("customer_account_id", "customer_accounts", "id"),
    ("sales_org_id", "orgs", "id"),
    ("tax_classification_id", "tax_classifications", "id"),
    ("payment_term_id", "payment_terms", "id"),
    ("currency_id", "currencies", "id"),
    ("rate_table_id", "rate_tables", "id"),
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
        mo = registry.get("customer_sales_org")
        assert mo is not None
        assert mo.table_name == "customer_sales_orgs"

    def test_parent_and_menu(self):
        schema = _load_raw("customer_sales_org")
        assert schema["parent_object"] == "customer_account"
        assert schema["ui_view_config"]["skip_auto_menu"] is True

    def test_required_and_override_fields(self):
        schema = _load_raw("customer_sales_org")
        for field_id in ("customer_account_id", "sales_org_id"):
            assert _field(schema, field_id)["required"] is True
        for field_id in ("tax_classification_id", "payment_term_id",
                         "incoterm_code", "currency_id", "rate_table_id"):
            assert _field(schema, field_id)["nullable"] is True

    def test_sales_org_candidate_set_narrowed(self):
        schema = _load_raw("customer_sales_org")
        source = _field(schema, "sales_org_id")["value_help"]["source"]
        assert source["target_bo"] == "org_sales_org"
        assert source["display_target_bo"] == "org"
        assert source["detail_target_bo"] == "org"

    def test_status_enum(self):
        schema = _load_raw("customer_sales_org")
        status = _field(schema, "status")
        assert status["default"] == "active"
        assert [v["value"] for v in status["enum_values"]] == ["active", "inactive"]

    def test_unique_index_declared(self):
        schema = _load_raw("customer_sales_org")
        found = [i for i in schema["indexes"]
                 if i.get("name") == "uidx_customer_sales_org_account_org"]
        assert found and found[0]["unique"] is True
        assert found[0]["fields"] == ["customer_account_id", "sales_org_id"]

    def test_account_child_section(self):
        schema = _load_raw("customer_account")
        children = (schema.get("ui_view_config") or {}).get("child_sections") or []
        match = [c for c in children if c.get("child_object") == "customer_sales_org"]
        assert match, "客户档案详情未挂载 customer_sales_org"
        assert match[0]["display"] == "tab"


class TestTable:

    def test_table_created(self, conn):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "customer_sales_orgs" in names

    def test_foreign_keys(self, conn):
        got = {(row[3], row[2], row[4]) for row in conn.execute(
            "PRAGMA foreign_key_list(customer_sales_orgs)")}
        assert got == set(EXPECTED_FKS)

    def test_unique_index(self, conn):
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            ("uidx_customer_sales_org_account_org",)).fetchone()
        assert sql and "UNIQUE" in sql[0].upper()

    def test_not_null_and_nullable(self, conn):
        info = {r[1]: r for r in conn.execute(
            "PRAGMA table_info(customer_sales_orgs)")}
        assert info["customer_account_id"][3] == 1
        assert info["sales_org_id"][3] == 1
        for field_id in ("tax_classification_id", "payment_term_id",
                         "incoterm_code", "currency_id", "rate_table_id"):
            assert info[field_id][3] == 0

    def test_dangling_reference_rejected(self, fk_conn):
        with pytest.raises(sqlite3.IntegrityError) as exc:
            seed_row(fk_conn, "customer_sales_orgs",
                     customer_account_id=999, sales_org_id=999)
        assert "FOREIGN KEY" in str(exc.value).upper()
