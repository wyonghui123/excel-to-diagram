# -*- coding: utf-8 -*-
"""
计算过程执行器单测 — 定价引擎 T2-2
====================================
对应 Spec FR-005（可配置计算序列 + 可插拔算子）、FR-006（计算基）、
FR-007（多层累加）、C5（步骤须带类型）、NFR-002（禁 eval）。

[T2 前提] 全部内存 dict 夹具，不建表、不依赖 BO / order_line / 主数据。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.calc_procedure_executor import (  # noqa: E402
    CalculationError,
    OPERATORS,
    execute,
    register_operator,
    registered_operators,
)


class TestC5步骤须带类型:
    """C5 / FR-005 AC：element_type 决定算子，禁止 if-else 硬编码分支。"""

    def test_all_fr005_element_types_registered(self):
        """FR-005 AC 列出的 element_type 全部有算子实现"""
        required = {
            "list_price", "tier", "attribute", "formula", "manual",
            "derived", "aggregate", "distribute", "round", "track",
            "quality_premium",
        }
        missing = required - set(registered_operators())
        # distribute 本期未单列（属 FR-012 拆分分摊，二期），故单独说明
        assert missing == {"distribute"}, f"缺失算子：{missing - {'distribute'}}"

    def test_unknown_element_type_raises(self):
        """未注册类型即报错，不静默跳过 —— 配置漏实现必须暴露"""
        with pytest.raises(CalculationError, match="未注册的 element_type"):
            execute([{"seq": 1, "element_type": "no_such_op", "params": {}}])

    def test_new_operator_registers_without_touching_engine(self):
        """C5 落地形式：新增算子 = 注册一个函数，**不改引擎代码**"""
        @register_operator("_test_custom_op")
        def _op(ctx, params):
            return 42.0

        assert "_test_custom_op" in registered_operators()
        r = execute([{"seq": 1, "element_type": "_test_custom_op", "params": {}}])
        assert r["amount"] == 42.0
        del OPERATORS["_test_custom_op"]

    def test_duplicate_registration_raises(self):
        """重复注册须报错，防静默覆盖既有算子"""
        with pytest.raises(CalculationError, match="已注册"):
            register_operator("list_price")(lambda ctx, p: 0.0)


class TestFR005序列与条件:
    """FR-005：有序计算序列 + 每步有条件地更新。"""

    def test_steps_executed_in_seq_order(self):
        """步骤按 seq 升序执行，忽略调用方顺序"""
        r = execute([
            {"seq": 2, "element_type": "track", "params": {"value": 1}},
            {"seq": 1, "element_type": "manual", "params": {"value": 10}},
        ])
        assert [s["seq"] for s in r["step_results"]] == [1, 2]

    def test_condition_false_skips_step(self):
        """condition 为假 → 跳过并记 reason"""
        r = execute([
            {"seq": 1, "element_type": "manual", "params": {"value": 10}},
            {"seq": 2, "element_type": "manual", "params": {"value": 99},
             "condition": False},
        ])
        assert r["amount"] == 10.0
        assert r["step_results"][1]["skipped"] is True
        assert r["step_results"][1]["skip_reason"] == "condition_false"


class TestFR007多层累加:
    """FR-007：基价 → 折扣 → 附加费 → 税 → 运费，逐层小计。"""

    def test_steps_accumulate_additively(self):
        """步骤间默认 additive（不累加就算不出净价）"""
        r = execute([
            {"seq": 1, "element_type": "list_price",
             "params": {"rate": 100}, "subtotal_key": "base"},
            {"seq": 2, "element_type": "list_price", "params": {"rate": -20}},
            {"seq": 3, "element_type": "list_price", "params": {"rate": 13}},
        ], base=1.0)
        assert r["amount"] == 93.0
        assert r["subtotals"]["base"] == 100.0

    def test_each_layer_subtotal_recorded(self):
        """逐层小计可回放（对标 Oracle Request Viewer / SF Waterfall）"""
        r = execute([
            {"seq": 1, "element_type": "list_price", "params": {"rate": 100},
             "subtotal_key": "s1_base"},
            {"seq": 2, "element_type": "list_price", "params": {"rate": -10},
             "subtotal_key": "s2_after_discount"},
            {"seq": 3, "element_type": "list_price", "params": {"rate": 5},
             "subtotal_key": "s3_net"},
        ], base=1.0)
        assert r["subtotals"] == {
            "s1_base": 100.0, "s2_after_discount": 90.0, "s3_net": 95.0,
        }
    def test_rolling_overwrites_instead_of_accumulating(self):
        """rolling=true → 净额被覆盖为当前值（对标 Oracle Running Net Price）

        [注] rolling 是**步骤级控制项**，写在步骤顶层而非 params 内。
        """
        r = execute([
            {"seq": 1, "element_type": "list_price", "params": {"rate": 100}},
            {"seq": 2, "element_type": "list_price", "params": {"rate": 30},
             "rolling": True},
        ], base=1.0)
        assert r["amount"] == 30.0


class TestFR006计算基:
    """FR-006：计算基四维度 + 互斥校验。"""

    def test_rolling_and_base_step_mutually_exclusive(self):
        """rolling=true 与 base_step 互斥（FR-006 AC）

        [注] rolling / base_step 是**步骤级控制项**，写在步骤顶层。
        """
        with pytest.raises(CalculationError, match="互斥"):
            execute([{"seq": 1, "element_type": "list_price",
                      "params": {"rate": 1}, "rolling": True, "base_step": "s1"}])

    def test_base_quantity_drives_amount(self):
        """base × rate = 金额（默认 pricing_quantity 语义）"""
        r = execute([{"seq": 1, "element_type": "list_price",
                      "params": {"rate": 10}}], base=3.0)
        assert r["amount"] == 30.0

    def test_activity_quantity_base_same_engine(self):
        """FR-006 跨域可复用：换 base_source 即可算活动量，**无需改引擎**"""
        r = execute([{"seq": 1, "element_type": "list_price",
                      "params": {"rate": 0.5}}], base=200.0)   # 200 度电 × 0.5
        assert r["amount"] == 100.0


class TestTier阶梯:
    """阶梯两语义（FR-005 / T0-7 `scale_semantic`）。"""

    def test_total_semantic_picks_tier_by_total_qty(self):
        """整单取档：总量落在哪档就取哪档的费率"""
        r = execute([{"seq": 1, "element_type": "tier", "params": {
            "tiers": [{"from": 0, "to": 100, "rate": 10},
                      {"from": 100, "to": 200, "rate": 8}],
            "quantity": 150, "semantic": "total",
        }}], base=1.0)
        assert r["amount"] == pytest.approx(8 * 150)

    def test_incremental_semantic_sums_segments(self):
        """逐档累进：分段计算后累加"""
        r = execute([{"seq": 1, "element_type": "tier", "params": {
            "tiers": [{"from": 0, "to": 100, "rate": 10},
                      {"from": 100, "to": 200, "rate": 8}],
            "quantity": 150, "semantic": "incremental",
        }}], base=1.0)
        assert r["amount"] == pytest.approx(100 * 10 + 50 * 8)

    def test_no_tiers_returns_zero(self):
        r = execute([{"seq": 1, "element_type": "tier", "params": {}}], base=1.0)
        assert r["amount"] == 0.0


class TestFormula安全:
    """NFR-002：禁 eval，仅白名单 AST。"""

    def test_formula_with_state_variables(self):
        r = execute([
            {"seq": 1, "element_type": "list_price", "params": {"rate": 100}},
            {"seq": 2, "element_type": "formula",
             "params": {"expr": "list_price * 0.9"}},
        ], base=1.0)
        assert r["amount"] == pytest.approx(190.0)

    def test_formula_rejects_illegal_characters(self):
        with pytest.raises(CalculationError, match="非法字符"):
            execute([{"seq": 1, "element_type": "formula",
                      "params": {"expr": "__import__('os').system('x')"}}])

    def test_formula_rejects_variable_not_in_whitelist(self):
        with pytest.raises(CalculationError, match="不在白名单"):
            execute([{"seq": 1, "element_type": "formula",
                      "params": {"expr": "some_var * 2"}}])

    def test_formula_rejects_non_arithmetic_syntax(self):
        """非四则语法（三元表达式）→ 拒绝

        [实测] 该表达式在字符白名单内（只有数字与关键字），故走到 AST 白名单
        分支，报"不支持的语法节点：IfExp"——**两道防线都生效**。
        """
        with pytest.raises(CalculationError, match="不支持的语法节点"):
            execute([{"seq": 1, "element_type": "formula",
                      "params": {"expr": "1 if 2 else 3"}}])

    def test_formula_division_by_zero_raises(self):
        with pytest.raises(CalculationError, match="除零"):
            execute([{"seq": 1, "element_type": "formula",
                      "params": {"expr": "base / 0"}}])


class TestRound取整:
    """取整算子：不在净额上累积误差。"""

    @pytest.mark.parametrize("mode,expected", [
        ("round", 93.0),   # 92.5 → 93（ROUND_HALF_UP）
        ("ceil", 93.0),
        ("floor", 92.0),
        ("none", 92.5),
    ])
    def test_rounding_modes(self, mode, expected):
        r = execute([{"seq": 1, "element_type": "round",
                      "params": {"value": 92.5, "mode": mode}}])
        assert r["state"]["rounded"] == pytest.approx(expected)

    def test_round_does_not_change_running_net(self):
        """取整产出展示值，**不污染净额**（避免逐步取整累积误差）"""
        r = execute([
            {"seq": 1, "element_type": "manual", "params": {"value": 92.5}},
            {"seq": 2, "element_type": "round", "params": {"mode": "round"}},
        ])
        assert r["state"]["rounded"] == 93.0
        assert r["amount"] == 92.5      # 净额仍是 92.5（round 返回 0.0，不累加）


class TestAggregate与Derived:
    def test_aggregate_over_multiple_sources(self):
        """aggregate 汇总多个来源（只读，不改净额）"""
        r = execute([
            {"seq": 1, "element_type": "manual", "params": {"value": 1}},
            {"seq": 2, "element_type": "manual", "params": {"value": 2}},
            {"seq": 3, "element_type": "manual", "params": {"value": 3}},
            {"seq": 4, "element_type": "aggregate",
             "params": {"op": "sum", "sources": ["manual"]}},
        ])
        # manual 每次覆盖 state['manual']，故只有最后一个 3
        assert r["state"]["aggregate"] == 3.0
        assert r["amount"] == 6.0        # 三次 manual 累加，aggregate 不参与

    @pytest.mark.parametrize("op,expected", [("sum", 6.0), ("avg", 2.0)])
    def test_aggregate_ops(self, op, expected):
        r = execute([
            {"seq": 1, "element_type": "track",
             "params": {"value": 1, "label": "a"}},
            {"seq": 2, "element_type": "track",
             "params": {"value": 2, "label": "b"}},
            {"seq": 3, "element_type": "track",
             "params": {"value": 3, "label": "c"}},
            {"seq": 4, "element_type": "aggregate",
             "params": {"op": op, "sources": ["a", "b", "c"]}},
        ])
        assert r["state"]["aggregate"] == pytest.approx(expected)

    def test_aggregate_over_running_net(self):
        """对已累加净额做聚合（只读，不改净额）

        [时机] aggregate 在**累加之后**执行，故读到的是"含本步"的净额 80.0。
        max/min 作用于**单个当前值**时无意义 —— 单值聚合等价于取该值。
        多值聚合请用 sources（见 test_aggregate_ops）。
        """
        r = execute([
            {"seq": 1, "element_type": "list_price", "params": {"rate": 100}},
            {"seq": 2, "element_type": "list_price", "params": {"rate": -20}},
            {"seq": 3, "element_type": "aggregate",
             "params": {"op": "max", "source": "running_net_amount"}},
        ], base=1.0)
        assert r["state"]["aggregate"] == pytest.approx(80.0)   # 100 + (-20)
        assert r["amount"] == 80.0                               # aggregate 不改净额

    def test_aggregate_missing_source_raises(self):
        with pytest.raises(CalculationError, match="源不存在"):
            execute([{"seq": 1, "element_type": "aggregate",
                      "params": {"op": "sum", "source": "nope"}}])

    def test_derived_references_prior_step(self):
        r = execute([
            {"seq": 1, "element_type": "manual", "params": {"value": 7}},
            {"seq": 2, "element_type": "derived", "params": {"source": "manual"}},
        ])
        assert r["state"]["derived"] == 7.0
        assert r["amount"] == 7.0        # derived 只读，不重复累加


class Test回放:
    def test_step_results_are_jsonable(self):
        import json
        r = execute([{"seq": 1, "element_type": "list_price",
                      "params": {"rate": 100}}], base=2.0)
        json.dumps(r["step_results"])          # 不抛异常即通过
        assert r["step_results"][0]["amount"] == 200.0

    def test_initial_state_visible_to_operators(self):
        """查表结果（FR-004 输出）可作为 initial_state 喂给 FR-005"""
        r = execute([{"seq": 1, "element_type": "list_price",
                      "params": {"rate": 5}}],
                    base=1.0, initial_state={"from_lookup": 999})
        assert r["state"]["from_lookup"] == 999
        assert r["amount"] == 5.0

    def test_empty_steps_returns_zero(self):
        r = execute([], base=10.0)
        assert r["amount"] == 0.0
        assert r["step_results"] == []
