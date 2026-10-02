# -*- coding: utf-8 -*-
"""[A7 2026-10-02] 异步补全协议：`complete_async(async_token)` + 三层归位键

职责（§12.1 A7 / §9.2 / §9.5）:
- **异步补全协议**（对齐 Temporal `completeAsync`）：外部系统（WMS / TMS）受理后
  返回 `{async_token}`，任务保持 `in_progress` 等待回执；WMS 完成后经回调
  `complete_async(token, outputs)` 归位（§9.2 规范 2：明确「Task 保持 in_progress」，
  11 态中**没有** waiting 态——`waiting` 是回执行的状态，不是任务状态）。
- **三层归位键**（2026-10-02 Q2 决策定型，对位 Oracle
  `WAIT_STEP_INSTANCE_ID + EXIT_VALUES`）：
    外层 批次信封幂等键 `envelope_key` ＋
    中层 任务键 `{run}:{task}:{attempt}`（调 A6 `build_idem_key`，唯一口径）＋
    可选行键 `biz_line_no`
  拼成 `receipt_key` 作回执去重唯一键。
- **部分完成语义**（验收硬项）：同一 attempt 下多行分别核销；未回行不产生回执，
  等待单保持 `waiting` / `partial`，全部行到齐才 `completed`。

分层纪律:
- 本模块**不改任务状态列**：完成任务需引擎按 §7.2 迁移（`in_progress → done`），
  由 executor / 引擎执行并落 A3 事件账；本模块只回传 `task_completed` 与
  `next_status="done"` 提示，不伪造 TASK_EVENT。
- 两表落**平台库**（与 A1/A3/A6 同库，Q1 拍板）；同库同事务，F5 不跨库。
- 状态只挂实例：等待单是「异步等待」这一实例的生命周期（waiting/partial/completed），
  任务主状态仍唯一在 `tasks.status`。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.2 / §9.5 / §12.1 A7
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §2.3
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

logger = logging.getLogger(__name__)

WAIT_TABLE = "task_async_waits"
RECEIPT_TABLE = "task_async_receipts"

# 等待单状态：未回 / 部分回 / 全部回（任务主状态不在此——见 docstring）
WAIT_STATUSES = ("waiting", "partial", "completed")

_NO_LINE = ""          # 无行键（单件回执 / 整体补全）


class AsyncWaitError(ValueError):
    """异步等待单非法（token 不存在 / 信封不符 / 已完成仍收新回执）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 三层归位键（唯一口径）
# ─────────────────────────────────────────────────────────────────────────────

def _reject_separator(value: str, field: str) -> str:
    value = str(value)
    if ":" in value:
        raise AsyncWaitError(f"{field} 不得含分隔符 ':'：{value!r}")
    return value


def build_receipt_key(envelope_key: str, idem_key: str,
                      biz_line_no: Optional[str] = None) -> str:
    """三层归位键全串 = `{envelope}:{run}:{task}:{attempt}[:{biz_line_no}]`。

    - `envelope_key`：外层批次信封幂等键（整批回执一次性去重的口径）
    - `idem_key`：中层任务键，须由 A6 `build_idem_key` 产出（不得各写一套）
    - `biz_line_no`：可选行键；缺省表示整体补全（无行粒度）

    Raises:
        AsyncWaitError: idem_key 为空或组件含分隔符
    """
    if not idem_key:
        raise AsyncWaitError("idem_key 不能为空（须由 build_idem_key 产出）")
    env = _reject_separator(envelope_key, "envelope_key") if envelope_key else ""
    key = f"{env}:{idem_key}"
    if biz_line_no:
        key = f"{key}:{_reject_separator(biz_line_no, 'biz_line_no')}"
    return key


def _task_idem_key(workflow_run_id: str, task_id: str, attempt: int) -> str:
    """中层任务键——直接复用 A6 唯一算法，避免出现第二套口径。"""
    from meta.core.task_idempotency import build_idem_key
    return build_idem_key(workflow_run_id or None, task_id, attempt)


# ─────────────────────────────────────────────────────────────────────────────
# 两表（MetaObject 驱动，与 A1/A3/A6 同一机制）
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


