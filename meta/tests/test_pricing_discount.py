# -*- coding: utf-8 -*-
"""W2-C 行级折扣与附加费定价链测试

依据: docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md §5
      §5.3 不变量 R-DSC-1 ~ R-DSC-3

覆盖:
  · 价格步骤只装「价格类」费率类型，不会串到同键的折扣记录
  · 折扣 / 附加费按各自费率类型的查找序列独立查表，按步注入 `lookup_amount`
  · 明细按步回放：`rate_type_code` / `factor_snapshot.lookup_amount` / `hit_ids`
  · 费率类型未配查找序列时显式注入 0（不把单价当百分比）
  · 净额转负即失败（R-DSC-1），不落结果行
  · `price_trace` 汇总折扣额与附加费额

建表与播种的 DML 放在 factories 助手（`_raw_sql_bridge`），
保证本文件默认口径即运行。
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
from meta.services.pricing_determination_service import (  # noqa: E402
    REASON_NEGATIVE_AMOUNT, PricingDeterminationService,
)
from meta.services.pricing_service import PricingService  # noqa: E402
from meta.tests.factories._raw_sql_bridge import insert, update  # noqa: E402

TABLES = ["key_schema", "lookup_sequence", "rate_type", "rate_table",
          "rate_record", "calc_procedure", "calc_procedure_step",
          "calc_result", "calc_detail", "pricing_determination"]

PROCEDURE_CODE = 'PRICE_STD_DISC'

#: 费率记录 ID（种子固定，供 hit_ids 断言）
RC = {
    'item1_price': 1, 'item2_price': 2, 'item3_price': 3,
    'item1_disc': 4, 'item2_disc': 5, 'item2_sur': 6,
    'item4_price': 7, 'item4_disc': 8,
}

NOW = "2026-10-25 00:00:00"

#: 四步标准过程（与迁移 v131 同口径）
STEPS = [
    {"seq": 10, "element_type": "formula", "rate_type_id": 1,
     "params": json.dumps({"expr": "lookup_amount * base"}), "rolling": 0},
    {"seq": 15, "element_type": "formula", "rate_type_id": 2,
     "params": json.dumps(
         {"expr": "running_net_amount * (1 - lookup_amount / 100)"}),
     "rolling": 1},
    {"seq": 18, "element_type": "formula", "rate_type_id": 3,
     "params": json.dumps(
         {"expr": "running_net_amount * (1 + lookup_amount / 100)"}),
     "rolling": 1},
    {"seq": 20, "element_type": "round",
     "params": json.dumps({"mode": "round", "digits": 2}), "rolling": 0},
]


def _create_schema(conn):
    """按 yaml 声明真建表（与被测服务实际查询的列一致）。"""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(ROOT, "meta", "schemas"))
    finally:
        logging.disable(previous)
    gen = SchemaGenerator("sqlite")
    for name in TABLES:
        mo = registry.get(name)
        assert mo is not None, f"{name} 未注册"
        conn.execute(gen.generate_create_table(mo))
        for idx in gen.generate_create_index(mo):
            conn.execute(idx)
    conn.commit()


def _seed(ds):
    """种入一份含价格 / 折扣 / 附加费的最小可算配置。

    · 键表 KS_ITEM（key_fields=["item_id"]）
    · 序列 LK_ITEM_STD（价格用，挂在确定规则上）
      序列 LK_ITEM_DISC（折扣/附加费用，挂在各自费率类型上）
    · 费率类型 1 价格 / 2 折扣 / 3 附加费
    · 价目行：物料 1 单价 10 + 折扣 10%；物料 2 单价 12.5 + 折扣 5%
      + 附加费 2%；物料 3 仅单价 8（无调整项）；物料 4 单价 10 + 折扣 150%
    """
    insert(ds, "key_schemas", id=1, code='KS_ITEM', name='物料匹配键',
           key_fields=json.dumps(["item_id"]), created_at=NOW, updated_at=NOW)
    for seq_id, code, name in ((1, 'LK_ITEM_STD', '物料标准查找序列'),
                                (2, 'LK_ITEM_DISC', '物料折扣查找序列')):
        insert(ds, "lookup_sequences", id=seq_id, code=code, name=name,
               steps=json.dumps([{"seq": 1, "key_schema_id": 1}]),
               created_at=NOW, updated_at=NOW)

    rate_types = [
        (1, 'RT_LIST_PRICE', '目录单价', 'price', '+', 1, 0),
        (2, 'RT_DISC_LINE', '行级折扣', 'discount_surcharge', '-', 2, 1),
        (3, 'RT_SURCHARGE_LINE', '行级附加费', 'discount_surcharge', '+', 2, 0),
    ]
    for rt_id, code, name, cls, sign, seq_id, manual in rate_types:
        insert(ds, "rate_types", id=rt_id, code=code, name=name,
               rate_class=cls, calc_type='percent', rate_source='rate_record',
               sign=sign, rounding='round', exclusion_group_id=None,
               numeric_field=None, display_scale=None,
               manual_allowed=manual, mandatory=0, statistical=0,
               lookup_sequence_id=seq_id, created_at=NOW, updated_at=NOW)

    insert(ds, "rate_tables", id=1, code='PL_STD', name='标准价目表',
           type='standard', currency='CNY', owner_org_id=None,
           status='approved', created_at=NOW, updated_at=NOW)

    insert(ds, "calc_procedures", id=1, code=PROCEDURE_CODE, name='标准折扣过程',
           procedure_type='pricing', result_semantic='price', currency='CNY',
           subtotal_keys='[]', created_at=NOW, updated_at=NOW)
    for step in STEPS:
        insert(ds, "calc_procedure_steps", calc_procedure_id=1,
               created_at=NOW, updated_at=NOW, **step)

    records = [
        (RC['item1_price'], 1, 1, 10.0),
        (RC['item2_price'], 2, 1, 12.5),
        (RC['item3_price'], 3, 1, 8.0),
        (RC['item4_price'], 4, 1, 10.0),
        (RC['item1_disc'], 1, 2, 10.0),
        (RC['item2_disc'], 2, 2, 5.0),
        (RC['item4_disc'], 4, 2, 150.0),
        (RC['item2_sur'], 2, 3, 2.0),
    ]
    for rec_id, item_id, rate_type_id, rate in records:
        insert(ds, "rate_records", id=rec_id, code=f"RC_{rec_id}",
               rate_table_id=1, key_schema_id=1,
               keys=json.dumps({"item_id": item_id}),
               rate_type_id=rate_type_id, rate=rate, hit_policy='exclusive',
               priority=100, status='active', created_at=NOW, updated_at=NOW)


def _seed_rule(ds):
    """确定规则：默认落 PRICE_STD_DISC + LK_ITEM_STD + PL_STD。"""
    insert(ds, "pricing_determinations", code='PD_STD', name='标准规则',
           sales_org_id=None, order_type_id=None, rate_table_id=1,
           calc_procedure_id=1, lookup_sequence_id=1, currency=None,
           seq=100, valid_from=None, valid_to=None, status='active',
           created_at=NOW, updated_at=NOW)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / 'discount.db'
    conn = sqlite3.connect(str(path))
    try:
        _create_schema(conn)
        _seed(conn)
        _seed_rule(conn)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture()
def conn(db_path):
    """引擎测试用裸连接（落库走 SAVEPOINT 路径）。"""
    c = sqlite3.connect(str(db_path))
    yield c
    c.close()


@pytest.fixture()
def ds(db_path):
    """确定服务测试用数据源适配器（提供 query / 连接池）。"""
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    yield adapter
    adapter.disconnect()


def _price(conn, item_id, qty=1.0, **kw):
    params = dict(process_code=PROCEDURE_CODE, rate_table_id=1,
                  slot_keys=[{"item_id": item_id}], base=qty,
                  sequence_code='LK_ITEM_STD')
    params.update(kw)
    return PricingService(conn).price_line(**params)


def _details(conn):
    rows = conn.execute(
        "SELECT seq, element_type, rate_type_code, hit_ids, factor_snapshot"
        "  FROM calc_details ORDER BY seq ASC").fetchall()
    out = []
    for seq, element_type, rate_type_code, hit_ids, snapshot in rows:
        out.append({
            "seq": seq,
            "element_type": element_type,
            "rate_type_code": rate_type_code,
            "hit_ids": json.loads(hit_ids) if hit_ids else [],
            "snapshot": json.loads(snapshot or '{}'),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 按步独立查表（R-DSC-2）
# ─────────────────────────────────────────────────────────────────────────────

class TestStepLookupBinding:

    def test_price_step_ignores_discount_record(self, conn):
        """价格步骤只装价格类候选：物料 2 的单价是 12.5，不是折扣的 5"""
        r = _price(conn, item_id=2, qty=1.0)
        assert r['step_results'][0]['amount'] == pytest.approx(12.5)

    def test_discount_reduces_net(self, conn):
        """物料 1：单价 10 × 2 - 10% = 18"""
        r = _price(conn, item_id=1, qty=2.0)
        assert r['net_amount'] == pytest.approx(18.0)

    def test_surcharge_stacks_after_discount(self, conn):
        """物料 2：25 → 5% 折扣 23.75 → 2% 附加费 24.225（先折后加）"""
        r = _price(conn, item_id=2, qty=2.0)
        by_seq = {s['seq']: s for s in r['step_results']}
        assert by_seq[15]['amount'] == pytest.approx(23.75)
        assert by_seq[18]['amount'] == pytest.approx(24.225)
        assert r['net_amount'] == pytest.approx(24.225)

    def test_no_adjustment_records_keeps_net(self, conn):
        """物料 3 无折扣/附加费价目行：命中值为 0，净额不动"""
        r = _price(conn, item_id=3, qty=3.0)
        assert r['net_amount'] == pytest.approx(24.0)

    def test_rate_type_without_sequence_injects_zero(self, conn):
        """折扣类型未配查找序列 → 注入 0，不会把单价 12.5 当 12.5% 下浮"""
        update(conn, "rate_types", {"id": 2}, lookup_sequence_id=None)
        r = _price(conn, item_id=2, qty=2.0)
        assert r['net_amount'] == pytest.approx(25.5)   # 25 × 1.02


# ─────────────────────────────────────────────────────────────────────────────
# 明细回放（FR-010）
# ─────────────────────────────────────────────────────────────────────────────

class TestDetailReplay:

    def test_detail_carries_step_rate_type_code(self, conn):
        _price(conn, item_id=2, qty=2.0,
               document_type='sales_order', document_id=7001)
        codes = [(d['seq'], d['rate_type_code']) for d in _details(conn)]
        assert codes == [(10, 'RT_LIST_PRICE'), (15, 'RT_DISC_LINE'),
                         (18, 'RT_SURCHARGE_LINE'), (20, None)]

    def test_detail_carries_step_lookup_amount(self, conn):
        _price(conn, item_id=2, qty=2.0,
               document_type='sales_order', document_id=7002)
        amounts = {d['seq']: d['snapshot'].get('lookup_amount')
                   for d in _details(conn)}
        assert amounts[10] == pytest.approx(12.5)
        assert amounts[15] == pytest.approx(5.0)
        assert amounts[18] == pytest.approx(2.0)

    def test_detail_hit_ids_belong_to_own_rate_type(self, conn):
        """每步的命中候选只来自该步费率类型，互不串用"""
        _price(conn, item_id=2, qty=2.0,
               document_type='sales_order', document_id=7003)
        hits = {d['seq']: d['hit_ids'] for d in _details(conn)}
        assert hits[10] == [RC['item2_price']]
        assert hits[15] == [RC['item2_disc']]
        assert hits[18] == [RC['item2_sur']]


# ─────────────────────────────────────────────────────────────────────────────
# 确定服务的调整额汇总与负额拦截（R-DSC-1）
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterminationAdjustments:

    def test_trace_carries_adjustment_amounts(self, ds):
        out = PricingDeterminationService(ds).determine_line(
            item_id=2, qty=2, currency='CNY', price_date='2026-10-25')
        trace = out['trace']
        assert out['pricing_status'] == 'determined'
        assert trace['discount_amount'] == pytest.approx(1.25)
        # 0.475 按分取整（`_adjustment_amounts` 统一 round 2）
        assert trace['surcharge_amount'] == pytest.approx(0.48)

    def test_unit_price_derived_from_adjusted_net(self, ds):
        out = PricingDeterminationService(ds).determine_line(
            item_id=2, qty=2, currency='CNY', price_date='2026-10-25')
        assert out['amount'] == pytest.approx(24.225)
        assert out['unit_price'] == pytest.approx(12.11)

    def test_no_adjustment_reports_zero_amounts(self, ds):
        out = PricingDeterminationService(ds).determine_line(
            item_id=3, qty=2, currency='CNY', price_date='2026-10-25')
        assert out['trace']['discount_amount'] == 0.0
        assert out['trace']['surcharge_amount'] == 0.0

    def test_negative_net_fails_with_reason(self, ds):
        """折扣 150% 使净额转负 → 失败并不返回金额（R-DSC-1）"""
        out = PricingDeterminationService(ds).determine_line(
            item_id=4, qty=1, currency='CNY', price_date='2026-10-25')
        assert out['pricing_status'] == 'failed'
        assert out['reason'] == REASON_NEGATIVE_AMOUNT
        assert out['unit_price'] is None
        assert out['trace']['reason'] == REASON_NEGATIVE_AMOUNT

    def test_negative_net_is_not_persisted(self, ds):
        PricingDeterminationService(ds).determine_line(
            item_id=4, qty=1, currency='CNY', price_date='2026-10-25',
            document_id=9001, document_line_id=901, persist=True)
        rows = ds.query(
            "SELECT COUNT(*) AS n FROM calc_results WHERE document_id = ?",
            [9001])
        assert rows[0]['n'] == 0
