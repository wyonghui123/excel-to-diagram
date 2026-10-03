# -*- coding: utf-8 -*-
"""[C3] 编排触发管道 —— 对象事件 → 唤起 Run（「事件进」的唯一入口）

职责:
- 把平台已有的事件通道（`event_outbox` + `event_consumer` 幂等消费）与编排
  定义层的 `trigger_kind='event'` 接起来：命中 → `workflow_engine.start_run()`。
- 「录入即任务」：对象事件（计划对象出现 / 变化、事实对象变化）→ 唤起 Run
  （综合缝合 §5.3「进任务 = 对象事件」）。

触发契约（`workflows.trigger_expr`；`trigger_kind='event'` 时必填，JSON 对象）:

    {"event": "<事件名>", "when": "<条件表达式，可选>", "doc_ref": "<payload 字段，可选>"}

- `event`：必填。订阅契约的事件名（与 `events.publish[].name` 同一命名空间）。
- `when`：可选。命中条件，**复用** `event_outbox.evaluate_condition`（ast 白名单，
  仅字面比较 / and / or / not / in）—— 与 `events.publish[].condition` 同一口径。
- `doc_ref`：可选。从 payload 取哪个字段作为 Run / Task 的 `doc_ref`
  （跨环节关联键，businessKey 等价物，综合缝合 §5.3）。

纪律:
- **不发明第二套通道**：复用 outbox 的 Dispatcher 与 `event_consumer` 的去重表
  （at-least-once 投递 → 消费端幂等是硬要求，roadmap §6.14.4 ②）。
- **不发明表达式语言**：见上（`evaluate_condition`）。
- **定义期闸门**：非法 `trigger_expr` 在 `publish_workflow` 即被拒，避免
  「写进去了但永不触发」的静默失败（roadmap §6.14.4 ④ 的同一取向）。
- 只唤起 Run，不写对象表（「不越权」，综合缝合 §5.5）。

边界（本项不做）:
- `schedule`（cron）：不建调度器；`manual` / `api` 由调用方直接 `start_run`。
- 跨应用 / 跨实例镜像（Q2 的「双记录镜像」）：归 C5。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §12.1 C3 / §7.4 / §12.1 Q2
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §5.3
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from meta.core.event_outbox import EventContractError, evaluate_condition
from meta.core.workflow_definition import DefinitionFinding, WorkflowDefinitionError
from meta.core.workflow_engine import start_run
from meta.core.workflow_store import TRIGGER_KINDS

logger = logging.getLogger(__name__)

#: 事件触发（C3 的唯一入口形态）
TRIGGER_EVENT = "event"

#: `trigger_expr` JSON 允许的键（白名单；未知键不报错但被忽略）
_TRIGGER_KEYS = ("event", "when", "doc_ref")


class _ProbeValue:
    """定义期探针值：与任意值比较均不抛错（只验结构，不关心真假）。

    `evaluate_condition` 同时承担「解析」与「求值」，而 `when` 里的比较
    （如 `qty > 1`）在空 row 上会因 `None > 1` 抛 TypeError。定义期只想校验
    **语法 / 白名单**，故用探针值走完同一条 `_eval_node` 路径 —— 结构非法仍抛
    `EventContractError`（含函数调用、下标、属性访问、未知运算符）。
    """

    __slots__ = ()

    def __eq__(self, other): return True
    def __ne__(self, other): return False
    def __gt__(self, other): return True
    def __ge__(self, other): return True
    def __lt__(self, other): return False
    def __le__(self, other): return True
    def __contains__(self, other): return True
    def __hash__(self): return 0


class _ProbeRow(dict):
    """`row.get()` 恒返回探针值 —— 让 `evaluate_condition` 只走结构校验分支。"""

    def get(self, key, default=None):
        return _ANY


_ANY = _ProbeValue()
_PROBE_ROW = _ProbeRow()


class WorkflowTriggerError(RuntimeError):
    """触发管道运行期错误（接线错误，非定义非法）。"""


@dataclass(frozen=True)
class TriggerSpec:
    """解析后的触发声明。`event_name` / `condition` 仅 kind=event 时非空。"""

    kind: str
    event_name: str = ""
    condition: str = ""
    doc_ref_field: str = ""

    @property
    def is_event(self) -> bool:
        return self.kind == TRIGGER_EVENT


# ─────────────────────────────────────────────────────────────────────────────
# 定义期：解析 + 校验（publish_workflow 在写库前调用）
# ─────────────────────────────────────────────────────────────────────────────

def _invalid(code: str, detail: str) -> WorkflowDefinitionError:
    return WorkflowDefinitionError([DefinitionFinding(code, detail)])


def parse_trigger_expr(trigger_kind: str, trigger_expr: Any) -> TriggerSpec:
    """解析 / 校验触发声明；非法抛 `WorkflowDefinitionError`。

    Raises:
        WorkflowDefinitionError: kind 未知 / event 缺 trigger_expr / 非 JSON 对象 /
            event 名为空 / when 非字符串 / when 语法非法
    """
    if trigger_kind not in TRIGGER_KINDS:
        raise _invalid("TRIGGER_KIND_INVALID",
                       f"trigger_kind='{trigger_kind}' 不在 {TRIGGER_KINDS} 内")
    if trigger_kind != TRIGGER_EVENT:
        # manual / api / schedule：本项不解释 expr（schedule 无调度器）
        return TriggerSpec(kind=trigger_kind)

    raw = trigger_expr.strip() if isinstance(trigger_expr, str) else ""
    if not raw:
        raise _invalid(
            "TRIGGER_EXPR_MISSING",
            "trigger_kind='event' 必须声明 trigger_expr"
            '（JSON：{"event": "<事件名>", "when": "<条件>", "doc_ref": "<字段>"}）')

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise _invalid("TRIGGER_EXPR_NOT_JSON",
                       f"trigger_expr 非法 JSON: {e}（原文 {raw!r}）") from e
    if not isinstance(data, dict):
        raise _invalid("TRIGGER_EXPR_NOT_OBJECT",
                       f"trigger_expr 需为 JSON 对象，实际 {type(data).__name__}")

    event_name = data.get("event")
    event_name = event_name.strip() if isinstance(event_name, str) else ""
    if not event_name:
        raise _invalid("TRIGGER_EVENT_NAME_MISSING",
                       "trigger_expr 缺少非空 'event'（事件名，触发入口的匹配键）")

    condition = data.get("when") or ""
    if not isinstance(condition, str):
        raise _invalid("TRIGGER_WHEN_INVALID",
                       f"trigger_expr.when 需为字符串，实际 {type(condition).__name__}")
    condition = condition.strip()
    if condition:
        try:
            evaluate_condition(condition, _PROBE_ROW)   # 只解析：语法/白名单校验
        except EventContractError as e:
            raise _invalid("TRIGGER_WHEN_INVALID",
                           f"trigger_expr.when 非法: {e}") from e

    doc_ref_field = data.get("doc_ref") or ""
    if not isinstance(doc_ref_field, str):
        raise _invalid("TRIGGER_DOC_REF_INVALID",
                       f"trigger_expr.doc_ref 需为字符串，"
                       f"实际 {type(doc_ref_field).__name__}")

    return TriggerSpec(kind=TRIGGER_EVENT, event_name=event_name,
                       condition=condition, doc_ref_field=doc_ref_field.strip())


def assert_trigger(trigger_kind: str, trigger_expr: Any) -> TriggerSpec:
    """定义期闸门（`publish_workflow` 调用）；通过返回 TriggerSpec。"""
    return parse_trigger_expr(trigger_kind, trigger_expr)


# ─────────────────────────────────────────────────────────────────────────────
# 运行期：匹配
# ─────────────────────────────────────────────────────────────────────────────

def condition_matches(condition: str, payload: Any) -> bool:
    """求值命中条件（空条件 = 恒命中）。

    fail-closed：payload 非对象或求值异常 → 不命中（宁可不起，不可乱起）。
    """
    if not condition:
        return True
    if not isinstance(payload, dict):
        return False
    try:
        return bool(evaluate_condition(condition, payload))
    except EventContractError as e:
        logger.warning("[WorkflowTrigger] 条件求值失败，按不命中处理: %s", e)
        return False


def matches_event(trigger_kind: str, trigger_expr: Any, event_name: str,
                  payload: Any) -> bool:
    """判定某定义是否被该事件命中（定义非法 → 抛 WorkflowDefinitionError）。"""
    spec = parse_trigger_expr(trigger_kind, trigger_expr)
    if not spec.is_event or spec.event_name != event_name:
        return False
    return condition_matches(spec.condition, payload)


# ─────────────────────────────────────────────────────────────────────────────
# 运行期：唤起
# ─────────────────────────────────────────────────────────────────────────────

def start_runs_for_event(
    data_source,
    *,
    event_name: str,
    payload: Any = None,
    app_id: str = "",
    created_by: str = "",
    trigger_kind: str = TRIGGER_EVENT,
) -> List[Dict[str, Any]]:
    """把一条事件投给全部命中的事件触发定义，各自唤起一个 Run。

    只扫**每个 workflow_key 的最新版本**（定义层版本化的「生效版」语义）。
    `trigger_expr` 的 doc_ref 字段从 payload 取值作为 Run / Task 的 `doc_ref`。

    Returns:
        唤起结果列表（`workflow_engine.start_run()` 的返回值，按 workflow_key 升序）
    """
    from meta.core.workflow_store import list_latest_workflows

    started: List[Dict[str, Any]] = []
    for workflow in list_latest_workflows(data_source, trigger_kind=TRIGGER_EVENT):
        spec = parse_trigger_expr(workflow.get("trigger_kind"),
                                  workflow.get("trigger_expr"))
        if spec.event_name != event_name:
            continue
        if not condition_matches(spec.condition, payload):
            continue

        doc_ref = ""
        if spec.doc_ref_field and isinstance(payload, dict):
            value = payload.get(spec.doc_ref_field)
            doc_ref = "" if value is None else str(value)

        run = start_run(
            data_source,
            workflow_key=workflow["workflow_key"],
            version=workflow["version"],
            name=workflow.get("name") or "",
            inputs=payload if isinstance(payload, dict) else None,
            trigger_kind=trigger_kind,
            doc_ref=doc_ref,
            app_id=app_id,
            created_by=created_by,
        )
        logger.info(
            "[WorkflowTrigger] 事件命中并唤起 Run: event=%s workflow=%s@%s run=%s",
            event_name, workflow["workflow_key"], workflow["version"], run["run_id"],
        )
        started.append(run)
    return started


def handle_task_trigger_event(
    data_source,
    payload: Any,
    *,
    event_name: str,
    app_id: str = "",
    created_by: str = "",
) -> Dict[str, Any]:
    """订阅方 handler 的**平台入口**（同一契约，跨应用一致）。

    用法（应用包内的 handler，由 `app.yaml` 的 `events.subscribe[].handler` 指向）:

        def handle(data_source, payload):
            from meta.core.workflow_trigger import handle_task_trigger_event
            return handle_task_trigger_event(
                data_source, payload, event_name="outbound_completed")

    幂等由 `event_consumer.consume_event()` 的去重表保证（本函数不另建机制）：
    同一 `idempotency_key` 重复投递时 handler 根本不会被调用。

    Returns:
        {"event_name", "started": [run_id...], "count"}
    """
    if not (isinstance(event_name, str) and event_name.strip()):
        raise WorkflowTriggerError(
            "handle_task_trigger_event 需要非空 event_name（handler 的接线参数）")
    runs = start_runs_for_event(
        data_source, event_name=event_name.strip(), payload=payload,
        app_id=app_id, created_by=created_by,
    )
    return {"event_name": event_name.strip(),
            "started": [r["run_id"] for r in runs],
            "count": len(runs)}


def build_event_handler(
    event_name: str,
    *,
    app_id: str = "",
) -> Callable[[Any, Any], Dict[str, Any]]:
    """生成 `handle(data_source, payload)` 形式的订阅 handler（供 app.yaml 引用）。"""
    def handle(data_source, payload):
        return handle_task_trigger_event(
            data_source, payload, event_name=event_name, app_id=app_id)

    handle.__name__ = "handle"
    return handle