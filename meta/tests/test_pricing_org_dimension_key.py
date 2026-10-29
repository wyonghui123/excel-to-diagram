# -*- coding: utf-8 -*-
"""销售组织维度进入定价匹配键（T2.2 / B8 · v152）验收

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md（组织维度价目键）

口径:
  真建表（SchemaGenerator）+ 真跑 `PricingDeterminationService.determine_line`
  → `PricingService.price_line`，不使用桩。
  金额口径：过程 `lookup_amount * base`，故 qty=1 时 `unit_price == 费率`。

覆盖:
  a) 全局价目表内两条「组织 × 物料」价目行 → 不同 sales_org_id 取各自价格
  b) 两张组织归属价目表 → 组织选表 + 组织键双保险
  c) 全局表存量「物料」键（无 org）→ 传/不传销售组织价格一致（零回归）
  d) v152 迁移在临时库的幂等性（两次执行终态一致 + verify PASS）
  e) 无销售组织时 org 槽被跳过：仅 org 键价目行不应命中

【DML 位置】建表与播种 DML 全部走 `_pricing_w1_helpers` / `registry`，
本文件不写裸 SQL DML（避免被 conftest 整体 skip 成假绿）。
"""
import json
import logging
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.core.sql_adapters import SQLiteAdapter  # noqa: E402
from meta.migrations.v152__pricing_org_dimension_key import (  # noqa: E402
    KEY_SCHEMA_ORG_CUST_ITEM,
    KEY_SCHEMA_ORG_ITEM,
    migrate,
    verify,
)
from meta.services.pricing_determination_service import (  # noqa: E402
    REASON_NO_CANDIDATE,
    PricingDeterminationService,
)
from meta.tests.factories._pricing_w1_helpers import (  # noqa: E402
    seed_rate_table,
    seed_rule,
    seed_row,
)

pytestmark = pytest.mark.unit

#: 按 yaml 声明真建表所需的最小对象集合（含定价确定规则与取价链路）
TABLES = ["pricing_determination", "factor_catalog", "key_schema",
          "lookup_sequence", "rate_type", "exclusion_group", "rate_table",
          "rate_record", "calc_procedure", "calc_procedure_step",
          "calc_result", "calc_detail"]

NOW = "2026-10-06 00:00:00"


def _build_schema(path):
    """按 yaml 声明在文件库建真表（SQLiteAdapter 不支持 :memory:）。"""
    prev = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(ROOT, "meta", "schemas"))
    finally:
        logging.disable(prev)
    gen = SchemaGenerator("sqlite")
    conn = sqlite3.connect(str(path))
    try:
        for name in TABLES:
            mo = registry.get(name)
            assert mo is not None, f"{name} 未注册"
            conn.execute(gen.generate_create_table(mo))
            for idx in gen.generate_create_index(mo):
                conn.execute(idx)
        conn.commit()
    finally:
        conn.close()


def _seed_key_schemas(path, item_id=1, org_item_id=2, org_cust_item_id=3,
                      cust_item_id=4):
    seed_row(path, "key_schemas", id=item_id, code="KS_ITEM", name="物料键",
             key_fields='["item_id"]', created_at=NOW, updated_at=NOW)
    seed_row(path, "key_schemas", id=org_item_id, code=KEY_SCHEMA_ORG_ITEM,
             name="组织×物料键", key_fields='["org_id","item_id"]',
             created_at=NOW, updated_at=NOW)
    seed_row(path, "key_schemas", id=org_cust_item_id,
             code=KEY_SCHEMA_ORG_CUST_ITEM, name="组织×客户×物料键",
             key_fields='["org_id","customer_account_id","item_id"]',
             created_at=NOW, updated_at=NOW)
    seed_row(path, "key_schemas", id=cust_item_id, code="KS_ITEM_CUST",
             name="客户×物料键",
             key_fields='["customer_account_id","item_id"]',
             created_at=NOW, updated_at=NOW)


def _seed_procedure(path, sequence_id, with_rate_type=False):
    if with_rate_type:
        seed_row(path, "rate_types", id=1, code="PRICE_BASE", name="基本价格",
                 rate_class="price", calc_type="percent", rate_source="rate_record",
                 sign="+", rounding=None, exclusion_group_id=None,
                 manual_allowed=0, mandatory=0, statistical=0,
                 lookup_sequence_id=sequence_id, created_at=NOW, updated_at=NOW)
    seed_row(path, "calc_procedures", id=1, code="PROC_STD", name="标准过程",
             procedure_type="pricing", result_semantic="price", currency="CNY",
             subtotal_keys='["s1"]', created_at=NOW, updated_at=NOW)
    seed_row(path, "calc_procedure_steps", calc_procedure_id=1, seq=1,
             element_type="formula", params='{"expr":"lookup_amount * base"}',
             subtotal_key="s1", created_at=NOW, updated_at=NOW)
    seed_row(path, "calc_procedure_steps", calc_procedure_id=1, seq=2,
             element_type="round", params='{"mode":"round","digits":2}',
             created_at=NOW, updated_at=NOW)


