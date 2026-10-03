# -*- coding: utf-8 -*-
"""[C1] 编排实例层引擎 —— Run 实例化 / 依赖求值 / 进度派生

职责:
- `start_run()`: 取定义版本 → 写 `workflow_runs`（含 `definition_snapshot` 深拷贝）
  → 按节点克隆 `tasks`（`status='pending'`，`deps` 由 `edges` 生成）
- `advance_run()`: 对 `pending` 任务求值 deps，满足则 `pending→ready`
  （复用 A2 状态机守卫 + A3 事件账落账）
- `run_progress()`: Run 进度**派生**聚合（`workflow_runs` 刻意无状态列，§3.2）

纪律:
- `definition_snapshot` 必须**深拷贝**（json round-trip）—— 否则后续发布新版本会
  经共享引用污染在途 Run
- 状态只挂实例：Run 无状态列；任务状态是唯一状态列，且只经状态机迁移
- 本模块不碰 Flask / BO registry

边界（C1 不做，留给后续能力项）:
- 上游 `outputs` 按 edge 注入下游 `inputs`（运行期数据流）—— 留待 C4/实例层
- 任务的实际执行（executor 分派）—— 归 A5/A4
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from meta.core.task_event_schema import record_task_event, record_transition
from meta.core.task_schema import (
    TASK_STATUSES,
    TASK_TABLE,
    WORKFLOW_RUN_TABLE,
)
from meta.core.task_state_machine import TransitionContext, require_transition
from meta.core.workflow_definition import incoming_edges
from meta.core.workflow_store import load_definition

#: Run 派生状态口径（非 DB 列）
RUN_STATUSES = ("empty", "pending", "in_progress", "done", "failed")

#: 派生「全流程完成」可接受的终态
_TERMINAL_OK = ("done", "skipped", "cancelled")

#: 派生「进行中」的状态集合
_RUNNING = ("ready", "claimed", "in_progress", "waiting_approval", "blocked")

_RUN_COLUMNS = (
    "id", "workflow_id", "workflow_key", "workflow_version", "name",
    "trigger_kind", "definition_snapshot", "variables", "inputs", "outputs",
    "created_by", "created_at", "started_at", "finished_at", "meta", "updated_at",
)

_TASK_COLUMNS = (
    "id", "code", "title", "description", "type", "status", "priority", "app_id",
    "executor_type", "executor_assignee", "executor_candidates", "assign_policy",
    "executor_config", "executor_fallback", "claim_timeout_seconds",
    "timeout_seconds", "retry_policy", "due_at", "sla", "parent_task_id",
    "workflow_run_id", "workflow_node_id", "deps", "inputs", "inputs_schema",
    "outputs", "outputs_schema", "acceptance", "attempt", "trace_id",
    "agent_session_id", "doc_ref", "line_refs", "created_by", "created_at",
    "started_at", "finished_at", "fail_reason", "meta", "updated_at",
)

_RUN_JSON = ("definition_snapshot", "variables", "inputs", "outputs", "meta")
_TASK_JSON = (
    "executor_candidates", "executor_config", "executor_fallback", "retry_policy",
    "deps", "inputs", "inputs_schema", "outputs", "outputs_schema", "acceptance",
    "sla", "line_refs", "meta",
)


class WorkflowEngineError(RuntimeError):
    """Run 实例化 / 推进失败。"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_text(value: Any) -> Optional[str]:
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _deep_copy(value: Any) -> Any:
    """json round-trip 深拷贝（快照隔离，杜绝共享引用污染）。"""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _decode(record: Dict[str, Any], json_columns: Sequence[str]) -> Dict[str, Any]:
    for key in json_columns:
        raw = record.get(key)
        if isinstance(raw, str) and raw:
            try:
                record[key] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    return record


