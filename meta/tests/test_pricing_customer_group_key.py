# -*- coding: utf-8 -*-
"""客户组维度进入定价匹配键（T2.3 / B4 · v153）验收

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/b4_attribute_condition_design.md

口径:
  真建表（SchemaGenerator）+ 真跑 `PricingDeterminationService.determine_line`
  → `PricingService.price_line`，不使用桩。
  金额口径：过程 `lookup_amount * base`，故 `unit_price == 费率`。

覆盖:
  a) 组价命中（组价 90 vs 普通价 100）
  b) 客户无组 → 组槽跳过，回退物料价 100
  c) 无关系 / 无组 → 物料价 100 且 pricing_status='determined'
  d) 组槽 + 组织槽叠加：更靠前的槽位（组织）取价
  e) v153 迁移幂等（两次执行第二次全 SKIP + verify PASS + seq 无重复）
  f) 阶梯与客户组互不干扰（qty=5 → 90，qty=50 → 80）

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
from meta.migrations.v153__pricing_customer_group_dimension import (  # noqa: E402
    KEY_SCHEMA_GROUP_ITEM,
    migrate,
    verify,
)
from meta.services.pricing_determination_service import (  # noqa: E402
    PricingDeterminationService,
)
from meta.tests.factories._pricing_w1_helpers import (  # noqa: E402
    seed_rate_table,
    seed_rule,
    seed_row,
)

pytestmark = pytest.mark.unit

#: 按 yaml 声明真建表所需的最小对象集合（含定价链 + 客户组来源表）
TABLES = ["pricing_determination", "factor_catalog", "key_schema",
          "lookup_sequence", "rate_type", "exclusion_group", "rate_table",
          "rate_record", "calc_procedure", "calc_procedure_step",
          "calc_result", "calc_detail", "party_group", "party_relation",
          "customer_account"]

NOW = "2026-10-06 00:00:00"

#: 键表 id（测试内固定）
KS_ITEM = 1
KS_GROUP_ITEM_ID = 2
KS_ITEM_CUST = 3
KS_ORG_CUST_ITEM = 4


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


def _seed_key_schemas(path):
    seed_row(path, "key_schemas", id=KS_ITEM, code="KS_ITEM", name="物料键",
             key_fields='["item_id"]', created_at=NOW, updated_at=NOW)
    seed_row(path, "key_schemas", id=KS_GROUP_ITEM_ID,
             code=KEY_SCHEMA_GROUP_ITEM, name="客户组×物料键",
             key_fields='["customer_group_id","item_id"]',
             created_at=NOW, updated_at=NOW)
    seed_row(path, "key_schemas", id=KS_ITEM_CUST, code="KS_ITEM_CUST",
             name="客户×物料键",
             key_fields='["customer_account_id","item_id"]',
             created_at=NOW, updated_at=NOW)
    seed_row(path, "key_schemas", id=KS_ORG_CUST_ITEM, code="KS_ORG_CUST_ITEM",
             name="组织×客户×物料键",
             key_fields='["org_id","customer_account_id","item_id"]',
             created_at=NOW, updated_at=NOW)


def _seed_procedure(path, sequence_id=1):
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


def _seed_chain(path, steps):
    """建最小可算链：键表 / 查找序列 / 价目表 / 过程 / 规则。"""
    _seed_key_schemas(path)
    seed_row(path, "lookup_sequences", id=1, code="LK_ITEM_CUST",
             name="客户优先查找序列", steps=steps,
             created_at=NOW, updated_at=NOW)
    _seed_procedure(path, sequence_id=1)
    seed_rate_table(path, code="PL_STD", name="全局标准价目表")
    seed_rule(path, code="PD_STD", rate_table_id=1)


def _seed_record(path, *, record_id, schema_id, keys, rate, priority=100,
                 scale=None, scale_semantic=None):
    values = dict(id=record_id, code=f"RC_{record_id}", rate_table_id=1,
                  key_schema_id=schema_id, keys=json.dumps(keys),
                  rate_type_id=1, rate=rate, hit_policy="exclusive",
                  priority=priority, status="active", rate_qty=1,
                  created_at=NOW, updated_at=NOW)
    if scale is not None:
        values["scale"] = json.dumps(scale)
        values["scale_semantic"] = scale_semantic
    seed_row(path, "rate_records", **values)


def _seed_customer(path, *, account_id=1, relation_id=1, group_id=10,
                   with_relation=True):
    """播种客户账户（可含/不含关系行；关系行的 group_id 可空）。"""
    if with_relation:
        seed_row(path, "party_relations", id=relation_id, party1_id=1,
                 party2_id=2, role="customer", internal_mark="external",
                 le_org_id=None, group_id=group_id, status="active")
    seed_row(path, "customer_accounts", id=account_id, relation_id=relation_id,
             name=f"客户{account_id}", created_at=NOW)


def _price(ds, qty=1, **kwargs):
    return PricingDeterminationService(ds).determine_line(
        item_id=1, qty=qty, currency="CNY", **kwargs)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "pricing_group.db"
    _build_schema(path)
    return path


@pytest.fixture()
def ds(db_path):
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    yield adapter
    adapter.disconnect()


#: 组槽在物料槽之前
GROUP_FIRST = '[{"seq":1,"key_schema_id":2},{"seq":2,"key_schema_id":1}]'


class TestCustomerGroupKey:

    # ---- a) 组价命中 -----------------------------------------------------
    def test_group_price_hits_over_item_price(self, db_path, ds):
        _seed_chain(db_path, GROUP_FIRST)
        _seed_record(db_path, record_id=1, schema_id=KS_GROUP_ITEM_ID,
                     keys={"customer_group_id": 10, "item_id": 1}, rate=90.0)
        _seed_record(db_path, record_id=2, schema_id=KS_ITEM,
                     keys={"item_id": 1}, rate=100.0)
        _seed_customer(db_path, group_id=10)

        got = _price(ds, customer_account_id=1)

        assert got["pricing_status"] == "determined"
        assert got["unit_price"] == 90.0
        assert got["trace"]["hit_ids"] == [1]

        # 无客户 → 组槽为 None 被跳过 → 物料价
        plain = _price(ds)
        assert plain["unit_price"] == 100.0

    # ---- b) 客户无组 → 回退 ------------------------------------------------
    def test_customer_without_group_falls_back(self, db_path, ds):
        _seed_chain(db_path, GROUP_FIRST)
        _seed_record(db_path, record_id=1, schema_id=KS_GROUP_ITEM_ID,
                     keys={"customer_group_id": 10, "item_id": 1}, rate=90.0)
        _seed_record(db_path, record_id=2, schema_id=KS_ITEM,
                     keys={"item_id": 1}, rate=100.0)
        _seed_customer(db_path, group_id=None)

        got = _price(ds, customer_account_id=1)

        assert got["pricing_status"] == "determined"
        assert got["unit_price"] == 100.0
        assert got["trace"]["hit_ids"] == [2]

    # ---- c) 无关系 / 无组 ------------------------------------------------
    def test_missing_relation_yields_item_price(self, db_path, ds):
        _seed_chain(db_path, GROUP_FIRST)
        _seed_record(db_path, record_id=1, schema_id=KS_GROUP_ITEM_ID,
                     keys={"customer_group_id": 10, "item_id": 1}, rate=90.0)
        _seed_record(db_path, record_id=2, schema_id=KS_ITEM,
                     keys={"item_id": 1}, rate=100.0)
        # 账户指向不存在的关系行（无 relation → JOIN 无结果）
        _seed_customer(db_path, account_id=2, relation_id=99,
                       with_relation=False)

        got = _price(ds, customer_account_id=2)

        assert got["pricing_status"] == "determined"
        assert got["unit_price"] == 100.0
        assert got["trace"]["hit_ids"] == [2]

    # ---- d) 组槽 + 组织槽叠加 --------------------------------------------
    def test_earlier_org_slot_wins_over_group_slot(self, db_path, ds):
        _seed_chain(db_path,
                    '[{"seq":1,"key_schema_id":4},{"seq":2,"key_schema_id":2},'
                    '{"seq":3,"key_schema_id":1}]')
        _seed_record(db_path, record_id=1, schema_id=KS_ORG_CUST_ITEM,
                     keys={"org_id": 1001, "customer_account_id": 1,
                           "item_id": 1}, rate=250.0)
        _seed_record(db_path, record_id=2, schema_id=KS_GROUP_ITEM_ID,
                     keys={"customer_group_id": 10, "item_id": 1}, rate=90.0)
        _seed_customer(db_path, group_id=10)

        both = _price(ds, customer_account_id=1, sales_org_id=1001)
        assert both["unit_price"] == 250.0
        assert both["trace"]["hit_ids"] == [1]

        # 无组织 → org 槽跳过 → 组价
        no_org = _price(ds, customer_account_id=1)
        assert no_org["unit_price"] == 90.0
        assert no_org["trace"]["hit_ids"] == [2]

    # ---- f) 阶梯与客户组互不干扰 -----------------------------------------
    def test_scale_and_group_do_not_interfere(self, db_path, ds):
        _seed_chain(db_path, GROUP_FIRST)
        _seed_record(db_path, record_id=1, schema_id=KS_GROUP_ITEM_ID,
                     keys={"customer_group_id": 10, "item_id": 1}, rate=0.0,
                     scale=[{"from": 0, "to": 10, "rate": 90},
                            {"from": 10, "to": 100, "rate": 80}],
                     scale_semantic="total")
        _seed_record(db_path, record_id=2, schema_id=KS_ITEM,
                     keys={"item_id": 1}, rate=100.0)
        _seed_customer(db_path, group_id=10)

        low = _price(ds, qty=5, customer_account_id=1)
        high = _price(ds, qty=50, customer_account_id=1)

        assert low["unit_price"] == 90.0
        assert low["trace"]["hit_ids"] == [1]
        assert high["unit_price"] == 80.0
        assert high["trace"]["hit_ids"] == [1]


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
    finally:
        conn.close()
    return {"factors": factors, "schemas": schemas, "steps": steps}


class TestMigrationIdempotency:

    def _seed_pre_migration(self, path):
        """按 v152 之后的库形态播种（尚无 group 因子/键表/槽位）。"""
        _seed_key_schemas(path)
        seed_row(path, "lookup_sequences", id=1, code="LK_ITEM_CUST",
                 name="客户优先查找序列",
                 steps='[{"seq":1,"key_schema_id":4},{"seq":2,"key_schema_id":3},'
                       '{"seq":3,"key_schema_id":1}]',
                 created_at=NOW, updated_at=NOW)
        _seed_procedure(path, sequence_id=1)
        seed_rate_table(path, code="PL_STD", name="全局标准价目表")
        seed_rule(path, code="PD_STD", rate_table_id=1)

    def test_two_runs_are_idempotent(self, tmp_path, capsys):
        db = tmp_path / "migrate_v153.db"
        _build_schema(db)
        self._seed_pre_migration(db)

        assert migrate(db) is True
        assert verify(db) is True
        first = _snapshot(db)

        conn = sqlite3.connect(str(db))
        try:
            group_id = conn.execute(
                "SELECT id FROM key_schemas WHERE code = ?",
                (KEY_SCHEMA_GROUP_ITEM,)).fetchone()[0]
        finally:
            conn.close()

        # org 首槽保留，group 槽插入 org 之后、客户槽之前
        assert first["steps"]["LK_ITEM_CUST"] == [
            {"seq": 1, "key_schema_id": KS_ORG_CUST_ITEM},
            {"seq": 2, "key_schema_id": group_id},
            {"seq": 3, "key_schema_id": KS_ITEM_CUST},
            {"seq": 4, "key_schema_id": KS_ITEM}]
        assert dict(first["schemas"])[KEY_SCHEMA_GROUP_ITEM] == [
            "customer_group_id", "item_id"]
        assert ("sales_order_line", "customer_group_id") in first["factors"]

        capsys.readouterr()
        assert migrate(db) is True
        second_out = capsys.readouterr().out
        assert "[FACTOR]" not in second_out
        assert "[KS]" not in second_out
        assert "[SEQ]" not in second_out
        assert verify(db) is True

        second = _snapshot(db)
        assert second == first
        seqs = [s["seq"] for s in second["steps"]["LK_ITEM_CUST"]]
        assert seqs == [1, 2, 3, 4]
        assert len(seqs) == len(set(seqs))
