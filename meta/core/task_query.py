# -*- coding: utf-8 -*-
"""[P1 2026-10-04] 任务读模型 — 管理员监控列表（只读、分页、过滤）

职责:
- 供 `/system/task-management`「监控」tab 消费：跨应用全量任务视图（不按 actor
  过滤，闸门在 REST 层走 is_admin）。
- 只读派生：不新建表、不写列；过滤条件白名单化，未知取值 fail-closed。

纪律:
- 与 A8 收件箱的区别：收件箱是**参与者视角**（行级可见性 fail-closed）；
  本模块是**运维视角**（全量），故**不得**在参与者页复用。
- 不臆造权限：是否有权调用由 REST 层裁定（is_admin）。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.4 / §12.1 A8（运维监控视角）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from meta.core.task_schema import TASK_STATUSES, TASK_TABLE

_TASK_COLUMNS = (
    "id", "title", "type", "status", "priority", "app_id",
    "executor_type", "executor_assignee", "due_at", "created_by",
    "workflow_run_id", "doc_ref", "created_at", "updated_at",
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _row(r) -> Dict[str, Any]:
    return {
        "id": r[0], "title": r[1], "type": r[2], "status": r[3],
        "priority": r[4], "app_id": r[5] or None,
        "executor_type": r[6] or None, "assignee": r[7] or None,
        "due_at": r[8] or None, "created_by": r[9] or None,
        "workflow_run_id": r[10] or None, "doc_ref": r[11] or None,
        "created_at": r[12] or None, "updated_at": r[13] or None,
    }


def list_tasks(data_source, *, status: Optional[str] = None,
               type: Optional[str] = None, app_id: Optional[str] = None,
               executor_type: Optional[str] = None,
               page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
               ) -> Dict[str, Any]:
    """全量任务分页列表（运维视角；只读）。

    Raises:
        ValueError: status 非法 / page / page_size 非正。
    """
    if status is not None and status not in TASK_STATUSES:
        raise ValueError(f"未知状态：{status!r}（合法值：{TASK_STATUSES}）")
    try:
        page = int(page)
        page_size = int(page_size)
    except (TypeError, ValueError):
        raise ValueError("page / page_size 必须为整数")
    if page <= 0 or page_size <= 0:
        raise ValueError("page / page_size 必须为正")
    page_size = min(page_size, MAX_PAGE_SIZE)

    where: List[str] = []
    params: List[Any] = []
    if status:
        where.append("status = ?"); params.append(status)
    if type:
        where.append("type = ?"); params.append(type)
    if app_id:
        where.append("app_id = ?"); params.append(app_id)
    if executor_type:
        where.append("executor_type = ?"); params.append(executor_type)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total_rows = data_source.execute(
        f"SELECT COUNT(*) FROM {TASK_TABLE} {clause}", tuple(params),
    ).fetchall()
    total = int(total_rows[0][0]) if total_rows else 0

    offset = (page - 1) * page_size
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} {clause} "
        f"ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?",
        tuple(params) + (page_size, offset),
    ).fetchall()
    return {"items": [_row(r) for r in rows], "total": total,
            "page": page, "page_size": page_size}