# -*- coding: utf-8 -*-
"""
定价编排服务端到端单测 — 定价引擎 T1-4
========================================
**真建表 + 真跑全链路**：查表(FR-004) → 算过程(FR-005/006/007) → 落结果+明细(FR-010/011)。

[关键前提] 全程**不依赖 order_line**：
  FR-011 按 §8.2.0 两步法先挂头级（document_line_id = NULL / level = header）。
  本测试据此跑通完整链路；行级挂载待 order_line 补齐后仅需填该字段。
"""
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.calc_procedure_executor import CalculationError  # noqa: E402
from meta.core.lookup_resolver import ResolutionError  # noqa: E402
from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.services.pricing_service import PricingError, PricingService  # noqa: E402
from meta.tests.factories._raw_sql_bridge import (  # noqa: E402
    delete, insert, update,
)

TABLES = ["factor_catalog", "key_schema", "lookup_sequence", "rate_type",
          "exclusion_group", "rate_table", "rate_record",
          "calc_procedure", "calc_result", "calc_detail"]


@pytest.fixture()
def ds():
    """内存 SQLite + 按 yaml 声明真实建表。"""
    logging_off = None
    import logging
    logging_off = logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(ROOT, "meta", "schemas"))
    finally:
        if logging_off is not None:
            logging.disable(logging_off)
    conn = sqlite3.connect(":memory:")
    gen = SchemaGenerator("sqlite")
    for name in TABLES:
        mo = registry.get(name)
        assert mo is not None, f"{name} 未注册"
        conn.execute(gen.generate_create_table(mo))
        for idx in gen.generate_create_index(mo):
            conn.execute(idx)
    yield conn
    conn.close()


def _seed(ds):
    """种入一份最小可算配置：键(客户) + 序列(1 槽) + 价目表(approved) + 过程 + 3 条费率。

    [两个序列分别配置 · 实施纠正]
      lookup_sequences.steps  = 查找槽位 [{seq, key_schema_id}]
      calc_procedures.steps   = 计算步骤 [{seq, element_type, ...}]
    """
    now = "2026-10-06 00:00:00"
    insert(ds, "key_schemas", id=1, code='KEY_CUST', name='客户键',
           key_fields='["customer"]', created_at=now, updated_at=now)
    insert(ds, "lookup_sequences", id=1, code='SEQ_STD', name='标准序列',
           steps='[{"seq":1,"key_schema_id":1}]', created_at=now, updated_at=now)
    insert(ds, "rate_types", id=1, code='PRICE_BASE', name='基本价格',
           rate_class='price', calc_type='percent', rate_source='rate_record',
           sign='+', rounding=None, exclusion_group_id=None, manual_allowed=0,
           mandatory=0, statistical=0, lookup_sequence_id=1,
           created_at=now, updated_at=now)
    insert(ds, "rate_tables", id=1, code='PL_STD', name='标准价目表',
           type='standard', currency='CNY', owner_org_id=None,
           status='approved', created_at=now, updated_at=now)
    # 过程：先 formula 取查表命中金额，再 round 产出展示值
    insert(ds, "calc_procedures", id=1, code='PROC_STD', name='标准过程',
           procedure_type='pricing', result_semantic='price', currency='CNY',
           steps='[{"seq":1,"element_type":"formula",'
                 '"params":{"expr":"lookup_amount"},'
                 '"subtotal_key":"s1"},'
                 '{"seq":2,"element_type":"round",'
                 '"params":{"mode":"round","digits":2}}]',
           subtotal_keys='["s1"]', created_at=now, updated_at=now)
    # 三条候选：priority 1/2/3
    for rid, prio, rate in ((1, 1, 100.0), (2, 2, 200.0), (3, 3, 300.0)):
        insert(ds, "rate_records", code=f"RC_{rid}", id=rid, rate_table_id=1,
               key_schema_id=1, keys='{"customer":1001}', rate_type_id=1,
               rate=rate, hit_policy='exclusive', priority=prio,
               status='active', created_at=now, updated_at=now)