def _select(data_source, sql: str, params: tuple, json_columns: Sequence[str]):
    cursor = data_source.execute(sql, params)
    return [_decode({col[0]: value for col, value in zip(cursor.description, row)},
                    json_columns)
            for row in cursor.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# 读取
# ─────────────────────────────────────────────────────────────────────────────

def get_run(data_source, run_id: str) -> Optional[Dict[str, Any]]:
    rows = _select(data_source,
                   f"SELECT {', '.join(_RUN_COLUMNS)} FROM {WORKFLOW_RUN_TABLE} "
                   "WHERE id = ?", (run_id,), _RUN_JSON)
    return rows[0] if rows else None


def list_run_tasks(data_source, run_id: str) -> List[Dict[str, Any]]:
    """Run 内全部任务（按定义顺序：主干 step_number → node_id）。"""
    return _select(data_source,
                   f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} "
                   "WHERE workflow_run_id = ? ORDER BY id ASC", (run_id,), _TASK_JSON)


def run_progress(data_source, run_id: str) -> Dict[str, Any]:
    """Run 进度派生聚合（Run 无状态列 —— 派生而非双写）。"""
    rows = data_source.execute(
        f"SELECT status, COUNT(*) FROM {TASK_TABLE} WHERE workflow_run_id = ? "
        "GROUP BY status", (run_id,)).fetchall()
    counts = {status: 0 for status in TASK_STATUSES}
    for status, count in rows:
        counts[status] = int(count)
    total = sum(counts.values())
    failed = counts.get("failed", 0) + counts.get("dead", 0)
    ok = sum(counts.get(s, 0) for s in _TERMINAL_OK)

    if total == 0:
        derived = "empty"
    elif failed:
        derived = "failed"
    elif ok == total:
        derived = "done"
    elif any(counts.get(s, 0) for s in _RUNNING):
        derived = "in_progress"
    else:
        derived = "pending"
    return {"run_id": run_id, "total": total, "counts": counts, "status": derived}


# ─────────────────────────────────────────────────────────────────────────────
# 实例化
# ─────────────────────────────────────────────────────────────────────────────

def start_run(
    data_source,
    *,
    workflow_key: str,
    version: Optional[int] = None,
    name: str = "",
    inputs: Any = None,
    variables: Any = None,
    trigger_kind: str = "manual",
    doc_ref: str = "",
    app_id: str = "",
    created_by: str = "",
) -> Dict[str, Any]:
    """按定义版本实例化一个 Run（定义快照 + 节点克隆为任务）。

    Raises:
        WorkflowEngineError: 定义为空 / 版本不存在（后者由 store 抛 WorkflowStoreError）
    """
    definition = load_definition(data_source, workflow_key, version)
    workflow = definition["workflow"]
    nodes = definition["nodes"]
    edges = definition["edges"]
    if not nodes:
        raise WorkflowEngineError(
            f"Workflow '{workflow_key}' v{workflow['version']} 无节点，无法实例化")

    run_id = uuid.uuid4().hex
    ts = _now_iso()
    node_to_task = {node["node_id"]: uuid.uuid4().hex for node in nodes}
    incoming = incoming_edges(nodes, edges)
    snapshot = _deep_copy({"workflow": workflow, "nodes": nodes, "edges": edges})

    with data_source.transaction():
        data_source.execute(
            f"INSERT INTO {WORKFLOW_RUN_TABLE} ({', '.join(_RUN_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _RUN_COLUMNS)})",
            (
                run_id, workflow["id"], workflow["workflow_key"],
                workflow["version"], name or workflow["name"], trigger_kind,
                _json_text(snapshot), _json_text(variables), _json_text(inputs),
                None, created_by or None, ts, ts, None,
                _json_text({"doc_ref": doc_ref} if doc_ref else None), ts,
            ),
        )

        for node in nodes:
            node_id = node["node_id"]
            deps = [
                {"task_id": node_to_task[edge["from"]], "when": edge["when"]}
                for edge in incoming.get(node_id, [])
                if edge["from"] in node_to_task
            ]
            task_id = node_to_task[node_id]
            data_source.execute(
                f"INSERT INTO {TASK_TABLE} ({', '.join(_TASK_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _TASK_COLUMNS)})",
                (
                    task_id, None, node["title"], node.get("description"),
                    node.get("type") or "story", "pending",
                    node.get("priority") or "P2", app_id or None,
                    node["executor_type"], node.get("executor_assignee"),
                    _json_text(node.get("executor_candidates")),
                    node.get("assign_policy") or "direct",
                    _json_text(node.get("executor_config")),
                    _json_text(node.get("executor_fallback")),
                    node.get("claim_timeout_seconds", 300),
                    node.get("timeout_seconds"), _json_text(node.get("retry_policy")),
                    None, _json_text(node.get("sla")), None,
                    run_id, node_id, _json_text(deps), None,
                    _json_text(node.get("inputs_schema")), None,
                    _json_text(node.get("outputs_schema")),
                    _json_text(node.get("acceptance")), 1, None, None,
                    doc_ref or None, None, created_by or None, ts, None, None,
                    None, _json_text(node.get("meta")), ts,
                ),
            )
            record_task_event(
                data_source, task_id=task_id, event_type="created",
                actor=created_by, actor_kind="human" if created_by else "system",
                payload={"workflow_run_id": run_id, "node_id": node_id,
                         "trigger_kind": trigger_kind},
                doc_ref=doc_ref, workflow_run_id=run_id, occurred_at=ts,
            )

    return {"run_id": run_id, "workflow_key": workflow["workflow_key"],
            "workflow_version": workflow["version"], "trigger_kind": trigger_kind,
            "task_ids": node_to_task, "task_count": len(node_to_task)}


