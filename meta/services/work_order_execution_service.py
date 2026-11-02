# -*- coding: utf-8 -*-
"""工单执行入口 —— 工序 → tasks 桥接（G13 / P3-2）

依据:
  docs/specs/tasks-project-g12-g13-execution-boundary-2026-11-01.md §6.2

口径:
  · `project_task` 不直接生成 `tasks`（上游 spec §8.2 硬规则 1）；
    本模块只接受 `work_order_id`，由工单执行入口调用。
  · 仅 `source_demand_type='project_task'` 的工单可桥接，且工单与源任务必须
    同一 `project_id`（AC-09）。
  · 每条工序创建一条 task：`doc_ref=work_order:<id>`、`line_refs=[工序 id]`
    （D10 方案 A：工序只存参数，动作流转只在 tasks）。
  · 幂等：按 `doc_ref` 下已存在的 `line_refs` 跳过，重复调用不新增。
  · 不自开事务（与 work_order_service 同构，事务边界由调用方控制）。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

WORK_ORDER_TABLE = 'work_orders'
PROJECT_TASK_TABLE = 'project_tasks'
OPERATION_TABLE = 'work_order_operations'
TASK_TABLE = 'tasks'

SOURCE_DEMAND_PROJECT_TASK = 'project_task'


class BridgeError(ValueError):
    """桥接前置条件不满足；`rule` 供调用方定位拒绝原因。"""

    def __init__(self, message: str, rule: str = '',
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.rule = rule
        self.details = details or {}


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _as_id(value: Any) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_one(ds, sql: str, params: List[Any]) -> Optional[Dict[str, Any]]:
    rows = ds.query(sql, params)
    return rows[0] if rows else None


def _existing_refs(ds, doc_ref: str) -> Dict[str, str]:
    """doc_ref 下已建任务的 工序 id → task id 映射。"""
    rows = ds.query(
        'SELECT id, line_refs FROM %s WHERE doc_ref = ?' % TASK_TABLE, [doc_ref])
    found: Dict[str, str] = {}
    for row in rows:
        refs = row.get('line_refs')
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except ValueError:
                refs = []
        if not isinstance(refs, list):
            continue
        for ref in refs:
            found[str(ref)] = str(row.get('id'))
    return found


def _insert_task(ds, row: Dict[str, Any]) -> None:
    columns = list(row.keys())
    sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
        TASK_TABLE, ', '.join(columns), ', '.join('?' * len(columns)))
    ds.execute(sql, [row[c] for c in columns])


def create_operation_tasks(ds, work_order_id: Any, *,
                           created_by: str,
                           executor_type: str = 'human') -> List[str]:
    """按工单工序创建执行 tasks，并回填指向工序的 `line_refs`。

    返回按工序顺序排列的 task id（含幂等命中的已有 id）。
    """
    wo_id = _as_id(work_order_id)
    if wo_id is None:
        raise BridgeError('工单 ID 非法：%s' % work_order_id,
                          rule='WORK_ORDER_NOT_FOUND',
                          details={'work_order_id': work_order_id})

    work_order = _load_one(
        ds,
        'SELECT id, project_id, source_demand_type, source_demand_id '
        'FROM %s WHERE id = ?' % WORK_ORDER_TABLE,
        [wo_id],
    )
    if work_order is None:
        raise BridgeError('工单不存在：%s' % wo_id,
                          rule='WORK_ORDER_NOT_FOUND',
                          details={'work_order_id': wo_id})

    if work_order.get('source_demand_type') != SOURCE_DEMAND_PROJECT_TASK:
        raise BridgeError(
            '仅 project_task 来源的工单可桥接任务（当前：%s）'
            % work_order.get('source_demand_type'),
            rule='BRIDGE_SOURCE_NOT_PROJECT_TASK',
            details={'work_order_id': wo_id,
                     'source_demand_type': work_order.get('source_demand_type')})

    source_task_id = _as_id(work_order.get('source_demand_id'))
    project_task = None
    if source_task_id is not None:
        project_task = _load_one(
            ds,
            'SELECT id, project_id FROM %s WHERE id = ?' % PROJECT_TASK_TABLE,
            [source_task_id],
        )
    if project_task is None:
        raise BridgeError(
            '工单来源项目任务不存在：%s' % work_order.get('source_demand_id'),
            rule='PROJECT_MISMATCH',
            details={'work_order_id': wo_id,
                     'source_demand_id': work_order.get('source_demand_id')})

    wo_project = _as_id(work_order.get('project_id'))
    task_project = _as_id(project_task.get('project_id'))
    if wo_project != task_project:
        raise BridgeError(
            '工单与来源项目任务不属于同一项目（%s != %s）'
            % (wo_project, task_project),
            rule='PROJECT_MISMATCH',
            details={'work_order_id': wo_id,
                     'work_order_project_id': wo_project,
                     'task_project_id': task_project})

    operations = ds.query(
        'SELECT id, operation_name FROM %s WHERE work_order_id = ? ORDER BY seq'
        % OPERATION_TABLE, [wo_id])
    if not operations:
        raise BridgeError('工单无工序，无法创建执行任务：%s' % wo_id,
                          rule='OPERATION_NOT_FOUND',
                          details={'work_order_id': wo_id})

    doc_ref = 'work_order:%s' % wo_id
    existing = _existing_refs(ds, doc_ref)
    task_ids: List[str] = []
    stamp = _now()

    for operation in operations:
        op_id = str(operation.get('id'))
        if op_id in existing:
            task_ids.append(existing[op_id])
            continue

        task_id = uuid4().hex
        _insert_task(ds, {
            'id': task_id,
            'title': operation.get('operation_name') or ('工序 %s' % op_id),
            'type': 'story',
            'status': 'pending',
            'priority': 'P2',
            'executor_type': executor_type,
            'created_by': created_by,
            'doc_ref': doc_ref,
            'line_refs': json.dumps([op_id]),
            'created_at': stamp,
            'updated_at': stamp,
        })
        existing[op_id] = task_id
        task_ids.append(task_id)

    return task_ids