def _price(ds, **kw):
    """便捷调用：默认带查找序列 SEQ_STD。"""
    params = dict(process_code="PROC_STD", rate_table_id=1,
                  slot_keys=[{"customer": 1001}], base=1.0,
                  sequence_code="SEQ_STD")
    params.update(kw)
    return PricingService(ds).price_line(**params)


class TestEndToEnd:
    def test_price_line_persists_result_and_details(self, ds):
        """查表 → 算过程 → 落 1 结果行 + 2 明细行"""
        _seed(ds)
        r = _price(ds, document_type="sales_order", document_id=5001)
        assert r["result_id"] is not None
        assert r["net_amount"] == 100.0          # precedence 取 priority=1
        assert r["hit_ids"] == [1]
        assert len(r["step_results"]) == 2

        n_res = ds.execute("SELECT COUNT(*) FROM calc_results").fetchone()[0]
        n_det = ds.execute("SELECT COUNT(*) FROM calc_details").fetchone()[0]
        assert (n_res, n_det) == (1, 2)

    def test_result_carries_header_level_host(self, ds):
        """FR-011：本期落头级（document_line_id 为空、level=header）"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        row = ds.execute("SELECT level, document_line_id, process_code,"
                         " result_semantic, currency FROM calc_results").fetchone()
        assert row[0] == "header"
        assert row[1] is None                    # 头级：行 ID 为空
        assert row[2] == "PROC_STD"
        assert row[3] == "price"
        assert row[4] == "CNY"

    def test_dry_run_does_not_persist(self, ds):
        """persist=False 只算不落库（预览 / defaults-preview 语义）"""
        _seed(ds)
        r = _price(ds, document_type="sales_order", document_id=5001,
                   persist=False)
        assert r["result_id"] is None
        assert r["net_amount"] == 100.0
        assert ds.execute("SELECT COUNT(*) FROM calc_results").fetchone()[0] == 0

    def test_subtotal_recorded_per_layer(self, ds):
        """FR-007 逐层小计可回放"""
        _seed(ds)
        r = _price(ds, document_type="sales_order", document_id=5001)
        assert r["subtotals"] == {"s1": 100.0}

    def test_works_without_lookup_sequence(self, ds):
        """sequence_code 留空 → 跳过查表，纯由计算步骤出结果

        （适用于费率已在单据上的情形，如销售价直接沿用）
        """
        _seed(ds)
        r = _price(ds, sequence_code=None)
        assert r["hit_ids"] == []              # 未走查表
        assert r["net_amount"] == 0.0          # lookup_amount 不存在 → formula 得 0
        assert r["result_id"] is None          # 未传宿主，不落库

    def test_unknown_sequence_raises(self, ds):
        _seed(ds)
        with pytest.raises(PricingError, match="查找序列不存在"):
            _price(ds, sequence_code="SEQ_NOPE")


class TestReplay:
    def test_explain_returns_result_with_details(self, ds):
        """IF-002：按 document_type + document_id 回放"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        assert len(ex["results"]) == 1
        res = ex["results"][0]
        assert res["net_amount"] == 100.0
        assert len(res["details"]) == 2
        assert [d["seq"] for d in res["details"]] == [1, 2]

    def test_detail_records_hit_and_skipped_candidates(self, ds):
        """FR-010：命中哪些候选、剔除了谁及原因，逐条可追

        [语义边界 · 实施实测] `skipped_candidates` 记的是
        **「因键不匹配 / 被更小 seq 槽位抢先」而跳过**的候选。
        **同槽位内**被 precedence/exclusive 取一落选**不算 skipped**——
        那是消解范式的正常结果，不是"跳过"。故本例 3 条同槽位候选中
        命中 id=1，skipped 为空是正确行为。
        """
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        d1 = ex["results"][0]["details"][0]
        assert d1["hit_ids"] == [1]
        # 同槽位内落选不记 skipped
        assert d1["skipped_candidates"] == []

    def test_detail_records_skipped_on_key_mismatch(self, ds):
        """键不匹配的候选才记入 skipped_candidates（带原因）"""
        _seed(ds)
        # 第 2 条候选的键不匹配槽位
        update(ds, "rate_records", {"id": 2}, keys='{"customer":9999}')
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        d1 = ex["results"][0]["details"][0]
        reasons = {c["candidate_id"]: c["reason"] for c in d1["skipped_candidates"]}
        assert reasons.get(2) == "not_in_slot_key"

    def test_detail_records_factor_snapshot(self, ds):
        """FR-010：记当时的因子取值（只存结果无法复现）"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        snap = ex["results"][0]["details"][0]["factor_snapshot"]
        assert snap["base"] == 1.0

    def test_detail_running_net_is_per_step(self, ds):
        """明细的 running_net_amount 是**逐步累计值**，不是恒 0"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        details = ex["results"][0]["details"]
        assert details[0]["running_net_amount"] == 100.0   # formula 累加后
        assert details[1]["running_net_amount"] == 100.0   # round 只读，净额不变

    def test_detail_amount_is_normalized_to_float(self, ds):
        """明细金额列名是 extended_amount，须被归一为数值（二次审查修正）"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        d = ex["results"][0]["details"][0]
        assert d["extended_amount"] == 100.0
        assert isinstance(d["extended_amount"], float)
        assert isinstance(d["rollup_flag"], bool)

    def test_detail_subtotal_key_and_flag(self, ds):
        """带 subtotal_key 的步骤应置 rollup_flag（报表可按小计汇总）"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        ex = PricingService(ds).explain("sales_order", 5001)
        d1 = ex["results"][0]["details"][0]
        assert d1["subtotal_key"] == "s1"
        assert d1["rollup_flag"] is True
        assert ex["results"][0]["subtotals"][0]["subtotal_key"] == "s1"

    def test_round_step_does_not_pollute_net(self, ds):
        """只读算子返回 0.0，不污染净额（与 T2-2 语义一致）"""
        _seed(ds)
        r = _price(ds)
        assert r["net_amount"] == 100.0
        assert r["step_results"][1]["amount"] == 0.0
        assert r["state"]["rounded"] == 100.0


