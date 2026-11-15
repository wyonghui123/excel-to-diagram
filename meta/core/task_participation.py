# -*- coding: utf-8 -*-
"""[M4-2 2026-11-15] 任务参与流水 — 「谁做了什么」的唯一账本（只记事实，不记分配）

分层纪律（spec §8.0 / §8.3 / R8）:
- 「谁能做」真源 = `tasks.executor_candidates`；`task_participations` **不**参与分配判定，
  只记录参与人的角色与决策结果（加签 / 会签 / 改派留痕）。
- 与 candidates 的双写（建任务、改派、加签）必须在**同一函数同一事务**内完成，
  否则两个答案会漂移。
- 弱引用不建 FK；append 语义靠「不删除」——改派把旧行置 `transferred` 而非 DELETE。

表结构见迁移 `v277__task_participation_delegation.py`（与 spec §8.1 DDL 一致）。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

logger = logging.getLogger(__name__)

PARTICIPATION_TABLE = "task_participations"

ROLES = ("required", "added", "transferred_in", "notify")
OUTCOMES = ("pending", "accepted", "rejected", "skipped", "transferred")

#: 计入会签分母的角色（改派进来的行尚未投票前也算）
VOTING_ROLES = ("required", "added", "transferred_in")

#: [M5-4] 知会角色：可见不可决策，不计入会签分母
NOTIFY_ROLE = "notify"


class ParticipationError(ValueError):
    """参与流水非法（未知角色/结果、重复投票、行不存在）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 建表（MetaObject 驱动，与 task_async / task_event 同一机制）
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


def _build_participation_meta() -> MetaObject:
    fields = [
        _f("id", FieldType.INTEGER, required=True, unique=True,
           description="记录 ID（自增主键）"),
        _f("task_id", FieldType.STRING, required=True, description="所属任务（弱引用无 FK）"),
        _f("participant", FieldType.STRING, required=True,
           description="参与人（用户 id）"),
        _f("role", FieldType.STRING, required=True, default="required",
           description="required / added / transferred_in"),
        _f("outcome", FieldType.STRING, required=True, default="pending",
           description="pending / accepted / rejected / skipped / transferred"),
        _f("comment", FieldType.TEXT, description="决策意见"),
        _f("decided_by", FieldType.STRING,
           description="实际投票人（委托场景 = 受托人）"),
        _f("on_behalf_of", FieldType.STRING,
           description="被代表投票的委托人（审计用；空 = 本人）"),
        _f("decided_at", FieldType.DATETIME, description="决策时间"),
        _f("created_by", FieldType.STRING, description="写行操作人"),
        _f("created_at", FieldType.DATETIME, description="写行时间"),
        _f("updated_at", FieldType.DATETIME, description="最后变更时间"),
    ]
    indexes = [
        _idx("idx_participation_task", ["task_id", "outcome"],
             description="按任务取参与进度"),
        _idx("idx_participation_actor", ["participant", "outcome"],
             description="按人反查名下参与任务"),
    ]
    return MetaObject(
        id=PARTICIPATION_TABLE, name="任务参与流水", table_name=PARTICIPATION_TABLE,
        description="任务参与人角色与决策结果（只记事实；分配真源仍是 executor_candidates）",
        fields=fields, indexes=indexes,
    )


def ensure_participation_tables(data_source):
    """建 task_participations 表 + 索引（幂等；启动期调用，落平台库）。"""
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    register_table_name(PARTICIPATION_TABLE)
    return sync_schema_from_meta(data_source, [_build_participation_meta()])


def participation_tables_exist(data_source) -> Dict[str, bool]:
    try:
        rows = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (PARTICIPATION_TABLE,),
        ).fetchall()
    except Exception:  # noqa: BLE001 - 库不可读视为不存在
        rows = []
    return {PARTICIPATION_TABLE: bool(rows)}


