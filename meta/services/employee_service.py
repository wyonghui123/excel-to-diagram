# -*- coding: utf-8 -*-
"""员工主服务（统一资源模型 P3 / FR-015）

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §FR-015

口径:
  · 纯函数: 调用方传入 sqlite3.Connection, 本模块只读, 不建连接、不 commit。
  · 资源 ↔ 员工**不建外键**: 两者都指向 `person_profile`, 按 person 求交
      （`resources.person_ref = employees.person_profile_id AND status='active'`）,
      同一个人跨厂/跨组织的多个人资源实例都能解析到同一条在职员工记录。
  · 可用性推导(FR-015 P3 实施):
      ① 员工当日有生效排班 ⇒ 以员工排班窗口为准, **不叠加**资源日历;
      ② 员工当日无排班 ⇒ 回退资源日历;
      ③ `resource_availability` 例外在两个分支上都生效(由
         `resource_matching_service` 的窗口求交逻辑统一处理)。
  · 排班窗口 dict 的键与 `resource_matching_service.shift_windows_for_date`
      保持一致(`calendar_shift_id` 为 None, 另带命中的排班 id), `capacity_factor`
      固定 1.0 —— 员工排班不做夜班折算。
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from meta.services.resource_matching_service import (
    WEEKDAY_FIELDS,
    ResourceMatchingError,
    _fetch_all,
    _fetch_one,
    _minutes_from_time,
    _normalize_date,
)

#: 主管向上追溯的最大层数(防脏数据成环死循环)
MAX_MANAGER_DEPTH = 20

#: 员工表的业务列(按固定顺序返回, 便于调用方稳定读取)
_EMPLOYEE_COLUMNS = (
    'id', 'employee_no', 'name', 'person_profile_id', 'user_id', 'org_id',
    'location_id', 'position', 'job_grade', 'employment_type', 'status',
    'hire_date', 'termination_date', 'manager_employee_id',
)


def _date_text(value: Any) -> Optional[str]:
    """把日期类值规范成 YYYY-MM-DD; 空值返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _add_error(errors: List[Dict[str, Any]], code: str, field: str,
               message: str) -> None:
    errors.append({'code': code, 'field': field, 'message': message})


def _load_employee(conn, employee_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        conn,
        'SELECT {0} FROM employees WHERE id = ?'.format(
            ', '.join(_EMPLOYEE_COLUMNS)),
        (employee_id,))


def resolve_resource_employee(conn, resource_id: int,
                              as_of: Any = None) -> Optional[Dict[str, Any]]:
    """解析人资源对应的**在职**员工记录(FR-015 求交口径)。

    · 无 `person_ref`(设备/车辆/场地等非人资源) ⇒ 返回 None;
    · person 存在但无在职员工(未建雇佣关系/已离职) ⇒ 返回 None;
    · 传入 as_of 时额外要求 `hire_date <= as_of`(按业务日期而非今天判定);
    · 同一 person 多条在职雇佣由 DB 部分唯一索引禁止, 此处仍按 id 升序取首行兜底。
    """
    resource = _fetch_one(
        conn,
        'SELECT id, person_ref FROM resources WHERE id = ?',
        (resource_id,))
    if not resource:
        raise ResourceMatchingError(
            '资源不存在: {0}'.format(resource_id), 'RESOURCE_NOT_FOUND')

    person_ref = resource['person_ref']
    if not person_ref:
        return None

    sql = (
        'SELECT {0} FROM employees '
        "WHERE person_profile_id = ? AND status = 'active'".format(
            ', '.join(_EMPLOYEE_COLUMNS))
    )
    params: List[Any] = [person_ref]
    if as_of is not None:
        sql += ' AND substr(hire_date, 1, 10) <= ?'
        params.append(_normalize_date(as_of))
    return _fetch_one(conn, sql + ' ORDER BY id LIMIT 1', tuple(params))