class TestRecalc:
    """重算语义：旧结果须作废但保留审计（FR-010 / status.invalid）"""

    def test_recalc_invalidates_previous_result(self, ds):
        """同一宿主重算 -> 旧行 status=invalid，新行 active，总行数保留"""
        _seed(ds)
        svc = PricingService(ds)
        r1 = _price(ds, document_type="so", document_id=1)
        r2 = _price(ds, document_type="so", document_id=1)
        assert r1["result_id"] != r2["result_id"]

        rows = ds.execute("SELECT status, COUNT(*) FROM calc_results"
                          " GROUP BY status ORDER BY status").fetchall()
        assert rows == [("active", 1), ("invalid", 1)]
        # 旧结果仍在（可审计），但回放只认 active
        assert len(svc.explain("so", 1)["results"]) == 1

    def test_recalc_keeps_history_per_line(self, ds):
        """行级结果与头级结果互不干扰（document_line_id 区分）"""
        _seed(ds)
        svc = PricingService(ds)
        _price(ds, document_type="so", document_id=1)                       # 头级
        _price(ds, document_type="so", document_id=1,
               document_line_id=88, level="line")                            # 行级
        active = ds.execute("SELECT level, COUNT(*) FROM calc_results"
                            " WHERE status='active' GROUP BY level"
                            " ORDER BY level").fetchall()
        assert active == [("header", 1), ("line", 1)]

        ex_h = svc.explain("so", 1)
        ex_l = svc.explain("so", 1, document_line_id=88)
        assert [r["level"] for r in ex_h["results"]] == ["header", "line"]
        assert [r["level"] for r in ex_l["results"]] == ["line"]


