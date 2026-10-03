# -*- coding: utf-8 -*-
"""后端测试套件 - [C2] 编排定义层结构校验

测试 meta.core.workflow_definition 模块（纯函数，无 DB / Flask）

覆盖目标（对齐 §12 C2 / 综合缝合 §1 / Oracle STEP_NUMBER 对位）:
  1. 主干: step_number 显式编号、唯一、为正
  2. 单亲: parent_step_number 引用存在、不得自指
  3. 分支块: 同块挂载点一致、块内节点必须声明挂载点
  4. **非通用 DAG（机器断言）**: 跨分支块合并被拒（MULTI_PARENT_NOT_ALLOWED），
     同块内合并允许 —— 这是本节的存在理由（否则只是文档口号）
  5. 边: 端点存在、when 白名单、无自环、无重复
  6. 视图助手: main_trunk / branch_blocks / incoming_edges / parent_of
"""

import pytest

from meta.core.workflow_definition import (
    DEFAULT_WHEN,
    TRUNK_PARENT,
    WHEN_VALUES,
    DefinitionFinding,
    DefinitionReport,
    WorkflowDefinitionError,
    assert_definition,
    branch_blocks,
    incoming_edges,
    main_trunk,
    node_index,
    parent_of,
    validate_definition,
)

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# 构造助手
# ─────────────────────────────────────────────────────────────────────────────

def _node(node_id, step=None, *, parent=None, group=None,
          title="节点", executor="human", **extra):
    node = {"node_id": node_id, "title": title, "executor_type": executor}
    if step is not None:
        node["step_number"] = step
    if parent is not None:
        node["parent_step_number"] = parent
    if group is not None:
        node["group_name"] = group
    node.update(extra)
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


# ─────────────────────────────────────────────────────────────────────────────
# 合法定义
# ─────────────────────────────────────────────────────────────────────────────

class TestValidDefinitions:

    def test_linear_trunk_ok(self):
        """TC-WFD-001: 线性主干（n1→n2→n3）合法"""
        assert validate_definition(_trunk(), [_edge("n1", "n2"), _edge("n2", "n3")]) == []

    def test_nodes_only_ok(self):
        """TC-WFD-002: 无 edges 时仅校验节点结构"""
        assert validate_definition(_trunk()) == []

    def test_branch_block_ok(self):
        """TC-WFD-003: 分支块（同组同挂载点）合法"""
        nodes = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g"),
            _node("a2", 3, parent=1, group="g"),
        ]
        assert validate_definition(nodes, [_edge("n1", "a1"), _edge("n1", "a2")]) == []

    def test_same_branch_merge_allowed(self):
        """TC-WFD-004: 同分支块内合并（a1→j, a2→j）合法 —— 非通用 DAG 的允许面"""
        nodes = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g"),
            _node("a2", 3, parent=1, group="g"),
            _node("j", 4, parent=1, group="g"),
        ]
        edges = [_edge("n1", "a1"), _edge("n1", "a2"),
                 _edge("a1", "j"), _edge("a2", "j")]
        assert validate_definition(nodes, edges) == []

    def test_assert_definition_returns_node_count(self):
        """TC-WFD-005: assert_definition 通过返回节点数"""
        assert assert_definition(_trunk(), []) == 3

    def test_when_whitelist_values(self):
        """TC-WFD-006: when 白名单口径固定（与 deps[].when 同源）"""
        assert WHEN_VALUES == ("done", "failed", "skipped", "done_or_skipped")
        assert DEFAULT_WHEN == "done"

    def test_all_when_values_accepted(self):
        """TC-WFD-007: when 白名单内每个值均被接受"""
        nodes = _trunk()
        for when in WHEN_VALUES:
            assert validate_definition(nodes, [_edge("n1", "n2", when)]) == []


# ─────────────────────────────────────────────────────────────────────────────
# 节点结构 findings
# ─────────────────────────────────────────────────────────────────────────────

