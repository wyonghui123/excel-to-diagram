# -*- coding: utf-8 -*-
"""[A3 2026-10-02] 任务事件账 schema — TASK_EVENT + WORKLOG（append-only）

职责:
- 平台提供**唯一**的任务事件账（§12.1 A3）：TASK_EVENT（迁移事件）+ WORKLOG
  （执行记录/审计）。两者落**平台库**（§12.1 Q1 拍板，与 A1 四表同库）。
- 「每次迁移 = 一条 TASK_EVENT + 一条 WORKLOG」（§7.2 / 综合 §6.2 关系 4）
  由 `record_transition()` 一次性配对写入，不靠调用方自觉。
- 事件账 ≈ OCED event-observes-objects 底座（§16.4）：事件即携带对象关联
  （task / run / doc_ref / line_refs / agent_session_id / trace_id），
  未来导出 OCED 兼容格式即可接 PM4PY / Celonis，无需额外埋点。

纪律:
- **append-only，不可删除**（§9.7 审计完整性）：本模块只提供 INSERT 读 API，
  **不提供** update / delete；纠正靠新增事件（如 hold → release）。
- 弱引用不建 FK：task_id / workflow_run_id / event_id / doc_ref 一律无外键。
- 行级 hold 事件亦落此账（Q3 / F1：hold / release 落 TASK_EVENT，
  **不改**任何状态列）；hold 当前态由事件账派生视图聚合（归 F1）。
- 写不自提交：`data_source` 的事务由调用方（引擎）持有，配对两写在**同一事务**内。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.2 / §9.7 / §12.1 A3 / §16.4
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §6.1 / §6.2
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

# ─────────────────────────────────────────────────────────────────────────────
# 表名与值域常量
# ─────────────────────────────────────────────────────────────────────────────

TASK_EVENT_ID = "task_event"
TASK_EVENT_TABLE = "task_events"

WORKLOG_ID = "task_worklog"
WORKLOG_TABLE = "task_worklogs"

# 事件类型：created（进入 pending，非状态间迁移）/ status_changed（§7.2 迁移）/
# hold、release（Q3 行级阻塞事件化，不改状态列）
EVENT_TYPES: Tuple[str, ...] = ("created", "status_changed", "hold", "release")

# WORKLOG 记录类型：迁移配对 / BO 调用 / Agent 工具调用 / 长任务心跳 / 人工备注（审核意见）
WORKLOG_ENTRY_TYPES: Tuple[str, ...] = (
    "transition", "bo_call", "agent_tool", "heartbeat", "note",
)


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
# 1. TASK_EVENT（事件账：每次迁移一条；兼 hold/release）
# ─────────────────────────────────────────────────────────────────────────────

def _build_task_event_meta() -> MetaObject:
    """构造 TASK_EVENT 表 MetaObject（who / when / what / task / run + OCED 对象关联）。"""
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="事件 ID（uuid4 hex，主键）"),
        _f("task_id", FieldType.STRING, required=True,
           description="所属任务 ID（弱引用无 FK）"),
        _f("workflow_run_id", FieldType.STRING,
           description="所属 Run（弱引用无 FK；OCED 关联）"),
        _f("event_type", FieldType.STRING, required=True, default="status_changed",
           description="created / status_changed / hold / release"),
        _f("from_status", FieldType.STRING,
           description="迁移前状态（created / hold / release 事件为空）"),
        _f("to_status", FieldType.STRING,
           description="迁移后状态（created 事件 = pending；hold / release 为空）"),
        _f("actor", FieldType.STRING,
           description="who：操作者 user_id / agent_id / system"),
        _f("actor_kind", FieldType.STRING,
           description="human / agent / system（executor 维度）"),
        _f("reason", FieldType.STRING,
           description="what：触发原因 / 守卫说明 / 审核意见摘要"),
        _f("payload", FieldType.JSON,
           description="what 细节（如 outputs hash、hold 原因编码、edge 判定结果）"),

        # OCED event-observes-objects（§16.4）
        _f("doc_ref", FieldType.STRING,
           description="业务对象弱引用（OCED 对象关联键）；无 FK"),
        _f("line_refs", FieldType.JSON,
           description="行级弱引用数组（行级 hold 场景；无 FK）"),
        _f("agent_session_id", FieldType.STRING,
           description="Agent 会话 ID（非 agent 来源为空）"),
        _f("trace_id", FieldType.STRING, description="OTel trace id"),

        _f("occurred_at", FieldType.DATETIME, required=True,
           description="when：业务发生时间（append-only 时间轴）"),
        _f("created_at", FieldType.DATETIME, description="落账时间"),
    ]

    indexes = [
        _idx("idx_task_events_task", ["task_id", "occurred_at"],
             description="按任务取事件轴（状态回放 / 派生视图）"),
        _idx("idx_task_events_run", ["workflow_run_id"],
             description="按 Run 聚合（Run 进度 / OCED 导出）"),
        _idx("idx_task_events_type", ["event_type", "occurred_at"],
             description="按类型扫描（hold 派生视图：hold/release 配对）"),
        _idx("idx_task_events_doc", ["doc_ref"],
             description="按单据追过程（OCED event-observes-objects）"),
        _idx("idx_task_events_trace", ["trace_id"],
             description="trace 关联"),
    ]

    return MetaObject(
        id=TASK_EVENT_ID,
        name="任务事件",
        table_name=TASK_EVENT_TABLE,
        description="任务生命周期事件账（append-only，不可删；≈ OCED 底座；兼 hold/release）",
        fields=fields,
        indexes=indexes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. WORKLOG（执行记录 / 审计；与迁移事件配对）
# ─────────────────────────────────────────────────────────────────────────────

def _build_worklog_meta() -> MetaObject:
    """构造 WORKLOG 表 MetaObject（who / when / what + 输入输出哈希，不可删除）。"""
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="记录 ID（uuid4 hex，主键）"),
        _f("task_id", FieldType.STRING, required=True,
           description="所属任务 ID（弱引用无 FK）"),
        _f("workflow_run_id", FieldType.STRING,
           description="所属 Run（弱引用无 FK）"),
        _f("event_id", FieldType.STRING,
           description="配对的 TASK_EVENT ID（迁移类记录；弱引用无 FK）"),
        _f("entry_type", FieldType.STRING, required=True, default="transition",
           description="transition / bo_call / agent_tool / heartbeat / note"),
        _f("actor", FieldType.STRING, description="who：操作者"),
        _f("actor_kind", FieldType.STRING, description="human / agent / system"),
        _f("summary", FieldType.STRING, description="what：人读摘要"),
        _f("detail", FieldType.JSON, description="what 明细（审核意见、BO 调用参数等）"),
        _f("inputs_hash", FieldType.STRING,
           description="入参哈希（防篡改 / 幂等比对）"),
        _f("outputs_hash", FieldType.STRING,
           description="出参哈希（防篡改 / 幂等比对）"),
        _f("progress_pct", FieldType.INTEGER,
           description="心跳进度（长任务；驱动超时判定）"),
        _f("doc_ref", FieldType.STRING, description="业务对象弱引用；无 FK"),
        _f("trace_id", FieldType.STRING, description="OTel trace id"),
        _f("occurred_at", FieldType.DATETIME, required=True, description="业务发生时间"),
        _f("created_at", FieldType.DATETIME, description="落账时间"),
    ]

    indexes = [
        _idx("idx_task_worklogs_task", ["task_id", "occurred_at"],
             description="按任务取执行记录（含 claim→done 时长统计）"),
        _idx("idx_task_worklogs_run", ["workflow_run_id"],
             description="按 Run 聚合审计"),
        _idx("idx_task_worklogs_event", ["event_id"],
             description="与事件配对回溯"),
    ]

    return MetaObject(
        id=WORKLOG_ID,
        name="任务执行记录",
        table_name=WORKLOG_TABLE,
        description="任务执行记录 / 审计日志（append-only，不可删；每次迁移与事件配对）",
        fields=fields,
        indexes=indexes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 建表入口
# ─────────────────────────────────────────────────────────────────────────────

def build_task_event_meta_objects() -> List[MetaObject]:
    """返回 A3 两表 MetaObject。"""
    return [_build_task_event_meta(), _build_worklog_meta()]


def ensure_task_event_tables(data_source):
    """在**平台库**建 task_events / task_worklogs 两表 + 索引（幂等，启动期调用）。

    与 A1 四表同一机制（sync_schema_from_meta）：表存在跳过、缺列补、索引
    `CREATE INDEX IF NOT EXISTS`。两表是**平台机制表**（非业务 BO），
    故显式登记进表名安全白名单。

    Returns:
        本次执行的 SQL 语句列表（首次 = 2 建表 + 索引；幂等重放仅索引 IF NOT EXISTS）。
    """
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    for name in (TASK_EVENT_TABLE, WORKLOG_TABLE):
        register_table_name(name)
    return sync_schema_from_meta(data_source, build_task_event_meta_objects())


def task_event_tables_exist(data_source) -> Dict[str, bool]:
    """返回 {表名: 是否存在}（验收用）。"""
    result = {}
    for name in (TASK_EVENT_TABLE, WORKLOG_TABLE):
        try:
            rows = data_source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchall()
        except Exception:  # noqa: BLE001 - 库不可读视为不存在
            rows = []
        result[name] = bool(rows)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 写路径（append-only；事务由调用方持有，配对两写须在同一事务内）
# ─────────────────────────────────────────────────────────────────────────────

def _json_text(value: Any, fallback: str = "null") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def record_task_event(
    data_source,
    *,
    task_id: str,
    event_type: str,
    from_status: str = "",
    to_status: str = "",
    actor: str = "",
    actor_kind: str = "",
    reason: str = "",
    payload: Any = None,
    doc_ref: str = "",
    line_refs: Any = None,
    agent_session_id: str = "",
    trace_id: str = "",
    workflow_run_id: str = "",
    occurred_at: Optional[str] = None,
) -> str:
    """写一条 TASK_EVENT，返回事件 ID（不自提交）。

    适用于非状态间迁移的事件（created / hold / release）。状态间迁移请用
    `record_transition()`，以保证「一事件 + WORKLOG」配对。
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"未知事件类型: {event_type!r}（合法值见 EVENT_TYPES）")

    event_id = uuid.uuid4().hex
    ts = occurred_at or _now_iso()
    data_source.execute(
        """INSERT INTO task_events
           (id, task_id, workflow_run_id, event_type, from_status, to_status,
            actor, actor_kind, reason, payload,
            doc_ref, line_refs, agent_session_id, trace_id,
            occurred_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id, task_id, workflow_run_id or None, event_type,
            from_status or None, to_status or None,
            actor or None, actor_kind or None, reason or None, _json_text(payload),
            doc_ref or None, _json_text(line_refs), agent_session_id or None,
            trace_id or None, ts, _now_iso(),
        ),
    )
    return event_id


def record_transition(
    data_source,
    *,
    task_id: str,
    from_status: str,
    to_status: str,
    actor: str = "",
    actor_kind: str = "",
    reason: str = "",
    summary: str = "",
    payload: Any = None,
    detail: Any = None,
    inputs_hash: str = "",
    outputs_hash: str = "",
    doc_ref: str = "",
    line_refs: Any = None,
    workflow_run_id: str = "",
    agent_session_id: str = "",
    trace_id: str = "",
    occurred_at: Optional[str] = None,
) -> Tuple[str, str]:
    """配对写入一次状态迁移：**一条 TASK_EVENT + 一条 WORKLOG**（§7.2 契约）。

    两写在调用方事务内完成（本函数不自提交）；`worklog.event_id` 指回事件。
    迁移合法性由 A2 状态机校验——非法迁移直接抛错，账本不落脏事件
    （对齐 §12.1「边界机制必须机器化」）。

    Returns:
        (event_id, worklog_id)
    """
    from meta.core.task_state_machine import assert_transition

    assert_transition(from_status, to_status)  # 非法迁移 → TaskTransitionError

    ts = occurred_at or _now_iso()
    event_id = record_task_event(
        data_source,
        task_id=task_id,
        event_type="status_changed",
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        actor_kind=actor_kind,
        reason=reason,
        payload=payload,
        doc_ref=doc_ref,
        line_refs=line_refs,
        agent_session_id=agent_session_id,
        trace_id=trace_id,
        workflow_run_id=workflow_run_id,
        occurred_at=ts,
    )

    worklog_id = uuid.uuid4().hex
    data_source.execute(
        """INSERT INTO task_worklogs
           (id, task_id, workflow_run_id, event_id, entry_type,
            actor, actor_kind, summary, detail,
            inputs_hash, outputs_hash, progress_pct, doc_ref, trace_id,
            occurred_at, created_at)
           VALUES (?, ?, ?, ?, 'transition', ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
        (
            worklog_id, task_id, workflow_run_id or None, event_id,
            actor or None, actor_kind or None,
            summary or f"{from_status} → {to_status}", _json_text(detail),
            inputs_hash or None, outputs_hash or None,
            doc_ref or None, trace_id or None, ts, _now_iso(),
        ),
    )
    return event_id, worklog_id