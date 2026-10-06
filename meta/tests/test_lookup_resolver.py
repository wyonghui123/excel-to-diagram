# -*- coding: utf-8 -*-
"""
查找序列引擎单测 — 定价引擎 T2-1
==================================
逐条对应 Spec TR-006 消解范式验收矩阵 + FR-004 Acceptance Criteria。

[T2 前提] 全部用内存 dict / Candidate 夹具，**不建表、不依赖 BO、不依赖 order_line**。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.lookup_resolver import (  # noqa: E402
    Candidate,
    LookupResult,
    ResolutionError,
    apply_weighted,
    lookup,
    resolve_candidates,
    RESOLUTION_BEST,
    RESOLUTION_EXCLUSIVE,
    RESOLUTION_PRECEDENCE,
    RESOLUTION_WEIGHTED,
    HIT_POLICY_ADDITIVE,
    HIT_POLICY_EXCLUSIVE,
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
