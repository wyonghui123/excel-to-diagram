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

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from meta.core.sla_ladder import RUNG_BREACH, RUNG_DEAD_LETTER, scan_escalations
from meta.core.decision_effect import reconcile_effects   # [B3 2026-10-03] 对账段
from meta.core.task_assignment import (
    reclaim_expired, reassign_task, resolve_assignment,
)
from meta.core.task_schema import TASK_TABLE

logger = logging.getLogger(__name__)

SLA_REASSIGN_REASON = "SLA 超时自动改派"


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


_SLA_TASK_COLUMNS = (
    "id", "type", "executor_config", "workflow_run_id", "trace_id", "doc_ref",
)


def _sla_reassign_rule(executor_config: Any) -> Dict[str, Any]:
    """读 `executor_config.sla_on_breach`（缺省 = 关闭；只认 dict）。"""
    cfg = executor_config
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg or "{}")
        except ValueError:
            return {}
    if not isinstance(cfg, dict):
        return {}
    rule = cfg.get("sla_on_breach")
    return rule if isinstance(rule, dict) else {}


def _record_sla_reassign(data_source, task: Dict[str, Any], rule: Dict[str, Any],
                         *, fallback: str, now_dt: datetime) -> None:
    """补一条 `action=sla_reassign` 工作日志（改派本身已由 reassign_task 留痕）。"""
    try:
        from meta.core.task_event_schema import record_worklog
        record_worklog(
            data_source, task_id=task["id"], entry_type="note",
            summary=SLA_REASSIGN_REASON, actor="system", actor_kind="system",
            detail={"action": "sla_reassign", "to_user": fallback,
                    "reason": str(rule.get("reason") or SLA_REASSIGN_REASON)},
            workflow_run_id=task.get("workflow_run_id") or "",
            trace_id=task.get("trace_id") or "",
            doc_ref=task.get("doc_ref") or "",
            occurred_at=now_dt.isoformat(timespec="seconds"),
        )
    except Exception:  # noqa: BLE001 - 日志失败不影响改派结果
        logger.warning("[M4-4] SLA 改派日志写入失败：%s", task.get("id"), exc_info=True)


def apply_sla_reassign(data_source, escalations: List[Dict[str, Any]], *,
                       now: Any = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """越线（T2）自动改派 —— **默认关闭**，仅当 `executor_config.sla_on_breach`
    显式声明 `{action:'reassign', fallback_assignee:'u-x'}` 时执行。

    通用能力：不区分任务类型；审批任务的目标权限由配置方（admin）负责，
    故 `target_permitted=True`（配置即授权，spec §8.5）。

    Returns:
        (applied, errors)
    """
    now_dt = now if isinstance(now, datetime) else datetime.now()
    applied: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for item in escalations or []:
        rung = int(item.get("rung") or 0)
        if rung < RUNG_BREACH or rung >= RUNG_DEAD_LETTER:
            continue  # T2 才动作；T3 死信走工单升级，不再改派
        task_id = str(item.get("task_id") or "")
        if not task_id:
            continue
        try:
            rows = data_source.execute(
                "SELECT {0} FROM {1} WHERE id = ?".format(
                    ", ".join(_SLA_TASK_COLUMNS), TASK_TABLE),
                (task_id,),
            ).fetchall()
            if not rows:
                continue                                        # 任务已删 → 忽略
            task = dict(zip(_SLA_TASK_COLUMNS, rows[0]))
            rule = _sla_reassign_rule(task["executor_config"])
            if rule.get("action") != "reassign":
                continue                                        # 默认关闭
            fallback = str(rule.get("fallback_assignee") or "").strip()
            if not fallback:
                continue
            reassign_task(
                data_source, task_id, to_user=fallback, actor="system",
                reason=str(rule.get("reason") or SLA_REASSIGN_REASON),
                admin=True,
                target_permitted=True if task["type"] == "approval" else None,
                now=now_dt,
            )
            _record_sla_reassign(data_source, task, rule,
                                 fallback=fallback, now_dt=now_dt)
            applied.append({"task_id": task_id, "sla_id": item.get("sla_id"),
                            "rung": rung, "to_user": fallback})
        except Exception as e:  # 单任务失败不拖垮整轮
            errors.append(_error("sla_reassign", e, task_id=task_id))
    return applied, errors


def platform_tick(data_source, *, now: Any = None, dispatch: bool = True,
                  reclaim: bool = True, escalate: bool = True,
                  reconcile: bool = True) -> Dict[str, Any]:
    """一次平台心跳：派工 → 回收 → 告警 → 决策-生效对账（各段可单独关闸）。

    对账段只跑**平台库内可判**的方向（done 无回执 / 配置完整性）；跨库方向
    （回执↔单据现状 / 等待单据无活跃任务）走 CLI 注入，见 meta/tools/task_decision_reconcile.py。

    Returns:
        {dispatched, reclaimed, escalations, sla_reassigns, reconciliations, errors,
         counts: {dispatched, reclaimed, escalations, sla_reassigns,
                  reconciliations, errors}}
    """
    now_dt = now if isinstance(now, datetime) else datetime.now()
    dispatched: List[Dict[str, Any]] = []
    reclaimed: List[Dict[str, Any]] = []
    escalations: List[Dict[str, Any]] = []
    sla_reassigns: List[Dict[str, Any]] = []
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
            # [M4-4 2026-11-15] 越线自动改派（默认关闭，读 executor_config.sla_on_breach）
            sla_reassigns, errs = apply_sla_reassign(data_source, escalations, now=now_dt)
            errors.extend(errs)
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
        "sla_reassigns": sla_reassigns,
        "reconciliations": reconciliations,
        "errors": errors,
        "counts": {
            "dispatched": len(dispatched),
            "reclaimed": len(reclaimed),
            "escalations": len(escalations),
            "sla_reassigns": len(sla_reassigns),
            "reconciliations": len(reconciliations),
            "errors": len(errors),
        },
    }