class TestAtomicity:
    """落库原子性：结果行与明细行必须同生共死（FR-010 可回放的前提）"""

    def test_result_and_details_written_together(self, ds):
        """正常路径：1 结果行 对应 N 明细行，不留孤儿"""
        _seed(ds)
        _price(ds, document_type="so", document_id=1)
        n_r = ds.execute("SELECT COUNT(*) FROM calc_results").fetchone()[0]
        n_d = ds.execute("SELECT COUNT(*) FROM calc_details").fetchone()[0]
        assert n_r == 1
        assert n_d == 2          # 过程有两个步骤

    def test_failure_rolls_back_result_row(self, ds):
        """明细写入失败 -> 结果行一并回滚（不留孤儿结果）

        用包装类注入失败点：sqlite3.Connection.execute 是只读内置方法，
        不能 monkeypatch，故包一层代理把「写明细」那次调用变成抛错。
        """
        _seed(ds)
        svc = PricingService(ds)

        class _Flaky:
            """代理 ds：calc_details 的 INSERT 抛错，其余透传。"""

            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, params=None):
                if "INSERT " + "INTO calc_details" in str(sql):
                    raise RuntimeError("simulated detail insert failure")
                return self._inner.execute(sql, params or [])

            def __getattr__(self, name):
                return getattr(self._inner, name)

        with pytest.raises(RuntimeError, match="simulated"):
            PricingService(_Flaky(ds)).price_line(
                "PROC_STD", 1, [{"customer": 1001}], 1.0,
                sequence_code="SEQ_STD", document_type="so", document_id=1)

        # 事务回滚后：既无结果行也无明细行，更不能是"有结果无明细"
        n_r = ds.execute("SELECT COUNT(*) FROM calc_results").fetchone()[0]
        n_d = ds.execute("SELECT COUNT(*) FROM calc_details").fetchone()[0]
        assert (n_r, n_d) == (0, 0)