def _seed_chain(path, *, org_slots=True, rule_table_id=1):
    """建最小可算链：KS_ITEM / 两张 org 键 / 查找序列 / 价目表 / 过程 / 规则。"""
    _seed_key_schemas(path)
    steps = ('[{"seq":1,"key_schema_id":2},{"seq":2,"key_schema_id":1}]'
             if org_slots else '[{"seq":1,"key_schema_id":1}]')
    seed_row(path, "lookup_sequences", id=1, code="LK_ITEM_STD",
             name="物料查找序列", steps=steps,
             created_at=NOW, updated_at=NOW)
    _seed_procedure(path, sequence_id=1, with_rate_type=True)
    if rule_table_id is not None:
        # 规则钉住价目表 1，必须真种一张 approved 全局表，否则解析即 NO_RATE_TABLE
        seed_rate_table(path, code="PL_STD", name="全局标准价目表")
    seed_rule(path, code="PD_STD", rate_table_id=rule_table_id)


def _seed_record(path, *, record_id, table_id, schema_id, keys, rate,
                 priority=100):
    seed_row(path, "rate_records", id=record_id, code=f"RC_{record_id}",
             rate_table_id=table_id, key_schema_id=schema_id,
             keys=json.dumps(keys), rate_type_id=1, rate=rate,
             hit_policy="exclusive", priority=priority, status="active",
             rate_qty=1, created_at=NOW, updated_at=NOW)


def _price(ds, **kwargs):
    return PricingDeterminationService(ds).determine_line(
        item_id=1, qty=1, currency="CNY", **kwargs)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "pricing_org.db"
    _build_schema(path)
    return path


@pytest.fixture()
def ds(db_path):
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    yield adapter
    adapter.disconnect()


class TestOrgDimensionKey:

    # ---- a) 同表内按组织键区分 ----------------------------------------
    def test_global_table_two_orgs_get_own_price(self, db_path, ds):
        """全局价目表：同物料、两条组织键价目行 → 各组织取各价"""
        _seed_chain(db_path)
        _seed_record(db_path, record_id=1, table_id=1, schema_id=2,
                     keys={"org_id": 1001, "item_id": 1}, rate=100.0)
        _seed_record(db_path, record_id=2, table_id=1, schema_id=2,
                     keys={"org_id": 1002, "item_id": 1}, rate=200.0)

        got_1001 = _price(ds, sales_org_id=1001)
        got_1002 = _price(ds, sales_org_id=1002)

        assert got_1001["pricing_status"] == "determined"
        assert got_1001["unit_price"] == 100.0
        assert got_1001["trace"]["hit_ids"] == [1]
        assert got_1002["pricing_status"] == "determined"
        assert got_1002["unit_price"] == 200.0
        assert got_1002["trace"]["hit_ids"] == [2]

    # ---- b) 组织归属表（表级 + 键级） ----------------------------------
    def test_org_owned_tables_select_own_table(self, db_path, ds):
        """两张组织表：组织选表命中，且表内 org 键与组织一致"""
        _seed_chain(db_path, rule_table_id=None)
        table_a = seed_rate_table(db_path, code="PL_A", name="组织1001价目表",
                                  owner_org_id=1001)
        table_b = seed_rate_table(db_path, code="PL_B", name="组织1002价目表",
                                  owner_org_id=1002)
        _seed_record(db_path, record_id=1, table_id=table_a, schema_id=2,
                     keys={"org_id": 1001, "item_id": 1}, rate=100.0)
        _seed_record(db_path, record_id=2, table_id=table_b, schema_id=2,
                     keys={"org_id": 1002, "item_id": 1}, rate=200.0)

        got_a = _price(ds, sales_org_id=1001)
        got_b = _price(ds, sales_org_id=1002)

        assert got_a["trace"]["rate_table_code"] == "PL_A"
        assert got_a["unit_price"] == 100.0
        assert got_a["trace"]["hit_ids"] == [1]
        assert got_b["trace"]["rate_table_code"] == "PL_B"
        assert got_b["unit_price"] == 200.0
        assert got_b["trace"]["hit_ids"] == [2]

    # ---- c) 存量「物料」键零回归 --------------------------------------
    def test_legacy_item_key_same_price_with_or_without_org(self, db_path, ds):
        """全局表存量物料键（keys 无 org）→ 传/不传销售组织价格一致"""
        _seed_chain(db_path)
        _seed_record(db_path, record_id=1, table_id=1, schema_id=1,
                     keys={"item_id": 1}, rate=100.0)

        without_org = _price(ds)
        with_org = _price(ds, sales_org_id=1001)

        assert without_org["pricing_status"] == "determined"
        assert without_org["unit_price"] == 100.0
        assert with_org["pricing_status"] == "determined"
        assert with_org["unit_price"] == 100.0
        assert with_org["trace"]["hit_ids"] == [1]

    # ---- e) 无组织值 → 跳过 org 槽，org 键行不命中 -----------------------
    def test_no_org_skips_org_slot_and_does_not_hit_org_record(self, db_path, ds):
        """订单无销售组织：org 槽为 None 被跳过，仅 org 键的价目行不命中"""
        _seed_chain(db_path)
        _seed_record(db_path, record_id=1, table_id=1, schema_id=2,
                     keys={"org_id": 1001, "item_id": 1}, rate=100.0)

        no_org = _price(ds)
        assert no_org["pricing_status"] == "failed"
        assert no_org["reason"] == REASON_NO_CANDIDATE

        with_org = _price(ds, sales_org_id=1001)
        assert with_org["pricing_status"] == "determined"
        assert with_org["unit_price"] == 100.0


