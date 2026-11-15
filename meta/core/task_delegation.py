# -*- coding: utf-8 -*-
"""[M4-3 2026-11-15] 任务委托 — 准入期身份展开（不改归属、不写 executor_assignee）

口径（spec §8.4）:
- 委托是「我授权某人在有效期内代表我处理符合范围的任务」；被委托人获得的是
  **准入身份**，不是任务归属：`executor_candidates` / `executor_assignee` 一律不动。
- 有效期 `effective_from ≤ now ≤ effective_to`（空 = 无限）；`status='active'`。
- 范围：`any` / `app` / `type` / `doc_ref_type` + `scope_value` 精确匹配任务对应列。
- 四眼约束：不允许委托给任务提交人（`created_by`）——该判定在**任务侧**执行
  （委托是全局配置，创建时尚不知具体任务），见 `task_decision` 归并层与 `reassign_task`。
- 撤销 = `status='revoked'`（保留审计），已投的票由参与行 `on_behalf_of` 留痕。

表结构见迁移 `v277__task_participation_delegation.py`（与 spec §8.1 DDL 一致）。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

logger = logging.getLogger(__name__)

DELEGATION_TABLE = "task_delegations"

SCOPE_TYPES = ("any", "app", "type", "doc_ref_type")
STATUSES = ("active", "revoked", "expired")

#: 任务列 → 委托 scope_type 的映射（scope 匹配唯一口径）
SCOPE_TASK_FIELD = {
    "app": "app_id",
    "type": "type",
    "doc_ref_type": "doc_ref_type",
}


class DelegationError(ValueError):
    """委托非法（自委托、区间倒置、区间重叠、范围缺失）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 建表（MetaObject 驱动）
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


def _build_delegation_meta() -> MetaObject:
    fields = [
        _f("id", FieldType.INTEGER, required=True, unique=True,
           description="记录 ID（自增主键）"),
        _f("delegator", FieldType.STRING, required=True, description="委托人（授权方）"),
        _f("delegate", FieldType.STRING, required=True, description="受托人（代理方）"),
        _f("scope_type", FieldType.STRING, required=True, default="any",
           description="any / app / type / doc_ref_type"),
        _f("scope_value", FieldType.STRING, description="范围值（scope_type=any 时为空）"),
        _f("effective_from", FieldType.DATETIME, description="生效时间（空 = 立即）"),
        _f("effective_to", FieldType.DATETIME, description="失效时间（空 = 无限）"),
        _f("status", FieldType.STRING, required=True, default="active",
           description="active / revoked / expired"),
        _f("reason", FieldType.TEXT, description="委托原因"),
        _f("created_by", FieldType.STRING, description="创建人（admin 代配时 ≠ delegator）"),
        _f("created_at", FieldType.DATETIME, description="创建时间"),
        _f("updated_at", FieldType.DATETIME, description="最后变更时间"),
    ]
    indexes = [
        _idx("uidx_task_delegation",
             ["delegator", "delegate", "scope_type", "scope_value", "effective_from"],
             unique=True, description="同一委托关系的同一生效起点唯一（防重复配置）"),
        _idx("idx_task_delegation_delegate", ["delegate", "status"],
             description="按受托人取生效委托（准入展开）"),
        _idx("idx_task_delegation_delegator", ["delegator", "status"],
             description="按委托人查配置"),
    ]
    return MetaObject(
        id=DELEGATION_TABLE, name="任务委托", table_name=DELEGATION_TABLE,
        description="任务委托配置（准入期身份展开；有效期 + 范围匹配；不改任务归属）",
        fields=fields, indexes=indexes,
    )


def ensure_delegation_tables(data_source):
    """建 task_delegations 表 + 索引（幂等；启动期调用，落平台库）。"""
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    register_table_name(DELEGATION_TABLE)
    return sync_schema_from_meta(data_source, [_build_delegation_meta()])


