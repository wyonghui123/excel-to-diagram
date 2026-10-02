# -*- coding: utf-8 -*-
"""[A6 2026-10-02] 任务幂等键 + 重放无副作用

职责（§12.1 A6）:
- **唯一算法**（跨应用必须同一套）：任务尝试幂等键 `{run}:{task}:{attempt}`
  （§9.2；run 为空用 `adhoc` 占位）、cron 窗口幂等键 `{action_id}:{time_window}`
  （§9.5）。所有应用/引擎一律调本模块取键，不得各写一套。
- **重放无副作用**：`run_idempotent()` 先领取键（唯一约束防重），命中即返回
  **首次执行的结果**、不再执行；未命中则执行并回写结果。
  执行抛异常 → 整个事务回滚 → 键不落库，可安全重试（不污染去重账）。

分层纪律:
- 领取（INSERT）与业务执行**在同一事务**内（对齐 event_consumer 的同库同事务先例）；
  故去重表必须与被执行的数据**同库**——任务运行时用平台库（Q1），
  若在应用库内做 BO 侧去重，应用须在自己的库上调用 `ensure_idempotency_table`。
- 本模块不判断业务对错、不写 TASK_EVENT（事件账归 A3）。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.2 / §9.5 / §12.1 A6
  先例: meta/core/event_consumer.py（幂等消费，同库同事务 + 唯一约束去重）
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

logger = logging.getLogger(__name__)

# 无 Workflow 的临时任务（ad-hoc）在幂等键中的占位（§9.2 原文）
ADHOC_RUN = "adhoc"

TABLE_ID = "task_idempotency"
TABLE = "task_idempotency"

# scope：任务尝试（{run}:{task}:{attempt}）/ cron 窗口（{action_id}:{time_window}）
SCOPES = ("task_attempt", "cron_window")

# 记录状态：已领取（执行中）/ 已完成（可重放取结果）/ 已失败
STATUSES = ("claimed", "completed", "failed")


class IdempotencyKeyError(ValueError):
    """幂等键非法（格式 / 组件含分隔符 / attempt 越界）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 键算法（唯一口径）
# ─────────────────────────────────────────────────────────────────────────────

def _reject_separator(value: str, field: str) -> str:
    value = str(value)
    if ":" in value:
        raise IdempotencyKeyError(f"{field} 不得含分隔符 ':'：{value!r}")
    return value


def build_idem_key(run_id: Optional[str], task_id: str, attempt: int) -> str:
    """任务尝试幂等键 `{run}:{task}:{attempt}`（§9.2）。

    - `run_id` 为空 → 用 `adhoc` 占位（ad-hoc 任务的跨系统回调去重口径）
    - `attempt` 从 1 起（§7.3 `attempt` 从 1 起）；非正整数直接拒绝

    Raises:
        IdempotencyKeyError
    """
    if not task_id:
        raise IdempotencyKeyError("task_id 不能为空")
    try:
        attempt_int = int(attempt)
    except (TypeError, ValueError):
        raise IdempotencyKeyError(f"attempt 必须为整数：{attempt!r}")
    if attempt_int < 1:
        raise IdempotencyKeyError(f"attempt 从 1 起，收到 {attempt_int}")

    run = _reject_separator(run_id, "run_id") if run_id else ADHOC_RUN
    return f"{run}:{_reject_separator(task_id, 'task_id')}:{attempt_int}"


def build_cron_idem_key(action_id: str, time_window: str) -> str:
    """cron 窗口幂等键 `{action_id}:{time_window}`（§9.5；防同周期重复触发）。

    `time_window` 由调度器按窗口粒度生成（如 `2026-10-02T17:00`）。
    """
    if not action_id:
        raise IdempotencyKeyError("action_id 不能为空")
    if not time_window:
        raise IdempotencyKeyError("time_window 不能为空")
    return f"{_reject_separator(action_id, 'action_id')}:{time_window}"


# ─────────────────────────────────────────────────────────────────────────────
# 去重账表（MetaObject 驱动，与 A1/A3 同一机制）
# ─────────────────────────────────────────────────────────────────────────────

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


def _build_idempotency_meta() -> MetaObject:
    """构造幂等账表 MetaObject。

    去重靠 `idem_key` 唯一索引（等价 `INSERT OR IGNORE` 语义，见 `claim_idempotent`）。
    """
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="记录 ID（uuid4 hex，主键）"),
        _f("idem_key", FieldType.STRING, required=True, unique=True,
           description="幂等键（唯一；{run}:{task}:{attempt} 或 {action}:{window}）"),
        _f("scope", FieldType.STRING, required=True, default="task_attempt",
           description="task_attempt / cron_window"),
        _f("task_id", FieldType.STRING, description="所属任务（弱引用无 FK）"),
        _f("workflow_run_id", FieldType.STRING, description="所属 Run（弱引用无 FK）"),
        _f("attempt", FieldType.INTEGER, description="尝试序号（与键一致）"),
        _f("status", FieldType.STRING, required=True, default="claimed",
           description="claimed / completed / failed"),
        _f("result", FieldType.JSON,
           description="首次执行结果（重放时原样返回，不重复执行）"),
        _f("created_at", FieldType.DATETIME, description="领取时间"),
        _f("completed_at", FieldType.DATETIME, description="回写时间"),
    ]

    indexes = [
        _idx("uq_task_idem_key", ["idem_key"], unique=True,
             description="幂等键唯一 → 去重（重放不重复执行）"),
        _idx("idx_task_idem_task", ["task_id", "attempt"],
             description="按任务取尝试记录"),
        _idx("idx_task_idem_run", ["workflow_run_id"],
             description="按 Run 聚合"),
    ]

    return MetaObject(
        id=TABLE_ID,
        name="任务幂等账",
        table_name=TABLE,
        description="任务幂等去重账（唯一键防重；存首次结果供重放原样返回）",
        fields=fields,
        indexes=indexes,
    )


