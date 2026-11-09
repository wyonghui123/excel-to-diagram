# -*- coding: utf-8 -*-
"""定价链契约测试（阶梯价闭环 / 外部价源桩）。

[TEST-EFF P2-1] 由两个同域（SO Wave3 定价，纯 tmp/in-memory SQLite）的 <=5 用例
小文件合并：
- test_external_rate_source_stub.py       (C1/M3 外部价源取数桩)
- test_sales_order_pricing_scale_chain.py (T2.1/B3 阶梯价闭环)
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
from meta.services.external_rate_source_stub import (  # noqa: E402
    ADAPTERS,
    EXTERNAL_SOURCE_UNSUPPORTED,
    ExternalRateSourceError,
    ManualOverrideAdapter,
    get_adapter,
)
from meta.services.pricing_determination_service import (  # noqa: E402
    REASON_ZERO_QTY,
    PricingDeterminationService,
)
from meta.tests.factories._pricing_w1_helpers import (  # noqa: E402
    seed_rate_table,
    seed_rule,
    seed_row,
)
from meta.tests.factories._raw_sql_bridge import insert  # noqa: E402

pytestmark = pytest.mark.unit


# ===========================================================================
# 一、外部价源取数接口桩（SO Wave3 C1/M3）
# ===========================================================================
# 依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §4 D9 / §10.11
# 测试策略:
#   · 内存 SQLite 真表（列齐全，与 YAML 字段一一对应）+ 包一层 DataSource 形状
#   · 种子行走 factories/_raw_sql_bridge（不在测试文件内联 DML）

_TABLE = 'external_rate_sources'

_SCHEMA = """
CREATE TABLE external_rate_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    source TEXT,
    quote_code TEXT,
    calendar_id INTEGER,
    fallback_rule TEXT,
    override_rate REAL,
    override_valid_from TEXT,
    override_valid_to TEXT,
    override_reason TEXT
);
"""


class _MemDS:
    """sqlite3 连接 → DataSource 形状（桩只用到 query）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    return conn


def _add_source(conn, code='LME_COPPER', rate=None, valid_from=None,
                valid_to=None, reason=None):
    insert(conn, _TABLE, code=code, name=code, source='custom',
           quote_code=None, calendar_id=None, fallback_rule=None,
           override_rate=rate, override_valid_from=valid_from,
           override_valid_to=valid_to, override_reason=reason)


def _adapter(conn, source_code=None):
    return ManualOverrideAdapter(_MemDS(conn), source_code=source_code)


def test_manual_override_hit():
    conn = _db()
    _add_source(conn, rate=88.5, valid_from='2026-10-01',
                valid_to='2026-11-30', reason='占位期人工取价')
    quote = _adapter(conn).fetch_quote('LME_COPPER', 10, 'USD', '2026-10-30')
    assert quote is not None
    assert quote['rate'] == 88.5
    assert quote['on_date'] == '2026-10-30'
    assert quote['currency'] == 'USD'
    assert quote['source'] == 'LME_COPPER'


def test_manual_override_missing_returns_none():
    conn = _db()
    _add_source(conn, rate=None, valid_from='2026-10-01',
                valid_to='2026-11-30')
    assert _adapter(conn).fetch_quote('LME_COPPER', 10, 'USD', '2026-10-30') is None


def test_manual_override_out_of_window_returns_none():
    conn = _db()
    _add_source(conn, rate=88.5, valid_from='2026-10-01',
                valid_to='2026-11-30')
    adapter = _adapter(conn)
    # 失效日之后
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-12-01') is None
    # 生效日之前
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-09-15') is None
    # 边界日（首末日均包含）
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-10-01') is not None
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-11-30') is not None


def test_manual_override_no_row_returns_none():
    conn = _db()
    _add_source(conn, code='LME_COPPER', rate=88.5)
    assert _adapter(conn).fetch_quote('PLATTS_ALUMINA', 10, 'USD', '2026-10-30') is None


def test_unknown_adapter_rejected():
    with pytest.raises(ExternalRateSourceError) as exc:
        get_adapter('platts')
    assert exc.value.code == EXTERNAL_SOURCE_UNSUPPORTED
    # 手工覆盖是本期唯一注册的适配器
    assert list(ADAPTERS) == ['manual_override']


# ===========================================================================
# 二、销售订单定价链 · 阶梯价闭环验收（SO Wave3 · T2.1 / B3）
# ===========================================================================
# 依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
#       §3.7（取价编排）/ FR-009（阶梯定档）
# 口径:
#   真建表 + 真跑 `PricingDeterminationService.determine_line` → `PricingService.price_line`，
#   不使用桩。阶梯语义取 `total`（整单取档），区间含下不含上 `[from, to)`。

#: 按 yaml 声明真建表所需的最小对象集合（含定价确定规则与阶梯取价链路）
TABLES = ["pricing_determination", "factor_catalog", "key_schema",
          "lookup_sequence", "rate_type", "exclusion_group", "rate_table",
          "rate_record", "calc_procedure", "calc_procedure_step",
          "calc_result", "calc_detail"]

#: 两档整单阶梯：0-10 每个 100；10-100 每个 90（区间含下不含上）
TIERS = [{"from": 0, "to": 10, "rate": 100.0},
         {"from": 10, "to": 100, "rate": 90.0}]

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


