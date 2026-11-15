# -*- coding: utf-8 -*-
"""[M4-2 2026-11-15] 参与归并与会签（任务域通用能力，spec §8.3）

分层纪律（spec §8.0 / §8.3 / R8）:
- 「谁能做」真源 = `tasks.executor_candidates`；`task_participations` 只记「谁做了什么」。
  加签必须与 candidates **同一函数同一事务**双写，否则两个答案漂移。
- 完成口径 = `tasks.executor_config.completion_mode`（`any` 默认 / `all` 会签），
  归并在参与流水层完成：不新增任务状态、不新增批次表、不复制真源。
- `all` 未齐 ⇒ 200 `{status:'partially_approved', remaining, votes}`，**不调 BO、不改任务状态**；
  协议本体（`decide_and_apply`）不改，只在命中归并时调用一次。
- 非 `approval` / `review` 任务同样支持 `all` 归并，但**不调 BO**（任务域通用能力，R11）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.decision_effect import (
    EFFECT_TASK_TYPES,
    DecisionEffectError,
    decide_and_apply,
    normalize_decision,
)
from meta.core.task_delegation import active_delegators_for, delegation_tables_exist
from meta.core.task_event_schema import record_worklog
from meta.core.task_participation import (
    NOTIFY_ROLE,
    PARTICIPATION_TABLE,
    ParticipationError,
    VOTING_ROLES,
    add_participation,
    list_participations,
    participation_tables_exist,
    pending_participants,
    record_outcome,
    skip_other_pending,
)
from meta.services.task_stage import advance_stage

logger = logging.getLogger(__name__)

COMPLETION_MODES = ("any", "all")
DEFAULT_COMPLETION_MODE = "any"
TERMINAL_STATUSES = ("done", "failed", "cancelled", "skipped", "dead")
DECIDED_OUTCOMES = ("accepted", "rejected", "skipped")

#: 归并所需的任务列（读路径唯一清单，避免 SELECT * 在旧库上缺列）
_TASK_COLUMNS = ("id", "title", "type", "status", "executor_config",
                 "executor_candidates", "executor_assignee", "created_by",
                 "doc_ref", "doc_ref_type", "app_id", "workflow_run_id",
                 "trace_id", "updated_at")


class ParticipationServiceError(Exception):
    """参与服务基类（HTTP 语义由 API 层映射）。"""


class ParticipationNotFoundError(ParticipationServiceError):
    """任务不存在。"""


class ParticipationPermissionError(ParticipationServiceError):
    """未登录 / 无任务准入。"""


class ParticipationConflictError(ParticipationServiceError):
    """终态、重复投票、四眼等冲突（409）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 读路径
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_task(data_source, task_id: str) -> Optional[Dict[str, Any]]:
    rows = data_source.execute(
        "SELECT {0} FROM tasks WHERE id = ?".format(", ".join(_TASK_COLUMNS)),
        (str(task_id),),
    ).fetchall()
    if not rows:
        return None
    return dict(zip(_TASK_COLUMNS, rows[0]))


def _read_config(task: Dict[str, Any]) -> Dict[str, Any]:
    config = task.get("executor_config")
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (TypeError, ValueError):
            config = {}
    return config if isinstance(config, dict) else {}


def completion_mode(task: Dict[str, Any]) -> str:
    """完成口径（`executor_config.completion_mode`，缺省 `any`）。"""
    mode = str(_read_config(task).get("completion_mode") or DEFAULT_COMPLETION_MODE)
    mode = mode.strip().lower()
    return mode if mode in COMPLETION_MODES else DEFAULT_COMPLETION_MODE


def quorum_required(task: Dict[str, Any]) -> Optional[int]:
    """通过票数下限（`executor_config.quorum_required`，spec §9.4）；无声明返回 None。"""
    raw = _read_config(task).get("quorum_required")
    try:
        required = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return required if required > 0 else None


def _accepted_votes(rows: List[Dict[str, Any]], candidates: List[str]) -> int:
    """当前候选池内的「通过」票数（每人取最新一行，旧阶段行不计）。"""
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        latest[row["participant"]] = row
    pool = set(candidates)
    return sum(1 for name, row in latest.items()
               if name in pool and row["outcome"] == "accepted")


def _read_candidates(task: Dict[str, Any]) -> List[str]:
    raw = task.get("executor_candidates")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = []
    if not isinstance(raw, (list, tuple)):
        return []
    seen: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _table_ready(data_source) -> bool:
    return bool(participation_tables_exist(data_source).get(PARTICIPATION_TABLE))


def _delegation_ready(data_source) -> bool:
    return bool(delegation_tables_exist(data_source).get("task_delegations"))


def _last_pending(rows: List[Dict[str, Any]], participant: str) -> Optional[Dict[str, Any]]:
    latest = None
    for row in rows:
        if row["participant"] == participant:
            latest = row
    # [M5-4] 知会行只读：不参与决策（role=notify 视同无待决）
    if latest is not None and latest["outcome"] == "pending" \
            and latest["role"] in VOTING_ROLES:
        return latest
    return None