def _snapshot(path):
    """读取迁移相关表的终态（只做 SELECT，不写库）。"""
    conn = sqlite3.connect(str(path))
    try:
        factors = [tuple(r) for r in conn.execute(
            "SELECT object_type, field_id FROM factor_catalogs"
            " ORDER BY object_type, field_id")]
        schemas = [(code, json.loads(fields or '[]')) for code, fields in
                   conn.execute("SELECT code, key_fields FROM key_schemas"
                                " ORDER BY code")]
        steps = {code: json.loads(raw or '[]') for code, raw in
                 conn.execute("SELECT code, steps FROM lookup_sequences"
                              " ORDER BY code")}
        records = [(rid, schema_id, json.loads(keys or '{}')) for rid, schema_id, keys
                   in conn.execute("SELECT id, key_schema_id, keys FROM rate_records"
                                   " ORDER BY id")]
    finally:
        conn.close()
    return {"factors": factors, "schemas": schemas,
            "steps": steps, "records": records}


class TestMigrationIdempotency:

    def _seed_pre_migration(self, path):
        """按 v130 之后的库形态播种（尚无 org 因子/键/序列首槽）。"""
        _seed_key_schemas(path, org_item_id=7, org_cust_item_id=8)
        seed_row(path, "lookup_sequences", id=1, code="LK_ITEM_STD",
                 name="物料查找序列", steps='[{"seq":1,"key_schema_id":1}]',
                 created_at=NOW, updated_at=NOW)
        seed_row(path, "lookup_sequences", id=2, code="LK_ITEM_CUST",
                 name="客户优先查找序列",
                 steps='[{"seq":1,"key_schema_id":4},{"seq":2,"key_schema_id":1}]',
                 created_at=NOW, updated_at=NOW)
        _seed_procedure(path, sequence_id=1, with_rate_type=True)
        seed_rule(path, code="PD_STD", rate_table_id=1)
        seed_rate_table(path, code="PL_STD", name="全局标准价目表")
        org_table = seed_rate_table(path, code="PL_ORG", name="组织1001价目表",
                                    owner_org_id=1001)
        _seed_record(path, record_id=1, table_id=1, schema_id=1,
                     keys={"item_id": 1}, rate=100.0)
        _seed_record(path, record_id=2, table_id=org_table, schema_id=1,
                     keys={"item_id": 1}, rate=50.0)

    def test_two_runs_are_idempotent(self, tmp_path, capsys):
        db = tmp_path / "migrate_v152.db"
        _build_schema(db)
        self._seed_pre_migration(db)

        assert migrate(db) is True
        assert verify(db) is True
        first = _snapshot(db)

        conn = sqlite3.connect(str(db))
        try:
            org_item_id = conn.execute(
                "SELECT id FROM key_schemas WHERE code = ?",
                (KEY_SCHEMA_ORG_ITEM,)).fetchone()[0]
            org_cust_item_id = conn.execute(
                "SELECT id FROM key_schemas WHERE code = ?",
                (KEY_SCHEMA_ORG_CUST_ITEM,)).fetchone()[0]
            record = conn.execute(
                "SELECT key_schema_id, keys FROM rate_records WHERE id = 2"
            ).fetchone()
        finally:
            conn.close()

        # 首槽已插入 org 键并顺延；存量组织行键表换 org 版 + keys 补 org_id
        assert first["steps"]["LK_ITEM_STD"] == [
            {"seq": 1, "key_schema_id": org_item_id},
            {"seq": 2, "key_schema_id": 1}]
        assert first["steps"]["LK_ITEM_CUST"] == [
            {"seq": 1, "key_schema_id": org_cust_item_id},
            {"seq": 2, "key_schema_id": 4},
            {"seq": 3, "key_schema_id": 1}]
        assert dict(first["schemas"])[KEY_SCHEMA_ORG_ITEM] == ["org_id", "item_id"]
        assert dict(first["schemas"])[KEY_SCHEMA_ORG_CUST_ITEM] == [
            "org_id", "customer_account_id", "item_id"]
        assert record[0] == org_item_id
        assert json.loads(record[1]) == {"item_id": 1, "org_id": 1001}
        # 全局表存量行保持原样
        assert first["records"][0] == (1, 1, {"item_id": 1})
        assert ("sales_order_line", "org_id") in first["factors"]

        capsys.readouterr()
        assert migrate(db) is True
        second_out = capsys.readouterr().out
        assert "[FACTOR]" not in second_out
        assert "[KS]" not in second_out
        assert "[SEQ]" not in second_out
        assert "[BACKFILL]" not in second_out
        assert verify(db) is True
        assert _snapshot(db) == first