def ensure_idempotency_table(data_source):
    """在**给定库**建 task_idempotency 表 + 索引（幂等）。

    去重表须与被执行的数据同库（同库同事务）：任务运行时用平台库；
    应用库内做 BO 侧去重时，应用在自己的库上调用本函数。
    """
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    register_table_name(TABLE)
    return sync_schema_from_meta(data_source, [_build_idempotency_meta()])


def idempotency_table_exists(data_source) -> bool:
    """验收用：表是否已存在。"""
    try:
        rows = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    return bool(rows)


# ─────────────────────────────────────────────────────────────────────────────
# 去重读写
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_text(value: Any, fallback: str = "null") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _is_unique_violation(error: Exception) -> bool:
    return "unique" in str(error).lower()


def claim_idempotent(
    data_source,
    idem_key: str,
    *,
    scope: str = "task_attempt",
    task_id: str = "",
    workflow_run_id: str = "",
    attempt: Optional[int] = None,
) -> bool:
    """领取幂等键：**首次返回 True（可执行），重复返回 False（重放，勿再执行）**。

    靠 `idem_key` 唯一索引判定（等价 `INSERT OR IGNORE`）。不自提交——
    须与后续业务执行处于同一事务，否则去重与执行会脱节。

    Raises:
        IdempotencyKeyError: 键为空或 scope 非法
    """
    if not str(idem_key):
        raise IdempotencyKeyError("幂等键不能为空")
    if scope not in SCOPES:
        raise IdempotencyKeyError(f"未知 scope: {scope!r}（合法值见 SCOPES）")

    try:
        data_source.execute(
            f"INSERT INTO {TABLE} "
            f"(id, idem_key, scope, task_id, workflow_run_id, attempt, status, "
            f"result, created_at, completed_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, 'claimed', 'null', ?, NULL)",
            (uuid.uuid4().hex, str(idem_key), scope, task_id or None,
             workflow_run_id or None, attempt, _now_iso()),
        )
        return True
    except Exception as e:  # noqa: BLE001 - 唯一冲突 = 重放，其余原样抛
        if _is_unique_violation(e):
            logger.info("[TaskIdem] 重放命中，跳过执行: key=%s", idem_key)
            return False
        raise


def complete_idempotent(
    data_source,
    idem_key: str,
    result: Any = None,
    *,
    status: str = "completed",
) -> None:
    """回写首次执行结果（重放时由 `get_idempotent` 原样返回）。不自提交。"""
    if status not in STATUSES:
        raise IdempotencyKeyError(f"未知 status: {status!r}（合法值见 STATUSES）")
    data_source.execute(
        f"UPDATE {TABLE} SET result = ?, status = ?, completed_at = ? "
        f"WHERE idem_key = ?",
        (_json_text(result), status, _now_iso(), str(idem_key)),
    )


def get_idempotent(data_source, idem_key: str) -> Optional[Dict[str, Any]]:
    """读幂等记录；不存在返回 None。

    `result` 由 JSON 文本解析为 Python 对象（消费方无需关心存储形态）。
    """
    rows = data_source.execute(
        f"SELECT idem_key, scope, task_id, workflow_run_id, attempt, status, "
        f"result, created_at, completed_at FROM {TABLE} WHERE idem_key = ?",
        (str(idem_key),),
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    try:
        parsed_result = json.loads(row[6]) if row[6] else None
    except (TypeError, ValueError):
        parsed_result = row[6]
    return {
        "idem_key": row[0], "scope": row[1], "task_id": row[2],
        "workflow_run_id": row[3], "attempt": row[4], "status": row[5],
        "result": parsed_result, "created_at": row[7], "completed_at": row[8],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 重放安全执行
# ─────────────────────────────────────────────────────────────────────────────

def run_idempotent(
    data_source,
    idem_key: str,
    fn: Callable[[Any], Any],
    *,
    scope: str = "task_attempt",
    task_id: str = "",
    workflow_run_id: str = "",
    attempt: Optional[int] = None,
) -> Dict[str, Any]:
    """重放无副作用地执行 `fn(data_source)`。

    - 首次：领取键 → 执行 `fn` → 同事务回写结果 → `{"status": "executed", "result": ...}`
    - 重放：键已存在 → **不执行** `fn`，返回首次结果
      → `{"status": "duplicate", "result": <首次结果>}`
    - `fn` 抛异常：整个事务回滚（键与结果一并撤销）→ 异常原样抛出，
      可安全重试（去重账不被污染）

    Returns:
        {"status": "executed" | "duplicate", "result": ..., "idem_key": ...}
    """
    with data_source.transaction():
        if not claim_idempotent(
            data_source, idem_key, scope=scope, task_id=task_id,
            workflow_run_id=workflow_run_id, attempt=attempt,
        ):
            stored = get_idempotent(data_source, idem_key)
            return {
                "status": "duplicate",
                "result": stored["result"] if stored else None,
                "idem_key": str(idem_key),
            }

        result = fn(data_source)
        complete_idempotent(data_source, idem_key, result)

    return {"status": "executed", "result": result, "idem_key": str(idem_key)}