def validate_employee(conn, data: Dict[str, Any],
                      employee_id: Optional[int] = None) -> Dict[str, Any]:
    """校验一条员工数据能否落库(纯校验, 不写库)。

    规则:
      ① `status='terminated'` 必须有 `termination_date`;
      ② `termination_date >= hire_date`;
      ③ `employee_no` 在职冲突(仅 status='active' 参与唯一, 历史离职行可同号);
      ④ `person_profile_id` 在职冲突(同一自然人同一时刻只有一条在职雇佣);
      ⑤ `manager_employee_id` 不得成环(自引用即错, 向上追溯 ≤ MAX_MANAGER_DEPTH 层)。

    更新场景(传 employee_id)时, data 未给的字段回退到库内现值。
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    existing = _load_employee(conn, employee_id) if employee_id else None

    def value(key: str) -> Any:
        current = data.get(key)
        if current is None and existing is not None:
            current = existing.get(key)
        return current

    status = value('status') or 'active'
    hire_date = _date_text(value('hire_date'))
    termination_date = _date_text(value('termination_date'))

    if status == 'terminated' and not termination_date:
        _add_error(errors, 'TERMINATION_DATE_REQUIRED', 'termination_date',
                   '离职状态(status=terminated)必须填写离职日期')
    if hire_date and termination_date and termination_date < hire_date:
        _add_error(errors, 'TERMINATION_BEFORE_HIRE', 'termination_date',
                   '离职日期不得早于入职日期({0} < {1})'.format(
                       termination_date, hire_date))

    if status == 'active':
        employee_no = value('employee_no')
        if employee_no:
            params: List[Any] = [employee_no]
            sql = ("SELECT id FROM employees WHERE employee_no = ? "
                   "AND status = 'active'")
            if employee_id is not None:
                sql += ' AND id <> ?'
                params.append(employee_id)
            conflict = _fetch_one(conn, sql + ' LIMIT 1', tuple(params))
            if conflict:
                _add_error(errors, 'EMPLOYEE_NO_CONFLICT', 'employee_no',
                           '工号 {0} 已存在在职员工(id={1})'.format(
                               employee_no, conflict['id']))

        person_profile_id = value('person_profile_id')
        if person_profile_id:
            params = [person_profile_id]
            sql = ("SELECT id FROM employees WHERE person_profile_id = ? "
                   "AND status = 'active'")
            if employee_id is not None:
                sql += ' AND id <> ?'
                params.append(employee_id)
            conflict = _fetch_one(conn, sql + ' LIMIT 1', tuple(params))
            if conflict:
                _add_error(errors, 'PERSON_PROFILE_CONFLICT', 'person_profile_id',
                           '该自然人已有在职员工记录(id={0})'.format(
                               conflict['id']))

    manager_id = value('manager_employee_id')
    if manager_id is not None:
        manager_id = int(manager_id)
        if employee_id is not None and manager_id == int(employee_id):
            _add_error(errors, 'MANAGER_SELF_REFERENCE', 'manager_employee_id',
                       '直属主管不能是员工本人')
        elif employee_id is not None:
            cycle = _walk_manager_chain(conn, manager_id, int(employee_id))
            if cycle is not None:
                _add_error(errors, 'MANAGER_CYCLE', 'manager_employee_id',
                           '直属主管汇报链成环(经过员工 id={0})'.format(cycle))

    return {'errors': errors, 'warnings': warnings}


def _walk_manager_chain(conn, start_id: int,
                        target_id: int) -> Optional[int]:
    """从 start_id 沿 manager_employee_id 向上追溯, 命中 target_id 即成环。"""
    current: Optional[int] = start_id
    for _ in range(MAX_MANAGER_DEPTH):
        if current is None:
            return None
        if int(current) == int(target_id):
            return int(current)
        row = _fetch_one(
            conn,
            'SELECT manager_employee_id FROM employees WHERE id = ?',
            (current,))
        if not row:
            return None
        current = row['manager_employee_id']
    return None


# ============================================================================
# 员工排班窗口 (FR-015)
# ============================================================================

def employee_shift_windows(conn, employee_id: int,
                           the_date: Any = None) -> List[Dict[str, Any]]:
    """展开某员工某天生效的排班窗口(绝对时间, 口径同日历班次)。

    生效条件:
      · `effective_from ~ effective_to` 覆盖该日(含边界, effective_to 空=长期);
      · 当日星期对应的 `day_mask_*` 为真(默认 1);
      · 班次模板 `shifts.is_active=1` 且在班次自身有效区间内。

    返回项键与 `shift_windows_for_date` 一致:
      calendar_shift_id(None) / shift_id / shift_code / shift_name / seq /
      start_time / end_time / crosses_midnight / gross_minutes / break_minutes /
      net_minutes / capacity_factor(1.0) / effective_minutes / weekday / day_type;
    另附 `employee_id` / `employee_shift_assignment_id`(命中排班行 id, 可解释)。
    """
    date_str = _normalize_date(the_date)
    weekday = date.fromisoformat(date_str).weekday()
    mask_field = WEEKDAY_FIELDS[weekday]

    rows = _fetch_all(
        conn,
        """
        SELECT esa.id AS assignment_id, esa.seq AS assignment_seq,
               s.id AS shift_id, s.code AS shift_code, s.name AS shift_name,
               s.start_time, s.end_time, s.crosses_midnight, s.break_minutes
        FROM employee_shift_assignments esa
        JOIN shifts s ON s.id = esa.shift_id
        WHERE esa.employee_id = ?
          AND COALESCE(esa.{0}, 1) <> 0
          AND substr(esa.effective_from, 1, 10) <= ?
          AND (esa.effective_to IS NULL OR substr(esa.effective_to, 1, 10) >= ?)
          AND s.is_active = 1
          AND (s.valid_from IS NULL OR substr(s.valid_from, 1, 10) <= ?)
          AND (s.valid_to IS NULL OR substr(s.valid_to, 1, 10) >= ?)
        ORDER BY esa.seq, esa.id
        """.format(mask_field),
        (employee_id, date_str, date_str, date_str, date_str))

    windows: List[Dict[str, Any]] = []
    for row in rows:
        start_minutes = _minutes_from_time(row['start_time'], 'start_time')
        end_minutes = _minutes_from_time(row['end_time'], 'end_time')
        gross = end_minutes - start_minutes
        if gross <= 0:
            gross += 24 * 60
        break_minutes = int(row['break_minutes'] or 0)
        net = max(0, gross - break_minutes)
        windows.append({
            'calendar_shift_id': None,
            'shift_id': row['shift_id'],
            'shift_code': row['shift_code'],
            'shift_name': row['shift_name'],
            'seq': row['assignment_seq'],
            'start_time': row['start_time'],
            'end_time': row['end_time'],
            'crosses_midnight': end_minutes <= start_minutes,
            'gross_minutes': gross,
            'break_minutes': break_minutes,
            'net_minutes': net,
            'capacity_factor': 1.0,
            'effective_minutes': float(net),
            'weekday': weekday,
            'day_type': None,
            'employee_id': employee_id,
            'employee_shift_assignment_id': row['assignment_id'],
        })
    return windows
