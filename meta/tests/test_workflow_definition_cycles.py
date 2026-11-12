# -*- coding: utf-8 -*-
"""G1 定义期无环检测（T4b.1）— meta.core.workflow_definition._validate_cycles

覆盖目标:
  1. 三节点 / 四节点有向环 → CYCLE_DETECTED（detail 含完整环路）
  2. 合法主干链 / 分支块扇出 + 同块合并 → 零误报
  3. 自环只报 EDGE_SELF_LOOP，不重复报 CYCLE_DETECTED
  4. 两个独立环各报一次
  5. assert_definition 遇到环抛 WorkflowDefinitionError
"""

import pytest

from meta.core.workflow_definition import (
    WorkflowDefinitionError,
    assert_definition,
    validate_definition,
)

pytestmark = pytest.mark.unit


def _node(node_id, step=None, *, parent=None, group=None, executor="human"):
    node = {"node_id": node_id, "title": "节点", "executor_type": executor}
    if step is not None:
        node["step_number"] = step
    if parent is not None:
        node["parent_step_number"] = parent
    if group is not None:
        node["group_name"] = group
    return node


def _edge(src, dst, when=None):
    edge = {"from": src, "to": dst}
    if when is not None:
        edge["when"] = when
    return edge


def _codes(findings):
    return [f.code for f in findings]


def _trunk():
    return [_node("n1", 1), _node("n2", 2), _node("n3", 3)]


def test_three_node_cycle_detected():
    findings = validate_definition(
        _trunk(), [_edge("n1", "n2"), _edge("n2", "n3"), _edge("n3", "n1")])
    assert _codes(findings) == ["CYCLE_DETECTED"]
    assert "n1 → n2 → n3 → n1" in findings[0].detail


def test_four_node_cycle_detected():
    nodes = [_node("a", 1), _node("b", 2), _node("c", 3), _node("d", 4)]
    findings = validate_definition(
        nodes, [_edge("a", "b"), _edge("b", "c"), _edge("c", "d"), _edge("d", "a")])
    assert _codes(findings) == ["CYCLE_DETECTED"]
    assert "a → b → c → d → a" in findings[0].detail


def test_linear_dag_is_clean():
    findings = validate_definition(
        _trunk(), [_edge("n1", "n2"), _edge("n2", "n3")])
    assert findings == []


def test_branch_fan_out_and_same_block_merge_is_clean():
    nodes = [_node("n1", 1), _node("b1", parent=1, group="g"),
             _node("b2", parent=1, group="g"), _node("n2", 2)]
    edges = [_edge("n1", "b1"), _edge("n1", "b2"),
             _edge("b1", "n2"), _edge("b2", "n2")]
    assert validate_definition(nodes, edges) == []


def test_self_loop_reported_once_as_edge_self_loop():
    findings = validate_definition(_trunk(), [_edge("n1", "n1")])
    assert _codes(findings) == ["EDGE_SELF_LOOP"]


def test_two_independent_cycles_each_reported():
    nodes = [_node("a", 1), _node("b", 2), _node("c", 3), _node("d", 4)]
    edges = [_edge("a", "b"), _edge("b", "a"), _edge("c", "d"), _edge("d", "c")]
    findings = validate_definition(nodes, edges)
    assert _codes(findings) == ["CYCLE_DETECTED", "CYCLE_DETECTED"]
    assert "a → b → a" in findings[0].detail
    assert "c → d → c" in findings[1].detail


def test_assert_definition_raises_on_cycle():
    with pytest.raises(WorkflowDefinitionError) as exc:
        assert_definition(_trunk(), [_edge("n1", "n2"), _edge("n2", "n1")])
    assert "CYCLE_DETECTED" in str(exc.value)