def delegation_tables_exist(data_source) -> Dict[str, bool]:
    try:
        rows = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (DELEGATION_TABLE,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    return {DELEGATION_TABLE: bool(rows)}


# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────

_COLUMNS = ("id", "delegator", "delegate", "scope_type", "scope_value",
            "effective_from", "effective_to", "status", "reason",
            "created_by", "created_at", "updated_at")


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


def _rows_to_dicts(rows) -> List[Dict[str, Any]]:
    return [dict(zip(_COLUMNS, row)) for row in rows]


def _normalize_scope(scope_type: str, scope_value: Any) -> tuple:
    scope_type = str(scope_type or "any")
    if scope_type not in SCOPE_TYPES:
        raise DelegationError(f"未知委托范围: {scope_type!r}（合法值：{SCOPE_TYPES}）")
    value = str(scope_value or "").strip()
    if scope_type == "any":
        return scope_type, ""
    if not value:
        raise DelegationError(f"scope_type={scope_type!r} 时 scope_value 必填")
    return scope_type, value


def _overlaps(a_from, a_to, b_from, b_to) -> bool:
    """两个 [from, to) 区间是否重叠（None = 无限）。"""
    a_end = a_to or datetime.max
    b_end = b_to or datetime.max
    a_start = a_from or datetime.min
    b_start = b_from or datetime.min
    return a_start < b_end and b_start < a_end


def _in_window(row: Dict[str, Any], now: datetime) -> bool:
    start = _parse_dt(row.get("effective_from"))
    end = _parse_dt(row.get("effective_to"))
    if start and now < start:
        return False
    if end and now > end:
        return False
    return True


def _matches_scope(row: Dict[str, Any], task: Dict[str, Any]) -> bool:
    scope_type = row.get("scope_type") or "any"
    if scope_type == "any":
        return True
    field = SCOPE_TASK_FIELD.get(scope_type)
    if not field:
        return False
    return str(task.get(field) or "") == str(row.get("scope_value") or "")


# ─────────────────────────────────────────────────────────────────────────────
# 写路径
# ─────────────────────────────────────────────────────────────────────────────

def create_delegation(data_source, *, delegator: str, delegate: str,
                      scope_type: str = "any", scope_value: Any = None,
                      effective_from: Any = None, effective_to: Any = None,
                      reason: str = "", created_by: str = "",
                      now: Optional[str] = None) -> Dict[str, Any]:
    delegator = str(delegator or "").strip()
    delegate = str(delegate or "").strip()
    if not delegator or not delegate:
        raise DelegationError("delegator / delegate 不能为空")
    if delegator == delegate:
        raise DelegationError("不能委托给自己")
    scope_type, scope_value = _normalize_scope(scope_type, scope_value)

    start_dt = _parse_dt(effective_from) or _parse_dt(now) or datetime.now()
    end_dt = _parse_dt(effective_to)
    if end_dt and start_dt and end_dt < start_dt:
        raise DelegationError("effective_to 不能早于 effective_from")

    existing = data_source.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {DELEGATION_TABLE} "
        "WHERE delegator = ? AND delegate = ? AND scope_type = ? "
        "AND COALESCE(scope_value, '') = ? AND status = 'active'",
        (delegator, delegate, scope_type, scope_value),
    ).fetchall()
    for row in _rows_to_dicts(existing):
        if _overlaps(start_dt, end_dt,
                     _parse_dt(row.get("effective_from")),
                     _parse_dt(row.get("effective_to"))):
            raise DelegationError("同一委托关系的有效期重叠")

    ts = now or _now_iso()
    cursor = data_source.execute(
        f"INSERT INTO {DELEGATION_TABLE} "
        "(delegator, delegate, scope_type, scope_value, effective_from, effective_to, "
        " status, reason, created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)",
        (delegator, delegate, scope_type, scope_value or None,
         start_dt.isoformat(timespec="seconds") if start_dt else None,
         end_dt.isoformat(timespec="seconds") if end_dt else None,
         reason or None, created_by or None, ts, ts),
    )
    new_id = getattr(cursor, "lastrowid", None)
    return get_delegation(data_source, int(new_id)) if new_id else {}


def get_delegation(data_source, delegation_id: int) -> Optional[Dict[str, Any]]:
    rows = data_source.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {DELEGATION_TABLE} WHERE id = ?",
        (int(delegation_id),),
    ).fetchall()
    return _rows_to_dicts(rows)[0] if rows else None


