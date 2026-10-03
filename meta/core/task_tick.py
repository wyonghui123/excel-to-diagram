# -*- coding: utf-8 -*-
"""[A5 2026-10-02] 统一心跳入口 — 派工 / 回收 / 告警 / 对账一次编排

职责（§12.1 A5 / §8.2 / §7.6）:
- 把 A4（投递 / 回收）、A9（SLA 梯队）与 B3（决策-生效对账）串成**一次平台心跳**：
  调度器 / cron / REST 只需调用 `platform_tick()` 一次，不必各自拼装四个入口。
- 各段独立、互不拖垮：单段或单任务失败收集进 `errors`，其余照常推进
  （心跳必须可重复调用；失败下轮自愈）。

分层纪律:
- 编排层不碰数据：不新建表、不写状态列、不改 A2 守卫 —— 各段各自的内务
  （事务、事件账、守卫）由被调模块自理。
- 幂等由被调模块保证（A4 条件 UPDATE / A9 梯级单调）；本层无状态、不发通知、
  不改任务字段（执行意图归引擎，通知归 A8 / IM）。
- 这不是完整引擎：E 系列（workflow / 依赖 / 重试）不在本轮范围，
  `platform_tick` 只做「心跳」，名字叫 tick 就是为了不越界。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §12.1 A5 / §8.2 / §7.6
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from meta.core.sla_ladder import scan_escalations
from meta.core.decision_effect import reconcile_effects   # [B3 2026-10-03] 对账段
from meta.core.task_assignment import reclaim_expired, resolve_assignment
from meta.core.task_schema import TASK_TABLE


def _error(stage: str, error: Any, *, task_id: str = None) -> Dict[str, Any]:
    return {"stage": stage, "task_id": task_id, "error": str(error)}


def _dispatch_ready_direct(data_source, *,
                           now_dt: datetime) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """扫 ready 且 direct 且指派非空的任务，逐个投递（§8.2）。"""
    dispatched: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    rows = data_source.execute(
        f"SELECT id FROM {TASK_TABLE} "
        "WHERE status = 'ready' AND assign_policy = 'direct' "
        "AND executor_assignee IS NOT NULL AND executor_assignee <> '' "
        "ORDER BY created_at"
    ).fetchall()
    for r in rows:
        task_id = r[0]
        try:
            result = resolve_assignment(data_source, task_id, now=now_dt)
            dispatched.append({
                "task_id": task_id,
                "assignee": result.get("assignee"),
                "policy": result.get("policy"),
            })
        except Exception as e:  # 单任务失败不拖垮整轮（心跳下轮自愈）
            errors.append(_error("dispatch", e, task_id=task_id))
    return dispatched, errors


def platform_tick(data_source, *, now: Any = None, dispatch: bool = True,
                  reclaim: bool = True, escalate: bool = True,
                  reconcile: bool = True) -> Dict[str, Any]:
    """一次平台心跳：派工 → 回收 → 告警 → 决策-生效对账（各段可单独关闸）。

    对账段只跑**平台库内可判**的方向（done 无回执 / 配置完整性）；跨库方向
    （回执↔单据现状 / 等待单据无活跃任务）走 CLI 注入，见 meta/tools/task_decision_reconcile.py。

    Returns:
        {dispatched, reclaimed, escalations, reconciliations, errors,
         counts: {dispatched, reclaimed, escalations, reconciliations, errors}}
    """
    now_dt = now if isinstance(now, datetime) else datetime.now()
    dispatched: List[Dict[str, Any]] = []
    reclaimed: List[Dict[str, Any]] = []
    escalations: List[Dict[str, Any]] = []
    reconciliations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    if dispatch:
        try:
            items, errs = _dispatch_ready_direct(data_source, now_dt=now_dt)
            dispatched.extend(items)
            errors.extend(errs)
        except Exception as e:  # 段级失败（如表缺失）→ 收集，不中断后续段
            errors.append(_error("dispatch", e))

    if reclaim:
        try:
            reclaimed = reclaim_expired(data_source, now=now_dt)
        except Exception as e:
            errors.append(_error("reclaim", e))

    if escalate:
        try:
            escalations = scan_escalations(data_source, now=now_dt, apply=True)
        except Exception as e:
            errors.append(_error("escalate", e))

    if reconcile:
        try:
            # 只读扫描：无 current_statuses / pending_docs 注入 → 仅平台库内可判方向
            reconciliations = reconcile_effects(data_source, now=now_dt)
        except Exception as e:
            errors.append(_error("reconcile", e))

    return {
        "dispatched": dispatched,
        "reclaimed": reclaimed,
        "escalations": escalations,
        "reconciliations": reconciliations,
        "errors": errors,
        "counts": {
            "dispatched": len(dispatched),
            "reclaimed": len(reclaimed),
            "escalations": len(escalations),
            "reconciliations": len(reconciliations),
            "errors": len(errors),
        },
    }