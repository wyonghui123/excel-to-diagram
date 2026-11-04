# -*- coding: utf-8 -*-
"""G15 ETO 执行守卫 —— 项目任务归属 / 可执行 / 引用判定的共享实现。

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2 / §4.4 / §5

口径:
  · G1 `project_task_id` 非空 ⇒ `project_id` 非空。
  · G2 任务必须属于同一 `project_id`。
  · G3 任务 `status ∈ {planned, in_progress}` 且 `task_type = activity`。
    `strict=False` 用于库存/收货侧（历史段数据允许旧状态值，只拒绝终态）。
  · G4 `projects.design_mode = engineered` 且项目 activity 任务数 > 1 ⇒ 任务必填。
  · G9 任务被工单 / 库存事务 / 收货行引用 ⇒ 禁止删除或置 cancelled（409）。
  · 表 / 列缺失时 fail-open（与 v179 之前的旧库保持兼容），不阻断旧链路。

本模块不抛服务自有异常，由调用方（work_order_service / receipt_service /
拦截器）转换成各自的错误类型。
"""

from typing import Any, Dict, Optional

EXECUTABLE_STATUSES = ('planned', 'in_progress')
TERMINAL_STATUSES = ('draft', 'done', 'cancelled')
TASK_TYPE_ACTIVITY = 'activity'
DESIGN_MODE_ENGINEERED = 'engineered'

RULE_PROJECT_REQUIRED = 'PROJECT_TASK_PROJECT_REQUIRED'
RULE_PROJECT_MISMATCH = 'PROJECT_TASK_PROJECT_MISMATCH'
RULE_NOT_EXECUTABLE = 'PROJECT_TASK_NOT_EXECUTABLE'
RULE_TASK_REQUIRED = 'PROJECT_TASK_REQUIRED'
RULE_TASK_LOCKED = 'PROJECT_TASK_LOCKED'
RULE_TASK_REFERENCED = 'PROJECT_TASK_REFERENCED'

TASK_TABLE = 'project_tasks'
PROJECT_TABLE = 'projects'

#: G9 引用来源（表名, 列名, 人读标签）
REFERENCE_SOURCES = (
    ('work_orders', 'project_task_id', '工单'),
    ('inventory_transactions', 'project_task_id', '库存事务'),
    ('receipt_lines', 'project_task_id', '收货行'),
)


class ProjectTaskGuardError(ValueError):
    """守卫拒绝；`status_code` 供调用方映射（G9 为 409，其余 400）。"""

    def __init__(self, message: str, field_name: str = '', rule: str = '',
                 status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule
        self.status_code = status_code
        self.details = details or {}


def to_int(value: Any) -> int:
    if value is None or value == '':
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def table_exists(ds, name: str) -> bool:
    try:
        return bool(ds.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [name]))
    except Exception:  # noqa: BLE001 - 旧库/测试替身缺表时 fail-open
        return False


def table_columns(ds, name: str) -> set:
    if not table_exists(ds, name):
        return set()
    try:
        return {row.get('name') for row in ds.query(
            'PRAGMA table_info(%s)' % name)}
    except Exception:  # noqa: BLE001
        return set()


def load_task(ds, task_id: Any) -> Optional[Dict[str, Any]]:
    """读取任务；表/列缺失或任务不存在时返回 None。"""
    tid = to_int(task_id)
    if not tid or not table_exists(ds, TASK_TABLE):
        return None
    rows = ds.query(
        'SELECT id, project_id, task_type, status FROM %s WHERE id = ?'
        % TASK_TABLE, [tid])
    return rows[0] if rows else None


def assert_task_scope(ds, project_id: Any, task_id: Any,
                      is_missing_empty: bool = False):
    """G1 + G2：任务必带项目，且任务属于该项目；返回任务行（可为 None）。

    `is_missing_empty=True` 时，任务行不存在按「无法判定」放行（旧库/外部数据），
    仅做 G1；work_order 侧保持严格（任务不存在直接拒绝）。
    """
    pid = to_int(project_id)
    tid = to_int(task_id)
    if not tid:
        return None
    if not pid:
        raise ProjectTaskGuardError(
            '填写项目任务时必须同时填写项目',
            field_name='project_id', rule=RULE_PROJECT_REQUIRED,
            details={'project_task_id': tid})
    task = load_task(ds, tid)
    if task is None:
        if is_missing_empty:
            return None
        raise ProjectTaskGuardError(
            '项目任务不存在: %s' % tid,
            field_name='project_task_id', rule=RULE_PROJECT_MISMATCH,
            details={'project_task_id': tid, 'project_id': pid})
    if to_int(task.get('project_id')) != pid:
        raise ProjectTaskGuardError(
            '项目任务 %s 不属于项目 %s' % (tid, pid),
            field_name='project_task_id', rule=RULE_PROJECT_MISMATCH,
            details={'project_task_id': tid, 'project_id': pid})
    return task