class TestWriteBack:
    """TBD-9 ②：结果按 result_semantic 约定写回单据字段"""

    def _mk_doc(self, ds, oid="so_doc", fields=(("id", "integer"),
                                                 ("unit_price", "float"),
                                                 ("amount", "float"))):
        """造一张最小单据表 + 注册其 meta（供 registry.get 拿字段名）"""
        from meta.core.models import MetaObject, MetaField, registry
        from meta.core.models_enums import FieldType
        cols = ", ".join(f"{n} {t}" for n, t in fields)
        ds.execute(f"CREATE TABLE IF NOT EXISTS {oid} ({cols})")
        if registry.get(oid) is None:
            mo = MetaObject(id=oid, name=oid, table_name=oid)
            for n, t in fields:
                mo.fields.append(MetaField(id=n, name=n,
                                          field_type=FieldType(t),
                                          db_column=n))
            registry.register(mo)

    def test_header_writes_amount_only(self, ds):
        """头级结果只写金额，不写单价（无行可挂）"""
        _seed(ds)
        self._mk_doc(ds)
        insert(ds, "so_doc", id=1, unit_price=None, amount=0)
        _price(ds, document_type="so_doc", document_id=1)
        r = PricingService(ds).write_back("so_doc", 1)
        assert r["written"] == {"amount": 100.0}
        assert ds.execute("SELECT amount, unit_price FROM so_doc"
                          " WHERE id=1").fetchone() == (100.0, None)

    def test_line_writes_unit_price_from_rate(self, ds):
        """行级结果写单价：优先用 calc_result.rate（= 查表命中费率）"""
        _seed(ds)
        self._mk_doc(ds)
        insert(ds, "so_doc", id=1, unit_price=None, amount=0)
        _price(ds, document_type="so_doc", document_id=1,
               document_line_id=88, level="line", base=2.0)
        r = PricingService(ds).write_back("so_doc", 1, document_line_id=88)
        # 过程是 formula("lookup_amount") -> 净额 = 命中费率 100，与 base 无关；
        # 单价取 calc_result.rate（= 命中费率），非 amount/base
        assert r["written"]["unit_price"] == 100.0
        assert r["written"]["amount"] == 100.0

    def test_rate_recorded_from_hit_candidate(self, ds):
        """calc_result.rate 落命中的费率（原实现硬编码 0）"""
        from meta.services.pricing_service import _to_num
        _seed(ds)
        self._mk_doc(ds, "so_doc6", fields=(("id", "integer"),
                                            ("unit_price", "float")))
        _price(ds, document_type="so_doc6", document_id=1,
               document_line_id=9, level="line", base=5.0)
        rate = _to_num(ds.execute("SELECT rate FROM calc_results")
                       .fetchone()[0])
        assert rate == 100.0        # priority=1 的候选

    def test_rate_derived_when_no_lookup(self, ds):
        """无查表时 rate 由 amount/base 派生"""
        from meta.services.pricing_service import _to_num
        _seed(ds)
        self._mk_doc(ds, "so_doc7", fields=(("id", "integer"),
                                            ("unit_price", "float")))
        # 用一个直接给 amount 的过程：base=4，公式产出 400 -> rate=100
        update(ds, "calc_procedures", {"code": 'PROC_STD'},
               steps='[{"seq":1,"element_type":"formula",'
                     '"params":{"expr":"base * 100"}}]')
        _price(ds, document_type="so_doc7", document_id=1,
               document_line_id=3, level="line", base=4.0,
               sequence_code=None)
        rate = _to_num(ds.execute("SELECT rate FROM calc_results")
                       .fetchone()[0])
        assert rate == 100.0

    def test_write_back_falls_back_to_candidate_field(self, ds):
        """单据无 unit_price 字段时落到候选集里的第一个（price）"""
        _seed(ds)
        self._mk_doc(ds, "so_doc2",
                     fields=(("id", "integer"), ("price", "float"),
                             ("total_amount", "float")))
        insert(ds, "so_doc2", id=1, price=None, total_amount=0)
        _price(ds, document_type="so_doc2", document_id=1)
        r = PricingService(ds).write_back("so_doc2", 1)
        assert r["written"] == {"total_amount": 100.0}

    def test_no_writable_field_reports_skip(self, ds):
        """单据只有 id 时不静默失败，明确报 skipped"""
        _seed(ds)
        self._mk_doc(ds, "so_doc3", fields=(("id", "integer"),))
        insert(ds, "so_doc3", id=1)
        _price(ds, document_type="so_doc3", document_id=1)
        r = PricingService(ds).write_back("so_doc3", 1)
        assert r["written"] == {}
        assert r["skipped"] and "金额字段" in r["skipped"][0]

    def test_only_active_result_written(self, ds):
        """只写 active；重算后旧结果（invalid）不参与写回"""
        _seed(ds)
        self._mk_doc(ds, "so_doc4",
                     fields=(("id", "integer"), ("amount", "float")))
        insert(ds, "so_doc4", id=1, amount=0)
        svc = PricingService(ds)
        _price(ds, document_type="so_doc4", document_id=1)
        # 改费率再算一次，净额变化
        update(ds, "rate_records", {"id": 1}, rate=300.0)
        _price(ds, document_type="so_doc4", document_id=1)
        r = svc.write_back("so_doc4", 1)
        assert r["written"]["amount"] == 300.0
        assert len(r["result_ids"]) == 1        # 只有一条 active

    def test_unknown_document_type_raises(self, ds):
        _seed(ds)
        with pytest.raises(PricingError, match="单据对象未注册"):
            PricingService(ds).write_back("no_such_bo", 1)

    def test_no_active_result_returns_skip(self, ds):
        _seed(ds)
        self._mk_doc(ds, "so_doc5", fields=(("id", "integer"),
                                            ("amount", "float")))
        r = PricingService(ds).write_back("so_doc5", 999)
        assert r["written"] == {}
        assert r["skipped"] == ["无 active 定价结果"]


class TestErrorHandling:
    """IF-001 Error Handling：无可用费率 / 过程未命中 → 明确原因，不静默。"""

    def test_unknown_process_raises(self, ds):
        _seed(ds)
        with pytest.raises(PricingError, match="定价过程不存在"):
            _price(ds, process_code="PROC_NOPE")

    def test_draft_rate_table_rejected(self, ds):
        """C-T0-11：仅 approved 参与取价，草稿价目表须被拒"""
        _seed(ds)
        update(ds, "rate_tables", {"id": 1}, status='draft')
        with pytest.raises(PricingError, match="未发布"):
            _price(ds)

    def test_no_matching_candidate_yields_zero(self, ds):
        """无命中 → 净额 0，不报错（可回放说明原因）"""
        _seed(ds)
        r = _price(ds, slot_keys=[{"customer": 9999}])
        assert r["net_amount"] == 0.0
        assert r["hit_ids"] == []

    def test_empty_steps_raises(self, ds):
        _seed(ds)
        update(ds, "calc_procedures", {"code": 'PROC_STD'}, steps='[]')
        with pytest.raises(PricingError, match="未定义步骤"):
            _price(ds)

    def test_unregistered_operator_raises(self, ds):
        """C5：element_type 未注册 → 报错，不静默跳过"""
        _seed(ds)
        update(ds, "calc_procedures", {"code": 'PROC_STD'},
               steps='[{"seq":1,"element_type":"no_such_op"}]')
        with pytest.raises(CalculationError, match="未注册的 element_type"):
            _price(ds)


