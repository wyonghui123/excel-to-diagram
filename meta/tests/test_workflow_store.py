# -*- coding: utf-8 -*-
"""后端测试套件 - [C1] 编排定义层存储（版本化发布 / 读取）

测试 meta.core.workflow_store 模块

覆盖目标（对齐 §12 C1 / §7.4 Workflow 模型）:
  1. 版本化发布: v1 → v2 递增，版本号由 store 分配（调用方不传）
  2. **只增不改**: 旧版本行保持原样（在途 Run 快照不受影响的前提）
  3. 幂等发布: 内容逐字段等价 → 返回既有版本、published=False、不产生空版本行
  4. 定义期闸门: 非法定义（C2 findings）不落任何版本行
  5. 读取: 版本序列 / 指定版本 / 完整定义（含节点与边）/ 节点排序
  6. 默认值落库: type/priority/assign_policy/claim_timeout_seconds

注: 本文件不含 raw 写 SQL —— 全走 public API，可被 conftest raw-SQL 门控放行。
"""

import json

import pytest

from meta.core.workflow_definition import WorkflowDefinitionError
from meta.core.workflow_store import (
    TRIGGER_KINDS,
    WorkflowStoreError,
    get_nodes,
    get_workflow,
    latest_version,
    list_latest_workflows,
    list_versions,
    load_definition,
    publish_workflow,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库：仅需定义层两表（workflows / task_templates）。"""
    from meta.core.datasource import get_data_source
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "c1_store.db"))
    with source.transaction():
        ensure_task_tables(source)
    yield source


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


def _trunk_v1():
    return [_node("n1", 1, title="受理"), _node("n2", 2, title="审批")]


def _nodes_by_id(nodes):
    return {n["node_id"]: n for n in nodes}


# ─────────────────────────────────────────────────────────────────────────────
# 发布
# ─────────────────────────────────────────────────────────────────────────────

class TestPublish:

    def test_first_publish_is_v1(self, ds):
        """TC-WFS-001: 首次发布为 v1，published=True，节点数正确"""
        result = publish_workflow(ds, workflow_key="wf-a", name="流程A",
                                  nodes=_trunk_v1())
        assert result["version"] == 1
        assert result["published"] is True
        assert result["node_count"] == 2
        assert result["workflow_key"] == "wf-a"
        assert result["workflow_id"]

    def test_second_changed_publish_bumps_version(self, ds):
        """TC-WFS-002: 内容变更 → v2，旧版本仍存在"""
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1())
        changed = [_node("n1", 1, title="受理改"), _node("n2", 2, title="审批")]
        result = publish_workflow(ds, workflow_key="wf-a", name="流程A",
                                  nodes=changed)
        assert result["version"] == 2
        assert result["published"] is True
        assert [v["version"] for v in list_versions(ds, "wf-a")] == [1, 2]

    def test_old_version_row_untouched(self, ds):
        """TC-WFS-003: 只增不改 —— v1 行与 v1 节点内容在发布 v2 后逐字段不变"""
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1())
        v1 = get_workflow(ds, "wf-a", 1)
        v1_nodes = _nodes_by_id(get_nodes(ds, v1["id"], 1))

        publish_workflow(ds, workflow_key="wf-a", name="流程A改名",
                         nodes=[_node("n1", 1, title="受理改"), _node("n2", 2)])

        assert get_workflow(ds, "wf-a", 1)["name"] == "流程A"
        assert _nodes_by_id(get_nodes(ds, v1["id"], 1))["n1"]["title"] == "受理"

    def test_idempotent_publish_same_content(self, ds):
        """TC-WFS-004: 内容等价 → published=False，不新增版本行"""
        first = publish_workflow(ds, workflow_key="wf-a", name="流程A",
                                 nodes=_trunk_v1())
        again = publish_workflow(ds, workflow_key="wf-a", name="流程A",
                                 nodes=_trunk_v1())
        assert again["published"] is False
        assert again["version"] == first["version"]
        assert again["workflow_id"] == first["workflow_id"]
        assert latest_version(ds, "wf-a") == 1
        assert len(list_versions(ds, "wf-a")) == 1

    def test_idempotent_when_only_edges_change(self, ds):
        """TC-WFS-005: 节点相同但边不同 → 视为新版本（边属内容）"""
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1(),
                         edges=[])
        result = publish_workflow(ds, workflow_key="wf-a", name="流程A",
                                  nodes=_trunk_v1(),
                                  edges=[{"from": "n1", "to": "n2"}])
        assert result["version"] == 2
        assert result["published"] is True

    def test_invalid_definition_rejected_without_version_row(self, ds):
        """TC-WFS-006: 跨分支块合并（非法定义）→ 抛错且不落版本行"""
        illegal = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g1"),
            _node("b1", 3, parent=1, group="g2"),
            _node("j", 4, parent=1, group="g1"),
        ]
        edges = [{"from": "a1", "to": "j"}, {"from": "b1", "to": "j"}]
        with pytest.raises(WorkflowDefinitionError) as exc:
            publish_workflow(ds, workflow_key="wf-a", name="流程A",
                             nodes=illegal, edges=edges)
        assert [f.code for f in exc.value.findings] == ["MULTI_PARENT_NOT_ALLOWED"]
        assert latest_version(ds, "wf-a") == 0

    def test_blank_key_rejected(self, ds):
        """TC-WFS-007: workflow_key 为空 → WorkflowStoreError"""
        with pytest.raises(WorkflowStoreError):
            publish_workflow(ds, workflow_key="  ", name="流程A", nodes=_trunk_v1())

    def test_blank_name_rejected(self, ds):
        """TC-WFS-008: name 为空 → WorkflowStoreError"""
        with pytest.raises(WorkflowStoreError):
            publish_workflow(ds, workflow_key="wf-a", name="", nodes=_trunk_v1())

    def test_bad_trigger_kind_rejected(self, ds):
        """TC-WFS-009: trigger_kind 不在值域 → WorkflowStoreError"""
        assert TRIGGER_KINDS == ("manual", "schedule", "event", "api")
        with pytest.raises(WorkflowStoreError):
            publish_workflow(ds, workflow_key="wf-a", name="流程A",
                             nodes=_trunk_v1(), trigger_kind="bogus")

    def test_all_trigger_kinds_accepted(self, ds):
        """TC-WFS-010: 值域内每种 trigger_kind 均可发布（event 需合法 trigger_expr）"""
        exprs = {"event": json.dumps({"event": "outbound_completed"})}
        for kind in TRIGGER_KINDS:
            result = publish_workflow(ds, workflow_key=f"wf-{kind}",
                                      name=f"流程{kind}", nodes=_trunk_v1(),
                                      trigger_kind=kind, trigger_expr=exprs.get(kind, ""))
            assert result["published"] is True

    def test_event_trigger_without_expr_rejected(self, ds):
        """TC-WFS-011: kind=event 缺 trigger_expr → 定义期拒绝且不落版本行"""
        with pytest.raises(WorkflowDefinitionError) as exc:
            publish_workflow(ds, workflow_key="wf-e", name="流程E",
                             nodes=_trunk_v1(), trigger_kind="event")
        assert exc.value.findings[0].code == "TRIGGER_EXPR_MISSING"
        assert latest_version(ds, "wf-e") == 0

    def test_event_trigger_bad_json_rejected(self, ds):
        """TC-WFS-012: kind=event 的 trigger_expr 非 JSON / 缺 event 名 → 拒绝"""
        with pytest.raises(WorkflowDefinitionError) as exc:
            publish_workflow(ds, workflow_key="wf-e", name="流程E",
                             nodes=_trunk_v1(), trigger_kind="event",
                             trigger_expr="not-json")
        assert exc.value.findings[0].code == "TRIGGER_EXPR_NOT_JSON"

        with pytest.raises(WorkflowDefinitionError) as exc2:
            publish_workflow(ds, workflow_key="wf-e", name="流程E",
                             nodes=_trunk_v1(), trigger_kind="event",
                             trigger_expr=json.dumps({"when": "x == 1"}))
        assert exc2.value.findings[0].code == "TRIGGER_EVENT_NAME_MISSING"
        assert latest_version(ds, "wf-e") == 0

    def test_event_trigger_bad_condition_rejected(self, ds):
        """TC-WFS-013: when 含非白名单表达式 → 定义期拒绝（不发明表达式语言）"""
        with pytest.raises(WorkflowDefinitionError) as exc:
            publish_workflow(ds, workflow_key="wf-e", name="流程E",
                             nodes=_trunk_v1(), trigger_kind="event",
                             trigger_expr=json.dumps(
                                 {"event": "e", "when": "__import__('os')"}))
        assert exc.value.findings[0].code == "TRIGGER_WHEN_INVALID"

    def test_non_event_kind_needs_no_expr(self, ds):
        """TC-WFS-014: manual / api / schedule 不要求 trigger_expr"""
        for kind in ("manual", "api", "schedule"):
            result = publish_workflow(ds, workflow_key=f"wf-{kind}",
                                      name=f"流程{kind}", nodes=_trunk_v1(),
                                      trigger_kind=kind)
            assert result["published"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 读取
# ─────────────────────────────────────────────────────────────────────────────

class TestRead:

    def test_latest_version_zero_when_absent(self, ds):
        """TC-WFS-020: 未发布的 key → latest_version=0，get_workflow=None"""
        assert latest_version(ds, "nope") == 0
        assert get_workflow(ds, "nope") is None

    def test_get_workflow_defaults_to_latest(self, ds):
        """TC-WFS-021: version=None 取最新版"""
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1())
        publish_workflow(ds, workflow_key="wf-a", name="流程A改名",
                         nodes=[_node("n1", 1, title="改")])
        assert get_workflow(ds, "wf-a")["version"] == 2
        assert get_workflow(ds, "wf-a")["name"] == "流程A改名"

    def test_nodes_sorted_by_step_number(self, ds):
        """TC-WFS-022: get_nodes 按 step_number 升序返回"""
        nodes = [_node("n3", 3), _node("n1", 1), _node("n2", 2)]
        result = publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=nodes)
        ordered = get_nodes(ds, result["workflow_id"], result["version"])
        assert [n["node_id"] for n in ordered] == ["n1", "n2", "n3"]

    def test_branch_node_fields_persisted(self, ds):
        """TC-WFS-023: 分支块节点的 parent_step_number / group_name 正确落库"""
        nodes = [
            _node("n1", 1),
            _node("a1", 2, parent=1, group="g"),
        ]
        result = publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=nodes)
        stored = _nodes_by_id(get_nodes(ds, result["workflow_id"], result["version"]))
        assert stored["a1"]["parent_step_number"] == 1
        assert stored["a1"]["group_name"] == "g"
        assert stored["n1"]["parent_step_number"] is None
        assert stored["n1"]["group_name"] is None

    def test_node_defaults_applied(self, ds):
        """TC-WFS-024: 未声明字段落库为默认值"""
        result = publish_workflow(ds, workflow_key="wf-a", name="流程A",
                                  nodes=[_node("n1", 1)])
        stored = _nodes_by_id(get_nodes(ds, result["workflow_id"], result["version"]))
        node = stored["n1"]
        assert node["type"] == "story"
        assert node["priority"] == "P2"
        assert node["assign_policy"] == "direct"
        assert node["claim_timeout_seconds"] == 300

    def test_load_definition_shape(self, ds):
        """TC-WFS-025: load_definition 返回 {workflow, nodes, edges}"""
        edges = [{"from": "n1", "to": "n2", "when": "done"}]
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1(),
                         edges=edges)
        definition = load_definition(ds, "wf-a")
        assert set(definition) == {"workflow", "nodes", "edges"}
        assert definition["workflow"]["version"] == 1
        assert [n["node_id"] for n in definition["nodes"]] == ["n1", "n2"]
        assert definition["edges"] == edges

    def test_load_definition_missing_raises(self, ds):
        """TC-WFS-026: 定义不存在 → WorkflowStoreError"""
        with pytest.raises(WorkflowStoreError):
            load_definition(ds, "nope")

    def test_workflow_json_columns_roundtrip(self, ds):
        """TC-WFS-027: sla / meta 以 JSON 往返（不是原样字符串）"""
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1(),
                         sla={"total_hours": 8}, meta_kv={"tier": "gold"})
        workflow = get_workflow(ds, "wf-a")
        assert workflow["sla"] == {"total_hours": 8}
        assert workflow["meta"] == {"tier": "gold"}

    def test_list_latest_workflows_one_row_per_key(self, ds):
        """TC-WFS-028: list_latest_workflows 每 key 只回最新版"""
        publish_workflow(ds, workflow_key="wf-a", name="流程A", nodes=_trunk_v1())
        publish_workflow(ds, workflow_key="wf-a", name="流程A改名",
                         nodes=[_node("n1", 1, title="改")])
        publish_workflow(ds, workflow_key="wf-b", name="流程B", nodes=_trunk_v1())

        rows = list_latest_workflows(ds)
        assert [(r["workflow_key"], r["version"]) for r in rows] == [("wf-a", 2),
                                                                    ("wf-b", 1)]
        assert rows[0]["name"] == "流程A改名"

    def test_list_latest_workflows_filter_by_trigger_kind(self, ds):
        """TC-WFS-029: 可按 trigger_kind 过滤（C3 事件触发只扫 event 类）"""
        publish_workflow(ds, workflow_key="wf-m", name="手动", nodes=_trunk_v1(),
                         trigger_kind="manual")
        publish_workflow(ds, workflow_key="wf-e", name="事件", nodes=_trunk_v1(),
                         trigger_kind="event",
                         trigger_expr=json.dumps({"event": "outbound_completed"}))
        rows = list_latest_workflows(ds, trigger_kind="event")
        assert [r["workflow_key"] for r in rows] == ["wf-e"]
        assert rows[0]["trigger_expr"] == json.dumps({"event": "outbound_completed"})