def _build_wait_meta() -> MetaObject:
    """等待单：一个任务尝试的异步补全等待（token 是回执凭证）。"""
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="记录 ID（uuid4 hex，主键）"),
        _f("async_token", FieldType.STRING, required=True, unique=True,
           description="异步补全凭证（回执须携带）"),
        _f("idem_key", FieldType.STRING, required=True, unique=True,
           description="中层任务键 {run}:{task}:{attempt}（A6 口径）"),
        _f("envelope_key", FieldType.STRING,
           description="外层批次信封幂等键（WMS/TMS 整批回执）"),
        _f("task_id", FieldType.STRING, required=True, description="所属任务（弱引用无 FK）"),
        _f("workflow_run_id", FieldType.STRING, description="所属 Run（弱引用无 FK）"),
        _f("attempt", FieldType.INTEGER, description="尝试序号（与任务键一致）"),
        _f("wait_status", FieldType.STRING, required=True, default="waiting",
           description="waiting / partial / completed（回执行状态，非任务状态）"),
        _f("expected_lines", FieldType.JSON,
           description="期望回执行键清单；空 = 整体补全（首条回执即完成）"),
        _f("received_lines", FieldType.JSON, description="已核销行键清单（部分完成累积）"),
        _f("outputs", FieldType.JSON, description="回执产出（合并后）"),
        _f("created_at", FieldType.DATETIME, description="开单时间"),
        _f("expires_at", FieldType.DATETIME,
           description="补全期限（超期由引擎按 §7.5 判 dead + 告警，本模块不改任务状态）"),
        _f("completed_at", FieldType.DATETIME, description="全部归位时间"),
    ]
    indexes = [
        _idx("uq_task_async_token", ["async_token"], unique=True,
             description="凭证唯一"),
        _idx("uq_task_async_idem", ["idem_key"], unique=True,
             description="同一任务尝试只允许一张等待单（防重复开单）"),
        _idx("idx_task_async_task", ["task_id"], description="按任务取等待单"),
        _idx("idx_task_async_status", ["wait_status"], description="按等待状态扫单"),
    ]
    return MetaObject(
        id=WAIT_TABLE, name="任务异步等待单", table_name=WAIT_TABLE,
        description="异步补全等待单（token 凭证 + 三层归位键 + 部分完成核销）",
        fields=fields, indexes=indexes,
    )


def _build_receipt_meta() -> MetaObject:
    """回执：append-only，每行一条；去重靠 receipt_key 唯一索引。"""
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="记录 ID（uuid4 hex，主键）"),
        _f("receipt_key", FieldType.STRING, required=True, unique=True,
           description="三层归位键 {envelope}:{run}:{task}:{attempt}[:{line}]"),
        _f("async_token", FieldType.STRING, required=True, description="回执凭证"),
        _f("idem_key", FieldType.STRING, description="中层任务键（便于按任务对账）"),
        _f("envelope_key", FieldType.STRING, description="外层批次信封键"),
        _f("task_id", FieldType.STRING, description="所属任务（弱引用无 FK）"),
        _f("biz_line_no", FieldType.STRING, description="行键（可空 = 整体补全）"),
        _f("outputs", FieldType.JSON, description="该行回执产出"),
        _f("occurred_at", FieldType.DATETIME, description="外部实际发生时间"),
        _f("created_at", FieldType.DATETIME, description="入账时间"),
    ]
    indexes = [
        _idx("uq_task_async_receipt", ["receipt_key"], unique=True,
             description="归位键唯一 → 重放不重复核销"),
        _idx("idx_task_async_receipt_token", ["async_token"], description="按凭证取回执"),
        _idx("idx_task_async_receipt_task", ["task_id"], description="按任务对账"),
        _idx("idx_task_async_receipt_env", ["envelope_key"], description="按信封对账"),
    ]
    return MetaObject(
        id=RECEIPT_TABLE, name="任务异步回执", table_name=RECEIPT_TABLE,
        description="异步补全回执（append-only；三层归位键去重；支持逐行核销）",
        fields=fields, indexes=indexes,
    )


def build_async_meta_objects() -> List[MetaObject]:
    """两张表的 MetaObject（等待单 + 回执）。"""
    return [_build_wait_meta(), _build_receipt_meta()]


def ensure_async_tables(data_source):
    """建两表 + 索引（幂等；启动期调用，落平台库）。"""
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    register_table_name(WAIT_TABLE)
    register_table_name(RECEIPT_TABLE)
    return sync_schema_from_meta(data_source, build_async_meta_objects())


def async_tables_exist(data_source) -> Dict[str, bool]:
    """验收用：两表是否已存在。"""
    out: Dict[str, bool] = {}
    for table in (WAIT_TABLE, RECEIPT_TABLE):
        try:
            rows = data_source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchall()
        except Exception:  # noqa: BLE001
            rows = []
        out[table] = bool(rows)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 读写
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_text(value: Any, fallback: str = "null") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(text: Any, fallback: Any) -> Any:
    if text is None or text == "":
        return fallback
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return fallback