def _delegators(data_source, actor: str, task: Dict[str, Any],
                *, now: Any = None) -> List[str]:
    if not _delegation_ready(data_source):
        return []
    try:
        return active_delegators_for(data_source, actor, task, now=now)
    except Exception:  # noqa: BLE001 - 委托不可读按无委托处理，不阻断投票
        logger.warning("[M4-2] 委托展开失败（按无委托处理）", exc_info=True)
        return [] 


def _votes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "participant": row["participant"],
            "outcome": row["outcome"],
            "decided_by": row.get("decided_by") or "",
            "on_behalf_of": row.get("on_behalf_of") or "",
            "comment": row.get("comment") or "",
            "decided_at": row.get("decided_at") or "",
        }
        for row in rows
        if row["outcome"] in DECIDED_OUTCOMES
    ]


def participations_view(data_source, task_id: str, *,
                        task: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """参与人进度（抽屉用）：参与行 + counts + remaining，表缺失按空降级。"""
    task = task or _load_task(data_source, task_id)
    if not task:
        raise ParticipationNotFoundError(f"任务不存在: {task_id}")
    rows = list_participations(data_source, task_id) if _table_ready(data_source) else []
    counts = {outcome: 0 for outcome in
              ("pending", "accepted", "rejected", "skipped", "transferred")}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    remaining = [row["participant"] for row in rows
                 if row["role"] in VOTING_ROLES and row["outcome"] == "pending"]
    return {
        "task_id": str(task_id),
        "completion_mode": completion_mode(task),
        "participants": rows,
        "counts": counts,
        "remaining": remaining,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 加签（M4-2）
# ─────────────────────────────────────────────────────────────────────────────

def _set_completion_mode(data_source, task_id: str, task: Dict[str, Any],
                         mode: str, actor: str, ts: str) -> bool:
    """require_all=true 时改 completion_mode（一次写入 + worklog）；已是目标值不写。"""
    current = completion_mode(task)
    if current == mode:
        return False
    config = _read_config(task)
    config["completion_mode"] = mode
    data_source.execute(
        "UPDATE tasks SET executor_config = ?, updated_at = ? WHERE id = ?",
        (json.dumps(config, ensure_ascii=False, default=str), ts, str(task_id)),
    )
    try:
        record_worklog(
            data_source, task_id=str(task_id), entry_type="note",
            summary="加签要求全员会签",
            detail={"action": "completion_mode", "from": current, "to": mode},
            actor=actor, actor_kind="human",
            workflow_run_id=str(task.get("workflow_run_id") or ""),
            doc_ref=str(task.get("doc_ref") or ""),
            trace_id=str(task.get("trace_id") or ""),
            occurred_at=ts,
        )
    except Exception:  # noqa: BLE001 - worklog 表缺失不阻断加签
        logger.warning("[M4-2] completion_mode 变更 worklog 写入失败: %s",
                       task_id, exc_info=True)
    return True


def participate(data_source, task_id: str, *, actor: str,
                participant: Optional[str] = None, comment: str = "",
                require_all: bool = False, admin: bool = False,
                now: Any = None) -> Dict[str, Any]:
    """加签：新增 `role='added', outcome='pending'` 行并与 candidates 双写。

    Returns: 参与人进度（同 `participations_view`）。

    Raises:
        ParticipationPermissionError: 未登录 / 无准入 / 代他人加签非 admin
        ParticipationNotFoundError:   任务不存在
        ParticipationConflictError:   终态 / 重复加签
    """
    actor = str(actor or "").strip()
    if not actor:
        raise ParticipationPermissionError("未登录")
    task = _load_task(data_source, task_id)
    if not task:
        raise ParticipationNotFoundError(f"任务不存在: {task_id}")
    if not _table_ready(data_source):
        raise ParticipationConflictError("参与流水表未初始化（请先执行迁移 v277）")
    if task["status"] in TERMINAL_STATUSES:
        raise ParticipationConflictError(f"任务已终态（{task['status']}），不能加签")

    target = str(participant or actor).strip()
    if not target:
        raise ParticipationPermissionError("participant 不能为空")

    rows = list_participations(data_source, task_id)
    # [P0] notify 只读：知会行不计准入，不能加签
    voting_rows = [row for row in rows if row["role"] in VOTING_ROLES]
    admitted = admin or any(row["participant"] == actor for row in voting_rows)
    if not admitted:
        admitted = bool(_delegators(data_source, actor, task, now=now))
    if not admitted and any(row["participant"] == actor for row in rows):
        raise ParticipationPermissionError("知会人只读，不能加签")
    if not admitted:
        raise ParticipationPermissionError("无该任务准入，不能加签")

    already = any(row["participant"] == target for row in rows)
    if already and participant is not None:
        raise ParticipationConflictError(f"{target} 已在参与人列表中")
    if already and not require_all:
        raise ParticipationConflictError(f"{target} 已是待决参与人，不能重复加签")

    ts = now or _now_iso()
    with data_source.transaction():
        if not already:
            try:
                add_participation(data_source, task_id, target, role="added",
                                  comment=comment, created_by=actor, now=ts)
            except ParticipationError as e:
                raise ParticipationConflictError(str(e)) from e
        # R8 双写：candidates 是唯一分配真源，加签追加而非替换
        candidates = _read_candidates(task)
        if target not in candidates:
            candidates.append(target)
            data_source.execute(
                "UPDATE tasks SET executor_candidates = ?, updated_at = ? WHERE id = ?",
                (json.dumps(candidates, ensure_ascii=False), ts, str(task_id)),
            )
        if require_all:
            _set_completion_mode(data_source, task_id, task, "all", actor, ts)
    return participations_view(data_source, task_id)


# ─────────────────────────────────────────────────────────────────────────────
# 决策归并（M4-2）
# ─────────────────────────────────────────────────────────────────────────────

def decide_with_participation(data_source, task_id: str, *, decision: str,
                              comment: str = "", actor: str = "",
                              reviewer_permission: Optional[bool] = None,
                              allow_rework: bool = False, admin: bool = False,
                              now: Any = None) -> Dict[str, Any]:
    """按 completion_mode 归并后提交决策；返回协议结果或 partial 结果。

    与 `decide_and_apply` 的差异只在「`all` 未齐」：返回
    `{status:'partially_approved', remaining, votes}` 且无任何副作用。
    参与表缺失或任务无参与行时完全退回协议本体（既有语义不变）。
    """
    decision = normalize_decision(decision)
    task = _load_task(data_source, task_id)
    legacy = dict(
        decision=decision, comment=comment, actor=actor, actor_kind="human",
        reviewer_permission=reviewer_permission, allow_rework=allow_rework,
    )
    if not task or not _table_ready(data_source):
        return decide_and_apply(data_source, str(task_id), **legacy)
    if task["status"] in TERMINAL_STATUSES:
        raise ParticipationConflictError(f"任务已终态（{task['status']}）")

    rows = list_participations(data_source, task_id)
    is_effect_task = task["type"] in EFFECT_TASK_TYPES
    targets: List[Tuple[str, str]] = []   # (participant, on_behalf_of)
    if actor and _last_pending(rows, actor) is not None:
        targets = [(actor, "")]
    elif admin:
        # 管理员不进归并：沿用协议短路（admin 逃生口，与 D-AP-06 一致）
        return decide_and_apply(data_source, str(task_id), **legacy)
    else:
        # [P0] notify 只读：知会人不是投票参与人
        if any(row["participant"] == actor and row["role"] == NOTIFY_ROLE
               for row in rows):
            raise ParticipationConflictError("知会人只读，不能投票")
        for delegator in _delegators(data_source, actor, task, now=now):
            if _last_pending(rows, delegator) is not None:
                targets.append((delegator, delegator))
        if not targets:
            raise ParticipationConflictError("非该任务参与人，不能投票")
        if is_effect_task and task.get("created_by") and task["created_by"] == actor:
            raise ParticipationConflictError("四眼约束：提交人不能代投票（委托无效）")

    if is_effect_task and reviewer_permission is not True:
        raise ParticipationPermissionError(
            f"缺少审批权限 {task.get('doc_ref_type') or '?'}:approve（D-AP-06）")

    ts = now or _now_iso()
    mode = completion_mode(task)
    required = quorum_required(task)
    with data_source.transaction():
        for participant, on_behalf in targets:
            try:
                record_outcome(
                    data_source, task_id, participant,
                    "accepted" if decision == "approve" else "rejected",
                    comment=comment, decided_by=actor,
                    on_behalf_of=on_behalf, now=ts,
                )
            except ParticipationError as e:
                raise ParticipationConflictError(str(e)) from e
        if decision == "reject":
            skip_other_pending(data_source, task_id, now=ts)

        remaining = pending_participants(data_source, task_id)
        # [P1] quorum：有下限时按票数判定；否则按 approve_mode 结算（spec §9.4）
        if required:
            met = _accepted_votes(
                list_participations(data_source, task_id),
                _read_candidates(task)) >= required
        else:
            met = not (mode == "all" and remaining)
        advanced: Optional[Dict[str, Any]] = None
        if decision == "approve" and met and remaining and (mode == "all" or required):
            # 阶段已通过但仍有未投票者：一并作废，避免残留待办
            skip_other_pending(data_source, task_id, roles=VOTING_ROLES, now=ts)
        if decision == "approve" and met:
            # [M5-3] 本阶段已通过：有下一阶段则原地推进（不落终态、不调 BO）
            advanced = advance_stage(data_source, task, actor=actor, now=ts)
        if decision == "approve" and not met:
            outcome: Dict[str, Any] = {
                "status": "partially_approved",
                "task_status": task["status"],
                "decision": decision,
                "remaining": remaining,
            }
            if required:
                outcome["quorum_required"] = required
        elif advanced is not None:
            outcome = advanced
        elif is_effect_task:
            outcome = dict(decide_and_apply(data_source, str(task_id), **legacy))
            outcome.setdefault("status", "completed")
            outcome.setdefault("remaining", [])
        else:
            outcome = {
                "status": "completed",
                "task_status": task["status"],
                "decision": decision,
                "effect_applied": False,
                "remaining": [],
            }
        outcome["votes"] = _votes(list_participations(data_source, task_id))
    return outcome