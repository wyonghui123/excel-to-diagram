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
    # [9.13.4.1] 单据侧只读投影：单据引用（历史任务两列为空 ⇒ 前端隐藏跳转）
    "doc_ref_type", "doc_ref_id",
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
        "doc_ref_type": r[14] or None, "doc_ref_id": r[15] or None,
    }


def _task_item(task: Dict[str, Any]) -> Dict[str, Any]:
    """把收件箱任务字典投影成本模块列表条目（与 `_row` 同形）。"""
    return {
        "id": task["id"], "title": task["title"], "type": task["type"],
        "status": task["status"], "priority": task["priority"],
        "app_id": task["app_id"] or None,
        "executor_type": task["executor_type"] or None,
        "assignee": task["executor_assignee"] or None,
        "due_at": task["due_at"] or None,
        "created_by": task["created_by"] or None,
        "workflow_run_id": task["workflow_run_id"] or None,
        "doc_ref": task["doc_ref"] or None,
        "created_at": task.get("created_at") or None,
        "updated_at": task["updated_at"] or None,
        "doc_ref_type": task["doc_ref_type"] or None,
        "doc_ref_id": task["doc_ref_id"] or None,
    }


def list_tasks(data_source, *, status: Optional[str] = None,
               type: Optional[str] = None, app_id: Optional[str] = None,
               executor_type: Optional[str] = None,
               doc_ref_type: Optional[str] = None,
               doc_ref_id: Optional[str] = None,
               actor: Optional[str] = None,
               page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
               ) -> Dict[str, Any]:
    """全量任务分页列表（运维视角；只读）。

    Args:
        actor: 非空时按行级可见性收敛（fail-closed，口径与 `task_detail` 一致：
            assignee / created_by / 候选 / 有效受托人 / 角色→应用授权）。
            管理员身份不在此层判定（REST 层决定是否走全量口径）。
        doc_ref_type / doc_ref_id: 单据引用过滤（审批投影用）。

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
    if doc_ref_type:
        where.append("doc_ref_type = ?"); params.append(doc_ref_type)
    if doc_ref_id:
        where.append("doc_ref_id = ?"); params.append(doc_ref_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    # [M5] 阶段序号是可选列（旧库未迁移时跳过，避免整条列表 500）
    from meta.core.task_inbox import (
        _TASK_COLUMNS as _INBOX_COLUMNS,
        _has_column, _row_to_task, _visible,
    )
    has_stage = _has_column(data_source, TASK_TABLE, "stage_no")
    stage_extra = ["stage_no"] if has_stage else []

    if actor:
        # 行级可见性：单据维度量级小，先取全量命中行再内存过滤（不下推 SQL）
        columns = list(_INBOX_COLUMNS) + ["doc_ref_id", "created_at"] + stage_extra
        rows = data_source.execute(
            f"SELECT {', '.join(columns)} FROM {TASK_TABLE} {clause} "
            f"ORDER BY updated_at DESC, created_at DESC",
            tuple(params),
        ).fetchall()
        base = len(_INBOX_COLUMNS)
        items: List[Dict[str, Any]] = []
        for r in rows:
            task = _row_to_task(r)
            task["doc_ref_id"] = r[base] or ""
            task["created_at"] = r[base + 1] if len(r) > base + 1 else None
            if has_stage and len(r) > base + 2:
                try:
                    task["stage_no"] = int(r[base + 2]) if r[base + 2] is not None else 1
                except (TypeError, ValueError):
                    task["stage_no"] = 1
            if _visible(task, actor=actor, role_apps=None, actor_roles=None,
                        data_source=data_source):
                item = _task_item(task)
                item["stage_no"] = task.get("stage_no", 1)
                items.append(item)
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total,
                "page": page, "page_size": page_size}

    total_rows = data_source.execute(
        f"SELECT COUNT(*) FROM {TASK_TABLE} {clause}", tuple(params),
    ).fetchall()
    total = int(total_rows[0][0]) if total_rows else 0

    offset = (page - 1) * page_size
    rows = data_source.execute(
        f"SELECT {', '.join(list(_TASK_COLUMNS) + stage_extra)} FROM {TASK_TABLE} {clause} "
        f"ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?",
        tuple(params) + (page_size, offset),
    ).fetchall()
    items = []
    for r in rows:
        item = _row(r)
        if has_stage:
            try:
                item["stage_no"] = int(r[16]) if r[16] is not None else 1
            except (TypeError, ValueError):
                item["stage_no"] = 1
        items.append(item)
    return {"items": items, "total": total,
            "page": page, "page_size": page_size}