def _is_unique_violation(error: Exception) -> bool:
    return "unique" in str(error).lower()


def _norm_lines(line_refs: Optional[List[str]]) -> Optional[List[str]]:
    if not line_refs:
        return None
    out: List[str] = []
    for ref in line_refs:
        value = _reject_separator(ref, "line_ref")
        if not value:
            raise AsyncWaitError("行键不得为空字符串")
        if value not in out:
            out.append(value)
    return out


def open_async_wait(
    data_source,
    *,
    task_id: str,
    workflow_run_id: str = "",
    attempt: int = 1,
    envelope_key: str = "",
    expected_line_refs: Optional[List[str]] = None,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """开一张异步等待单，返回 `async_token`（外部系统受理后须带此 token 回调）。

    - 同一任务尝试（`{run}:{task}:{attempt}`）只允许一张等待单：重复开单被
      唯一约束拒绝 → 抛出（防同一 attempt 出现两个凭证）
    - `expected_line_refs` 给定时为**部分完成**模式：逐行核销，未回行保持 waiting

    Returns:
        {"async_token", "idem_key", "envelope_key", "wait_status", "expected_lines"}

    Raises:
        AsyncWaitError: 已开过单 / 参数非法
    """
    if not task_id:
        raise AsyncWaitError("task_id 不能为空")
    idem_key = _task_idem_key(workflow_run_id, task_id, attempt)
    lines = _norm_lines(expected_line_refs)
    if envelope_key:
        envelope_key = _reject_separator(envelope_key, "envelope_key")

    token = uuid.uuid4().hex
    expires_at = None
    if ttl_seconds:
        expires_at = (datetime.now() + timedelta(seconds=int(ttl_seconds))).isoformat(
            timespec="seconds")

    with data_source.transaction():
        try:
            data_source.execute(
                f"INSERT INTO {WAIT_TABLE} "
                f"(id, async_token, idem_key, envelope_key, task_id, workflow_run_id, "
                f"attempt, wait_status, expected_lines, received_lines, outputs, "
                f"created_at, expires_at, completed_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, 'waiting', ?, '[]', 'null', ?, ?, NULL)",
                (uuid.uuid4().hex, token, idem_key, envelope_key or None, task_id,
                 workflow_run_id or None, int(attempt), _json_text(lines),
                 _now_iso(), expires_at),
            )
        except Exception as e:  # noqa: BLE001
            if _is_unique_violation(e):
                raise AsyncWaitError(
                    f"该任务尝试已有等待单（idem_key={idem_key}），不得重复开单"
                ) from e
            raise

    logger.info("[TaskAsync] 开等待单 token=%s idem=%s expected=%s",
                token, idem_key, lines)
    return {
        "async_token": token,
        "idem_key": idem_key,
        "envelope_key": envelope_key,
        "wait_status": "waiting",
        "expected_lines": lines,
    }


def get_async_wait(data_source, async_token: str) -> Optional[Dict[str, Any]]:
    """读等待单；不存在返回 None（已解析 JSON 列）。"""
    rows = data_source.execute(
        f"SELECT id, async_token, idem_key, envelope_key, task_id, workflow_run_id, "
        f"attempt, wait_status, expected_lines, received_lines, outputs, "
        f"created_at, expires_at, completed_at FROM {WAIT_TABLE} "
        f"WHERE async_token = ?",
        (str(async_token),),
    ).fetchall()
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r[0], "async_token": r[1], "idem_key": r[2], "envelope_key": r[3],
        "task_id": r[4], "workflow_run_id": r[5], "attempt": r[6],
        "wait_status": r[7], "expected_lines": _load_json(r[8], None),
        "received_lines": _load_json(r[9], []), "outputs": _load_json(r[10], None),
        "created_at": r[11], "expires_at": r[12], "completed_at": r[13],
    }


def get_receipt(data_source, receipt_key: str) -> Optional[Dict[str, Any]]:
    """读回执；不存在返回 None。"""
    rows = data_source.execute(
        f"SELECT id, receipt_key, async_token, idem_key, envelope_key, task_id, "
        f"biz_line_no, outputs, occurred_at, created_at FROM {RECEIPT_TABLE} "
        f"WHERE receipt_key = ?",
        (str(receipt_key),),
    ).fetchall()
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r[0], "receipt_key": r[1], "async_token": r[2], "idem_key": r[3],
        "envelope_key": r[4], "task_id": r[5], "biz_line_no": r[6],
        "outputs": _load_json(r[7], None), "occurred_at": r[8], "created_at": r[9],
    }


