# -*- coding: utf-8 -*-
"""
查找序列引擎单测 — 定价引擎 T2-1
==================================
逐条对应 Spec TR-006 消解范式验收矩阵 + FR-004 Acceptance Criteria。

[T2 前提] 全部用内存 dict / Candidate 夹具，**不建表、不依赖 BO、不依赖 order_line**。
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.lookup_resolver import (  # noqa: E402
    Candidate,
    LookupResult,
    ResolutionError,
    apply_weighted,
    lookup,
    resolve_candidates,
    resolve_scale,
    RESOLUTION_BEST,
    RESOLUTION_EXCLUSIVE,
    RESOLUTION_PRECEDENCE,
    RESOLUTION_WEIGHTED,
    HIT_POLICY_ADDITIVE,
    HIT_POLICY_EXCLUSIVE,
    SCALE_INCREMENTAL,
    SCALE_TOTAL,
    SKIP_HIT_BY_EARLIER,
    SKIP_NOT_IN_GROUP,
)


# --------------------------------------------------------------------------
# TR-006 夹具：3 条同键费率记录，rate = 100 / 200 / 300
# --------------------------------------------------------------------------
def _tr006_candidates():
    return [
        Candidate(id=1, priority=1, value=100.0, key_schema_id=1,
                  keys={"customer": 1001}),
        Candidate(id=2, priority=2, value=200.0, key_schema_id=1,
                  keys={"customer": 1001}),
        Candidate(id=3, priority=3, value=300.0, key_schema_id=1,
                  keys={"customer": 1001}),
    ]


class TestTR006消解范式验收矩阵:
    """TR-006：同一份候选数据下，四种范式各跑一次，结果须与预期一致且互不干扰。"""

    def test_precedence_priority_1_2_3_hits_100(self):
        """优先级 precedence：priority 1/2/3 → 命中 priority 1 → 100"""
        r = resolve_candidates(_tr006_candidates(), RESOLUTION_PRECEDENCE)
        assert len(r) == 1
        assert r[0].id == 1
        assert r[0].value == 100.0

    def test_best_min_amount_hits_100(self):
        """取优 best（最低净价）：显式开启 + 度量 → 命中 100"""
        r = resolve_candidates(_tr006_candidates(), RESOLUTION_BEST, measure="min_amount")
        assert len(r) == 1
        assert r[0].value == 100.0

    def test_exclusive_keeps_single_winner(self):
        """互斥 exclusive：同组 → 只保留获胜者"""
        r = resolve_candidates(_tr006_candidates(), RESOLUTION_EXCLUSIVE)
        assert len(r) == 1

    def test_weighted_05_03_02_equals_170(self):
        """权重分配 weighted：权重 0.5/0.3/0.2
        → 100×.5 + 200×.3 + 300×.2 = 50 + 60 + 60 = 170

        [口径修正 2026-10-06] Spec TR-006 原文写"= 140"，是**算术错误**
        （50+60+60=170，非 140）。此处按正确数学断言。
        """
        cands = [
            Candidate(id=1, priority=1, value=100.0, allocation_weight=0.5),
            Candidate(id=2, priority=2, value=200.0, allocation_weight=0.3),
            Candidate(id=3, priority=3, value=300.0, allocation_weight=0.2),
        ]
        r = resolve_candidates(cands, RESOLUTION_WEIGHTED)
        assert len(r) == 3                      # 多候选全部参与，不取一
        assert apply_weighted(r, 1.0) == pytest.approx(170.0)

    def test_weight_not_normalized_rejected(self):
        """权重和不归一 → 拒绝计算并报错（不静默缩放）"""
        cands = [
            Candidate(id=1, value=100.0, allocation_weight=0.5),
            Candidate(id=2, value=200.0, allocation_weight=0.3),
        ]
        with pytest.raises(ResolutionError, match="权重和须归一"):
            resolve_candidates(cands, RESOLUTION_WEIGHTED)
        with pytest.raises(ResolutionError, match="权重和须归一"):
            apply_weighted(cands, 1.0)

    def test_weighted_with_null_weight_is_error(self):
        """weighted 组内不可混用空权重候选（FR-008 AC）"""
        cands = [
            Candidate(id=1, value=100.0, allocation_weight=0.5),
            Candidate(id=2, value=200.0, allocation_weight=None),
        ]
        with pytest.raises(ResolutionError, match="不可混用"):
            resolve_candidates(cands, RESOLUTION_WEIGHTED)


class TestFR004确定性:
    """FR-004 AC：同 priority 须有确定 tie-break，禁止不确定顺序。"""

    def test_same_priority_tiebreak_by_id(self):
        """同 priority → 按 id 升序，**不依赖输入顺序**"""
        a = Candidate(id=2, priority=1, value=200.0)
        b = Candidate(id=1, priority=1, value=100.0)
        r1 = resolve_candidates([a, b], RESOLUTION_PRECEDENCE)
        r2 = resolve_candidates([b, a], RESOLUTION_PRECEDENCE)
        assert r1[0].id == r2[0].id == 1          # 两次输入顺序不同，结果相同

    def test_priority_then_id_ordering(self):
        """排序键 = (priority asc, id asc)"""
        cands = [
            Candidate(id=9, priority=2, value=999.0),
            Candidate(id=5, priority=1, value=111.0),
            Candidate(id=7, priority=1, value=777.0),
        ]
        r = resolve_candidates(cands, RESOLUTION_PRECEDENCE)
        assert r[0].id == 5                        # priority 1 优先
        assert r[0].value == 111.0


class TestFR004命中策略:
    """FR-004：命中策略下沉到 rate_record.hit_policy（C-T0-4）。"""

    def test_default_hit_policy_is_exclusive(self):
        """缺省 = exclusive（与 v1.5 行为一致，TR-001 零迁移）"""
        c = Candidate(id=1, value=100.0)
        assert c.hit_policy == HIT_POLICY_EXCLUSIVE

    def test_exclusive_stops_later_slots(self):
        """命中即停：后续槽位候选全部标记 hit_by_earlier_slot"""
        cands = [
            Candidate(id=1, key_schema_id=1, keys={"customer": 1001}, value=100.0,
                      hit_policy=HIT_POLICY_EXCLUSIVE),
            Candidate(id=2, key_schema_id=2, keys={"material": "M1"}, value=50.0),
        ]
        r = lookup(
            candidates=cands,
            steps=[{"seq": 1, "key_schema_id": 1}, {"seq": 2, "key_schema_id": 2}],
            slot_keys=[{"customer": 1001}, {"material": "M1"}],
        )
        assert r.amount == 100.0
        assert r.hit_ids == [1]
        # 第 2 槽的候选被标记为被抢先
        later = [t for t in r.traces if t.slot_seq == 2][0]
        assert (2, SKIP_HIT_BY_EARLIER) in later.skipped

    def test_additive_continues_and_accumulates(self):
        """命中继续累加：additive 时后续槽位照常查、金额叠加"""
        cands = [
            Candidate(id=1, key_schema_id=1, keys={"customer": 1001}, value=100.0,
                      hit_policy=HIT_POLICY_ADDITIVE),
            Candidate(id=2, key_schema_id=2, keys={"material": "M1"}, value=30.0),
        ]
        r = lookup(
            candidates=cands,
            steps=[{"seq": 1, "key_schema_id": 1}, {"seq": 2, "key_schema_id": 2}],
            slot_keys=[{"customer": 1001}, {"material": "M1"}],
        )
        assert r.amount == 130.0                   # 100 + 30（槽位间 additive，D2）
        assert r.hit_ids == [1, 2]

    def test_default_no_match_returns_zero(self):
        """无命中 → amount 0，hit=False"""
        cands = [Candidate(id=1, key_schema_id=1, keys={"customer": 9999}, value=100.0)]
        r = lookup(cands, [{"seq": 1, "key_schema_id": 1}], [{"customer": 1001}])
        assert r.amount == 0.0
        assert r.hit is False


class TestFR004槽位与回放:
    """FR-004 AC：命中后可回答"命中哪一行 / 为什么其它行被跳过"。"""

    def test_steps_sorted_by_seq_regardless_of_input_order(self):
        """槽位按 seq 升序，忽略调用方给的顺序

        [构造说明] 两个候选均为 exclusive（第 1 槽命中即停），故金额只有 10.0。
        本例验证的是**槽位处理顺序**正确（trace seq 为 [1,2]），不是金额累加；
        槽位间 additive 的验证见 test_additive_continues_and_accumulates。
        """
        cands = [
            Candidate(id=1, key_schema_id=1, keys={"customer": 1001}, value=10.0),
            Candidate(id=2, key_schema_id=2, keys={"material": "M1"}, value=20.0),
        ]
        r = lookup(
            cands,
            steps=[{"seq": 2, "key_schema_id": 2}, {"seq": 1, "key_schema_id": 1}],
            slot_keys=[{"material": "M1"}, {"customer": 1001}],
        )
        assert [t.slot_seq for t in r.traces] == [1, 2]
        assert r.hit_ids == [1]                   # 第 1 槽（seq=1）先处理并命中即停

    def test_trace_records_skip_reason(self):
        """未命中候选带跳过原因"""
        cands = [
            Candidate(id=1, key_schema_id=1, keys={"customer": 1001}, value=10.0),
            Candidate(id=2, key_schema_id=1, keys={"customer": 9999}, value=20.0),
        ]
        r = lookup(cands, [{"seq": 1, "key_schema_id": 1}], [{"customer": 1001}])
        t = r.traces[0]
        assert t.hit_ids == [1]
        assert (2, SKIP_NOT_IN_GROUP) in t.skipped

    def test_inactive_record_skipped(self):
        """停用记录不参与查找"""
        cands = [
            Candidate(id=1, key_schema_id=1, keys={"customer": 1001}, value=10.0,
                      inactive=True),
            Candidate(id=2, key_schema_id=1, keys={"customer": 1001}, value=20.0),
        ]
        r = lookup(cands, [{"seq": 1, "key_schema_id": 1}], [{"customer": 1001}])
        assert r.hit_ids == [2]
        assert (1, "record_inactive") in r.traces[0].skipped

    def test_result_to_dict_is_jsonable(self):
        """回放结构可序列化（供 FR-010 calc_detail 消费）"""
        import json
        cands = [Candidate(id=1, key_schema_id=1, keys={"customer": 1001}, value=10.0)]
        r = lookup(cands, [{"seq": 1, "key_schema_id": 1}], [{"customer": 1001}])
        json.dumps(r.to_dict())          # 不抛异常即通过
        assert r.to_dict()["hit_ids"] == [1]


class TestFR008度量显式化:
    """FR-008 AC：Best Price 绝不隐式默认。"""

    def test_best_without_measure_raises(self):
        with pytest.raises(ResolutionError, match="必须显式定义度量"):
            resolve_candidates(_tr006_candidates(), RESOLUTION_BEST)

    def test_best_max_amount(self):
        r = resolve_candidates(_tr006_candidates(), RESOLUTION_BEST, measure="max_amount")
        assert r[0].value == 300.0

    def test_unknown_resolution_raises(self):
        with pytest.raises(ResolutionError, match="未知的消解范式"):
            resolve_candidates(_tr006_candidates(), "random_way")

    def test_unknown_measure_raises(self):
        with pytest.raises(ResolutionError, match="未知的度量"):
            resolve_candidates(_tr006_candidates(), RESOLUTION_BEST, measure="whatever")


class TestCandidate构造:
    """Candidate.from_dict 的缺省值须与 T0 表声明一致。"""

    def test_from_dict_defaults_match_table_defaults(self):
        c = Candidate.from_dict({"id": 7, "value": 9.0})
        assert c.priority == 100          # rate_record.priority default=100
        assert c.hit_policy == "exclusive"  # hit_policy default=exclusive
        assert c.allocation_weight is None  # 可空
        assert c.inactive is False

    def test_from_dict_status_inactive(self):
        """rate_record.status=inactive 应映射为 inactive=True"""
        c = Candidate.from_dict({"id": 1, "value": 1.0, "status": "inactive"})
        assert c.inactive is True

    def test_from_dict_keeps_raw(self):
        """原始 dict 保留，便于回放时取未建模字段"""
        src = {"id": 1, "value": 1.0, "extra": "x"}
        assert Candidate.from_dict(src).raw is src


# --------------------------------------------------------------------------
# FR-009 阶梯：档位表 0-10 / 10-50 / 50-∞（费率 100 / 90 / 80）
# --------------------------------------------------------------------------
_TIERS = [
    {"from": 0, "to": 10, "rate": 100.0},
    {"from": 10, "to": 50, "rate": 90.0},
    {"from": 50, "to": None, "rate": 80.0},
]


def _tiered(semantic, tiers=None, value=0.0, **kw):
    return Candidate(id=1, value=value, key_schema_id=1,
                     keys={"customer": 1001},
                     scale=list(tiers if tiers is not None else _TIERS),
                     scale_semantic=semantic, **kw)


class TestFR009阶梯:
    """FR-009 AC：至少两种语义 —— 整单取档（total）/ 逐档累进（incremental）。"""

    def test_total_picks_tier_rate(self):
        """整单取档：qty=20 落在 [10,50) → 费率 90（金额 = 90 × 20 = 1800）"""
        sc = resolve_scale(_tiered(SCALE_TOTAL), 20)
        assert sc["rate"] == 90.0
        assert sc["tier"] == {"from": 10, "to": 50, "rate": 90.0}

    def test_total_top_tier_is_open_ended(self):
        """顶档 `to` 缺省 = 不封口：qty=999 落到 [50, ∞) → 80"""
        sc = resolve_scale(_tiered(SCALE_TOTAL), 999)
        assert sc["rate"] == 80.0
        assert sc["tier"]["to"] is None

    def test_incremental_equivalent_rate(self):
        """逐档累进：qty=20 → 10×100 + 10×90 = 1900 → 等效费率 95"""
        sc = resolve_scale(_tiered(SCALE_INCREMENTAL), 20)
        assert sc["rate"] == pytest.approx(95.0)
        assert sc["tier"] is None          # 累进无单一命中档

    def test_zero_qty_yields_zero_rate(self):
        """qty=0 → 金额必为 0，不因"档位未覆盖 0"误报配置错误（头级调用常见）"""
        assert resolve_scale(_tiered(SCALE_TOTAL), 0)["rate"] == 0.0
        assert resolve_scale(_tiered(SCALE_INCREMENTAL), 0)["rate"] == 0.0

    def test_negative_qty_yields_zero_rate(self):
        """负数量同 0 处理（二次审查补）。

        [为何要这条] 原实现只判 `q == 0`，负数量会落入档位匹配：`total` 找不到
        覆盖负值的档位 → **抛错**；而 `_op_tier` 对同一输入**静默返 0** —— 两条
        路径分叉。退货/红字应由 `calc_result.sign` 表达，不在阶梯算子内取负。
        """
        assert resolve_scale(_tiered(SCALE_TOTAL), -5)["rate"] == 0.0
        assert resolve_scale(_tiered(SCALE_INCREMENTAL), -5)["rate"] == 0.0

    def test_empty_semantic_means_disabled(self):
        """scale 有值但 scale_semantic 为空 = 阶梯不启用（表声明）→ 取 value"""
        c = _tiered(None, value=7.0)
        assert resolve_scale(c, 20)["rate"] == 7.0

    def test_no_scale_returns_value(self):
        """未分档记录：费率 = value（与 FR-009 之前行为一致）"""
        assert resolve_scale(Candidate(id=1, value=7.0), 20)["rate"] == 7.0

    def test_unknown_semantic_raises(self):
        with pytest.raises(ResolutionError, match="未知的阶梯语义"):
            resolve_scale(_tiered("graduated"), 20)

    def test_missing_qty_raises(self):
        """声明了阶梯却拿不到数量 → 无从定档，拒绝计算"""
        with pytest.raises(ResolutionError, match="未提供阶梯基数"):
            resolve_scale(_tiered(SCALE_TOTAL), None)

    def test_qty_in_gap_raises(self):
        """档位有空隙 → 拒绝计算并报错（不静默取 0）"""
        gapped = [{"from": 0, "to": 10, "rate": 100.0},
                  {"from": 50, "to": 60, "rate": 80.0}]
        with pytest.raises(ResolutionError, match="不落在"):
            resolve_scale(_tiered(SCALE_TOTAL, tiers=gapped), 20)

    def test_from_dict_parses_scale_json(self):
        """scale 是 json 列，须反序列化（否则下游会把 json 文本当档位数组遍历）"""
        c = Candidate.from_dict({"id": 1, "value": 0.0,
                                 "scale": json.dumps(_TIERS),
                                 "scale_semantic": "total",
                                 "scale_divisor": "quantity"})
        assert c.scale[1]["rate"] == 90.0
        assert c.scale_semantic == "total"
        assert c.scale_divisor == "quantity"

    def test_from_dict_bad_scale_json_raises(self):
        """scale 解析失败必须报错 —— 静默当"不分档"会**静默算错价**
        （与 `keys` 解析失败不同：后者只是匹配不上，保守且不会算错）"""
        with pytest.raises(ResolutionError, match="不是合法 json"):
            Candidate.from_dict({"id": 1, "value": 0.0, "scale": "{not json"})

    @pytest.mark.parametrize("bad", ['{"from": 0, "to": 10, "rate": 100}',
                                     "[1, 2, 3]",
                                     "123",
                                     '"text"'])
    def test_from_dict_scale_wrong_shape_raises(self, bad):
        """shape 不对也要报错（二次审查补）。

        [为何要这条] 原实现只查 `isinstance(scale, list)` 再赋 `[]` ——
        **json 合法但形状不对**（对象 / 元素非 dict）会被静默降级为"不分档"，
        与畸形 json 同样会取占位 `value` 静默算错价。
        """
        with pytest.raises(ResolutionError, match="档位对象数组"):
            Candidate.from_dict({"id": 1, "value": 0.0, "scale": bad,
                                 "scale_semantic": "total"})

    def test_from_dict_empty_scale_is_legal(self):
        """`scale` 缺省 / 空串 / 空数组 = 不分档，**不算配置错误**"""
        for empty in (None, "", "[]"):
            c = Candidate.from_dict({"id": 1, "value": 7.0, "scale": empty})
            assert c.scale == []

    def test_best_on_tiered_record_raises(self):
        """best 范式不可用于分档记录（二次审查补）。

        [为何要这条] `best` 按 `c.value` 比优，而分档记录的 `value` 是**占位值**
        （真实费率由档位定）——拿它比优 = 比一串占位值，**静默选出错误记录**。
        正确的比优须按定档后费率（需数量），本期未实现，故显式拒绝。
        """
        with pytest.raises(ResolutionError, match="best 范式不可用于分档"):
            resolve_candidates([_tiered(SCALE_TOTAL)],
                               RESOLUTION_BEST, measure="min_amount")

    def test_lookup_applies_scale_and_records_trace(self):
        """端到端：amount = 定档后费率（不是占位的 value=0），且回放留痕"""
        r = lookup(
            candidates=[_tiered(SCALE_TOTAL)],
            steps=[{"seq": 1, "key_schema_id": 1}],
            slot_keys=[{"customer": 1001}],
            scale_qty=20,
        )
        assert r.amount == 90.0            # 若仍读 c.value 则为 0 → 静默错价
        assert r.rates[1] == 90.0
        assert r.traces[0].scales[0]["tier"]["from"] == 10

    def test_lookup_without_scale_qty_raises(self):
        """命中分档记录但不给基数 → 报错，不静默按 value 算"""
        with pytest.raises(ResolutionError, match="未提供阶梯基数"):
            lookup(
                candidates=[_tiered(SCALE_TOTAL)],
                steps=[{"seq": 1, "key_schema_id": 1}],
                slot_keys=[{"customer": 1001}],
            )

    def test_scale_applies_inside_weighted_branch(self):
        """加权 + 阶梯：权重乘的是**定档后费率**（不是占位 value）"""
        a = _tiered(SCALE_TOTAL, allocation_weight=0.5)
        b = Candidate(id=2, priority=2, value=200.0, key_schema_id=1,
                      keys={"customer": 1001}, allocation_weight=0.5)
        r = lookup(
            candidates=[a, b],
            steps=[{"seq": 1, "key_schema_id": 1}],
            slot_keys=[{"customer": 1001}],
            resolution=RESOLUTION_WEIGHTED,
            scale_qty=20,
        )
        # 90×0.5 + 200×0.5 = 145（若漏传 rates 则为 0×0.5 + 200×0.5 = 100）
        assert r.amount == pytest.approx(145.0)


class TestScaleParity:
    """FR-009 的两个语义在**两条路径**上必须同义，否则同一份配置换个写法就换了价：
    查找序列 `resolve_scale`（返费率） vs 计算过程内联 `tier` 算子（返金额）。

    判据：`费率 × 数量 == 算子金额`。任一侧改动导致分叉，本用例立即失败。
    """

    @pytest.mark.parametrize("qty", [-10, -1, 0, 1, 9, 10, 20, 49, 50, 999])
    @pytest.mark.parametrize("semantic", [SCALE_TOTAL, SCALE_INCREMENTAL])
    def test_rate_times_qty_equals_inline_tier_amount(self, semantic, qty):
        from meta.core.calc_procedure_executor import OPERATORS, StepContext

        rate = resolve_scale(_tiered(semantic), qty)["rate"]
        ctx = StepContext(state={}, base=float(qty))
        amount = OPERATORS["tier"](ctx, {"tiers": list(_TIERS), "semantic": semantic})
        assert rate * qty == pytest.approx(amount)


# ============================================================================
# 【FR-009 收口 · 2026-10-07】rate_qty（"每 10 个"）折算
# ============================================================================
class TestRateQty折算:
    """`rate_record.rate_qty` = 定价数量（如"每 10 个"填 10）。

    [缺陷背景] 该字段此前**全仓零消费** —— `rate` 被当成"每个的单价"直接
    × base。实测：`rate=100 / rate_qty=10 / base=100` 得**10000**，
    而业务期望 1000（`100/10 × 100`）→ **静默 10 倍超收**，无异常无告警。
    引擎契约是「金额 = **每单位**费率 × 数量」，故须折算成每 1 个的单价。

    [落点] 折算收敛在 `resolve_scale`（所有费率出口的唯一收口），避免
    服务层二次除法；`_op_tier` 处理的是**过程内联档位**（无 rate_qty 概念），
    故 `TestScaleParity` 的 `rate × qty == amount` 判据在 `rate_qty=1`
    （默认）下仍成立，见 `test_parity_holds_when_rate_qty_is_one`。
    """

    def test_per_unit_rate_divides_by_rate_qty(self):
        assert Candidate(id=1, value=100.0, rate_qty=10).per_unit_rate() == 10.0

    def test_per_unit_rate_defaults_to_identity(self):
        """未声明 rate_qty（默认 1）→ 折算为恒等，存量行为不变"""
        assert Candidate(id=1, value=100.0).per_unit_rate() == 100.0

    @pytest.mark.parametrize("bad", [0, -5])
    def test_non_positive_rate_qty_falls_back_to_one(self, bad):
        """0 / 负数属配置矛盾，本期兜底为 1 而非抛错。

        [取舍] 抛错会让存量脏数据**阻断整张价目表**取价，风险高于"按 1 处理"。
        """
        assert Candidate(id=1, value=100.0,
                         rate_qty=bad).per_unit_rate() == 100.0

    def test_from_dict_reads_textual_rate_qty(self):
        """sqlite 的 number 列读回可能是文本 / NULL，须统一（与 `_num` 同口径）"""
        assert Candidate.from_dict(
            {"id": 1, "rate": 100, "rate_qty": "10"}
        ).per_unit_rate() == 10.0
        assert Candidate.from_dict(
            {"id": 2, "rate": 100, "rate_qty": None}
        ).per_unit_rate() == 100.0

    def test_explicit_rate_argument_is_normalized(self):
        """`per_unit_rate(rate)` 传入档位费率时同样折算（阶梯路径依赖此形）"""
        c = Candidate(id=1, value=999.0, rate_qty=10)
        assert c.per_unit_rate(100.0) == 10.0

    def test_no_scale_record_is_normalized(self):
        """不分档路径：rate_qty=10 → 每单位 10（此前得 100，10 倍超收）"""
        c = Candidate(id=1, value=100.0, rate_qty=10)
        assert resolve_scale(c, 100)["rate"] == 10.0

    @pytest.mark.parametrize("semantic", [SCALE_TOTAL, SCALE_INCREMENTAL])
    def test_tier_path_is_normalized(self, semantic):
        """阶梯两语义一并折算 —— 否则「每 10 个 + 阶梯」留下第二处超收口子。

        qty=50 时两语义各自的未折算费率（`_TIERS` = [0,10)100 / [10,50)90 /
        [50,∞)80）：
          - total       = 命中 [50,∞) 档 → 80
          - incremental = (10×100 + 40×90) ÷ 50 = 4600 ÷ 50 = 92
        `rate_qty=10` 后两者都应 ÷10（未折算则金额为 4600 / 9200，10 倍超收）。
        """
        sc = resolve_scale(_tiered(semantic, rate_qty=10), 50)
        assert sc["rate"] == pytest.approx({SCALE_TOTAL: 8.0,
                                            SCALE_INCREMENTAL: 9.2}[semantic])
        # 与不声明 rate_qty 的同档结果严格成 1/10 —— 直接锁定"折算只做一次"
        base = resolve_scale(_tiered(semantic), 50)["rate"]
        assert sc["rate"] * 10 == pytest.approx(base)

    def test_tier_trace_records_normalized_rate(self):
        """留痕的 `tier.rate` 记折算后值，使 FR-010 回放能直接用它复算"""
        sc = resolve_scale(_tiered(SCALE_TOTAL, rate_qty=10), 20)
        assert sc["tier"]["rate"] == 9.0     # 命中档 90 / 10

    def test_lookup_amount_uses_normalized_rate(self):
        """端到端：`LookupResult.rates` / `amount` 均为每单位费率"""
        r = lookup(
            candidates=[Candidate(id=1, value=100.0, rate_qty=10,
                                  key_schema_id=1, keys={"customer": 1001})],
            steps=[{"seq": 1, "key_schema_id": 1}],
            slot_keys=[{"customer": 1001}],
        )
        assert r.rates[1] == 10.0
        assert r.amount == pytest.approx(10.0)

    def test_parity_holds_when_rate_qty_is_one(self):
        """默认 `rate_qty=1` 下与内联 `tier` 算子仍同义（守护 TestScaleParity
        的前提未被本次改动破坏）"""
        from meta.core.calc_procedure_executor import OPERATORS, StepContext

        rate = resolve_scale(_tiered(SCALE_TOTAL), 20)["rate"]
        ctx = StepContext(state={}, base=20.0)
        amount = OPERATORS["tier"](
            ctx, {"tiers": list(_TIERS), "semantic": SCALE_TOTAL})
        assert rate * 20 == pytest.approx(amount)
