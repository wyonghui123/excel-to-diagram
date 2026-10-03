# -*- coding: utf-8 -*-
"""[A8 2026-10-02] 统一收件箱 — 跨应用待办聚合（只读派生，不落列）

职责（§12.1 A8 / §9.4）:
- 人工 executor 的**唯一入口**：一个列表聚合「待录入 / 待确认 / 待审核 /
  Agent 移交 / SLA 告警」（§9.4），按桶与 type 分组供前端复用。
- **行级可见性过滤是验收硬项**（§12.1「五」Q1 派生）：任务落平台库即跨应用
  共享，无过滤即越权可见。判据 fail-closed：actor 为空 → 不可见。

分层纪律:
- 只读：不新建表、不写任何列；buckets / primary_bucket 一律**派生**不落列。
- 分区机器派生：alert（SLA 梯队越线）/ approval（待审）/ todo（名下活跃）/
  agent_handoff（人工任务 + Agent 会话上下文）/ claimable（候选池可抢）。
- 不臆造权限表：角色→应用授权映射由调用方显式传入（role_apps + actor_roles），
  用户/角色系统接入后替换数据来源即可。

待办（有意留白，勿臆造）:
- 组（candidate group）展开依赖用户/角色系统（§12.1 不建模组织），沿 A4
  `is_candidate` 的**字面命中**口径；待权限体系接入后统一补。
- v1 全表扫描 + 内存过滤（收件箱量级小）；量大后下沉 SQL + 索引。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.4 / §12.1 A8 /
  §12.1「五」Q1（行级可见性过滤硬项）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from meta.core.sla_ladder import RUNG_WARN, ladder_status
from meta.core.task_assignment import is_candidate
from meta.core.task_schema import TASK_TABLE

logger = logging.getLogger(__name__)

# 分区（顺序即 primary_bucket 优先级：越紧急越靠前）
BUCKETS: Tuple[str, ...] = (
    "alert", "approval", "todo", "agent_handoff", "claimable",
)

# 名下活跃（待办口径）；waiting_approval 是「等别人」不进 todo
TODO_STATUSES = ("ready", "claimed", "in_progress", "blocked")
# 待审口径（审核任务可能在等待审批态等审核人）
APPROVAL_STATUSES = TODO_STATUSES + ("waiting_approval",)

DEFAULT_LIMIT = 50

_TASK_COLUMNS = (
    "id", "title", "type", "status", "priority", "app_id",
    "executor_type", "executor_assignee", "executor_candidates",
    "assign_policy", "due_at", "created_by", "updated_at",
    "agent_session_id", "workflow_run_id", "doc_ref",
)


# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────

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


def _row_to_task(r) -> Dict[str, Any]:
    return {
        "id": r[0], "title": r[1], "type": r[2], "status": r[3],
        "priority": r[4], "app_id": r[5] or "",
        "executor_type": r[6] or "human",
        "executor_assignee": r[7] or "",
        "executor_candidates": _load_json(r[8], []),
        "assign_policy": r[9] or "direct",
        "due_at": r[10] or "", "created_by": r[11] or "",
        "updated_at": r[12] or "", "agent_session_id": r[13] or "",
        "workflow_run_id": r[14] or "", "doc_ref": r[15] or "",
    }


def _alerts_by_task(data_source, *, now: datetime) -> Dict[str, Dict[str, Any]]:
    """活跃 SLA 中已越线（rung >= warn）的任务 → 最高梯级告警（只读）。"""
    try:
        statuses = ladder_status(data_source, now=now)
    except Exception as e:  # SLA 表缺失等 → 按无告警降级（收件箱不因告警侧崩）
        logger.warning("[A8] SLA 梯队扫描失败（按无告警处理）：%s", e)
        return {}
    alerts: Dict[str, Dict[str, Any]] = {}
    for item in statuses:
        if int(item.get("rung") or 0) < RUNG_WARN:
            continue
        task_id = item["task_id"]
        current = alerts.get(task_id)
        if current is None or item["rung"] > current["rung"]:
            alerts[task_id] = {
                "rung": item["rung"], "rung_name": item["rung_name"],
                "pct_used": item.get("pct_used"),
            }
    return alerts


def _visible(task: Dict[str, Any], *, actor: Optional[str],
             role_apps: Optional[Dict[str, Iterable[str]]],
             actor_roles: Optional[Iterable[str]]) -> bool:
    """行级可见性（fail-closed）：分配者 / 候选 / 创建者 / 角色→应用授权。"""
    if not actor:
        return False
    if task["executor_assignee"] == actor:
        return True
    if task["created_by"] == actor:
        return True
    if is_candidate(task, actor):
        return True
    if role_apps and actor_roles:
        for role in actor_roles:
            if task["app_id"] and task["app_id"] in (role_apps.get(role) or []):
                return True
    return False


def _derive_buckets(task: Dict[str, Any], *, actor: Optional[str],
                    alert: Optional[Dict[str, Any]]) -> List[str]:
    """派生所属分区（按 BUCKETS 顺序；每任务仍只出一条 entry）。"""
    out: List[str] = []
    status = task["status"]
    is_assignee = bool(actor) and task["executor_assignee"] == actor

    if alert:
        out.append("alert")
    if is_assignee and task["type"] == "approval" and status in APPROVAL_STATUSES:
        out.append("approval")
    if is_assignee and status in TODO_STATUSES:
        out.append("todo")
    if (is_assignee and task["executor_type"] == "human"
            and task["agent_session_id"] and status in TODO_STATUSES):
        out.append("agent_handoff")
    if (status == "ready" and task["assign_policy"] == "claim"
            and is_candidate(task, actor or "")):
        out.append("claimable")
    return out


def _entry(task: Dict[str, Any], *, buckets: List[str],
           alert: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "task_id": task["id"], "title": task["title"], "type": task["type"],
        "status": task["status"], "priority": task["priority"],
        "app_id": task["app_id"] or None,
        "assignee": task["executor_assignee"] or None,
        "executor_type": task["executor_type"],
        "due_at": task["due_at"] or None,
        "updated_at": task["updated_at"] or None,
        "doc_ref": task["doc_ref"] or None,
        "workflow_run_id": task["workflow_run_id"] or None,
        "buckets": buckets,
        "primary_bucket": buckets[0],
        "is_handoff": "agent_handoff" in buckets,
        "alert": alert,
    }


def _sort_key(entry: Dict[str, Any]):
    updated = _parse_dt(entry["updated_at"])
    due = _parse_dt(entry["due_at"])
    updated_key = -updated.timestamp() if updated else float("inf")
    due_key = due.timestamp() if due else float("inf")
    return (updated_key, due_key)


def _collect(data_source, *, actor: Optional[str],
             role_apps: Optional[Dict[str, Iterable[str]]],
             actor_roles: Optional[Iterable[str]],
             app_id: Optional[str], now_dt: datetime) -> List[Dict[str, Any]]:
    alerts = _alerts_by_task(data_source, now=now_dt)
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE}"
    ).fetchall()

    entries: List[Dict[str, Any]] = []
    for r in rows:
        task = _row_to_task(r)
        if app_id and task["app_id"] != app_id:
            continue
        if not _visible(task, actor=actor, role_apps=role_apps,
                        actor_roles=actor_roles):
            continue
        alert = alerts.get(task["id"])
        buckets = _derive_buckets(task, actor=actor, alert=alert)
        if not buckets:
            continue  # 与我无待办关系（终态 / 未就绪 / 纯粹他人任务）
        entries.append(_entry(task, buckets=buckets, alert=alert))
    entries.sort(key=_sort_key)
    return entries


def _counts(entries: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {b: 0 for b in BUCKETS}
    for e in entries:
        for b in e["buckets"]:
            counts[b] += 1
    counts["total"] = len(entries)
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# 读 API（供 REST / IM / 前端复用）
# ─────────────────────────────────────────────────────────────────────────────

def inbox_query(data_source, *, actor: Optional[str],
                role_apps: Optional[Dict[str, Iterable[str]]] = None,
                actor_roles: Optional[Iterable[str]] = None,
                app_id: Optional[str] = None, bucket: Optional[str] = None,
                limit: Optional[int] = DEFAULT_LIMIT,
                now: Any = None) -> Dict[str, Any]:
    """统一收件箱查询：返回 entries（每任务一条）+ 分区计数。

    - `bucket` 过滤只收窄返回列表；counts 始终是全量口径（角标不因过滤失真）。
    - `app_id` 只作收窄；可见性以 `_visible`（fail-closed）为准。
    """
    if bucket is not None and bucket not in BUCKETS:
        raise ValueError(f"未知收件箱分区：{bucket!r}（合法值：{BUCKETS}）")
    now_dt = now if isinstance(now, datetime) else datetime.now()

    entries = _collect(data_source, actor=actor, role_apps=role_apps,
                       actor_roles=actor_roles, app_id=app_id, now_dt=now_dt)
    counts = _counts(entries)

    if bucket:
        entries = [e for e in entries if bucket in e["buckets"]]
    if limit is not None:
        entries = entries[:limit]

    return {"entries": entries, "counts": counts, "total": counts["total"]}


def inbox_counts(data_source, *, actor: Optional[str],
                 role_apps: Optional[Dict[str, Iterable[str]]] = None,
                 actor_roles: Optional[Iterable[str]] = None,
                 app_id: Optional[str] = None,
                 now: Any = None) -> Dict[str, int]:
    """只读分区角标（全量口径，等价于 inbox_query 的 counts）。"""
    now_dt = now if isinstance(now, datetime) else datetime.now()
    entries = _collect(data_source, actor=actor, role_apps=role_apps,
                       actor_roles=actor_roles, app_id=app_id, now_dt=now_dt)
    return _counts(entries)


def task_detail(data_source, task_id: str, *, actor: Optional[str],
                role_apps: Optional[Dict[str, Iterable[str]]] = None,
                actor_roles: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    """按**行级可见性**取单条任务（fail-closed）。

    供详情 / 活动流共用同一道闸门：不可见或不存在 → None（REST 侧统一映射 404，
    不泄露「存在但无权」与「不存在」的差异）。
    """
    if not task_id or not actor:
        return None
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} WHERE id = ?",
        (str(task_id),),
    ).fetchall()
    if not rows:
        return None
    task = _row_to_task(rows[0])
    if not _visible(task, actor=actor, role_apps=role_apps, actor_roles=actor_roles):
        return None
    return task