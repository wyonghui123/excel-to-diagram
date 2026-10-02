# -*- coding: utf-8 -*-
"""[A4 2026-10-02] 分配与认领 — direct / claim 两策略（§8.2 / §12.1 A4）

职责:
- 把 A1（字段）+ A2（迁移与守卫）+ A3（事件账）**拼成可调用的派工服务**：
  ready 时按 `assign_policy` 投递、认领时校验候选池并锁定认领人、超时未开始回收、
  候选池反查（支撑 Agent Worker 轮询，§8.2）。
- 范围收口（§13 R5）：只开 `direct` / `claim`；`round_robin` / `skill_based` /
  `ai_routed` 数据成熟度未到，一律 fail-closed 拒绝，不做半成品。

分层纪律:
- 不新建表、不改 A1 schema：状态复用 tasks 既有列（`executor_assignee` /
  `executor_candidates` / `assign_policy` / `claim_timeout_seconds`）。
- 迁移一律走 A2 `require_transition`（守卫 fail-closed）；落账走 A3
  `record_transition`（一事件 + 一工作日志）。
- 认领时间不新增列：由 A3 `ready→claimed` 事件的 `occurred_at` 提供（append-only 可靠）。
- 并发抢单用条件 UPDATE（`WHERE status='ready'`）+ rowcount 判定，防两方同时锁定。

待办（有意留白，勿臆造）:
- 候选池中的「组」展开依赖用户/角色系统（§12.1 有意不建模组织）。本轮按**字面命中**
  （candidates 直接含 actor_id）实现；组展开待 A8 / 权限体系接入时补。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §8.2 / §12.1 A4 / §13 R5
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.task_event_schema import record_transition
from meta.core.task_schema import TASK_TABLE
from meta.core.task_state_machine import (
    TransitionContext, evaluate_transition, require_transition,
)

# 本轮开启 / 关闸的策略（§13 R5：先上 direct/claim，其余按数据成熟度逐级开）
ENABLED_POLICIES = ("direct", "claim")
DEFERRED_POLICIES = ("round_robin", "skill_based", "ai_routed")

DEFAULT_ASSIGN_POLICY = "direct"
DEFAULT_CLAIM_TIMEOUT_SECONDS = 300


class AssignmentError(Exception):
    """分配 / 认领前置不满足（策略关闸、候选池未命中、并发被抢占……）。"""


_TASK_COLUMNS = (
    "id", "title", "status", "executor_type", "executor_assignee",
    "executor_candidates", "assign_policy", "claim_timeout_seconds",
    "workflow_run_id", "trace_id", "agent_session_id", "doc_ref", "line_refs",
    "updated_at",
)


# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


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
        raise AssignmentError(f"任务不存在：{task_id}")
    r = rows[0]
    return {
        "id": r[0], "title": r[1], "status": r[2], "executor_type": r[3],
        "executor_assignee": r[4] or "",
        "executor_candidates": _load_json(r[5], []),
        "assign_policy": r[6] or DEFAULT_ASSIGN_POLICY,
        "claim_timeout_seconds": r[7], "workflow_run_id": r[8] or "",
        "trace_id": r[9] or "", "agent_session_id": r[10] or "",
        "doc_ref": r[11] or "", "line_refs": _load_json(r[12], None),
    }


def _require_enabled_policy(policy: str) -> str:
    """策略门禁：未开启 / 未知 → 拒绝（fail-closed，§13 R5）。"""
    if policy in DEFERRED_POLICIES:
        raise AssignmentError(
            f"分配策略 {policy!r} 尚未开启（§13 R5：按数据成熟度逐级开；"
            f"当前仅 {'/'.join(ENABLED_POLICIES)}）"
        )
    if policy not in ENABLED_POLICIES:
        raise AssignmentError(
            f"未知分配策略：{policy!r}（合法值：{ENABLED_POLICIES + DEFERRED_POLICIES}）"
        )
    return policy


def _candidates(task: Dict[str, Any]) -> List[str]:
    raw = task.get("executor_candidates")
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = []
        for key in ("users", "agents", "groups"):
            value = raw.get(key) or []
            items.extend(value if isinstance(value, list) else [value])
    else:
        items = []
    return [str(x) for x in items]


def is_candidate(task: Dict[str, Any], actor_id: str) -> bool:
    """认领人是否在候选池内。

    TODO: 组（candidate group）展开依赖用户/角色系统（§12.1 不建模组织），
    当前仅按字面命中 actor_id；待 A8 / 权限体系接入后补 group 展开。
    """
    return str(actor_id) in _candidates(task)


def _persist_claim(data_source, task_id: str, assignee: str) -> bool:
    """条件抢单：仅当仍为 ready 时锁定，返回是否抢到（防并发双锁）。"""
    cursor = data_source.execute(
        f"UPDATE {TASK_TABLE} SET status = 'claimed', executor_assignee = ?, "
        f"updated_at = ? WHERE id = ? AND status = 'ready'",
        (str(assignee), _now_iso(), str(task_id)),
    )
    rowcount = getattr(cursor, "rowcount", None)
    if rowcount is not None:
        return rowcount > 0
    # 驱动不返回 rowcount：回读复核（fail-closed，避免把失败当成功 → 双认领）
    rows = data_source.execute(
        f"SELECT status, executor_assignee FROM {TASK_TABLE} WHERE id = ?",
        (str(task_id),),
    ).fetchall()
    return bool(rows) and rows[0][0] == "claimed" and (rows[0][1] or "") == str(assignee)


def _persist_release(data_source, task_id: str) -> bool:
    """回收：claimed → ready，并清空 assignee。"""
    cursor = data_source.execute(
        f"UPDATE {TASK_TABLE} SET status = 'ready', executor_assignee = NULL, "
        f"updated_at = ? WHERE id = ? AND status = 'claimed'",
        (_now_iso(), str(task_id)),
    )
    rowcount = getattr(cursor, "rowcount", None)
    if rowcount is not None:
        return rowcount > 0
    rows = data_source.execute(
        f"SELECT status FROM {TASK_TABLE} WHERE id = ?", (str(task_id),)
    ).fetchall()
    return bool(rows) and rows[0][0] == "ready"


def _last_claim_at(data_source, task_id: str) -> Optional[datetime]:
    """取最近一次 ready→claimed 的业务时间（认领时间，从 A3 事件账反查）。"""
    rows = data_source.execute(
        "SELECT occurred_at FROM task_events "
        "WHERE task_id = ? AND from_status = 'ready' AND to_status = 'claimed' "
        "ORDER BY occurred_at DESC, created_at DESC LIMIT 1",
        (str(task_id),),
    ).fetchall()
    return _parse_dt(rows[0][0]) if rows else None


def _result(task: Dict[str, Any], *, status: str, assignee: str,
            policy: str) -> Dict[str, Any]:
    return {
        "task_id": task["id"], "status": status,
        "assignee": assignee or None, "policy": policy,
        "candidates": _candidates(task),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 投递（引擎在任务进入 ready 时调用）
# ─────────────────────────────────────────────────────────────────────────────

def resolve_assignment(data_source, task_id: str, *, now: Any = None) -> Dict[str, Any]:
    """按 `assign_policy` 投递（§8.2 决策树）。

    - `direct`：锁定 `executor_assignee`，ready→claimed；
    - `claim`：投递候选池，保持 ready（不锁人）；
    - 其余策略：拒绝（未开启）。
    """
    task = _load_task(data_source, task_id)
    if task["status"] != "ready":
        raise AssignmentError(f"任务非 ready，无法投递：{task['status']}")
    policy = _require_enabled_policy(task["assign_policy"])

    if policy == "claim":
        # 投递候选池：只需任务处于 ready，等人认领
        return _result(task, status="ready", assignee="", policy=policy)

    assignee = task["executor_assignee"]
    if not assignee:
        raise AssignmentError("direct 策略要求 executor_assignee 非空")

    require_transition(
        "ready", "claimed",
        TransitionContext(actor=assignee, actor_kind="system", assign_policy_hit=True),
    )
    with data_source.transaction():
        if not _persist_claim(data_source, task["id"], assignee):
            raise AssignmentError("任务已被他人认领（并发抢占）")
        record_transition(
            data_source, task_id=task["id"], from_status="ready", to_status="claimed",
            actor=assignee, actor_kind="system", reason="direct 自动分派",
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
            occurred_at=now,
        )
    return _result(task, status="claimed", assignee=assignee, policy=policy)


# ─────────────────────────────────────────────────────────────────────────────
# 认领（人或 Agent 主动抢单）
# ─────────────────────────────────────────────────────────────────────────────

def claim_task(data_source, task_id: str, actor_id: str, *,
               actor_kind: str = "human", now: Any = None) -> Dict[str, Any]:
    """候选池抢单：命中 → ready→claimed 并锁定认领人（人 / Agent 同一通道）。"""
    if not actor_id:
        raise AssignmentError("认领人不能为空")

    task = _load_task(data_source, task_id)
    if task["status"] != "ready":
        raise AssignmentError(f"任务非 ready，无法认领：{task['status']}")
    policy = _require_enabled_policy(task["assign_policy"])
    if policy != "claim":
        raise AssignmentError(f"策略 {policy!r} 不可抢单（direct 由引擎锁定）")
    if not is_candidate(task, actor_id):
        raise AssignmentError(f"{actor_id} 不在候选池 {_candidates(task)}")

    require_transition(
        "ready", "claimed",
        TransitionContext(actor=actor_id, actor_kind=actor_kind, actor_in_candidates=True),
    )
    with data_source.transaction():
        if not _persist_claim(data_source, task["id"], actor_id):
            raise AssignmentError("任务已被他人认领（并发抢占）")
        record_transition(
            data_source, task_id=task["id"], from_status="ready", to_status="claimed",
            actor=actor_id, actor_kind=actor_kind, reason="候选池认领",
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
            occurred_at=now,
        )
    return _result(task, status="claimed", assignee=actor_id, policy=policy)


# ─────────────────────────────────────────────────────────────────────────────
# 超时回收 / 候选池反查
# ─────────────────────────────────────────────────────────────────────────────

def reclaim_expired(data_source, *, now: Any = None) -> List[Dict[str, Any]]:
    """回收超时未开始的认领（claimed→ready，§7.2 `claim_timed_out`）。

    仅处理 `assign_policy=claim` 的 claimed 任务；认领时间取 A3 事件。
    返回被回收清单（空 = 无）。
    """
    now_dt = _parse_dt(now) or datetime.now()
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} "
        "WHERE status = 'claimed' AND assign_policy = 'claim'"
    ).fetchall()

    reclaimed: List[Dict[str, Any]] = []
    for r in rows:
        task_id = r[0]
        claimed_at = _last_claim_at(data_source, task_id)
        if claimed_at is None:
            # 经非 claim_task 路径进入 claimed（无 ready→claimed 事件）：
            # 回退 tasks.updated_at（认领锁定时的写入时间），仍为空才跳过（不臆造时间）
            claimed_at = _parse_dt(r[13])
            if claimed_at is None:
                continue
        timeout = r[7] if r[7] is not None else DEFAULT_CLAIM_TIMEOUT_SECONDS
        elapsed = (now_dt - claimed_at).total_seconds()

        # 扫描场景：未超时是常态，只跳过不抛错（守卫仍 fail-closed 决定放行与否）
        gate = evaluate_transition(
            "claimed", "ready",
            TransitionContext(claim_elapsed_seconds=elapsed,
                              claim_timeout_seconds=float(timeout)),
        )
        if not gate.ok:
            continue
        with data_source.transaction():
            if not _persist_release(data_source, task_id):
                continue  # 已被其他路径处理
            record_transition(
                data_source, task_id=task_id, from_status="claimed", to_status="ready",
                actor="system", actor_kind="system", reason="认领超时自动回收",
                workflow_run_id=r[8] or "", trace_id=r[9] or "",
                occurred_at=now,
            )
        reclaimed.append({
            "task_id": task_id, "assignee": r[4] or None,
            "elapsed_seconds": elapsed, "timeout_seconds": float(timeout),
        })
    return reclaimed


def list_claimable(data_source, actor_id: str) -> List[Dict[str, Any]]:
    """候选池反查：返回该执行者可认领的 ready 任务（Agent Worker 轮询入口）。"""
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} "
        "WHERE status = 'ready' AND assign_policy = 'claim' ORDER BY created_at"
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        task = {
            "id": r[0], "title": r[1], "status": r[2], "executor_type": r[3],
            "executor_assignee": r[4] or "",
            "executor_candidates": _load_json(r[5], []),
            "assign_policy": r[6] or DEFAULT_ASSIGN_POLICY,
            "claim_timeout_seconds": r[7],
        }
        if is_candidate(task, actor_id):
            out.append({
                "task_id": task["id"], "title": task["title"],
                "executor_type": task["executor_type"],
                "candidates": _candidates(task),
            })
    return out