def assert_task_executable(ds, project_id: Any, task_id: Any,
                           strict: bool = True):
    """G3：任务须为 activity 且处于可执行状态；返回任务行。"""
    task = assert_task_scope(ds, project_id, task_id)
    if task is None:
        return None
    task_type = str(task.get('task_type') or '').strip().lower()
    if task_type and task_type != TASK_TYPE_ACTIVITY:
        raise ProjectTaskGuardError(
            '只有活动（activity）任务可以执行，当前为 %s' % task_type,
            field_name='project_task_id', rule=RULE_NOT_EXECUTABLE,
            details={'project_task_id': to_int(task_id),
                     'task_type': task.get('task_type')})
    status = str(task.get('status') or '').strip().lower()
    if strict:
        if status not in EXECUTABLE_STATUSES:
            raise ProjectTaskGuardError(
                '任务状态 %s 不可执行（仅 planned / in_progress）' % (status or '空'),
                field_name='project_task_id', rule=RULE_NOT_EXECUTABLE,
                details={'project_task_id': to_int(task_id),
                         'status': task.get('status')})
    elif status in TERMINAL_STATUSES:
        raise ProjectTaskGuardError(
            '任务已进入终态 %s，不可再执行' % status,
            field_name='project_task_id', rule=RULE_NOT_EXECUTABLE,
            details={'project_task_id': to_int(task_id),
                     'status': task.get('status')})
    return task


def assert_engineered_task_required(ds, project_id: Any, task_id: Any) -> None:
    """G4：engineered 且项目 activity 任务数 > 1 ⇒ 工单必须挂任务。"""
    pid = to_int(project_id)
    if not pid or to_int(task_id):
        return
    if not table_exists(ds, PROJECT_TABLE) \
            or 'design_mode' not in table_columns(ds, PROJECT_TABLE):
        return
    rows = ds.query(
        'SELECT design_mode FROM %s WHERE id = ?' % PROJECT_TABLE, [pid])
    if not rows:
        return
    mode = str(rows[0].get('design_mode') or '').strip().lower()
    if mode != DESIGN_MODE_ENGINEERED:
        return
    if not table_exists(ds, TASK_TABLE):
        return
    count = 0
    columns = table_columns(ds, TASK_TABLE)
    if 'task_type' in columns:
        found = ds.query(
            'SELECT COUNT(*) AS total FROM %s WHERE project_id = ? '
            'AND task_type = ?' % TASK_TABLE,
            [pid, TASK_TYPE_ACTIVITY])
        count = to_int(found[0].get('total')) if found else 0
    else:
        found = ds.query(
            'SELECT COUNT(*) AS total FROM %s WHERE project_id = ?'
            % TASK_TABLE, [pid])
        count = to_int(found[0].get('total')) if found else 0
    if count > 1:
        raise ProjectTaskGuardError(
            '工程定制（engineered）项目有 %s 个活动任务，工单必须指定项目任务'
            % count,
            field_name='project_task_id', rule=RULE_TASK_REQUIRED,
            details={'project_id': pid, 'activity_task_count': count})


def reference_counts(ds, task_id: Any) -> Dict[str, int]:
    """G9：统计任务被各来源引用的行数（缺表/缺列视为 0）。"""
    tid = to_int(task_id)
    counts: Dict[str, int] = {}
    if not tid:
        return counts
    for table, column, label in REFERENCE_SOURCES:
        if not table_exists(ds, table) or column not in table_columns(ds, table):
            continue
        rows = ds.query(
            'SELECT COUNT(*) AS total FROM %s WHERE %s = ?' % (table, column),
            [tid])
        counts[label] = to_int(rows[0].get('total')) if rows else 0
    return counts


def assert_task_not_referenced(ds, task_id: Any) -> None:
    """G9：任务被引用时禁止删除 / 置 cancelled。"""
    counts = {label: value for label, value in reference_counts(ds, task_id).items()
              if value > 0}
    if not counts:
        return
    detail = '、'.join('%s %s 条' % (label, value)
                      for label, value in sorted(counts.items()))
    raise ProjectTaskGuardError(
        '项目任务已被引用（%s），请先解绑后再删除或取消' % detail,
        field_name='id', rule=RULE_TASK_REFERENCED, status_code=409,
        details={'project_task_id': to_int(task_id), 'references': counts})