class TestValidPeriod:
    def test_valid_on_filters_out_of_range_records(self, ds):
        """valid_on 过滤有效期（区间含下不含上）"""
        _seed(ds)
        update(ds, "rate_records", {"id": 1},
               valid_from='2026-01-01', valid_to='2026-06-01')
        r = _price(ds, valid_on="2026-03-01")
        assert r["hit_ids"] == [1]
        r2 = _price(ds, valid_on="2026-09-01")
        assert r2["hit_ids"] == [2]              # 1 已过期，落到 priority=2

    def test_no_valid_on_ignores_date_filter(self, ds):
        _seed(ds)
        update(ds, "rate_records", {"id": 1}, valid_to='2020-01-01')
        r = _price(ds)
        assert r["hit_ids"] == [1]                # 不传日期则不过滤


class TestZeroDependency:
    """本批次的核心承诺：整条链路不依赖 order_line / 主数据。"""

    def test_no_order_line_dependency_in_code(self):
        """服务层代码不引用 order_line —— 保证 FR-011 两步法可行"""
        src = open(os.path.join(ROOT, "meta", "services", "pricing_service.py"),
                   encoding="utf-8").read()
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.strip().startswith("#"))
        # 去掉 docstring 段（"""..."""）后再查
        code = code.split('"""')[0] + code.split('"""')[-1] \
            if code.count('"""') >= 2 else code
        assert "order_line" not in code

    def test_detail_does_not_redundant_currency(self, ds):
        """T1 取舍②：明细不冗余存币种（避免两份真相源）"""
        _seed(ds)
        _price(ds, document_type="sales_order", document_id=5001)
        cols = [d[1] for d in ds.execute("PRAGMA table_info(calc_details)")]
        assert "currency" not in cols

    def test_currency_taken_from_process_not_arbitrary_table(self, ds):
        """币种取过程声明值（曾误取任意价目表的币种）"""
        _seed(ds)
        insert(ds, "rate_tables", id=2, code='PL_EUR', name='欧元表',
               type='standard', currency='EUR', owner_org_id=None,
               status='approved', created_at='2026-10-06',
               updated_at='2026-10-06')
        update(ds, "calc_procedures", {"code": 'PROC_STD'}, currency='USD')
        _price(ds, document_type="sales_order", document_id=5001)
        cur = ds.execute("SELECT currency FROM calc_results").fetchone()[0]
        assert cur == "USD"


