# -*- coding: utf-8 -*-
"""[P1 2026-11-16] 任务控制动作 — cancel（spec §9.13.4.2 第 3 条 / §9.13.6 第 2 步）

职责:
- `cancel_task`：把非终态任务置为 `cancelled`，落一条迁移事件 + 一条工作日志。
- 只做「取消」：hold / resume 由 `task_hold.py` 提供（只写 TASK_EVENT、**不改状态列**），
  REST 层薄包装，不在此重复实现。

分层纪律:
- 迁移走 A2 `require_transition`（结构 + 守卫，fail-closed）；
- 落账走 A3 `record_transition`（不自提交，事务由本模块持有）；
- 并发安全：条件 UPDATE（`WHERE id = ? AND status = ?`）+ rowcount 判定，
  驱动不返回 rowcount 时回读复核（与 A4 `_persist_claim` 同口径）；
- 除状态列外只写终态时间 `finished_at`（与 done / skipped 同口径），
  不碰单据域任何字段（单据回退属 withdraw，§9.13.4.2 第 4 条）。

对应方案:
  docs/specs/spec-approval-workflow-2026-11-15.md §9.13.4.2 第 3 条 / §9.13.6 第 2 步
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, FrozenSet

from meta.core.task_event_schema import record_transition
from meta.core.task_schema import TASK_TABLE
from meta.core.task_state_machine import (
    TERMINAL_STATES, TransitionContext, require_transition,
)

#: 允许取消的来源状态（与 `TASK_ACTIONS['cancel'].allowed_from` 逐字一致）
CANCELLABLE_STATES: FrozenSet[str] = frozenset({
    "pending", "ready", "claimed", "in_progress", "failed", "waiting_approval",
})

_TASK_COLUMNS = (
    "status", "workflow_run_id", "trace_id", "agent_session_id",
    "doc_ref", "line_refs",
)


class TaskControlError(RuntimeError):
    """控制动作前置不满足（已终态 / 状态不可取消 / 并发被抢占）。"""


class TaskNotFoundError(TaskControlError):
    """任务不存在（HTTP 404，区别于前置不满足的 409）。"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_json(text: Any, fallback: Any) -> Any:
    if text is None or text == "":
        return fallback
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return fallback


def _load_task(data_source, task_id: str) -> Dict[str, Any]:
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} WHERE id = ?",
        (str(task_id),),
    ).fetchall()
    if not rows:
        raise TaskNotFoundError(f"任务不存在：{task_id}")
    r = rows[0]
    return {
        "status": r[0] or "",
        "workflow_run_id": r[1] or "",
        "trace_id": r[2] or "",
        "agent_session_id": r[3] or "",
        "doc_ref": r[4] or "",
        "line_refs": _load_json(r[5], None),
    }


def _persist_cancel(data_source, task_id: str, from_status: str) -> bool:
    """条件取消：仅当仍处于读取到的状态时生效，返回是否成功。"""
    ts = _now_iso()
    cursor = data_source.execute(
        f"UPDATE {TASK_TABLE} SET status = 'cancelled', "
        f"finished_at = COALESCE(finished_at, ?), updated_at = ? "
        f"WHERE id = ? AND status = ?",
        (ts, ts, str(task_id), str(from_status)),
    )
    rowcount = getattr(cursor, "rowcount", None)
    if rowcount is not None:
        return rowcount > 0
    # 驱动不返回 rowcount：回读复核（fail-closed，避免把失败当成功）
    rows = data_source.execute(
        f"SELECT status FROM {TASK_TABLE} WHERE id = ?", (str(task_id),)
    ).fetchall()
    return bool(rows) and rows[0][0] == "cancelled"


def cancel_task(data_source, task_id: str, *, actor: str = "",
                actor_kind: str = "human", reason: str = "",
                occurred_at: Any = None) -> Dict[str, Any]:
    """取消任务（鉴权由调用方完成：created_by 或 admin）。

    Raises:
        TaskNotFoundError: 任务不存在（映射 404）
        TaskControlError: 已终态 / 状态不可取消 / 并发被抢占（映射 409）
        TaskTransitionError: 迁移结构或守卫不通过（映射 409）
    """
    task = _load_task(data_source, task_id)
    status = task["status"]
    if status in TERMINAL_STATES:
        raise TaskControlError(f"任务已处于终态，不能取消：{status}")
    if status not in CANCELLABLE_STATES:
        raise TaskControlError(f"当前状态不可取消：{status}")

    require_transition(status, "cancelled",
                       TransitionContext(actor=actor or None, actor_kind=actor_kind))

    with data_source.transaction():
        if not _persist_cancel(data_source, str(task_id), status):
            raise TaskControlError("任务状态已被他人改变，取消未生效")
        event_id, _worklog_id = record_transition(
            data_source, task_id=str(task_id), from_status=status,
            to_status="cancelled", actor=actor, actor_kind=actor_kind,
            reason=reason or "任务取消",
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
            occurred_at=occurred_at,
        )
    return {"task_id": str(task_id), "status": "cancelled",
            "from_status": status, "event_id": event_id}