# ─────────────────────────────────────────────────────────────────────────────
# 推进（依赖求值）
# ─────────────────────────────────────────────────────────────────────────────

def deps_satisfied(deps: Any, status_by_task_id: Dict[str, str]) -> bool:
    """AND 语义求值 deps（fail-closed：未知 when / 未知任务一律不满足）。

    `when` 值域见 `workflow_definition.WHEN_VALUES`；未声明按 `done`。
    """
    if not deps:
        return True
    if not isinstance(deps, (list, tuple)):
        return False
    for dep in deps:
        if not isinstance(dep, dict):
            return False
        actual = status_by_task_id.get(dep.get("task_id") or "")
        want = dep.get("when") or "done"
        if want == "done":
            ok = actual == "done"
        elif want == "skipped":
            ok = actual == "skipped"
        elif want == "done_or_skipped":
            ok = actual in ("done", "skipped")
        elif want == "failed":
            ok = actual == "failed"
        else:
            ok = False
        if not ok:
            return False
    return True


def advance_run(data_source, run_id: str, *, actor: str = "engine",
                actor_kind: str = "system") -> Dict[str, Any]:
    """把 deps 已满足的 `pending` 任务提升为 `ready`（幂等：可重复调用）。

    Returns:
        {"run_id", "promoted": [task_id...], "blocked": [task_id...]}
    """
    tasks = list_run_tasks(data_source, run_id)
    status_by_task_id = {t["id"]: t["status"] for t in tasks}
    promoted: List[str] = []
    blocked: List[str] = []

    for task in tasks:
        if task["status"] != "pending":
            continue
        if not deps_satisfied(task.get("deps"), status_by_task_id):
            blocked.append(task["id"])
            continue

        require_transition("pending", "ready",
                           TransitionContext(deps_satisfied=True, actor=actor,
                                             actor_kind=actor_kind))
        with data_source.transaction():
            cursor = data_source.execute(
                f"UPDATE {TASK_TABLE} SET status = ?, started_at = COALESCE(started_at, ?), "
                "updated_at = ? WHERE id = ? AND status = ?",
                ("ready", _now_iso(), _now_iso(), task["id"], "pending"),
            )
            if cursor.rowcount == 0:      # 并发下已被提升 → 视为已推进
                continue
            record_transition(
                data_source, task_id=task["id"], from_status="pending",
                to_status="ready", actor=actor, actor_kind=actor_kind,
                reason="deps 满足，引擎提升", summary="pending → ready",
                doc_ref=task.get("doc_ref") or "",
                workflow_run_id=run_id, trace_id=task.get("trace_id") or "",
            )
        promoted.append(task["id"])
        status_by_task_id[task["id"]] = "ready"

    return {"run_id": run_id, "promoted": promoted, "blocked": blocked}