class TestFR009阶梯链路:
    """FR-009 端到端：分档费率记录走完整链路（查表 → 定档 → 算过程 → 落库 + 留痕）。

    [为何单列这一层] 内核层 `test_lookup_resolver.TestFR009阶梯` 只验
    `lookup()` / `resolve_scale`。但分档记录的 `value` 是**无意义占位（通常为 0）**
    ——若服务层仍读 `c.value`，就会把 0 当单价算出来并写回单据，
    这是一条**静默错价路径**，只有跑全链路才暴露（内核层看不见服务层的取用方式）。
    """

    # 三档：0-10 → 100；10-50 → 90；50+ → 80（顶档不封口，yaml 里就是写 `to:` 留空）
    _TIERS = ('[{"from": 0, "to": 10, "rate": 100.0}, '
              '{"from": 10, "to": 50, "rate": 90.0}, '
              '{"from": 50, "to": null, "rate": 80.0}]')

    def _seed_tiered(self, ds, semantic):
        """把标准夹具改造成「单条分档记录 + 费率×数量过程」。

        [为何改过程] 标准夹具的过程是 `formula("lookup_amount")`，直接把**费率**
        当金额。要验证 `费率 × 数量 == 金额` 的等价，过程须显式乘基数。
        """
        _seed(ds)
        update(ds, "calc_procedures", {"code": 'PROC_STD'},
               steps='[{"seq":1,"element_type":"formula",'
                     '"params":{"expr":"lookup_amount * base"}}]')
        delete(ds, "rate_records", id=[2, 3])
        # 分档记录的 rate/value 是**占位 0**：真实费率完全由命中的档位决定
        update(ds, "rate_records", {"id": 1}, scale=self._TIERS,
               scale_semantic=semantic, value=0.0, rate=0.0)

    def _stored_rate(self, ds):
        from meta.services.pricing_service import _to_num
        return _to_num(ds.execute("SELECT rate FROM calc_results").fetchone()[0])

    def test_total_tier_flows_through_full_chain(self, ds):
        """total 整单取档：base=20 落 10-50 档 → 费率 90 → 金额 90×20=1800"""
        self._seed_tiered(ds, "total")
        r = _price(ds, document_type="so", document_id=1, base=20.0)
        assert r["net_amount"] == pytest.approx(1800.0)
        # 落库的 rate 必须是**定档后费率 90**，不是占位 0
        assert self._stored_rate(ds) == pytest.approx(90.0)

    def test_incremental_tier_equivalent_rate(self, ds):
        """incremental 逐档累进：base=20 → 10×100+10×90=1900 → 等效费率 95"""
        self._seed_tiered(ds, "incremental")
        r = _price(ds, document_type="so", document_id=1, base=20.0)
        assert r["net_amount"] == pytest.approx(95.0 * 20.0)
        assert self._stored_rate(ds) == pytest.approx(95.0)

    def test_scale_trace_persisted_in_factor_snapshot(self, ds):
        """FR-010：明细须能回答"落到哪一档 / 定出什么费率"（FR-009 的可解释性）"""
        self._seed_tiered(ds, "total")
        _price(ds, document_type="so", document_id=1, base=20.0)
        ex = PricingService(ds).explain("so", 1)
        scales = ex["results"][0]["details"][0]["factor_snapshot"]["scales"]
        assert len(scales) == 1
        assert scales[0]["candidate_id"] == 1
        assert scales[0]["rate"] == pytest.approx(90.0)
        assert scales[0]["tier"] == {"from": 10.0, "to": 50.0, "rate": 90.0}

    def test_write_back_uses_tier_rate_not_placeholder(self, ds):
        """写回行单价取**定档后费率**，绝不把占位 0 写进单据（静默错价防护）"""
        from meta.core.models import MetaObject, MetaField
        from meta.core.models_enums import FieldType
        self._seed_tiered(ds, "total")
        ds.execute("CREATE TABLE IF NOT EXISTS so_tier (id integer,"
                   " unit_price float, amount float)")
        if registry.get("so_tier") is None:
            mo = MetaObject(id="so_tier", name="so_tier", table_name="so_tier")
            for n in ("id", "unit_price", "amount"):
                ft = FieldType("integer") if n == "id" else FieldType("float")
                mo.fields.append(MetaField(id=n, name=n, field_type=ft, db_column=n))
            registry.register(mo)
        insert(ds, "so_tier", id=1, unit_price=None, amount=0)
        _price(ds, document_type="so_tier", document_id=1, base=20.0,
               document_line_id=88, level="line")
        wb = PricingService(ds).write_back("so_tier", 1, document_line_id=88)
        assert wb["written"]["unit_price"] == pytest.approx(90.0)

    def test_bad_scale_json_raises_resolution_error(self, ds):
        """scale 非法 json → 抛 ResolutionError（不静默当"不分档"取占位 0）"""
        _seed(ds)
        update(ds, "rate_records", {"id": 1}, scale='{not json',
               scale_semantic='total')
        with pytest.raises(ResolutionError, match="不是合法 json"):
            _price(ds)
