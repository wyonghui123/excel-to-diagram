# -*- coding: utf-8 -*-
"""[A9 2026-10-02] SLA 梯队与告警 — 第二状态的统一出口

职责（§12.1 A9 / §7.6）:
- 在 F2 的 SLA 对象上推进**升级梯队**（阈值属业务域、机制属平台）：
    T0 `warn_at_pct`               → 通知 assignee
    T1 `alert_at_pct`（警戒线）     → 通知 assignee + 组长
    T2 `due_at`                    → 执行 on_breach 动作（notify / reassign /
                                     escalate_fallback / dead_letter）
    T3 `due_at + grace_seconds`    → 死信 + 工单升级
- **告警产出**：`scan_escalations()` 扫活跃 SLA，返回升级清单供统一收件箱（A8）/
  IM 消费。本模块只产出告警事实与动作意图，**不直接发通知、不改任务状态**
  （执行归 A4/A5/引擎；通知归 A8/IM —— 边界不越）。
- **幂等去重（机器化）**：梯级单调不回退，进度记在 SLA 对象自身
  （`last_escalation_rung` / `last_escalation_at` / `breach_at` / `has_breached`）——
  cron 反复扫描不会重复告警。SLA 生命周期**不入** A3 事件账（§12.1 Q3 拍板，
  取代 §7.6 早期「每次升级都是一条 TASK_EVENT」的草案口径）。

分层纪律:
- 只读 SLA 对象 + 推进其升级进度列，不新建账本、不写 Task 状态列。
- 判定是纯函数（`resolve_rung`），可单测无副作用。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.6 / §12.1 A9 / §12.1「五」Q3
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.task_sla import (
    ACTIVE_STAGES, ON_BREACH_ACTIONS, SLA_TABLE, evaluate_sla, list_slas,
)

# 梯级（0 = 未升级；单调递增）
RUNG_NONE = 0
RUNG_WARN = 1
RUNG_ALERT = 2
RUNG_BREACH = 3
RUNG_DEAD_LETTER = 4

RUNG_NAMES = {
    RUNG_NONE: "none",
    RUNG_WARN: "warn",
    RUNG_ALERT: "alert",
    RUNG_BREACH: "breach",
    RUNG_DEAD_LETTER: "dead_letter",
}

DEFAULT_BREACH_ACTION = "notify"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_rung(progress: Dict[str, Any]) -> int:
    """按派生进度判定当前梯级（纯函数；只升不降）。"""
    if progress.get("is_dead_letter"):
        return RUNG_DEAD_LETTER
    if progress.get("is_breached"):
        return RUNG_BREACH
    if progress.get("is_alert"):
        return RUNG_ALERT
    if progress.get("is_warn"):
        return RUNG_WARN
    return RUNG_NONE


def resolve_action(rung: int, on_breach: Any) -> str:
    """梯级 → 动作意图（T2 取 on_breach 配置；T3 强制死信）。"""
    if rung >= RUNG_DEAD_LETTER:
        return "dead_letter"
    if rung == RUNG_BREACH:
        candidate = on_breach
        if isinstance(candidate, dict):
            candidate = candidate.get("action")
        candidate = candidate if isinstance(candidate, str) else DEFAULT_BREACH_ACTION
        return candidate if candidate in ON_BREACH_ACTIONS else DEFAULT_BREACH_ACTION
    if rung >= RUNG_WARN:
        return "notify"
    return ""


def _advance(data_source, sla: Dict[str, Any], rung: int, *, now: datetime) -> None:
    """把 SLA 的升级进度推进到 rung（单调；首次越线记 breach_at）。"""
    sets = {
        "last_escalation_rung": rung,
        "last_escalation_at": now.isoformat(timespec="seconds"),
    }
    if rung >= RUNG_BREACH:
        sets["has_breached"] = 1
        if not sla.get("breach_at"):
            sets["breach_at"] = now.isoformat(timespec="seconds")
    assigns = ", ".join(f"{k} = ?" for k in sets)
    data_source.execute(
        f"UPDATE {SLA_TABLE} SET {assigns}, updated_at = ? WHERE id = ?",
        tuple(list(sets.values()) + [_now_iso(), sla["id"]]),
    )


def scan_escalations(data_source, *, now: Any = None,
                     apply: bool = True) -> List[Dict[str, Any]]:
    """扫描活跃 SLA，返回本轮**新到达**的升级清单（幂等：已发梯级不重复）。

    Args:
        apply: True → 推进 SLA 升级进度列（cron 用法）；
               False → 纯预览，不改库。

    Returns:
        [{sla_id, task_id, rung, rung_name, action, pct_used, remaining_seconds,
          due_at, detail}]
        消费方：统一收件箱（A8）/ IM / 通知服务 —— 执行动作（reassign 等）归引擎。
    """
    now_dt = now if isinstance(now, datetime) else (evaluate_now() if now is None else now)
    findings: List[Dict[str, Any]] = []

    for sla in list_slas(data_source, active_only=True):
        if sla.get("stage") not in ACTIVE_STAGES:
            continue
        progress = evaluate_sla(sla, now=now_dt)
        rung = resolve_rung(progress)
        last = int(sla.get("last_escalation_rung") or 0)
        if rung <= last:
            continue
        findings.append({
            "sla_id": sla["id"],
            "task_id": sla["task_id"],
            "rung": rung,
            "rung_name": RUNG_NAMES.get(rung, ""),
            "action": resolve_action(rung, sla.get("on_breach")),
            "pct_used": progress["pct_used"],
            "remaining_seconds": progress["remaining_seconds"],
            "due_at": sla.get("due_at"),
            "detail": f"SLA {sla.get('sla_key')} 到达 {RUNG_NAMES.get(rung, '')} 梯级"
                      f"（已消耗 {progress['pct_used']}%）",
        })
        if apply:
            _advance(data_source, sla, rung, now=now_dt)

    return findings


def evaluate_now() -> datetime:
    """当前时刻（便于测试注入 / 统一口径）。"""
    return datetime.now()


def ladder_status(data_source, *, now: Any = None) -> List[Dict[str, Any]]:
    """只读：每个活跃 SLA 的当前梯级（仪表盘 / 收件箱聚合用，不改库）。"""
    now_dt = now if isinstance(now, datetime) else (evaluate_now() if now is None else now)
    status = []
    for sla in list_slas(data_source, active_only=True):
        progress = evaluate_sla(sla, now=now_dt)
        status.append({
            "sla_id": sla["id"], "task_id": sla["task_id"],
            "stage": sla["stage"],
            "rung": resolve_rung(progress),
            "rung_name": RUNG_NAMES.get(resolve_rung(progress), ""),
            "pct_used": progress["pct_used"],
            "has_breached": bool(sla.get("has_breached")),
        })
    return status