class TestNodeFindings:

    def test_nodes_not_list(self):
        """TC-WFD-010: nodes 非数组"""
        assert _codes(validate_definition("nope")) == ["NODES_NOT_LIST"]

    def test_nodes_empty(self):
        """TC-WFD-011: nodes 为空"""
        assert _codes(validate_definition([])) == ["NODES_EMPTY"]

    def test_node_not_object(self):
        """TC-WFD-012: 节点非对象"""
        findings = validate_definition([_node("n1", 1), "bad"])
        assert "NODE_NOT_OBJECT" in _codes(findings)

    def test_node_id_missing(self):
        """TC-WFD-013: 缺 node_id"""
        findings = validate_definition([{"title": "t", "executor_type": "human",
                                         "step_number": 1}])
        assert _codes(findings) == ["NODE_ID_MISSING"]

    def test_node_id_duplicate(self):
        """TC-WFD-014: node_id 重复"""
        findings = validate_definition([_node("n1", 1), _node("n1", 2)])
        assert _codes(findings) == ["NODE_ID_DUPLICATE"]

    def test_required_key_missing(self):
        """TC-WFD-015: 必填键（title / executor_type）缺失"""
        findings = validate_definition([_node("n1", 1, title="")])
        assert _codes(findings) == ["NODE_KEY_MISSING"]

    def test_trunk_requires_step_number(self):
        """TC-WFD-016: 主干节点必须显式提供 step_number"""
        findings = validate_definition([_node("n1")])
        assert _codes(findings) == ["STEP_NUMBER_INVALID"]

    def test_step_number_must_be_positive(self):
        """TC-WFD-017: step_number 必须 ≥1"""
        findings = validate_definition([_node("n1", 0)])
        assert _codes(findings) == ["STEP_NUMBER_INVALID"]

    def test_step_number_duplicate(self):
        """TC-WFD-018: step_number 重复"""
        findings = validate_definition([_node("n1", 1), _node("n2", 1)])
        assert _codes(findings) == ["STEP_NUMBER_DUPLICATE"]

    def test_parent_self_reference(self):
        """TC-WFD-019: parent_step_number 指向自身"""
        findings = validate_definition([_node("n1", 2, parent=2, group="g")])
        assert _codes(findings) == ["PARENT_SELF_REFERENCE"]

    def test_group_requires_parent(self):
        """TC-WFD-020: 分支块节点必须声明挂载点"""
        findings = validate_definition([_node("n1", 2, group="g")])
        assert _codes(findings) == ["GROUP_PARENT_REQUIRED"]

    def test_parent_not_found(self):
        """TC-WFD-021: parent_step_number 不在主干节点中"""
        findings = validate_definition([_node("n1", 2, parent=9, group="g")])
        assert _codes(findings) == ["PARENT_NOT_FOUND"]

    def test_group_mount_conflict(self):
        """TC-WFD-022: 同组挂载点不一致"""
        nodes = [
            _node("n1", 1), _node("n2", 2),
            _node("a1", 3, parent=1, group="g"),
            _node("a2", 4, parent=2, group="g"),
        ]
        assert _codes(validate_definition(nodes)) == ["GROUP_MOUNT_CONFLICT"]


# ─────────────────────────────────────────────────────────────────────────────
# 边 findings
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeFindings:

    def test_edge_not_object(self):
        """TC-WFD-030: 边非对象"""
        assert "EDGE_NOT_OBJECT" in _codes(validate_definition(_trunk(), ["x"]))

    def test_edge_endpoint_missing(self):
        """TC-WFD-031: 边缺端点"""
        findings = validate_definition(_trunk(), [{"from": "n1"}])
        assert _codes(findings) == ["EDGE_ENDPOINT_MISSING"]

    def test_edge_node_unknown(self):
        """TC-WFD-032: 边端点不是已知 node_id"""
        findings = validate_definition(_trunk(), [_edge("n1", "n9")])
        assert _codes(findings) == ["EDGE_NODE_UNKNOWN"]

    def test_edge_when_invalid(self):
        """TC-WFD-033: when 不在白名单内"""
        findings = validate_definition(_trunk(), [_edge("n1", "n2", "bogus")])
        assert _codes(findings) == ["EDGE_WHEN_INVALID"]

    def test_edge_self_loop(self):
        """TC-WFD-034: 边自环"""
        findings = validate_definition(_trunk(), [_edge("n1", "n1")])
        assert _codes(findings) == ["EDGE_SELF_LOOP"]

    def test_edge_duplicate(self):
        """TC-WFD-035: 重复边"""
        findings = validate_definition(_trunk(), [_edge("n1", "n2"), _edge("n1", "n2")])
        assert _codes(findings) == ["EDGE_DUPLICATE"]


# ─────────────────────────────────────────────────────────────────────────────
# 非通用 DAG 断言（核心）
# ─────────────────────────────────────────────────────────────────────────────

