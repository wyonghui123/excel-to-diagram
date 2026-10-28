# -*- coding: utf-8 -*-
"""销售订单行状态机声明测试（Spec §10 TBD-4 / §0 C3 / §4.8 INV）

依据: docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md
      §0 C3    订单行 status 原本零校验
      §4.8 INV fulfillment_status 禁止出现在 rules.state_transition 中
      §10 TBD-4 订单行 state_transition 声明（同批小改，独立验收）

验收要点:
  · 恰好 3 条 state_transition，全部作用于 status 字段
  · 合法单向边只有 open→closed / open→cancelled / closed→cancelled
  · cancelled 是终态，无出边；不声明 closed→open（重开）
  · 不得对 fulfillment_status（派生字段）声明任何状态机
  · 行状态机不复制抬头状态机（不含 draft / submitted / confirmed）
  · YAML 能被真实解析器 parse_rule 解析为 MetaStateTransition
"""

import pytest
import yaml

pytestmark = pytest.mark.unit

from pathlib import Path

from meta.core.models import MetaStateTransition, RuleTrigger, RuleType
from meta.core.yaml_loader import parse_rule

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "sales_order_line.yaml"

# 设计口径：3 条合法单向边
EXPECTED_EDGES = {
    ("open", "closed"),
    ("open", "cancelled"),
    ("closed", "cancelled"),
}

LINE_STATES = {"open", "closed", "cancelled"}


@pytest.fixture(scope="module")
def schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def state_rules(schema) -> list:
    return [r for r in (schema.get("rules") or []) if r.get("type") == "state_transition"]


# ---------------- 声明结构 ----------------

def test_rules_section_exists(schema):
    """订单行 YAML 必须声明 rules 段（C3 零校验层已补齐）"""
    assert schema.get("rules"), "sales_order_line.yaml 缺少 rules 段"


def test_exactly_three_state_transitions(state_rules):
    assert len(state_rules) == 3, f"期望 3 条 state_transition，实际 {len(state_rules)}"


def test_all_state_transitions_target_status_field(state_rules):
    for r in state_rules:
        assert r.get("state_field") == "status", f"{r['id']} 的 state_field 必须是 status"


def test_rule_ids_unique(state_rules):
    ids = [r["id"] for r in state_rules]
    assert len(ids) == len(set(ids)), f"规则 id 重复: {ids}"


def test_each_rule_has_triggers_and_ui_hints(state_rules):
    for r in state_rules:
        assert r.get("triggers") == ["before_update"], f"{r['id']} 必须以 before_update 触发"
        hints = r.get("ui_hints") or {}
        assert hints.get("label"), f"{r['id']} 缺少 ui_hints.label"
        assert hints.get("icon"), f"{r['id']} 缺少 ui_hints.icon"
        assert hints.get("confirm_message"), f"{r['id']} 缺少 ui_hints.confirm_message"


# ---------------- 转移边 ----------------

def test_transition_edges_match_design(state_rules):
    edges = {(f, r["to_state"]) for r in state_rules for f in r.get("from_states", [])}
    assert edges == EXPECTED_EDGES, f"转移边不符设计，实际 {sorted(edges)}"


def test_cancelled_is_terminal(state_rules):
    """cancelled 为终态：不得作为任何规则 from_states"""
    for r in state_rules:
        assert "cancelled" not in r.get("from_states", []), f"{r['id']} 从 cancelled 出发，违反终态约束"


def test_no_reopen_edge(state_rules):
    """closed → open（重开）本轮不声明"""
    for r in state_rules:
        if r["to_state"] == "open":
            pytest.fail(f"{r['id']} 声明了回到 open 的边，本轮不支持重开")


def test_states_belong_to_status_enum(schema, state_rules):
    """from_states / to_state 必须是 status 字段声明的枚举值"""
    status_field = next(f for f in schema["fields"] if f["id"] == "status")
    enum_values = {e["value"] for e in status_field["enum_values"]}

    assert enum_values == LINE_STATES
    for r in state_rules:
        assert r["to_state"] in enum_values, f"{r['id']} 的 to_state 不在枚举内"
        for f in r.get("from_states", []):
            assert f in enum_values, f"{r['id']} 的 from_states 含非法值 {f}"


# ---------------- 与抬头状态机隔离 ----------------

def test_line_machine_does_not_copy_header_machine(state_rules):
    """行状态极简，不复制抬头的 draft/submitted/confirmed"""
    header_only = {"draft", "submitted", "confirmed"}
    for r in state_rules:
        touched = set(r.get("from_states", [])) | {r["to_state"]}
        assert not (touched & header_only), f"{r['id']} 引入了抬头状态 {touched & header_only}"


def test_fulfillment_status_never_declared(schema, state_rules):
    """§4.8 INV：派生字段禁止纳入状态机（否则人工转移与事实回写互相覆盖）"""
    for r in state_rules:
        assert r.get("state_field") != "fulfillment_status"
        touched = set(r.get("from_states", [])) | {r["to_state"]}
        assert "fulfillment_status" not in touched
    # 全文兜底：任何 rules 条目都不得以 fulfillment_* 为状态字段
    for r in schema.get("rules") or []:
        assert not str(r.get("state_field", "")).startswith("fulfillment_")


# ---------------- 真实解析器 ----------------

def test_parse_rule_produces_meta_state_transition(state_rules):
    parsed = [parse_rule(r) for r in state_rules]

    for obj, raw in zip(parsed, state_rules):
        assert isinstance(obj, MetaStateTransition), f"{raw['id']} 未解析为 MetaStateTransition"
        assert obj.id == raw["id"]
        assert obj.state_field == "status"
        assert obj.to_state == raw["to_state"]
        assert obj.from_states == raw["from_states"]
        assert RuleTrigger.BEFORE_UPDATE in obj.triggers
        assert obj.enabled is True
        assert obj.ui_hints is not None and obj.ui_hints.label

    assert all(isinstance(obj.rule_type, RuleType) for obj in parsed)
    assert {obj.rule_type for obj in parsed} == {RuleType.STATE_TRANSITION}
