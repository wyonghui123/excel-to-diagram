# -*- coding: utf-8 -*-
"""后端测试套件 - [C3] 编排触发管道（对象事件 → 唤起 Run）

测试 meta.core.workflow_trigger 模块

覆盖目标（对齐 §12.1 C3 / 综合缝合 §5.3 / roadmap §6.14.4）:
  1. 定义期闸门: 非法 trigger_expr（缺 event / 非 JSON / 非对象 / when 非白名单）
     → WorkflowDefinitionError，不落版本行
  2. 匹配: 事件名相等 + when 条件命中（复用 evaluate_condition 的 ast 白名单）
  3. 唤起: 命中 → start_run（doc_ref 由 trigger_expr 指定字段从 payload 取；
     Run inputs = 事件载荷）
  4. 只扫最新版: 定义升级后在途 Run 不受影响，触发走新版本
  5. 同一契约: build_event_handler 生成的 handler 与 app.yaml 订阅契约同形
  6. **复用幂等**: 经 event_consumer.consume_event 消费 → 同一 idempotency_key
     重复投递不再唤起第二个 Run（不另建幂等机制）
  7. 手工 event 事件: manual / api / schedule 不参与事件扫描

注: 平台内部表（tasks / task_events / workflow_*）暂无 Factory；按仓库既有惯例
走 raw SQL escape hatch（同 test_decision_effect.py 注释），避免整文件被 conftest
raw-SQL 门控拦跳。本文件 raw 写仅用于**预置任务状态**。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
from datetime import datetime

import pytest

from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import list_run_tasks
from meta.core.workflow_store import publish_workflow
from meta.core.workflow_trigger import (
    TRIGGER_EVENT,
    TriggerSpec,
    WorkflowTriggerError,
    build_event_handler,
    condition_matches,
    handle_task_trigger_event,
    matches_event,
    parse_trigger_expr,
    start_runs_for_event,
)

pytestmark = pytest.mark.unit

EVENT = "outbound_completed"


# ─────────────────────────────────────────────────────────────────────────────
# 夹具 / 助手
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（任务四表 + 事件账两表 + 幂等去重表）。"""
    from meta.core.datasource import get_data_source
    from meta.core.event_consumer import ensure_consumed_table

    source = get_data_source("sqlite", database=str(tmp_path / "c3.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_consumed_table(source)
    yield source


def _now():
    return datetime.now().isoformat(timespec="seconds")


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


def _nodes():
    return [_node("n1", 1, title="受理"), _node("n2", 2, title="复核")]


def _expr(**kw):
    return json.dumps(kw, ensure_ascii=False)


def _publish_event_workflow(ds, *, key="wf-out", event=EVENT, when=None,
                            doc_ref=None, nodes=None, version_hint=None):
    spec = {"event": event}
    if when is not None:
        spec["when"] = when
    if doc_ref is not None:
        spec["doc_ref"] = doc_ref
    return publish_workflow(ds, workflow_key=key, name=f"流程{key}",
                            nodes=nodes or _nodes(), trigger_kind="event",
                            trigger_expr=json.dumps(spec, ensure_ascii=False))


def _runs(ds):
    return list_run_tasks


def _count(ds, table, where="", params=()):
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return ds.execute(sql, params).fetchone()[0]


def _run_rows(ds):
    """Run 行投影。`doc_ref` 不在列上 —— 按 spec §5.3 存于 `meta.doc_ref`。"""
    rows = ds.execute(
        "SELECT id, workflow_key, workflow_version, trigger_kind, inputs, meta "
        "FROM workflow_runs ORDER BY created_at, id").fetchall()
    projected = []
    for r in rows:
        meta = json.loads(r[5]) if r[5] else {}
        projected.append({"id": r[0], "workflow_key": r[1],
                          "workflow_version": r[2], "trigger_kind": r[3],
                          "inputs": r[4], "doc_ref": meta.get("doc_ref")})
    return projected


def _set_status(ds, task_id, status):
    """预置任务状态（仅测试用；平台内部表无 Factory）。"""
    with ds.transaction():
        ds.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                   (status, _now(), task_id))


# ─────────────────────────────────────────────────────────────────────────────
# 1. 定义期：解析与校验
# ─────────────────────────────────────────────────────────────────────────────

class TestParseTriggerExpr:

    def test_non_event_kinds_pass_through(self):
        """TC-WFT-001: manual / api / schedule 不解释 expr"""
        for kind in ("manual", "api", "schedule"):
            spec = parse_trigger_expr(kind, "")
            assert spec.kind == kind
            assert spec.is_event is False
            assert spec.event_name == ""

    def test_event_minimal(self):
        """TC-WFT-002: 只声明 event 名即可"""
        spec = parse_trigger_expr(TRIGGER_EVENT, _expr(event=EVENT))
        assert spec == TriggerSpec(kind=TRIGGER_EVENT, event_name=EVENT)

    def test_event_full(self):
        """TC-WFT-003: when / doc_ref 被解析"""
        spec = parse_trigger_expr(
            TRIGGER_EVENT,
            _expr(event=EVENT, when="status == 'shipped'", doc_ref="order_no"))
        assert spec.event_name == EVENT
        assert spec.condition == "status == 'shipped'"
        assert spec.doc_ref_field == "order_no"

    def test_unknown_kind_rejected(self):
        """TC-WFT-004: 未知 kind → TRIGGER_KIND_INVALID"""
        with pytest.raises(Exception) as exc:
            parse_trigger_expr("bogus", "")
        assert exc.value.findings[0].code == "TRIGGER_KIND_INVALID"

    @pytest.mark.parametrize("raw, code", [
        ("", "TRIGGER_EXPR_MISSING"),
        ("   ", "TRIGGER_EXPR_MISSING"),
        ("not-json", "TRIGGER_EXPR_NOT_JSON"),
        ("[1, 2]", "TRIGGER_EXPR_NOT_OBJECT"),
        ('{"when": "x == 1"}', "TRIGGER_EVENT_NAME_MISSING"),
        ('{"event": "   "}', "TRIGGER_EVENT_NAME_MISSING"),
        ('{"event": "e", "when": 123}', "TRIGGER_WHEN_INVALID"),
        ('{"event": "e", "when": "__import__(\'os\')"}', "TRIGGER_WHEN_INVALID"),
        ('{"event": "e", "doc_ref": 9}', "TRIGGER_DOC_REF_INVALID"),
    ])
    def test_invalid_trigger_expr_rejected(self, raw, code):
        """TC-WFT-005: 非法 trigger_expr 的 finding code 逐项对位"""
        with pytest.raises(Exception) as exc:
            parse_trigger_expr(TRIGGER_EVENT, raw)
        assert exc.value.findings[0].code == code

    def test_whitelisted_condition_forms_accepted(self):
        """TC-WFT-006: 白名单条件形态（比较 / in / and / not）均可解析"""
        for when in ("status == 'shipped'", "status in ['a', 'b']",
                     "qty > 1 and status == 'x'", "not status == 'x'"):
            spec = parse_trigger_expr(TRIGGER_EVENT, _expr(event=EVENT, when=when))
            assert spec.condition == when


# ─────────────────────────────────────────────────────────────────────────────
# 2. 匹配
# ─────────────────────────────────────────────────────────────────────────────

class TestMatching:

    def test_event_name_equality(self):
        """TC-WFT-010: 事件名不等 → 不命中"""
        expr = _expr(event=EVENT)
        assert matches_event(TRIGGER_EVENT, expr, EVENT, {}) is True
        assert matches_event(TRIGGER_EVENT, expr, "other_event", {}) is False

    def test_non_event_kind_never_matches(self):
        """TC-WFT-011: manual 定义不参与事件匹配"""
        assert matches_event("manual", "", EVENT, {}) is False

    def test_condition_gate(self):
        """TC-WFT-012: when 条件不满足 → 不命中"""
        expr = _expr(event=EVENT, when="status == 'shipped'")
        assert matches_event(TRIGGER_EVENT, expr, EVENT, {"status": "shipped"}) is True
        assert matches_event(TRIGGER_EVENT, expr, EVENT, {"status": "created"}) is False

    def test_condition_empty_hits(self):
        """TC-WFT-013: 无 when → 恒命中"""
        assert condition_matches("", {"any": 1}) is True

    def test_condition_fail_closed_on_non_dict(self):
        """TC-WFT-014: payload 非对象 → 不命中（fail-closed）"""
        assert condition_matches("status == 'x'", None) is False
        assert condition_matches("status == 'x'", "raw") is False

    def test_condition_missing_field_is_false(self):
        """TC-WFT-015: payload 缺字段 → 条件为假（不抛错）"""
        assert condition_matches("status == 'shipped'", {}) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. 唤起（核心）
# ─────────────────────────────────────────────────────────────────────────────

class TestStartRunsForEvent:

    def test_matching_event_starts_one_run(self, ds):
        """TC-WFT-020: 命中 → 恰一个 Run，且克隆任务"""
        _publish_event_workflow(ds)
        started = start_runs_for_event(ds, event_name=EVENT,
                                       payload={"order_no": "ORD-1"})
        assert len(started) == 1
        assert started[0]["workflow_key"] == "wf-out"
        assert started[0]["trigger_kind"] == "event"
        assert len(list_run_tasks(ds, started[0]["run_id"])) == 2

    def test_non_matching_event_starts_none(self, ds):
        """TC-WFT-021: 事件名不匹配 → 不起流程"""
        _publish_event_workflow(ds)
        assert start_runs_for_event(ds, event_name="other", payload={}) == []
        assert _run_rows(ds) == []

    def test_condition_filters_out(self, ds):
        """TC-WFT-022: 条件不满足 → 不起流程"""
        _publish_event_workflow(ds, when="status == 'shipped'")
        assert start_runs_for_event(ds, event_name=EVENT,
                                    payload={"status": "created"}) == []
        started = start_runs_for_event(ds, event_name=EVENT,
                                       payload={"status": "shipped"})
        assert len(started) == 1

    def test_doc_ref_taken_from_payload_field(self, ds):
        """TC-WFT-023: doc_ref 字段声明 → Run 与克隆任务都带上业务键"""
        _publish_event_workflow(ds, doc_ref="order_no")
        started = start_runs_for_event(ds, event_name=EVENT,
                                       payload={"order_no": "ORD-7", "status": "x"})
        run_rows = _run_rows(ds)
        assert run_rows[0]["doc_ref"] == "ORD-7"
        tasks = list_run_tasks(ds, started[0]["run_id"])
        assert {t["doc_ref"] for t in tasks} == {"ORD-7"}

    def test_no_doc_ref_declaration_leaves_it_empty(self, ds):
        """TC-WFT-024: 未声明 doc_ref → Run.doc_ref 为空（不猜测）"""
        _publish_event_workflow(ds)
        start_runs_for_event(ds, event_name=EVENT, payload={"order_no": "ORD-7"})
        assert _run_rows(ds)[0]["doc_ref"] is None

    def test_payload_becomes_run_inputs(self, ds):
        """TC-WFT-025: Run inputs = 事件载荷（触发对象快照）"""
        _publish_event_workflow(ds)
        payload = {"order_no": "ORD-9", "quantity": 3}
        start_runs_for_event(ds, event_name=EVENT, payload=payload)
        run_row = _run_rows(ds)[0]
        assert json.loads(run_row["inputs"]) == payload

    def test_app_id_propagated_to_tasks(self, ds):
        """TC-WFT-026: app_id 透传到克隆任务（A8 行级可见性）"""
        _publish_event_workflow(ds)
        started = start_runs_for_event(ds, event_name=EVENT, payload={},
                                       app_id="tms")
        tasks = list_run_tasks(ds, started[0]["run_id"])
        assert {t["app_id"] for t in tasks} == {"tms"}

    def test_multiple_matching_workflows_each_start(self, ds):
        """TC-WFT-027: 多个定义订阅同一事件 → 各自起 Run（按 key 升序）"""
        _publish_event_workflow(ds, key="wf-a")
        _publish_event_workflow(ds, key="wf-b")
        _publish_event_workflow(ds, key="wf-c", event="other")
        started = start_runs_for_event(ds, event_name=EVENT, payload={})
        assert [s["workflow_key"] for s in started] == ["wf-a", "wf-b"]

    def test_only_latest_version_is_scanned(self, ds):
        """TC-WFT-028: 只扫最新版 —— v2 的条件生效，v1 不再被扫"""
        _publish_event_workflow(ds, when="status == 'shipped'")
        # v2：改为无条件命中（内容变更 → 新版本）
        _publish_event_workflow(ds, when=None)
        started = start_runs_for_event(ds, event_name=EVENT,
                                       payload={"status": "created"})
        assert len(started) == 1
        assert started[0]["workflow_version"] == 2

    def test_manual_workflow_not_scanned(self, ds):
        """TC-WFT-029: manual 定义不出现在事件扫描里"""
        publish_workflow(ds, workflow_key="wf-m", name="手动", nodes=_nodes(),
                         trigger_kind="manual")
        assert start_runs_for_event(ds, event_name=EVENT, payload={}) == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. 同一契约 + 幂等（复用 event_consumer）
# ─────────────────────────────────────────────────────────────────────────────

class TestHandlerContract:

    def test_build_event_handler_shape(self, ds):
        """TC-WFT-040: build_event_handler 返回 handle(data_source, payload)"""
        handler = build_event_handler(EVENT)
        assert callable(handler)
        assert handler.__name__ == "handle"

    def test_handler_starts_run_and_reports(self, ds):
        """TC-WFT-041: handler 直接调用 → 唤起并回执 run_id 列表"""
        _publish_event_workflow(ds)
        result = handle_task_trigger_event(ds, {"order_no": "ORD-1"},
                                           event_name=EVENT)
        assert result["event_name"] == EVENT
        assert result["count"] == 1
        assert len(result["started"]) == 1

    def test_handler_requires_event_name(self, ds):
        """TC-WFT-042: 未接线 event_name → 运行期报错（接线错误，非静默）"""
        with pytest.raises(WorkflowTriggerError):
            handle_task_trigger_event(ds, {}, event_name="")
        with pytest.raises(WorkflowTriggerError):
            handle_task_trigger_event(ds, {}, event_name="   ")

    def test_consume_event_idempotent_single_run(self, ds):
        """TC-WFT-043: 经 consume_event 消费后，同一幂等键重投不再起第二个 Run"""
        from meta.core.event_consumer import consume_event

        _publish_event_workflow(ds)
        handler = build_event_handler(EVENT)
        payload = {"order_no": "ORD-1", "status": "shipped"}

        first = consume_event(ds, consumer_app="tms", event_name=EVENT,
                              idempotency_key="ORD-1", payload=payload,
                              handler=handler, event_id="evt-1")
        second = consume_event(ds, consumer_app="tms", event_name=EVENT,
                               idempotency_key="ORD-1", payload=payload,
                               handler=handler, event_id="evt-2")

        assert first["status"] == "consumed"
        assert second["status"] == "duplicate"
        assert _count(ds, "workflow_runs") == 1, "重复投递起了第二个 Run"
        assert _count(ds, "consumed_events") == 1

    def test_consume_event_distinct_keys_start_distinct_runs(self, ds):
        """TC-WFT-044: 幂等只针对同一键 —— 不同业务键各自起 Run"""
        from meta.core.event_consumer import consume_event

        _publish_event_workflow(ds)
        handler = build_event_handler(EVENT)
        for key in ("ORD-1", "ORD-2"):
            consume_event(ds, consumer_app="tms", event_name=EVENT,
                          idempotency_key=key,
                          payload={"order_no": key}, handler=handler)
        assert _count(ds, "workflow_runs") == 2

    def test_handler_failure_rolls_back_run_and_mark(self, ds):
        """TC-WFT-045: 消费事务内起 Run 失败 → Run 与去重标记一并回滚（不毒化幂等键）"""
        from meta.core.event_consumer import consume_event

        # 命中事件但引用不存在的 workflow（通过删除定义行模拟运行期失败）：
        # 这里用「定义不存在」以外的路径 —— 直接构造非法 trigger_expr 不可行
        # （发布期已拦），故改注入一个会抛错的 handler 包装来验证事务性。
        def _boom(data_source, payload):
            handle_task_trigger_event(data_source, payload, event_name=EVENT)
            raise RuntimeError("C3_FAIL_MARKER: 模拟后续处理失败")

        _publish_event_workflow(ds)
        with pytest.raises(RuntimeError):
            consume_event(ds, consumer_app="tms", event_name=EVENT,
                          idempotency_key="ORD-1", payload={"order_no": "ORD-1"},
                          handler=_boom)
        assert _count(ds, "workflow_runs") == 0, "Run 未随事务回滚"
        assert _count(ds, "consumed_events") == 0, "去重标记未随事务回滚"