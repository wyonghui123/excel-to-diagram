# -*- coding: utf-8 -*-
"""[F2 2026-10-02] SLA 独立对象 — 第二轴（Stage + Has breached）

职责（§12.1 F2 / 综合 §4.2-3 / §7.6）:
- 平台提供 SLA 的**独立第二轴**（对标 ServiceNow `task_sla`：Stage = in_progress /
  paused / completed / cancelled + Has breached），**不污染 Task 主状态列**
  （「双轴 ≠ 双状态列」）。SLA 生命周期**不入** A3 事件账（Q3 拍板），
  其运行态与升级进度均落在本对象自身。
- 只做「对象 + 状态推进」：开单 / 暂停 / 恢复 / 关闭 / 取消 / 进度派生。
  **梯队与告警**（何时 warn / breach）归 A9 `sla_ladder`——阈值属业务域、机制属平台，
  故本模块只承载配置快照（`warn_at_pct` / `on_breach` / 宽限）与进度事实。

分层纪律:
- 落**平台库**，与 A1/A3/A6/A7 同库同事务。
- 任务对业务对象仅弱引用（`task_id` / `workflow_run_id` 无 FK），同 A1 口径。
- 时间一律 ISO 字符串（与 A1/A3 同口径）；`paused_seconds` 为业务时间口径的扣除项。
- 百分比/越线判定是**派生**（`evaluate_sla` 纯计算），不落多余列。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.6 / §12.1 F2 / §12.1「五」Q3
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §4.2-3
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

SLA_ID = "task_sla"
SLA_TABLE = "task_slas"

# Stage（ServiceNow task_sla 口径；Has breached 是正交的客观事实轴）
SLA_STAGES = ("in_progress", "paused", "completed", "cancelled")
ACTIVE_STAGES = ("in_progress", "paused")

# T2 on_breach 动作域（§7.6）
ON_BREACH_ACTIONS = ("notify", "reassign", "escalate_fallback", "dead_letter")

DEFAULT_WARN_AT_PCT = 80.0
DEFAULT_ALERT_AT_PCT = 100.0


class SlaError(Exception):
    """SLA 操作前置不满足（不存在 / 状态不允许）。"""


def _f(fid: str, ftype: FieldType, *, required: bool = False,
       unique: bool = False, default=None, description: str = "") -> MetaField:
    return MetaField(
        id=fid, name=fid, field_type=ftype, db_column=fid,
        required=required, unique=unique, default=default, description=description,
    )


def _idx(name: str, columns, *, unique: bool = False, description: str = "") -> MetaIndex:
    return MetaIndex(
        fields=list(columns), db_columns=list(columns), name=name,
        unique=unique, source=IndexSource.SCHEMA, description=description,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 表结构
# ─────────────────────────────────────────────────────────────────────────────

def _build_sla_meta() -> MetaObject:
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="SLA 实例 ID（uuid4 hex，主键）"),
        _f("task_id", FieldType.STRING, required=True,
           description="所属任务 ID（弱引用无 FK）"),
        _f("workflow_run_id", FieldType.STRING, description="所属 Run（弱引用无 FK）"),
        _f("sla_key", FieldType.STRING, default="resolution",
           description="SLA 定义标识（response / resolution / 业务自定义）"),
        _f("name", FieldType.STRING, description="显示名"),

        # 第二轴：Stage（生命周期）× Has breached（客观事实），两轴正交
        _f("stage", FieldType.STRING, required=True, default="in_progress",
           description="in_progress / paused / completed / cancelled（第二轴，不入 Task 状态列）"),
        _f("has_breached", FieldType.BOOLEAN, default=False,
           description="是否已越线（客观事实；完成前 remain true）"),

        # 配置快照（阈值属业务域）
        _f("target_seconds", FieldType.FLOAT, description="SLA 时长（秒）"),
        _f("warn_at_pct", FieldType.FLOAT, default=DEFAULT_WARN_AT_PCT,
           description="T0 预警阈值（已消耗百分比）"),
        _f("alert_at_pct", FieldType.FLOAT, default=DEFAULT_ALERT_AT_PCT,
           description="T1 警戒线阈值（已消耗百分比）"),
        _f("grace_seconds", FieldType.FLOAT, default=0,
           description="T3 宽限期（due 之后多久转死信）"),
        _f("on_breach", FieldType.JSON,
           description="T2 越线动作快照（notify/reassign/escalate_fallback/dead_letter）"),

        # 时间轴（业务时间 = 墙钟 − 累计暂停）
        _f("start_at", FieldType.DATETIME, required=True, description="起算时间"),
        _f("due_at", FieldType.DATETIME, description="截止时间（start + target）"),
        _f("breach_at", FieldType.DATETIME, description="实际越线时间（首次）"),
        _f("ended_at", FieldType.DATETIME, description="结束时间（completed / cancelled）"),
        _f("paused_at", FieldType.DATETIME, description="当前暂停起点（未暂停为空）"),
        _f("paused_seconds", FieldType.FLOAT, default=0,
           description="累计暂停秒数（业务时间扣除项）"),

        # 升级进度（A9 梯队推进用；单调不回退 → 幂等去重）
        _f("last_escalation_rung", FieldType.INTEGER, default=0,
           description="已发出最高梯级（0 未发；1 warn / 2 alert / 3 breach / 4 dead_letter）"),
        _f("last_escalation_at", FieldType.DATETIME, description="最近一次升级时间"),

        _f("meta", FieldType.JSON, description="业务自定义 KV"),
        _f("created_at", FieldType.DATETIME), _f("updated_at", FieldType.DATETIME),
    ]

    indexes = [
        _idx("idx_task_slas_task", ["task_id"], description="按任务取 SLA（通常 1~2 条）"),
        _idx("idx_task_slas_due", ["stage", "due_at"],
             description="A9 梯队扫描：取活跃 SLA 按截止排序"),
        _idx("idx_task_slas_run", ["workflow_run_id"], description="按 Run 聚合"),
    ]

    return MetaObject(
        id=SLA_ID, name="任务 SLA", table_name=SLA_TABLE,
        description="SLA 独立第二轴（Stage × Has breached；对标 ServiceNow task_sla）",
        fields=fields, indexes=indexes,
    )


def build_sla_meta_objects() -> List[MetaObject]:
    return [_build_sla_meta()]


def ensure_sla_tables(data_source):
    """在**平台库**建 task_slas 表 + 索引（幂等，启动期调用）。"""
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    register_table_name(SLA_TABLE)
    return sync_schema_from_meta(data_source, build_sla_meta_objects())


def sla_tables_exist(data_source) -> Dict[str, bool]:
    try:
        rows = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (SLA_TABLE,)
        ).fetchall()
    except Exception:  # noqa: BLE001 - 库不可读视为不存在
        rows = []
    return {SLA_TABLE: bool(rows)}


# ─────────────────────────────────────────────────────────────────────────────
# 读写辅助
# ─────────────────────────────────────────────────────────────────────────────

_COLUMNS = (
    "id", "task_id", "workflow_run_id", "sla_key", "name", "stage", "has_breached",
    "target_seconds", "warn_at_pct", "alert_at_pct", "grace_seconds", "on_breach",
    "start_at", "due_at", "breach_at", "ended_at", "paused_at", "paused_seconds",
    "last_escalation_rung", "last_escalation_at", "created_at", "updated_at",
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _json_text(value: Any, fallback: str = "null") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        # 已是 JSON 容器文本（{"action": ...} / [...]）则原样；否则按字符串编码，
        # 保证读侧 _load_json（json.loads）能还原为同一值，不丢成 None。
        stripped = value.strip()
        if stripped[:1] in ("{", "["):
            return value
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, default=str)


def _row_to_dict(row) -> Dict[str, Any]:
    d = dict(zip(_COLUMNS, row))
    d["on_breach"] = _load_json(d.get("on_breach"), None)
    return d


def _load_json(text: Any, fallback: Any) -> Any:
    if text is None or text == "":
        return fallback
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return fallback


def _update(data_source, sla_id: str, **columns: Any) -> None:
    sets, params = [], []
    for key, value in columns.items():
        if value is None:
            continue
        sets.append(f"{key} = ?")
        params.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    params.extend([_now_iso(), str(sla_id)])
    data_source.execute(
        f"UPDATE {SLA_TABLE} SET {', '.join(sets)} WHERE id = ?", tuple(params)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 开单
# ─────────────────────────────────────────────────────────────────────────────

def open_sla(
    data_source,
    *,
    task_id: str,
    sla_key: str = "resolution",
    name: str = "",
    target_seconds: Optional[float] = None,
    due_at: Any = None,
    warn_at_pct: float = DEFAULT_WARN_AT_PCT,
    alert_at_pct: float = DEFAULT_ALERT_AT_PCT,
    grace_seconds: float = 0,
    on_breach: Any = None,
    workflow_run_id: str = "",
    start_at: Any = None,
) -> Dict[str, Any]:
    """开一张 SLA 单（stage=in_progress）。返回 SLA 行 dict。"""
    start = _parse_dt(start_at) or datetime.now()
    if target_seconds is None and due_at is not None:
        due_dt = _parse_dt(due_at)
        if due_dt is not None:
            target_seconds = (due_dt - start).total_seconds()
    due_dt = _parse_dt(due_at)
    if due_dt is None and target_seconds is not None:
        from datetime import timedelta
        due_dt = start + timedelta(seconds=float(target_seconds))

    sla_id = uuid.uuid4().hex
    data_source.execute(
        f"""INSERT INTO {SLA_TABLE}
            (id, task_id, workflow_run_id, sla_key, name, stage, has_breached,
             target_seconds, warn_at_pct, alert_at_pct, grace_seconds, on_breach,
             start_at, due_at, breach_at, ended_at, paused_at, paused_seconds,
             last_escalation_rung, last_escalation_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'in_progress', 0, ?, ?, ?, ?, ?, ?, ?, NULL, NULL,
                    NULL, 0, 0, NULL, ?, ?)""",
        (
            sla_id, str(task_id), workflow_run_id or None, sla_key, name or None,
            target_seconds, warn_at_pct, alert_at_pct, grace_seconds,
            _json_text(on_breach), _iso(start), _iso(due_dt), _now_iso(), _now_iso(),
        ),
    )
    return get_sla(data_source, sla_id)


def open_sla_for_task(data_source, task_id: str, *,
                      sla_key: str = "resolution", start_at: Any = None) -> Dict[str, Any]:
    """按任务的 `sla` 配置快照 + `due_at` 开单（§7.6：阈值属业务域，随任务配）。"""
    rows = data_source.execute(
        "SELECT sla, due_at, workflow_run_id FROM tasks WHERE id = ?", (str(task_id),)
    ).fetchall()
    if not rows:
        raise SlaError(f"任务不存在：{task_id}")
    cfg = _load_json(rows[0][0], {}) or {}
    due_at = rows[0][1]
    run_id = rows[0][2] or ""
    if not isinstance(cfg, dict):
        cfg = {}
    return open_sla(
        data_source, task_id=task_id, sla_key=sla_key,
        name=cfg.get("name", ""), target_seconds=cfg.get("target_seconds"),
        due_at=due_at, warn_at_pct=cfg.get("warn_at_pct", DEFAULT_WARN_AT_PCT),
        alert_at_pct=cfg.get("alert_at_pct", DEFAULT_ALERT_AT_PCT),
        grace_seconds=cfg.get("grace_seconds", 0), on_breach=cfg.get("on_breach"),
        workflow_run_id=run_id, start_at=start_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 读
# ─────────────────────────────────────────────────────────────────────────────

def get_sla(data_source, sla_id: str) -> Dict[str, Any]:
    rows = data_source.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {SLA_TABLE} WHERE id = ?", (str(sla_id),)
    ).fetchall()
    if not rows:
        raise SlaError(f"SLA 不存在：{sla_id}")
    return _row_to_dict(rows[0])


def list_slas(data_source, *, task_id: Optional[str] = None,
              active_only: bool = False) -> List[Dict[str, Any]]:
    where, params = [], []
    if task_id:
        where.append("task_id = ?")
        params.append(str(task_id))
    if active_only:
        where.append(f"stage IN ({', '.join(['?'] * len(ACTIVE_STAGES))})")
        params.extend(ACTIVE_STAGES)
    sql = f"SELECT {', '.join(_COLUMNS)} FROM {SLA_TABLE}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY start_at"
    return [_row_to_dict(r) for r in data_source.execute(sql, tuple(params)).fetchall()]


def _require_stage(data_source, sla_id: str, allowed) -> Dict[str, Any]:
    sla = get_sla(data_source, sla_id)
    if sla["stage"] not in allowed:
        raise SlaError(f"SLA {sla_id} 当前 stage={sla['stage']}，不允许该操作（需 {allowed}）")
    return sla


# ─────────────────────────────────────────────────────────────────────────────
# 状态推进
# ─────────────────────────────────────────────────────────────────────────────

def pause_sla(data_source, sla_id: str, *, at: Any = None) -> Dict[str, Any]:
    """暂停计时（业务时间扣除；对齐 ServiceNow Paused）。"""
    _require_stage(data_source, sla_id, ("in_progress",))
    _update(data_source, sla_id, stage="paused", paused_at=_iso(_parse_dt(at) or datetime.now()))
    return get_sla(data_source, sla_id)


def resume_sla(data_source, sla_id: str, *, at: Any = None) -> Dict[str, Any]:
    """恢复计时，累计暂停秒数。"""
    sla = _require_stage(data_source, sla_id, ("paused",))
    now = _parse_dt(at) or datetime.now()
    paused_at = _parse_dt(sla.get("paused_at")) or now
    total = float(sla.get("paused_seconds") or 0) + max(0.0, (now - paused_at).total_seconds())
    _update(data_source, sla_id, stage="in_progress", paused_at=None, paused_seconds=total)
    return get_sla(data_source, sla_id)


def close_sla(data_source, sla_id: str, *, achieved: Optional[bool] = None,
              at: Any = None) -> Dict[str, Any]:
    """结束 SLA（stage=completed）；`achieved=False` 记为越线。"""
    now = _parse_dt(at) or datetime.now()
    sla = _require_stage(data_source, sla_id, ACTIVE_STAGES)
    progress = evaluate_sla(sla, now=now)
    breached = (not achieved) if achieved is not None else bool(progress["is_breached"])
    _update(data_source, sla_id, stage="completed", ended_at=_iso(now),
            has_breached=1 if breached else 0,
            paused_at=None)
    return get_sla(data_source, sla_id)


def cancel_sla(data_source, sla_id: str, *, at: Any = None) -> Dict[str, Any]:
    """作废 SLA（stage=cancelled；不计越线）。"""
    _require_stage(data_source, sla_id, ACTIVE_STAGES)
    _update(data_source, sla_id, stage="cancelled",
            ended_at=_iso(_parse_dt(at) or datetime.now()), paused_at=None)
    return get_sla(data_source, sla_id)


# ─────────────────────────────────────────────────────────────────────────────
# 进度派生（纯计算）
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_sla(sla: Dict[str, Any], *, now: Any = None) -> Dict[str, Any]:
    """派生 SLA 进度（业务时间口径：墙钟 − 累计暂停）。

    Returns:
        {stage, elapsed_seconds, remaining_seconds, pct_used, is_warn, is_alert,
         is_breached, is_dead_letter, due_at}
    """
    now_dt = _parse_dt(now) or datetime.now()
    start = _parse_dt(sla.get("start_at")) or now_dt
    stage = sla.get("stage") or "in_progress"

    # 已结束的按结束时刻冻结
    if stage in ("completed", "cancelled") and sla.get("ended_at"):
        end_dt = _parse_dt(sla.get("ended_at")) or now_dt
    else:
        end_dt = now_dt

    paused = float(sla.get("paused_seconds") or 0)
    if stage == "paused" and sla.get("paused_at"):
        paused_at = _parse_dt(sla.get("paused_at")) or end_dt
        paused += max(0.0, (end_dt - paused_at).total_seconds())

    elapsed = max(0.0, (end_dt - start).total_seconds() - paused)

    target = sla.get("target_seconds")
    target = float(target) if target is not None else None
    if target is None:
        due_dt = _parse_dt(sla.get("due_at"))
        target = max(0.0, (due_dt - start).total_seconds()) if due_dt else None

    pct_used = (elapsed / target * 100.0) if target else 0.0
    warn_pct = float(sla.get("warn_at_pct") if sla.get("warn_at_pct") is not None
                     else DEFAULT_WARN_AT_PCT)
    alert_pct = float(sla.get("alert_at_pct") if sla.get("alert_at_pct") is not None
                      else DEFAULT_ALERT_AT_PCT)
    grace = float(sla.get("grace_seconds") or 0)

    has_target = target is not None and target > 0
    # 越线 / 死信统一按**业务时间**（elapsed 已扣累计暂停）判定：暂停期间墙钟推进
    # 但不越线；grace_seconds=0（默认）不设死信梯队，避免 due+0 把 T2/T3 折叠。
    is_breached = bool(has_target and elapsed >= target)
    is_dead_letter = bool(has_target and grace > 0 and elapsed >= target + grace)

    return {
        "stage": stage,
        "elapsed_seconds": round(elapsed, 3),
        "remaining_seconds": round(target - elapsed, 3) if target else None,
        "pct_used": round(pct_used, 3),
        "is_warn": pct_used >= warn_pct,
        "is_alert": pct_used >= alert_pct,
        "is_breached": is_breached,
        "is_dead_letter": is_dead_letter,
        "due_at": sla.get("due_at"),
    }