def _seed_chain(path, tiers=None, semantic=None):
    """种入一份最小可算的阶梯取价配置（物料键 + 单槽序列 + 过程 + 一条费率）。

    `tiers` 为空 = 不分档（回归：仍按普通费率命中）。
    """
    seed_row(path, "key_schemas", id=1, code="KEY_ITEM", name="物料键",
             key_fields='["item_id"]')
    seed_row(path, "lookup_sequences", id=1, code="SEQ_ITEM", name="物料查找序列",
             steps='[{"seq":1,"key_schema_id":1}]')
    seed_row(path, "rate_types", id=1, code="PRICE_BASE", name="基本价格",
             rate_class="price", calc_type="percent", rate_source="rate_record",
             sign="+", rounding=None, exclusion_group_id=None,
             manual_allowed=0, mandatory=0, statistical=0,
             lookup_sequence_id=1, created_at=NOW, updated_at=NOW)
    seed_rate_table(path, code="PL_STD", name="标准价目表")
    seed_row(path, "calc_procedures", id=1, code="PROC_STD", name="标准过程",
             procedure_type="pricing", result_semantic="price", currency="CNY",
             subtotal_keys='["s1"]', created_at=NOW, updated_at=NOW)
    # 步骤：先按「每单位费率 × 数量」出金额，再取整（取整不累加）
    seed_row(path, "calc_procedure_steps", calc_procedure_id=1, seq=1,
             element_type="formula", params='{"expr":"lookup_amount * base"}',
             subtotal_key="s1", created_at=NOW, updated_at=NOW)
    seed_row(path, "calc_procedure_steps", calc_procedure_id=1, seq=2,
             element_type="round", params='{"mode":"round","digits":2}',
             created_at=NOW, updated_at=NOW)
    seed_rule(path, code="PD_STD")
    seed_row(path, "rate_records", id=1, code="RC_ITEM", rate_table_id=1,
             key_schema_id=1, keys='{"item_id":1}', rate_type_id=1,
             rate=100.0, hit_policy="exclusive", priority=1, status="active",
             rate_qty=1, scale=(json.dumps(tiers) if tiers else None),
             scale_semantic=semantic, created_at=NOW, updated_at=NOW)


def _manual_tier(tiers, qty):
    """按 `[from, to)` 手工定档，返回 (from, to, rate)。"""
    for t in tiers:
        lo, hi = float(t["from"]), float(t["to"])
        if lo <= qty < hi:
            return lo, hi, float(t["rate"])
    raise AssertionError(f"数量 {qty} 不落在任何档位")


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "pricing_scale.db"
    _build_schema(path)
    return path


@pytest.fixture()
def ds(db_path):
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    yield adapter
    adapter.disconnect()


def _determine(ds, qty):
    return PricingDeterminationService(ds).determine_line(
        item_id=1, qty=qty, currency="CNY")


class TestScaleChain:

    def test_small_qty_hits_first_tier(self, db_path, ds):
        """qty=5 → 命中首档 100 → 单价 100.0，trace.scales 透出档位"""
        _seed_chain(db_path, TIERS, "total")

        out = _determine(ds, 5)

        assert out["pricing_status"] == "determined"
        assert out["unit_price"] == 100.0
        assert out["amount"] == 500.0
        scales = out["trace"]["scales"]
        assert len(scales) == 1
        scale = scales[0]
        assert scale["candidate_id"] == 1
        assert scale["semantic"] == "total"
        assert scale["qty"] == 5.0
        assert scale["rate"] == 100.0
        assert scale["tier"] == {"from": 0.0, "to": 10.0, "rate": 100.0}

    def test_large_qty_hits_second_tier(self, db_path, ds):
        """qty=50 → 命中次档 90 → 单价 90.0，档位与手工计算一致"""
        _seed_chain(db_path, TIERS, "total")

        out = _determine(ds, 50)

        assert out["unit_price"] == 90.0
        assert out["amount"] == 4500.0
        scale = out["trace"]["scales"][0]
        assert scale["tier"] == {"from": 10.0, "to": 100.0, "rate": 90.0}

    def test_boundary_qty_belongs_to_upper_tier(self, db_path, ds):
        """边界 qty=10（含下不含上）→ 命中第二档 90，与手工口径一致"""
        _seed_chain(db_path, TIERS, "total")

        out = _determine(ds, 10)
        lo, hi, rate = _manual_tier(TIERS, 10)

        assert (lo, hi) == (10.0, 100.0)
        assert rate == 90.0
        assert out["unit_price"] == rate
        assert out["amount"] == rate * 10
        assert out["trace"]["scales"][0]["tier"] == {
            "from": lo, "to": hi, "rate": rate}

    def test_no_scale_still_prices_and_scales_empty(self, db_path, ds):
        """无阶梯记录回归：仍按普通费率命中，trace.scales 为空"""
        _seed_chain(db_path)

        out = _determine(ds, 5)

        assert out["pricing_status"] == "determined"
        assert out["unit_price"] == 100.0
        assert out["amount"] == 500.0
        assert out["trace"]["scales"] == []

    def test_failed_path_exposes_empty_scales(self, db_path, ds):
        """失败路径同样保留 scales 键（与成功路径同形状，便于回放）"""
        _seed_chain(db_path, TIERS, "total")

        out = _determine(ds, 0)

        assert out["pricing_status"] == "failed"
        assert out["reason"] == REASON_ZERO_QTY
        assert out["trace"]["scales"] == []