def _pending_lines(expected: Optional[List[str]], received: List[str]) -> List[str]:
    if not expected:
        return []
    return [line for line in expected if line not in received]


def complete_async(
    data_source,
    async_token: str,
    outputs: Any = None,
    *,
    biz_line_no: str = "",
    envelope_key: str = "",
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """异步补全归位（WMS/TMS 回执入口）。幂等：同一归位键重放不重复核销。

    部分完成语义：
      - 有 `expected_lines`：逐行核销（`biz_line_no` 必须命中期望清单）；
        未回行不产生回执 → 等待单保持 `waiting`（一条未回）/ `partial`（回了一部分）；
        全部到齐 → `completed`
      - 无 `expected_lines`：整体补全，首条回执即 `completed`

    Returns:
        {"status": "received" | "duplicate" | "completed_already",
         "async_token", "receipt_key", "wait_status", "received_lines",
         "missing_lines", "task_completed", "next_status"}

    Raises:
        AsyncWaitError: token 不存在 / 信封与开单时不一致 / 已完成仍收新回执 /
            路径外行键 / 重复开单
    """
    if not async_token:
        raise AsyncWaitError("async_token 不能为空")

    with data_source.transaction():
        wait = get_async_wait(data_source, async_token)
        if wait is None:
            raise AsyncWaitError(f"异步等待单不存在：{async_token}")

        if envelope_key and wait["envelope_key"] and \
                envelope_key != wait["envelope_key"]:
            raise AsyncWaitError(
                f"信封不符：开单 {wait['envelope_key']!r}，回执 {envelope_key!r}"
            )
        envelope = envelope_key or wait["envelope_key"] or ""

        expected: Optional[List[str]] = wait["expected_lines"]
        line = _reject_separator(biz_line_no, "biz_line_no") if biz_line_no else ""
        if expected and not line:
            raise AsyncWaitError("该等待单为逐行补全，回执必须携带 biz_line_no")
        if expected and line not in expected:
            raise AsyncWaitError(f"路径外行键 {line!r}（不在期望清单）")

        receipt_key = build_receipt_key(envelope, wait["idem_key"], line or None)

        try:
            data_source.execute(
                f"INSERT INTO {RECEIPT_TABLE} "
                f"(id, receipt_key, async_token, idem_key, envelope_key, task_id, "
                f"biz_line_no, outputs, occurred_at, created_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, receipt_key, async_token, wait["idem_key"],
                 envelope or None, wait["task_id"], line or None,
                 _json_text(outputs), occurred_at or _now_iso(), _now_iso()),
            )
        except Exception as e:  # noqa: BLE001
            if _is_unique_violation(e):
                logger.info("[TaskAsync] 回执重放已忽略: %s", receipt_key)
                return {
                    "status": "duplicate", "async_token": async_token,
                    "receipt_key": receipt_key, "wait_status": wait["wait_status"],
                    "received_lines": wait["received_lines"],
                    "missing_lines": _pending_lines(expected, wait["received_lines"]),
                    "task_completed": wait["wait_status"] == "completed",
                    "next_status": "done" if wait["wait_status"] == "completed" else None,
                }
            raise

        if wait["wait_status"] == "completed":
            raise AsyncWaitError(f"等待单已完成，拒绝新回执：{receipt_key}")

        received = list(wait["received_lines"] or [])
        if line and line not in received:
            received.append(line)

        if expected:
            missing = _pending_lines(expected, received)
            wait_status = "completed" if not missing else ("partial" if received else "waiting")
        else:
            missing = []
            wait_status = "completed"

        merged_outputs = wait["outputs"]
        if outputs is not None:
            merged_outputs = outputs
        completed_at = _now_iso() if wait_status == "completed" else None

        data_source.execute(
            f"UPDATE {WAIT_TABLE} SET wait_status = ?, received_lines = ?, "
            f"outputs = ?, completed_at = ? WHERE async_token = ?",
            (wait_status, _json_text(received), _json_text(merged_outputs),
             completed_at, async_token),
        )

    logger.info("[TaskAsync] 回执归位 %s → %s (received=%s missing=%s)",
                receipt_key, wait_status, received, missing)
    return {
        "status": "received",
        "async_token": async_token,
        "receipt_key": receipt_key,
        "wait_status": wait_status,
        "received_lines": received,
        "missing_lines": missing,
        "task_completed": wait_status == "completed",
        # 任务主状态迁移由引擎执行（本模块不改状态列、不伪造 TASK_EVENT）
        "next_status": "done" if wait_status == "completed" else None,
    }