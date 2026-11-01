# -*- coding: utf-8 -*-
"""工时录入服务 —— 项目侧 G14 / 统一资源模型 FR-004

依据:
  docs/specs/tasks-project-g14-labor-view-2026-11-01.md §3 P1-2
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md FR-004 / FR-008

口径（R-TE-1 … R-TE-6）:
  · R-TE-1 `project_task_id` 与 `work_order_operation_id` 至少填一个。
  · R-TE-2 两者都在时，任务 `project_id` 必须等于工单 `project_id`
    （工单 `project_id` 为空时以任务为准）。
  · R-TE-3 传工序时由工序反查并回填 `work_order_id`；显式值不一致直接拒绝。
  · R-TE-4 传资源分配时须与工序、资源一致（首期只校验，不回写计划量）。
  · R-TE-5 `minutes` 必须 1–1440 的整数；`work_date` 不得晚于今天。
  · R-TE-6 资源必须 `is_active=1`；不限制 `resource_kind`。

只写 `time_entries` 一行；**事务边界由调用方控制**（本服务不自行开事务）。
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

TIME_ENTRY_TABLE = 'time_entries'
RESOURCE_TABLE = 'resources'
PROJECT_TASK_TABLE = 'project_tasks'
WORK_ORDER_TABLE = 'work_orders'
OPERATION_TABLE = 'work_order_operations'
ASSIGNMENT_TABLE = 'resource_assignments'

ENTRY_TYPES = ('manual', 'timer', 'import')
DEFAULT_ENTRY_TYPE = 'manual'

PROJECT_TASK_LABOR_VIEW = 'v_project_task_labor'
PROJECT_LABOR_VIEW = 'v_project_labor'
RESOURCE_LABOR_DAILY_VIEW = 'v_resource_labor_daily'

MIN_MINUTES = 1
MAX_MINUTES = 1440

_ONE_DAY = timedelta(days=1)


class LaborError(ValueError):
    """工时校验拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = '',
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule
        self.details = details or {}


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _parse_date(value: Any) -> date:
    """接受 date / datetime / 'YYYY-MM-DD'（允许带时分秒）。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace('T', ' ')
    if not text:
        raise LaborError('工作日期不能为空', field_name='work_date',
                         rule='ST_TIME_INVALID')
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        raise LaborError('工作日期格式非法：%s' % value,
                         field_name='work_date', rule='ST_TIME_INVALID')


def _parse_minutes(value: Any) -> int:
    minutes = None
    if isinstance(value, bool):
        minutes = None
    elif isinstance(value, int):
        minutes = value
    elif isinstance(value, float) and value.is_integer():
        minutes = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        minutes = int(value.strip())
    if minutes is None or minutes < MIN_MINUTES or minutes > MAX_MINUTES:
        raise LaborError('工时分钟必须为 %d–%d 的整数（当前：%s）'
                         % (MIN_MINUTES, MAX_MINUTES, value),
                         field_name='minutes', rule='ST_TIME_INVALID',
                         details={'min': MIN_MINUTES, 'max': MAX_MINUTES})
    return minutes


def _as_id(value: Any) -> Optional[int]:
    """可空外键归一：空值 → None，数字串 → int。"""
    if _blank(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class LaborService:
    """实际工时录入（校验 + 落行）。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------ 录入
    def record_time(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(payload or {})

        work_date = _parse_date(payload.get('work_date')) \
            if not _blank(payload.get('work_date')) else None
        if work_date is None:
            raise LaborError('工作日期不能为空', field_name='work_date',
                             rule='ST_TIME_INVALID')
        if work_date > date.today():
            raise LaborError('工作日期不得晚于今天：%s' % work_date,
                             field_name='work_date', rule='ST_TIME_INVALID')

        minutes = _parse_minutes(payload.get('minutes'))
        resource_id = _as_id(payload.get('resource_id'))
        if resource_id is None:
            raise LaborError('资源不能为空', field_name='resource_id',
                             rule='ST_RESOURCE_INACTIVE')
        resource = self._load_one(
            resource_id, 'SELECT id, code, name, is_active FROM resources WHERE id = ?')
        if resource is None or int(resource.get('is_active') or 0) != 1:
            raise LaborError('资源不存在或已停用：%s' % resource_id,
                             field_name='resource_id',
                             rule='ST_RESOURCE_INACTIVE',
                             details={'resource_id': resource_id})

        project_task_id = _as_id(payload.get('project_task_id'))
        operation_id = _as_id(payload.get('work_order_operation_id'))
        work_order_id = _as_id(payload.get('work_order_id'))
        assignment_id = _as_id(payload.get('resource_assignment_id'))

        # R-TE-1：必须至少有一个锚点
        if project_task_id is None and operation_id is None:
            raise LaborError('工时必须挂在项目任务或工单工序上',
                             field_name='project_task_id',
                             rule='ST_TIME_ENTRY_ANCHOR_REQUIRED')

        task = None
        if project_task_id is not None:
            task = self._load_one(
                project_task_id,
                'SELECT id, project_id, task_no FROM project_tasks WHERE id = ?')
            if task is None:
                raise LaborError('项目任务不存在：%s' % project_task_id,
                                 field_name='project_task_id',
                                 rule='ST_PROJECT_MISMATCH',
                                 details={'project_task_id': project_task_id})

        operation = None
        if operation_id is not None:
            operation = self._load_one(
                operation_id,
                'SELECT id, work_order_id, operation_name '
                'FROM work_order_operations WHERE id = ?')
            if operation is None:
                raise LaborError('工单工序不存在：%s' % operation_id,
                                 field_name='work_order_operation_id',
                                 rule='ST_WORK_ORDER_MISMATCH',
                                 details={'work_order_operation_id': operation_id})
            # R-TE-3：由工序反查 work_order_id 并回填
            derived_work_order_id = _as_id(operation.get('work_order_id'))
            if work_order_id is not None and work_order_id != derived_work_order_id:
                raise LaborError('显式工单与工序所属工单不一致',
                                 field_name='work_order_id',
                                 rule='ST_WORK_ORDER_MISMATCH',
                                 details={'work_order_id': work_order_id,
                                          'derived_work_order_id': derived_work_order_id})
            work_order_id = derived_work_order_id

        work_order = None
        if work_order_id is not None:
            work_order = self._load_one(
                work_order_id,
                'SELECT id, work_order_no, project_id FROM work_orders WHERE id = ?')
            if work_order is None:
                raise LaborError('工单不存在：%s' % work_order_id,
                                 field_name='work_order_id',
                                 rule='ST_WORK_ORDER_MISMATCH',
                                 details={'work_order_id': work_order_id})

        # R-TE-2：任务与工单的项目必须一致（工单项目为空时以任务为准）
        if task is not None and work_order is not None:
            task_project_id = _as_id(task.get('project_id'))
            wo_project_id = _as_id(work_order.get('project_id'))
            if wo_project_id is not None and task_project_id != wo_project_id:
                raise LaborError('项目任务与工单不属于同一项目',
                                 field_name='project_task_id',
                                 rule='ST_PROJECT_MISMATCH',
                                 details={'task_project_id': task_project_id,
                                          'work_order_project_id': wo_project_id})

        # R-TE-4：资源分配必须与工序、资源一致
        if assignment_id is not None:
            assignment = self._load_one(
                assignment_id,
                'SELECT id, work_order_operation_id, resource_id '
                'FROM resource_assignments WHERE id = ?')
            if assignment is None:
                raise LaborError('资源分配不存在：%s' % assignment_id,
                                 field_name='resource_assignment_id',
                                 rule='ST_ASSIGNMENT_MISMATCH',
                                 details={'resource_assignment_id': assignment_id})
            assignment_operation_id = _as_id(assignment.get('work_order_operation_id'))
            assignment_resource_id = _as_id(assignment.get('resource_id'))
            if (assignment_operation_id != operation_id
                    or assignment_resource_id != resource_id):
                raise LaborError('资源分配与工序 / 资源不一致',
                                 field_name='resource_assignment_id',
                                 rule='ST_ASSIGNMENT_MISMATCH',
                                 details={'assignment_operation_id': assignment_operation_id,
                                          'operation_id': operation_id,
                                          'assignment_resource_id': assignment_resource_id,
                                          'resource_id': resource_id})

        entry_type = payload.get('entry_type')
        if _blank(entry_type):
            entry_type = DEFAULT_ENTRY_TYPE
        billable = payload.get('billable')
        if _blank(billable):
            billable = True
        elif isinstance(billable, str):
            billable = billable.strip().lower() in ('1', 'true', 'yes', 'y')

        now = _now()
        row = {
            'work_date': work_date.strftime('%Y-%m-%d'),
            'resource_id': resource_id,
            'minutes': minutes,
            'project_task_id': project_task_id,
            'work_order_id': work_order_id,
            'work_order_operation_id': operation_id,
            'resource_assignment_id': assignment_id,
            'entry_type': entry_type,
            'billable': 1 if billable else 0,
            'note': payload.get('note'),
            'created_at': now,
            'updated_at': now,
        }
        entry_id = self._insert(TIME_ENTRY_TABLE, row)
        return {'id': entry_id}

    # ------------------------------------------------------------ 聚合只读查询
    def project_task_labor(self, project_id: Optional[Any] = None,
                           task_id: Optional[Any] = None) -> List[Dict[str, Any]]:
        """任务级实际工时（读 `v_project_task_labor`）。"""
        clauses, params = [], []
        if not _blank(project_id):
            clauses.append('project_id = ?')
            params.append(_as_id(project_id))
        if not _blank(task_id):
            clauses.append('project_task_id = ?')
            params.append(_as_id(task_id))
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = self.ds.query(
            'SELECT * FROM %s%s ORDER BY actual_minutes DESC, project_task_id'
            % (PROJECT_TASK_LABOR_VIEW, where), params)
        return [dict(row) for row in rows]

    def project_labor(self, project_id: Optional[Any] = None) \
            -> List[Dict[str, Any]]:
        """项目级实际工时（读 `v_project_labor`）。"""
        params, where = [], ''
        if not _blank(project_id):
            where = ' WHERE project_id = ?'
            params.append(_as_id(project_id))
        rows = self.ds.query(
            'SELECT * FROM %s%s ORDER BY actual_minutes DESC, project_id'
            % (PROJECT_LABOR_VIEW, where), params)
        return [dict(row) for row in rows]

    def resource_utilization(self, resource_id: Any, start_date: Any,
                             end_date: Any) -> Dict[str, Any]:
        """资源逐日实际工时 vs 可用产能（含首尾日期）。

        产能复用 `resource_matching_service.available_minutes()`（日历 / 班次 /
        例外口径只有一套）；无日历资源按 0 计，实际工时仍照实返回并标
        `capacity_missing=True`，不抛错。
        """
        from meta.services.resource_matching_service import (
            ResourceMatchingError,
            available_minutes,
        )

        rid = _as_id(resource_id)
        if rid is None:
            raise LaborError('资源不能为空', field_name='resource_id',
                             rule='RESOURCE_NOT_FOUND')
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        if start > end:
            raise LaborError('开始日期不得晚于结束日期：%s > %s' % (start, end),
                             field_name='start_date', rule='ST_TIME_INVALID')

        # 视图按资源过滤；日期在 Python 侧归一，兼容 DATETIME 带时分秒的行。
        actual_by_day: Dict[str, int] = {}
        rows = self.ds.query(
            'SELECT work_date, actual_minutes FROM %s WHERE resource_id = ?'
            % RESOURCE_LABOR_DAILY_VIEW, [rid])
        for row in rows:
            day = str(row.get('work_date') or '')[:10]
            if day:
                actual_by_day[day] = int(row.get('actual_minutes') or 0)

        conn = self._raw_connection()
        daily, total_actual, total_available, total_overtime = [], 0, 0.0, 0.0
        cursor = start
        while cursor <= end:
            key = cursor.isoformat()
            actual = actual_by_day.get(key, 0)
            try:
                available = float(available_minutes(conn, rid, cursor))
            except ResourceMatchingError as exc:
                raise LaborError(str(exc), field_name='resource_id',
                                 rule=exc.code or 'RESOURCE_NOT_FOUND')
            utilization = round(actual / available * 100, 1) if available > 0 else 0.0
            overtime = max(actual - available, 0)
            daily.append({
                'work_date': key,
                'actual_minutes': actual,
                'available_minutes': available,
                'utilization_pct': utilization,
                'overtime_minutes': overtime,
                'capacity_missing': available == 0 and actual > 0,
            })
            total_actual += actual
            total_available += available
            total_overtime += overtime
            cursor += _ONE_DAY

        return {
            'resource_id': rid,
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'actual_minutes': total_actual,
            'available_minutes': total_available,
            'utilization_pct': round(total_actual / total_available * 100, 1)
            if total_available > 0 else 0.0,
            'overtime_minutes': total_overtime,
            'days': len(daily),
            'daily': daily,
        }

    # ------------------------------------------------------------------ 工具
    def _raw_connection(self) -> Any:
        """取底层 sqlite 连接（`available_minutes` 接口要求 raw conn）。"""
        for attr in ('conn', '_connection'):
            conn = getattr(self.ds, attr, None)
            if conn is not None:
                return conn
        raise LaborError('当前数据源不支持原生连接，无法计算可用产能',
                         rule='RESOURCE_NOT_FOUND')

    def _load_one(self, record_id: int, sql: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(sql, [record_id])
        return rows[0] if rows else None

    def _insert(self, table: str, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            table, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [row[c] for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)


def record_time(data_source, payload: Dict[str, Any]) -> Dict[str, Any]:
    """模块级便捷入口（等价于 `LaborService(data_source).record_time(payload)`）。"""
    return LaborService(data_source).record_time(payload)
