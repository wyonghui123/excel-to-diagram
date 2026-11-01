# -*- coding: utf-8 -*-
"""统一资源模型匹配 / 产能服务 (P2c)

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md
      FR-003 资源能力与技能 / FR-005 产能与可用性 / FR-008 资源分配

口径:
  · 纯函数: 调用方传入 sqlite3.Connection, 本模块只读, 不建连接、不 commit。
  · 日历优先级唯一(FR-005):
      resource.calendar_id > resource_group.calendar_id
      > location.calendar_id > 调用方给的默认日历;
    高优先级为空才回退, 不做多日历叠加。
  · 班次 = 模板(shifts) + 日历挂载(calendar_shifts):
      净工时 = (跨天展开后的总时长 - break_minutes) × capacity_factor。
  · 例外日(calendar_days):
      day_type='holiday' 当日全部班次失效;
      day_type='workday' 无视周掩码强制开工(中国调休)。
  · 无日历 = 无可用时间(返回 0), 不做"缺省 24 小时"猜测。
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

WEEKDAY_FIELDS = (
    'day_mask_mon', 'day_mask_tue', 'day_mask_wed', 'day_mask_thu',
    'day_mask_fri', 'day_mask_sat', 'day_mask_sun',
)

#: 占用资源时间窗的分配状态(canceled / completed 不占用)
ACTIVE_ASSIGNMENT_STATUSES = ('planned', 'confirmed', 'in_progress')


class ResourceMatchingError(ValueError):
    """资源匹配 / 产能校验参数或业务规则冲突。"""

    status_code = 400

    def __init__(self, message: str, code: str = 'RESOURCE_MATCHING_ERROR'):
        super().__init__(message)
        self.code = code


def _fetch_all(conn, sql: str, params=()) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_one(conn, sql: str, params=()) -> Optional[Dict[str, Any]]:
    rows = _fetch_all(conn, sql, params)
    return rows[0] if rows else None


def _normalize_date(value: Any) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return date.today().isoformat()
    text = text[:10]
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ResourceMatchingError(
            '日期格式非法(需 YYYY-MM-DD): {0!r}'.format(value), 'INVALID_DATE')
    return text


def _normalize_datetime(value: Any, label: str) -> str:
    if isinstance(value, datetime):
        return value.replace(microsecond=0, tzinfo=None).strftime(
            '%Y-%m-%d %H:%M:%S')
    text = str(value or '').strip().replace(' ', 'T')
    if not text:
        raise ResourceMatchingError('{0} 不能为空'.format(label), 'INVALID_WINDOW')
    if text.endswith('Z'):
        text = text[:-1]
    if len(text) > 10 and ('+' in text[10:] or text[10:].count('-') > 2):
        head, tail = text[:10], text[10:]
        for sep in ('+',):
            if sep in tail:
                tail = tail.split(sep)[0]
        text = head + tail
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ResourceMatchingError(
            '{0} 时间格式非法: {1!r}'.format(label, value), 'INVALID_WINDOW')
    return parsed.replace(microsecond=0, tzinfo=None).strftime(
        '%Y-%m-%d %H:%M:%S')


def _minutes_from_time(value: Any, label: str) -> int:
    text = str(value or '').strip()
    parts = text.split(':')
    if len(parts) < 2:
        raise ResourceMatchingError(
            '{0} 时间格式非法(需 HH:MM): {1!r}'.format(label, value), 'INVALID_TIME')
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        raise ResourceMatchingError(
            '{0} 时间格式非法(需 HH:MM): {1!r}'.format(label, value), 'INVALID_TIME')
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        raise ResourceMatchingError(
            '{0} 时间越界: {1!r}'.format(label, value), 'INVALID_TIME')
    return hours * 60 + minutes


# ============================================================================
# 日历解析
# ============================================================================

def resolve_resource_calendar(conn, resource_id: int,
                              default_calendar_id: Optional[int] = None,
                              as_of: Any = None) -> Optional[int]:
    """按 FR-005 的唯一优先级解析资源实际使用的日历。

    资源 -> 所属组(priority 升序 / id 升序, 只看生效成员关系) -> 地点 -> 默认。
    返回 None 表示整条链路都没有日历。
    """
    the_date = _normalize_date(as_of)
    resource = _fetch_one(
        conn,
        'SELECT id, calendar_id, location_id FROM resources WHERE id = ?',
        (resource_id,))
    if not resource:
        raise ResourceMatchingError(
            '资源不存在: {0}'.format(resource_id), 'RESOURCE_NOT_FOUND')

    if resource['calendar_id']:
        return resource['calendar_id']

    groups = _fetch_all(
        conn,
        """
        SELECT m.group_id, g.calendar_id
        FROM resource_group_members m
        JOIN resource_groups g ON g.id = m.group_id
        WHERE m.resource_id = ?
          AND (m.valid_from IS NULL OR substr(m.valid_from, 1, 10) <= ?)
          AND (m.valid_to IS NULL OR substr(m.valid_to, 1, 10) >= ?)
          AND g.is_active = 1
          AND g.calendar_id IS NOT NULL
        ORDER BY COALESCE(m.priority, 999999), m.id
        """,
        (resource_id, the_date, the_date))
    if groups:
        return groups[0]['calendar_id']

    if resource['location_id']:
        location = _fetch_one(
            conn,
            'SELECT calendar_id FROM locations WHERE id = ?',
            (resource['location_id'],))
        if location and location['calendar_id']:
            return location['calendar_id']

    return default_calendar_id


# ============================================================================
# 班次展开
# ============================================================================

def shift_windows_for_date(conn, calendar_id: int,
                           the_date: Any = None) -> List[Dict[str, Any]]:
    """展开某日历某天生效的班次窗口。

    只读取本日历挂载的 calendar_shifts, 不递归 parent_calendar_id
    (与 FR-005「不做多日历叠加」一致)。
    """
    date_str = _normalize_date(the_date)
    calendar = _fetch_one(
        conn,
        'SELECT id, status, {0} FROM calendars WHERE id = ?'.format(
            ', '.join(WEEKDAY_FIELDS)),
        (calendar_id,))
    if not calendar:
        raise ResourceMatchingError(
            '日历不存在: {0}'.format(calendar_id), 'CALENDAR_NOT_FOUND')
    if (calendar.get('status') or 'active') != 'active':
        return []

    exception = _fetch_one(
        conn,
        """
        SELECT day_type FROM calendar_days
        WHERE calendar_id = ? AND substr(date, 1, 10) = ?
        """,
        (calendar_id, date_str))
    day_type = exception['day_type'] if exception else None
    if day_type == 'holiday':
        return []

    weekday = date.fromisoformat(date_str).weekday()
    if day_type == 'workday':
        mask_enabled = True
    else:
        raw_mask = calendar.get(WEEKDAY_FIELDS[weekday])
        mask_enabled = True if raw_mask is None else bool(raw_mask)

    if not mask_enabled:
        return []

    rows = _fetch_all(
        conn,
        """
        SELECT cs.id AS calendar_shift_id, cs.seq, cs.capacity_factor,
               s.id AS shift_id, s.code AS shift_code, s.name AS shift_name,
               s.start_time, s.end_time, s.crosses_midnight, s.break_minutes
        FROM calendar_shifts cs
        JOIN shifts s ON s.id = cs.shift_id
        WHERE cs.calendar_id = ?
          AND (cs.valid_from IS NULL OR substr(cs.valid_from, 1, 10) <= ?)
          AND (cs.valid_to IS NULL OR substr(cs.valid_to, 1, 10) >= ?)
          AND s.is_active = 1
          AND (s.valid_from IS NULL OR substr(s.valid_from, 1, 10) <= ?)
          AND (s.valid_to IS NULL OR substr(s.valid_to, 1, 10) >= ?)
        ORDER BY cs.seq, cs.id
        """,
        (calendar_id, date_str, date_str, date_str, date_str))

    windows: List[Dict[str, Any]] = []
    for row in rows:
        start_minutes = _minutes_from_time(row['start_time'], 'start_time')
        end_minutes = _minutes_from_time(row['end_time'], 'end_time')
        gross = end_minutes - start_minutes
        if gross <= 0:
            gross += 24 * 60
        break_minutes = int(row['break_minutes'] or 0)
        net = max(0, gross - break_minutes)
        factor_raw = row['capacity_factor']
        factor = 1.0 if factor_raw is None else float(factor_raw)
        windows.append({
            'calendar_shift_id': row['calendar_shift_id'],
            'shift_id': row['shift_id'],
            'shift_code': row['shift_code'],
            'shift_name': row['shift_name'],
            'seq': row['seq'],
            'start_time': row['start_time'],
            'end_time': row['end_time'],
            'crosses_midnight': end_minutes <= start_minutes,
            'gross_minutes': gross,
            'break_minutes': break_minutes,
            'net_minutes': net,
            'capacity_factor': factor,
            'effective_minutes': net * factor,
            'weekday': weekday,
            'day_type': day_type,
        })
    return windows


def available_minutes(conn, resource_id: int, the_date: Any = None,
                      default_calendar_id: Optional[int] = None,
                      calendar_id: Optional[int] = None) -> float:
    """资源当日可用分钟(FR-005 产能公式)。

    = Σ 班次净工时 × resource.capacity_units × utilization_pct / 100

    显式传入 calendar_id 时跳过优先级解析(用于"临时日历"模拟)。
    None / 无日历时返回 0.0。
    """
    the_date = _normalize_date(the_date)
    resource = _fetch_one(
        conn,
        'SELECT id, capacity_units, utilization_pct FROM resources WHERE id = ?',
        (resource_id,))
    if not resource:
        raise ResourceMatchingError(
            '资源不存在: {0}'.format(resource_id), 'RESOURCE_NOT_FOUND')

    if calendar_id is None:
        calendar_id = resolve_resource_calendar(
            conn, resource_id, default_calendar_id, as_of=the_date)
    if calendar_id is None:
        return 0.0

    windows = shift_windows_for_date(conn, calendar_id, the_date)
    units = float(resource['capacity_units'] or 1)
    utilization = float(resource['utilization_pct']
                        if resource['utilization_pct'] is not None else 100)
    return sum(window['effective_minutes'] for window in windows) * units \
        * utilization / 100.0


# ============================================================================
# 多口径产能 (FR-005)
# ============================================================================

#: 按时间计量的产能口径: 有效值由日历开机时长推导; 其余口径按声明值展开
TIME_CAPACITY_CATEGORIES = frozenset({'labor_hours', 'machine_hours'})


def capacity_by_category(conn, resource_id: Optional[int] = None,
                         group_id: Optional[int] = None,
                         the_date: Any = None,
                         default_calendar_id: Optional[int] = None,
                         ) -> Dict[str, Any]:
    """读取资源/组的多口径日产能(resource_capacities)。

    口径:
      · 同一类别多条有效期重叠时, 取 valid_from 最新的有效行(同等取 id 最大);
      · labor_hours / machine_hours 的有效值 = 日历开机时长 × units × util%;
      · tool_count / vehicle_weight / vehicle_volume / facility_capacity
        按声明值 capacity_per_day × units × util%(日历不影响计量单位);
      · 日历: 资源用 FR-005 优先级链路, 组用 resource_group.calendar_id。
    """
    the_date = _normalize_date(the_date)
    if resource_id is None and group_id is None:
        raise ResourceMatchingError(
            'resource_id 与 group_id 至少提供一个', 'INVALID_ARGUMENT')

    if resource_id is not None and group_id is not None:
        scope_sql = '(resource_id = ? OR resource_group_id = ?)'
        scope_params: List[Any] = [resource_id, group_id]
    elif resource_id is not None:
        scope_sql = 'resource_id = ?'
        scope_params = [resource_id]
    else:
        scope_sql = 'resource_group_id = ?'
        scope_params = [group_id]

    rows = _fetch_all(
        conn,
        """
        SELECT id, resource_id, resource_group_id, capacity_category,
               capacity_uom_id, capacity_per_day, capacity_units,
               utilization_pct, valid_from, valid_to
        FROM resource_capacities
        WHERE {0}
          AND (valid_from IS NULL OR substr(valid_from, 1, 10) <= ?)
          AND (valid_to IS NULL OR substr(valid_to, 1, 10) >= ?)
        ORDER BY capacity_category ASC,
                 COALESCE(valid_from, '0000-00-00') DESC, id DESC
        """.format(scope_sql),
        tuple(scope_params + [the_date, the_date]))

    calendar_id: Optional[int] = None
    if resource_id is not None:
        calendar_id = resolve_resource_calendar(
            conn, resource_id, default_calendar_id, as_of=the_date)
    else:
        group = _fetch_one(
            conn,
            'SELECT calendar_id FROM resource_groups WHERE id = ?',
            (group_id,))
        calendar_id = group['calendar_id'] if group and group['calendar_id'] \
            else default_calendar_id

    windows = shift_windows_for_date(conn, calendar_id, the_date) \
        if calendar_id else []
    window_minutes = float(sum(w['effective_minutes'] for w in windows))

    categories: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        category = row['capacity_category']
        if category in categories:
            continue
        units = float(row['capacity_units'] or 1)
        utilization = float(row['utilization_pct']
                            if row['utilization_pct'] is not None else 100)
        if category in TIME_CAPACITY_CATEGORIES and window_minutes > 0:
            effective = window_minutes * units * utilization / 100.0
        else:
            effective = float(row['capacity_per_day'] or 0) * units \
                * utilization / 100.0
        categories[category] = {
            'capacity_category': category,
            'scope': 'resource' if row['resource_id'] else 'group',
            'capacity_uom_id': row['capacity_uom_id'],
            'declared_per_day': row['capacity_per_day'],
            'capacity_units': units,
            'utilization_pct': utilization,
            'effective_per_day': effective,
            'valid_from': row['valid_from'],
            'valid_to': row['valid_to'],
        }

    return {
        'resource_id': resource_id,
        'group_id': group_id,
        'as_of': the_date,
        'calendar_id': calendar_id,
        'calendar_minutes': window_minutes,
        'categories': categories,
    }


# ============================================================================
# 技能匹配
# ============================================================================

def match_resources(conn, skill_id: Optional[int] = None,
                    min_level: Optional[int] = None,
                    group_id: Optional[int] = None,
                    as_of: Any = None,
                    resource_kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """按技能 / 最低等级 / 组 / 资源类型筛可用资源。

    · 传 skill_id 时要求存在**当时有效**的能力(valid_to < as_of 视为过期并排除);
    · 结果按能力等级降序, 同级按 code 升序, 保证确定性。
    """
    if min_level is not None and skill_id is None:
        raise ResourceMatchingError(
            'min_level 必须与 skill_id 同时使用', 'INVALID_ARGUMENT')

    as_of_date = _normalize_date(as_of)
    selected = [
        'r.id AS resource_id', 'r.code', 'r.name', 'r.resource_kind',
        'r.capacity_per_day', 'r.capacity_uom_id',
    ]
    joins: List[str] = []
    join_params: List[Any] = []
    where = [
        'r.is_active = 1',
        '(r.valid_from IS NULL OR substr(r.valid_from, 1, 10) <= ?)',
        '(r.valid_to IS NULL OR substr(r.valid_to, 1, 10) >= ?)',
    ]
    where_params: List[Any] = [as_of_date, as_of_date]

    if skill_id is not None:
        selected.append('cap.level AS level')
        joins.append(
            'JOIN resource_capabilities cap ON cap.resource_id = r.id '
            'AND cap.skill_id = ? '
            'AND (cap.valid_from IS NULL OR substr(cap.valid_from, 1, 10) <= ?) '
            'AND (cap.valid_to IS NULL OR substr(cap.valid_to, 1, 10) >= ?)')
        join_params.extend([skill_id, as_of_date, as_of_date])
        if min_level is not None:
            where.append('cap.level >= ?')
            where_params.append(min_level)

    if group_id is not None:
        where.append(
            'EXISTS (SELECT 1 FROM resource_group_members m '
            'WHERE m.group_id = ? AND m.resource_id = r.id '
            'AND (m.valid_from IS NULL OR substr(m.valid_from, 1, 10) <= ?) '
            'AND (m.valid_to IS NULL OR substr(m.valid_to, 1, 10) >= ?))')
        where_params.extend([group_id, as_of_date, as_of_date])

    if resource_kind:
        where.append('r.resource_kind = ?')
        where_params.append(resource_kind)

    order_by = 'cap.level DESC, r.code ASC' if skill_id is not None \
        else 'r.code ASC'
    sql = 'SELECT {0} FROM resources r {1} WHERE {2} ORDER BY {3}'.format(
        ', '.join(selected), ' '.join(joins), ' AND '.join(where), order_by)
    return _fetch_all(conn, sql, tuple(join_params + where_params))


# ============================================================================
# 分配校验 (FR-008)
# ============================================================================

def validate_assignment(conn, work_order_operation_id: int, resource_id: int,
                        planned_start: Any, planned_end: Any,
                        planned_qty: Optional[float] = None,
                        max_qty: Optional[float] = None,
                        allow_overlap: bool = False,
                        exclude_assignment_id: Optional[int] = None,
                        ) -> Dict[str, Any]:
    """校验一次资源分配是否可落库。违规抛 ResourceMatchingError。

    校验顺序: 工序存在 -> 资源存在且启用 -> 属工序指定组 -> 数量
              -> 时间窗合法 -> 同资源时间窗不重叠。
    工序本身无数字段(work_order_operations 无 qty), 故上限由调用方 max_qty 传入。
    """
    operation = _fetch_one(
        conn,
        'SELECT id, resource_group_id, required_skill_id '
        'FROM work_order_operations WHERE id = ?',
        (work_order_operation_id,))
    if not operation:
        raise ResourceMatchingError(
            '工序不存在: {0}'.format(work_order_operation_id),
            'OPERATION_NOT_FOUND')

    resource = _fetch_one(
        conn,
        'SELECT id, is_active, code FROM resources WHERE id = ?',
        (resource_id,))
    if not resource:
        raise ResourceMatchingError(
            '资源不存在: {0}'.format(resource_id), 'RESOURCE_NOT_FOUND')
    if not resource['is_active']:
        raise ResourceMatchingError(
            '资源已停用: {0}'.format(resource['code']), 'RESOURCE_INACTIVE')

    start_text = _normalize_datetime(planned_start, 'planned_start')
    end_text = _normalize_datetime(planned_end, 'planned_end')
    if start_text >= end_text:
        raise ResourceMatchingError(
            '计划结束必须晚于开始: {0} -> {1}'.format(start_text, end_text),
            'INVALID_WINDOW')

    if planned_qty is not None:
        if planned_qty <= 0:
            raise ResourceMatchingError(
                '计划量必须大于 0: {0}'.format(planned_qty), 'INVALID_QTY')
        if max_qty is not None and planned_qty > max_qty:
            raise ResourceMatchingError(
                '计划量 {0} 超过工序可分配量 {1}'.format(planned_qty, max_qty),
                'QTY_EXCEEDS_OPERATION')

    group_id = operation['resource_group_id']
    if group_id:
        member = _fetch_one(
            conn,
            """
            SELECT 1 AS ok FROM resource_group_members
            WHERE group_id = ? AND resource_id = ?
              AND (valid_from IS NULL OR substr(valid_from, 1, 10) <= ?)
              AND (valid_to IS NULL OR substr(valid_to, 1, 10) >= ?)
            LIMIT 1
            """,
            (group_id, resource_id, start_text[:10], start_text[:10]))
        if not member:
            raise ResourceMatchingError(
                '资源 {0} 不属于工序指定的组 {1}'.format(
                    resource['code'], group_id), 'RESOURCE_NOT_IN_GROUP')

    if not allow_overlap:
        overlap_sql = """
            SELECT id, resource_id, planned_start, planned_end,
                   work_order_operation_id
            FROM resource_assignments
            WHERE resource_id = ?
              AND status IN ({0})
              AND planned_start IS NOT NULL AND planned_end IS NOT NULL
              AND substr(planned_start, 1, 19) < ?
              AND substr(planned_end, 1, 19) > ?
        """.format(', '.join("'{0}'".format(s)
                      for s in ACTIVE_ASSIGNMENT_STATUSES))
        overlap_params: List[Any] = [resource_id, end_text, start_text]
        if exclude_assignment_id is not None:
            overlap_sql += ' AND id <> ?'
            overlap_params.append(exclude_assignment_id)
        overlap_sql += ' ORDER BY planned_start, id LIMIT 1'
        overlap = _fetch_one(conn, overlap_sql, tuple(overlap_params))
        if overlap:
            raise ResourceMatchingError(
                '资源 {0} 在 {1} ~ {2} 已有分配(id={3})'.format(
                    resource['code'], overlap['planned_start'],
                    overlap['planned_end'], overlap['id']),
                'ASSIGNMENT_OVERLAP')

    warnings: List[str] = []
    if operation['required_skill_id']:
        capability = _fetch_one(
            conn,
            """
            SELECT 1 AS ok FROM resource_capabilities
            WHERE resource_id = ? AND skill_id = ?
              AND (valid_from IS NULL OR substr(valid_from, 1, 10) <= ?)
              AND (valid_to IS NULL OR substr(valid_to, 1, 10) >= ?)
            LIMIT 1
            """,
            (resource_id, operation['required_skill_id'], start_text[:10],
             start_text[:10]))
        if not capability:
            warnings.append('SKILL_NOT_VERIFIED')

    return {
        'ok': True,
        'operation_id': operation['id'],
        'resource_id': resource_id,
        'planned_start': start_text,
        'planned_end': end_text,
        'planned_qty': planned_qty,
        'warnings': warnings,
    }