class TestNonDagAssertion:
    """『非通用 DAG』必须可机器判定，不能只是文档口号。"""

    def test_cross_branch_merge_rejected(self):
        """TC-WFD-040: 跨分支块合并被拒（g1 的 a1 与 g2 的 b1 同时汇入 j）"""
        nodes = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g1"),
            _node("b1", 3, parent=1, group="g2"),
            _node("j", 4, parent=1, group="g1"),
        ]
        findings = validate_definition(nodes, [_edge("a1", "j"), _edge("b1", "j")])
        assert _codes(findings) == ["MULTI_PARENT_NOT_ALLOWED"]

    def test_trunk_multi_parent_rejected(self):
        """TC-WFD-041: 两个主干节点汇入同一节点也被拒（n:1 合并非本模型语义）"""
        findings = validate_definition(
            _trunk(), [_edge("n1", "n3"), _edge("n2", "n3")])
        assert _codes(findings) == ["MULTI_PARENT_NOT_ALLOWED"]

    def test_same_branch_multi_parent_allowed(self):
        """TC-WFD-042: 同分支块内多入边允许（对照 TC-WFD-004）"""
        nodes = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g"),
            _node("a2", 3, parent=1, group="g"),
            _node("j", 4, parent=1, group="g"),
        ]
        findings = validate_definition(nodes, [_edge("a1", "j"), _edge("a2", "j")])
        assert findings == []

    def test_assert_definition_raises_with_findings(self):
        """TC-WFD-043: 断言失败抛错并携带全部 findings"""
        nodes = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g1"),
            _node("b1", 3, parent=1, group="g2"),
            _node("j", 4, parent=1, group="g1"),
        ]
        with pytest.raises(WorkflowDefinitionError) as exc:
            assert_definition(nodes, [_edge("a1", "j"), _edge("b1", "j")])
        assert [f.code for f in exc.value.findings] == ["MULTI_PARENT_NOT_ALLOWED"]


# ─────────────────────────────────────────────────────────────────────────────
# 视图助手
# ─────────────────────────────────────────────────────────────────────────────

class TestViews:

    def test_parent_of_normalizes(self):
        """TC-WFD-050: parent_of 归一（空/0/非法 → 主干 0；字符串数字 → int）"""
        assert parent_of({}) == TRUNK_PARENT
        assert parent_of({"parent_step_number": ""}) == TRUNK_PARENT
        assert parent_of({"parent_step_number": 0}) == TRUNK_PARENT
        assert parent_of({"parent_step_number": "abc"}) == TRUNK_PARENT
        assert parent_of({"parent_step_number": "3"}) == 3
        assert parent_of({"parent_step_number": 3}) == 3

    def test_main_trunk_sorted(self):
        """TC-WFD-051: main_trunk 仅取无父节点并按 step_number 升序"""
        nodes = [_node("n3", 3), _node("n1", 1), _node("a", 2, parent=1, group="g")]
        assert [n["node_id"] for n in main_trunk(nodes)] == ["n1", "n3"]

    def test_branch_blocks_grouping(self):
        """TC-WFD-052: branch_blocks 按 group_name 归集"""
        nodes = [_node("a1", 2, parent=1, group="g"), _node("b1", 3, parent=1, group="h")]
        assert branch_blocks(nodes) == {"g": ["a1"], "h": ["b1"]}

    def test_incoming_edges_default_when_and_grouping(self):
        """TC-WFD-053: incoming_edges 按目标归并，when 缺省补 done"""
        nodes = _trunk()
        result = incoming_edges(nodes, [_edge("n1", "n2"), _edge("n2", "n3", "skipped")])
        assert result["n1"] == []
        assert result["n2"] == [{"from": "n1", "when": "done"}]
        assert result["n3"] == [{"from": "n2", "when": "skipped"}]

    def test_node_index(self):
        """TC-WFD-054: node_index 由 node_id 建索引"""
        index = node_index(_trunk())
        assert set(index) == {"n1", "n2", "n3"}
        assert index["n2"]["step_number"] == 2

    def test_report_shape(self):
        """TC-WFD-055: DefinitionReport OK 判定与序列化"""
        assert DefinitionReport().ok is True
        report = DefinitionReport([DefinitionFinding("X", "细节")])
        assert report.ok is False
        assert report.codes() == ["X"]
        assert report.to_dict() == {"ok": False,
                                    "findings": [{"code": "X", "detail": "细节"}]}
