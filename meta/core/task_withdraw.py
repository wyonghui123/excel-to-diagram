# -*- coding: utf-8 -*-
"""[P1 2026-11-16] 任务侧撤回（withdraw）— 审批单据回退 + 任务取消

职责:
- `withdraw_task`：提交人撤回在途审批（spec §9.13.4.2 第 4 条）。
  **不是 cancel**：撤回承诺单据回退副作用，取消不承诺（D-AP-18）。
- 顺序：先校验（who / when / 无有效 approve）→ 单据回退（幂等）→ 任务 → cancelled。
  单据先回退、任务后归位：单据失败则任务保持 waiting_approval（可重试），
  避免「任务已取消但单据仍挂 submitted」的悬挂。

分层纪律:
- 鉴权事实由本模块兜底复核（`created_by` 严格相等，admin 不放行），REST 层同口径；
- 「无任何有效 approve」从任务账判定（`tasks.outputs.decision='approve'` 且 done），
  **不读**单据 approval_status（审批投影纪律）；
- 单据回退副作用只在 `document_approval_decision.withdraw_approval` 落库；
- 幂等：单据回退包在 `run_idempotent`（键 `{task_id}:{attempt}:withdraw`，与
  决策生效同一 scope），重试不会二次回退；任务取消走 A3 事件账。

对应方案:
  docs/specs/spec-approval-workflow-2026-11-15.md §9.13.4.2 第 4 条 / §9.13.6 第 3 步
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from meta.core.decision_effect import build_effect_key
from meta.core.task_control import TaskControlError, TaskNotFoundError, cancel_task
from meta.core.task_idempotency import run_idempotent
from meta.core.task_schema import TASK_TABLE
from meta.services.document_approval_decision import withdraw_approval

#: 可撤回的任务状态（审批在途）
WITHDRAWABLE_STATES = frozenset({"waiting_approval"})

_TASK_COLUMNS = (
    "id", "type", "status", "created_by", "attempt", "doc_ref",
    "doc_ref_type", "doc_ref_id", "outputs", "workflow_run_id",
)


class TaskWithdrawError(TaskControlError):
    """撤回前置不满足（非审批任务 / 状态不符 / 单据回退失败）。"""


class TaskWithdrawPermissionError(TaskWithdrawError):
    """非提交人撤回（HTTP 403）。"""


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
        "id": r[0], "type": r[1] or "", "status": r[2] or "",
        "created_by": r[3] or "", "attempt": r[4] or 1,
        "doc_ref": r[5] or "", "doc_ref_type": r[6] or "",
        "doc_ref_id": r[7] or "", "outputs": _load_json(r[8], {}),
        "workflow_run_id": r[9] or "",
    }


def _ensure_no_approved(data_source, task: Dict[str, Any]) -> None:
    """「无任何有效 approve」：同单据下不存在 done 且 decision=approve 的审批任务。"""
    doc_ref_type = task["doc_ref_type"]
    doc_ref_id = task["doc_ref_id"]
    if doc_ref_id:
        sql = ("SELECT id, outputs FROM tasks WHERE type = 'approval' "
               "AND doc_ref_type = ? AND doc_ref_id = ? AND status = 'done'")
        params = (doc_ref_type, doc_ref_id)
    else:
        sql = ("SELECT id, outputs FROM tasks WHERE type = 'approval' "
               "AND doc_ref_type = ? AND doc_ref = ? AND status = 'done'")
        params = (doc_ref_type, task["doc_ref"])
    for row in data_source.execute(sql, params).fetchall():
        outputs = _load_json(row[1], {})
        if str((outputs or {}).get("decision") or "") == "approve":
            raise TaskWithdrawError(
                "单据已存在有效审批通过（任务 %s），不能撤回" % row[0])


def withdraw_task(data_source, task_id: str, *, actor: str,
                  actor_kind: str = "human", reason: str = "",
                  occurred_at: Any = None) -> Dict[str, Any]:
    """提交人撤回在途审批：单据回退 → 任务 cancelled。

    Raises:
        TaskNotFoundError: 任务不存在（404）
        TaskWithdrawPermissionError: 非提交人（403）
        TaskWithdrawError: 非审批任务 / 状态不可撤回 / 单据回退失败（409）
        TaskTransitionError: 迁移结构或守卫不通过（409）
    """
    task = _load_task(data_source, str(task_id))
    if task["type"] != "approval":
        raise TaskWithdrawError(
            "非审批任务不能撤回（请使用 cancel）：type=%s" % (task["type"] or ""))
    if task["status"] not in WITHDRAWABLE_STATES:
        raise TaskWithdrawError("当前状态不可撤回：%s" % (task["status"] or ""))
    if not actor or str(actor) != str(task["created_by"]):
        raise TaskWithdrawPermissionError("仅提交人可撤回审批")
    if not task["doc_ref_id"] and not task["doc_ref"]:
        raise TaskWithdrawError("审批任务缺少单据引用，无法回退")

    _ensure_no_approved(data_source, task)

    attempt = int(task["attempt"] or 1)
    idem_key = "%s:withdraw" % build_effect_key(str(task["id"]), attempt)

    def _rollback(_ds):
        receipt = withdraw_approval(task["doc_ref_type"], task["doc_ref_id"])
        if not receipt.get("success"):
            raise TaskWithdrawError(
                receipt.get("message") or "单据回退未生效")
        return receipt.get("data") or {}

    wrapped = run_idempotent(
        data_source, idem_key, _rollback,
        scope="task_attempt", task_id=str(task["id"]),
        workflow_run_id=task["workflow_run_id"], attempt=attempt,
    )
    document = wrapped.get("result") or {}

    outcome = cancel_task(
        data_source, str(task["id"]), actor=actor, actor_kind=actor_kind,
        reason=reason or "提交人撤回审批（单据回退）", occurred_at=occurred_at)

    return {
        "task_id": task["id"],
        "status": outcome["status"],
        "from_status": outcome["from_status"],
        "event_id": outcome["event_id"],
        "doc_ref_type": task["doc_ref_type"],
        "doc_ref_id": task["doc_ref_id"],
        "document": document,
        "idempotent": wrapped.get("status") == "duplicate",
        "withdrawn_at": _now_iso(),
    }