# ─────────────────────────────────────────────────────────────────────────────
# 写路径（事务由调用方持有）
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _require(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ParticipationError(f"{field} 不能为空")
    return text


def seed_participants(data_source, task_id: str, participants: Iterable[str], *,
                      role: str = "required", created_by: str = "",
                      now: Optional[str] = None) -> List[str]:
    """建任务时落参与行（与 candidates 双写）。

    只在「该参与人尚无参与行」时插入，重放幂等。返回本次新增的 participant。
    """
    if role not in ROLES:
        raise ParticipationError(f"未知参与角色: {role!r}")
    ts = now or _now_iso()
    added: List[str] = []
    for participant in [str(p) for p in (participants or []) if str(p or "")]:
        rows = data_source.execute(
            f"SELECT id FROM {PARTICIPATION_TABLE} "
            "WHERE task_id = ? AND participant = ? LIMIT 1",
            (str(task_id), participant),
        ).fetchall()
        if rows:
            continue
        data_source.execute(
            f"INSERT INTO {PARTICIPATION_TABLE} "
            "(task_id, participant, role, outcome, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (str(task_id), participant, role, created_by or None, ts, ts),
        )
        added.append(participant)
    return added


def add_participation(data_source, task_id: str, participant: str, *,
                      role: str = "added", comment: str = "",
                      created_by: str = "", now: Optional[str] = None) -> Dict[str, Any]:
    """加签：新增一行 `role='added', outcome='pending'`（已存在则拒绝，防重复加签）。"""
    if role not in ROLES:
        raise ParticipationError(f"未知参与角色: {role!r}")
    participant = _require(participant, "participant")
    ts = now or _now_iso()
    rows = data_source.execute(
        f"SELECT id, outcome FROM {PARTICIPATION_TABLE} "
        "WHERE task_id = ? AND participant = ? ORDER BY id DESC LIMIT 1",
        (str(task_id), participant),
    ).fetchall()
    if rows and rows[0][1] == "pending":
        raise ParticipationError(f"{participant} 已是待决参与人，不能重复加签")
    data_source.execute(
        f"INSERT INTO {PARTICIPATION_TABLE} "
        "(task_id, participant, role, outcome, comment, created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)",
        (str(task_id), participant, role, comment or None, created_by or None, ts, ts),
    )
    return {"task_id": str(task_id), "participant": participant,
            "role": role, "outcome": "pending"}


def mark_pending_transferred(data_source, task_id: str, *,
                             exclude: Optional[str] = None,
                             now: Optional[str] = None) -> int:
    """改派留痕：把仍 pending 的旧参与行置 `transferred`（不删除）。

    `exclude` = 改派目标：其已有 pending 行保留并升为 transferred_in（见
    `upsert_transferred_in`），避免把新人的待决行误置为已转出。
    """
    ts = now or _now_iso()
    sql = (f"UPDATE {PARTICIPATION_TABLE} SET outcome = 'transferred', updated_at = ? "
           "WHERE task_id = ? AND outcome = 'pending'")
    params: List[Any] = [ts, str(task_id)]
    if exclude:
        sql += " AND participant <> ?"
        params.append(str(exclude))
    cursor = data_source.execute(sql, params)
    return int(getattr(cursor, "rowcount", 0) or 0)


def upsert_transferred_in(data_source, task_id: str, participant: str, *,
                          created_by: str = "", comment: str = "",
                          now: Optional[str] = None) -> None:
    """改派目标行：已有 pending 行则升为 `transferred_in`，否则新增一行 pending。"""
    participant = _require(participant, "participant")
    ts = now or _now_iso()
    rows = data_source.execute(
        f"SELECT id FROM {PARTICIPATION_TABLE} "
        "WHERE task_id = ? AND participant = ? AND outcome = 'pending' "
        "ORDER BY id DESC LIMIT 1",
        (str(task_id), participant),
    ).fetchall()
    if rows:
        data_source.execute(
            f"UPDATE {PARTICIPATION_TABLE} SET role = 'transferred_in', updated_at = ? "
            "WHERE id = ?",
            (ts, rows[0][0]),
        )
        return
    data_source.execute(
        f"INSERT INTO {PARTICIPATION_TABLE} "
        "(task_id, participant, role, outcome, comment, created_by, created_at, updated_at) "
        "VALUES (?, ?, 'transferred_in', 'pending', ?, ?, ?, ?)",
        (str(task_id), participant, comment or None, created_by or None, ts, ts),
    )


def record_outcome(data_source, task_id: str, participant: str, outcome: str, *,
                   comment: str = "", decided_by: str = "",
                   on_behalf_of: str = "", now: Optional[str] = None) -> Dict[str, Any]:
    """给某参与人的 pending 行落结果；行已非 pending → 409 语义（ParticipationError）。"""
    if outcome not in ("accepted", "rejected", "skipped"):
        raise ParticipationError(f"未知决策结果: {outcome!r}")
    ts = now or _now_iso()
    rows = data_source.execute(
        f"SELECT id, outcome FROM {PARTICIPATION_TABLE} "
        "WHERE task_id = ? AND participant = ? ORDER BY id DESC LIMIT 1",
        (str(task_id), str(participant)),
    ).fetchall()
    if not rows:
        raise ParticipationError(f"{participant} 不是该任务的参与人")
    row_id, current = rows[0]
    if current != "pending":
        raise ParticipationError(f"{participant} 已投过票（{current}），不能重复投票")
    data_source.execute(
        f"UPDATE {PARTICIPATION_TABLE} SET outcome = ?, comment = ?, decided_by = ?, "
        "on_behalf_of = ?, decided_at = ?, updated_at = ? WHERE id = ?",
        (outcome, comment or None, decided_by or participant, on_behalf_of or None,
         ts, ts, row_id),
    )
    return {"participant": participant, "outcome": outcome,
            "decided_by": decided_by or participant, "on_behalf_of": on_behalf_of or ""}


def skip_other_pending(data_source, task_id: str, *, exclude: Optional[str] = None,
                       roles: Optional[Iterable[str]] = None,
                       now: Optional[str] = None) -> int:
    """reject 后其余 pending 行置 skipped（fail-closed）。

    `roles` 限定只跳过的角色（缺省 = 全部 pending）；阶段推进时只跳过投票角色，
    知会行保留 pending 以便收件箱只读展示。
    """
    ts = now or _now_iso()
    sql = (f"UPDATE {PARTICIPATION_TABLE} SET outcome = 'skipped', updated_at = ? "
           "WHERE task_id = ? AND outcome = 'pending'")
    params: List[Any] = [ts, str(task_id)]
    if exclude:
        sql += " AND participant <> ?"
        params.append(str(exclude))
    if roles:
        role_list = list(roles)
        sql += " AND role IN ({0})".format(", ".join("?" * len(role_list)))
        params.extend(role_list)
    cursor = data_source.execute(sql, params)
    return int(getattr(cursor, "rowcount", 0) or 0)


# ─────────────────────────────────────────────────────────────────────────────
# 读路径
# ─────────────────────────────────────────────────────────────────────────────

_COLUMNS = ("id", "task_id", "participant", "role", "outcome", "comment",
            "decided_by", "on_behalf_of", "decided_at", "created_by",
            "created_at", "updated_at")


def _rows_to_dicts(rows) -> List[Dict[str, Any]]:
    return [dict(zip(_COLUMNS, row)) for row in rows]


def list_participations(data_source, task_id: str) -> List[Dict[str, Any]]:
    rows = data_source.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {PARTICIPATION_TABLE} "
        "WHERE task_id = ? ORDER BY id ASC",
        (str(task_id),),
    ).fetchall()
    return _rows_to_dicts(rows)


def pending_participants(data_source, task_id: str, *,
                         roles: Optional[Iterable[str]] = None) -> List[str]:
    role_list = list(roles or VOTING_ROLES)
    placeholders = ", ".join("?" * len(role_list))
    rows = data_source.execute(
        f"SELECT DISTINCT participant FROM {PARTICIPATION_TABLE} "
        f"WHERE task_id = ? AND outcome = 'pending' AND role IN ({placeholders}) "
        "ORDER BY participant ASC",
        [str(task_id)] + role_list,
    ).fetchall()
    return [r[0] for r in rows]


def is_participant(data_source, task_id: str, actor: str) -> bool:
    rows = data_source.execute(
        f"SELECT 1 FROM {PARTICIPATION_TABLE} WHERE task_id = ? AND participant = ? LIMIT 1",
        (str(task_id), str(actor)),
    ).fetchall()
    return bool(rows)