def list_delegations(data_source, *, delegator: Optional[str] = None,
                     delegate: Optional[str] = None,
                     include_inactive: bool = False) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if delegator:
        clauses.append("delegator = ?")
        params.append(str(delegator))
    if delegate:
        clauses.append("delegate = ?")
        params.append(str(delegate))
    if not include_inactive:
        clauses.append("status = 'active'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = data_source.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM {DELEGATION_TABLE} {where} ORDER BY id DESC",
        params,
    ).fetchall()
    return _rows_to_dicts(rows)


def update_delegation(data_source, delegation_id: int, *,
                      status: Optional[str] = None,
                      effective_to: Any = "_keep",
                      reason: Optional[str] = None,
                      now: Optional[str] = None) -> Dict[str, Any]:
    """更新委托（撤销 / 调整失效时间 / 原因）。区间倒置拒绝。"""
    row = get_delegation(data_source, delegation_id)
    if not row:
        raise DelegationError(f"委托不存在：{delegation_id}")
    if status is not None and status not in STATUSES:
        raise DelegationError(f"未知委托状态: {status!r}（合法值：{STATUSES}）")

    end_value = row.get("effective_to") if effective_to == "_keep" else effective_to
    end_dt = _parse_dt(end_value)
    start_dt = _parse_dt(row.get("effective_from"))
    if end_dt and start_dt and end_dt < start_dt:
        raise DelegationError("effective_to 不能早于 effective_from")

    ts = now or _now_iso()
    sets = ["updated_at = ?"]
    params: List[Any] = [ts]
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if effective_to != "_keep":
        sets.append("effective_to = ?")
        params.append(end_dt.isoformat(timespec="seconds") if end_dt else None)
    if reason is not None:
        sets.append("reason = ?")
        params.append(reason or None)
    params.append(int(delegation_id))
    data_source.execute(
        f"UPDATE {DELEGATION_TABLE} SET {', '.join(sets)} WHERE id = ?", params,
    )
    return get_delegation(data_source, delegation_id) or {}


def revoke_delegation(data_source, delegation_id: int, *,
                      now: Optional[str] = None) -> Dict[str, Any]:
    """撤销 = 改 status='revoked'（保留审计；已投的票由 on_behalf_of 留痕）。"""
    return update_delegation(data_source, delegation_id, status="revoked", now=now)


# ─────────────────────────────────────────────────────────────────────────────
# 准入展开（只读派生）
# ─────────────────────────────────────────────────────────────────────────────

def active_delegators_for(data_source, actor: str, task: Dict[str, Any], *,
                          now: Any = None) -> List[str]:
    """返回「在有效期内、范围命中该任务」的委托人列表（actor 为受托人）。"""
    if not actor:
        return []
    ts = _parse_dt(now) or datetime.now()
    try:
        rows = data_source.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {DELEGATION_TABLE} "
            "WHERE delegate = ? AND status = 'active' ORDER BY id ASC",
            (str(actor),),
        ).fetchall()
    except Exception:  # noqa: BLE001 - 表缺失按无委托处理（收件箱不因此崩）
        logger.warning("[M4-3] 委托表不可读，按无委托处理", exc_info=True)
        return []
    delegators: List[str] = []
    for row in _rows_to_dicts(rows):
        if row["delegator"] in delegators:
            continue
        if not _in_window(row, ts):
            continue
        if not _matches_scope(row, task):
            continue
        delegators.append(row["delegator"])
    return delegators


def is_delegate_for(data_source, actor: str, task: Dict[str, Any], *,
                    now: Any = None) -> bool:
    return bool(active_delegators_for(data_source, actor, task, now=now))


def list_active_for_delegate(data_source, delegate: str, *,
                             now: Any = None) -> List[Dict[str, Any]]:
    """返回受托人当前有效的委托配置（已按有效期过滤；scope 由调用方结合任务匹配）。"""
    if not delegate:
        return []
    ts = _parse_dt(now) or datetime.now()
    try:
        rows = data_source.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {DELEGATION_TABLE} "
            "WHERE delegate = ? AND status = 'active' ORDER BY id ASC",
            (str(delegate),),
        ).fetchall()
    except Exception:  # noqa: BLE001 - 表缺失按无委托处理
        logger.warning("[M4-3] 委托表不可读，按无委托处理", exc_info=True)
        return []
    return [row for row in _rows_to_dicts(rows) if _in_window(row, ts)]