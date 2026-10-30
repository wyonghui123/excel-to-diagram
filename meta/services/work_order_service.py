# -*- coding: utf-8 -*-
"""服务工单 / SLA 服务 —— B6：工单创建、SLA 覆盖命中、业务日历计时与事件结算。

批次 4a 增补：`order_type=production` 分支（需求追溯 + 组件展开）。
  · service 路径行为不变（R-ST-0..R-ST-8 全部收窄为 service 专属）。
  · production 走 `source_demand_type` + `source_demand_id`（计划行 / 订单行），
    禁 `asset_ref` / `coverage_id` / `schedule_kind='service'`；
    不匹配 SLA、不生成里程碑、不写 service_events（只写 change_events 一条）。
  · `expand_components()` 按 `item_structures(usage='production')` 展开组件，
    幂等重建 `work_order_components`（先 DELETE 再 INSERT）。
  · 物料与数量由需求来源**自动推导**（计划行 → 订单行 item_id + promised_qty，
    未承诺时回退订单行 qty；订单行 → 自身 item_id / qty），payload 显式值优先；
    推导不出时记 `no_structure(missing_item_or_qty)`，不阻断建单。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md
      §10.5 对象模型 / §10.6 状态机与 SLA 规则 / §10.7 接线 / §10.10 B6 验收

口径:
  · 工单唯一挂载点 = `schedule_id`，且计划行必须 `schedule_kind='service'`（R-ST-0）。
  · SLA 规则命中：同一工单**恰好 1 条**规则才生成里程碑；0 / 多条返回
    `SLA_RULE_AMBIGUOUS` + trace，并写 `service_events(event_type='sla_trace')`（R-ST-2）。
  · `due_at` 一律按业务日历推进（`calendars` 周模式 + `calendar_days` 例外日），
    每日 09:00–17:00 共 480 业务分钟；**禁自然日**（R-ST-3）。
  · 挂起 → 里程碑 Paused；恢复 → 累加 `paused_total_minutes` 并顺延 `due_at`（R-ST-4）。
  · 里程碑只由 `service_events` 推进；工单状态不直写里程碑（R-ST-5）。
  · `resolve` 事件 → 解决里程碑 Met（超期则 Breached）→ 服务计划行 completed
    → `service_status` 重算；**绝不写** `fulfillment_status`（R-ST-7 / INV-1）。
  · 事务边界由调用方控制（与 ShipmentService 同构，本服务不自行开事务）。

覆写 `_load_*` / `_insert` 即可注入测试数据。
"""

import json
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WORK_ORDER_TABLE = 'work_orders'
OPERATION_TABLE = 'work_order_operations'
COMPONENT_TABLE = 'work_order_components'
COVERAGE_TABLE = 'sla_coverages'
COVERAGE_RULE_TABLE = 'sla_coverage_rules'
MILESTONE_TABLE = 'sla_milestones'
EVENT_TABLE = 'service_events'
SCHEDULE_TABLE = 'sales_order_schedules'
ORDER_LINE_TABLE = 'sales_order_lines'
SALES_ORDER_TABLE = 'sales_orders'
STRUCTURE_TABLE = 'item_structures'
STRUCTURE_LINE_TABLE = 'item_structure_lines'
CALENDAR_TABLE = 'calendars'
CALENDAR_DAY_TABLE = 'calendar_days'
CHANGE_EVENT_TABLE = 'change_events'

SCHEDULE_KIND_SERVICE = 'service'

ORDER_TYPE_SERVICE = 'service'
ORDER_TYPE_PRODUCTION = 'production'

SOURCE_DEMAND_SCHEDULE = 'sales_order_schedule'
SOURCE_DEMAND_LINE = 'sales_order_line'
SOURCE_DEMAND_TYPES = (SOURCE_DEMAND_SCHEDULE, SOURCE_DEMAND_LINE)

STRUCTURE_USAGE_PRODUCTION = 'production'
STRUCTURE_STATUS_ACTIVE = 'active'

MILESTONE_FIRST_RESPONSE = 'first_response'
MILESTONE_RESOLUTION = 'resolution'
MILESTONE_TYPES = (MILESTONE_FIRST_RESPONSE, MILESTONE_RESOLUTION)

STATUS_NEW = 'New'
STATUS_IN_PROGRESS = 'In Progress'
STATUS_WAITING = 'Waiting'
STATUS_RESOLVED = 'Resolved'
STATUS_CLOSED = 'Closed'
STATUS_CANCELLED = 'Cancelled'
STATUS_SETTLED = (STATUS_RESOLVED, STATUS_CLOSED)

MILESTONE_PENDING = 'Pending'
MILESTONE_RUNNING = 'Running'
MILESTONE_PAUSED = 'Paused'
MILESTONE_WARNED = 'Warned'
MILESTONE_MET = 'Met'
MILESTONE_BREACHED = 'Breached'
MILESTONE_OPEN = (MILESTONE_PENDING, MILESTONE_RUNNING, MILESTONE_WARNED)
MILESTONE_PAUSABLE = (MILESTONE_RUNNING, MILESTONE_WARNED)

#: 业务日窗口：09:00–17:00，共 480 业务分钟（R-ST-3 口径）
BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 17
BUSINESS_DAY_MINUTES = 480

#: 无日历时默认标准周：周一至周五工作，周六周日休息
DEFAULT_DAY_MASK = (True, True, True, True, True, False, False)

SERVICE_STATUS_NONE = 'none'
SERVICE_STATUS_PLANNED = 'planned'
SERVICE_STATUS_PARTIAL = 'partial'
SERVICE_STATUS_COMPLETED = 'completed'
SERVICE_STATUS_CANCELLED = 'cancelled'

SLA_RULE_AMBIGUOUS = 'SLA_RULE_AMBIGUOUS'


class WorkOrderError(ValueError):
    """服务工单守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

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


def _fmt(value: datetime) -> str:
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _parse_dt(value: Any) -> datetime:
    """接受 datetime / 'YYYY-MM-DD HH:MM:SS' / ISO 的时分秒或纯日期。"""
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace('T', ' ')
    if len(text) >= 19:
        text = text[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise WorkOrderError('时间格式非法：%s' % value, rule='ST_TIME_INVALID')


def _int_minutes(value: Any, default: int = 0) -> int:
    if _blank(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise WorkOrderError('分钟数必须是数字：%s' % value,
                             rule='SLA_MINUTES_INVALID')


def _num(value: Any) -> Optional[float]:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round4(value: float) -> float:
    """ROUND_HALF_UP 保留 4 位小数（组件需求量口径）。"""
    return float(Decimal(str(value)).quantize(Decimal('0.0001'),
                                              rounding=ROUND_HALF_UP))


class WorkOrderService:
    """服务工单创建、SLA 覆盖命中、业务日历计时与事件结算。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------ 创建

    def create_work_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """按 order_type 分流：service（SLA 路径，行为不变）/ production（需求追溯 + 组件展开）。"""
        payload = dict(payload or {})
        order_type = payload.get('order_type') or ORDER_TYPE_SERVICE
        if order_type == ORDER_TYPE_PRODUCTION:
            return self._create_production(payload)
        if order_type != ORDER_TYPE_SERVICE:
            raise WorkOrderError(
                '工单类型 %s 尚未启用（仅支持 service / production）' % order_type,
                field_name='order_type', rule='ST_ORDER_TYPE_UNSUPPORTED')
        return self._create_service(payload)

    def _create_service(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建服务工单并生成 SLA 里程碑；返回 `{'id', 'work_order_no', 'status', 'sla'}`。"""
        schedule = self._require_service_schedule(payload.get('schedule_id'))

        order_id = payload.get('order_id')
        if not _blank(order_id) and str(order_id) != str(schedule.get('order_id')):
            raise WorkOrderError('工单来源订单与计划行不一致',
                                 field_name='order_id', rule='ST_SCHEDULE_INVALID')
        order_id = order_id if not _blank(order_id) else schedule.get('order_id')

        order_line_id = payload.get('order_line_id')
        if not _blank(order_line_id) and str(order_line_id) != str(schedule.get('line_id')):
            raise WorkOrderError('工单订单行与计划行反查结果不一致',
                                 field_name='order_line_id',
                                 rule='ST_SCHEDULE_INVALID')
        order_line_id = order_line_id if not _blank(order_line_id) \
            else schedule.get('line_id')

        severity = payload.get('severity')
        if _blank(severity):
            raise WorkOrderError('工单必须填写严重度（SLA 条件列）',
                                 field_name='severity',
                                 rule='SLA_SEVERITY_REQUIRED')

        opened_at = payload.get('opened_at') or _now()
        _parse_dt(opened_at)  # 格式校验（非法直接拒绝）

        work_order_no = payload.get('work_order_no') or self._next_work_order_no()
        now = _now()
        row = {
            'work_order_no': work_order_no,
            'order_type': payload.get('order_type') or 'service',
            'schedule_id': schedule.get('id'),
            'order_id': order_id,
            'order_line_id': order_line_id,
            'customer_account_id': payload.get('customer_account_id'),
            'severity': severity,
            'channel': payload.get('channel'),
            'status': payload.get('status') or STATUS_NEW,
            'coverage_id': None,
            'asset_ref': payload.get('asset_ref'),
            'source_demand_type': None,
            'source_demand_id': None,
            'opened_at': opened_at,
            'first_response_at': payload.get('first_response_at'),
            'resolved_at': payload.get('resolved_at'),
            'closed_at': payload.get('closed_at'),
            'created_at': now,
            'updated_at': now,
        }
        work_order_id = self._insert(WORK_ORDER_TABLE, row)

        self._append_event(work_order_id, 'create', opened_at,
                           payload.get('actor'),
                           {'severity': severity,
                            'channel': payload.get('channel')})
        self._append_change_event(work_order_id, 'state_change',
                                  {'status': (None, row['status'])})

        match = self.match_coverage({
            'severity': severity,
            'channel': payload.get('channel'),
            'org_id': payload.get('org_id'),
            'customer_account_id': payload.get('customer_account_id'),
            'opened_at': opened_at,
        })

        milestones: List[Dict[str, Any]] = []
        if match.get('coverage') and match.get('rule'):
            coverage = match['coverage']
            self.ds.execute(
                'UPDATE %s SET coverage_id = ?, updated_at = ? WHERE id = ?'
                % WORK_ORDER_TABLE, [coverage.get('id'), now, work_order_id])
            milestones = self._create_milestones(
                work_order_id, match['rule'], coverage.get('calendar_id'),
                opened_at)
            sla = {
                'code': None,
                'reason': None,
                'trace': match.get('trace'),
                'coverage_id': coverage.get('id'),
                'milestones': milestones,
                'candidates': match.get('candidates'),
            }
        else:
            # R-ST-2：0 / 多条都不生成里程碑，写 trace 供详情页提示
            self._append_event(
                work_order_id, 'sla_trace', opened_at, payload.get('actor'),
                {'code': match.get('code'),
                 'reason': match.get('reason'),
                 'trace': match.get('trace'),
                 'candidates': match.get('candidates')})
            sla = {
                'code': match.get('code'),
                'reason': match.get('reason'),
                'trace': match.get('trace'),
                'coverage_id': None,
                'milestones': [],
                'candidates': match.get('candidates'),
            }

        return {
            'id': work_order_id,
            'work_order_no': work_order_no,
            'status': row['status'],
            'schedule_id': schedule.get('id'),
            'sla': sla,
        }

    # -------------------------------------------------------- 生产工单（批次 4a）

    def _create_production(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建生产工单：需求追溯 + 可选组件展开；不匹配 SLA、不写 service_events。"""
        demand_type = payload.get('source_demand_type')
        demand_id = payload.get('source_demand_id')
        if _blank(demand_type) or _blank(demand_id) \
                or str(demand_type) not in SOURCE_DEMAND_TYPES:
            raise WorkOrderError(
                '生产工单必须提供有效需求来源（source_demand_type / source_demand_id）',
                field_name='source_demand_id', rule='ST_SOURCE_DEMAND_REQUIRED')

        if not _blank(payload.get('asset_ref')):
            raise WorkOrderError('生产工单不允许填写资产引用',
                                 field_name='asset_ref',
                                 rule='ST_ASSET_NOT_ALLOWED')
        if not _blank(payload.get('coverage_id')):
            raise WorkOrderError('生产工单不允许绑定 SLA 覆盖',
                                 field_name='coverage_id',
                                 rule='ST_SLA_NOT_ALLOWED')

        demand = self._resolve_demand(str(demand_type), demand_id)

        schedule_id = payload.get('schedule_id')
        if not _blank(schedule_id):
            self._reject_service_schedule(schedule_id)

        order_line_id = payload.get('order_line_id')
        if not _blank(order_line_id) \
                and str(order_line_id) != str(demand.get('order_line_id')):
            raise WorkOrderError('订单行与需求来源反查结果不一致',
                                 field_name='order_line_id',
                                 rule='ST_SOURCE_DEMAND_INVALID')
        order_line_id = order_line_id if not _blank(order_line_id) \
            else demand.get('order_line_id')

        # 组件展开的物料与数量：payload 显式优先，缺省由需求来源自动推导（T4.2）
        item_id = payload.get('item_id')
        if _blank(item_id):
            item_id = demand.get('item_id')
        qty = payload.get('qty')
        if _blank(qty):
            qty = demand.get('qty')

        customer_account_id = payload.get('customer_account_id')
        if _blank(customer_account_id):
            customer_account_id = demand.get('customer_account_id')

        opened_at = payload.get('opened_at') or _now()
        _parse_dt(opened_at)  # 格式校验（非法直接拒绝）

        work_order_no = payload.get('work_order_no') or self._next_work_order_no()
        now = _now()
        row = {
            'work_order_no': work_order_no,
            'order_type': ORDER_TYPE_PRODUCTION,
            'schedule_id': None if _blank(schedule_id) else schedule_id,
            'order_id': demand.get('order_id'),
            'order_line_id': order_line_id,
            'customer_account_id': customer_account_id,
            'severity': payload.get('severity'),
            'channel': payload.get('channel'),
            'status': payload.get('status') or STATUS_NEW,
            'coverage_id': None,
            'asset_ref': None,
            'source_demand_type': str(demand_type),
            'source_demand_id': demand_id,
            'opened_at': opened_at,
            'first_response_at': payload.get('first_response_at'),
            'resolved_at': None,
            'closed_at': None,
            'created_at': now,
            'updated_at': now,
        }
        work_order_id = self._insert(WORK_ORDER_TABLE, row)

        # 生产工单无 SLA：只写 change_events 一条 state_change（P-3）
        self._append_change_event(work_order_id, 'state_change',
                                  {'status': (None, row['status'])})

        expansion = self._maybe_expand_components(work_order_id, item_id, qty)
        return {
            'id': work_order_id,
            'work_order_no': work_order_no,
            'status': row['status'],
            'order_type': ORDER_TYPE_PRODUCTION,
            'schedule_id': row['schedule_id'],
            'source_demand_type': row['source_demand_type'],
            'source_demand_id': row['source_demand_id'],
            'item_id': item_id,
            'qty': qty,
            'component_expansion': expansion,
            'sla': None,
        }

    def _maybe_expand_components(self, work_order_id: int, item_id: Any,
                                 qty: Any) -> Dict[str, Any]:
        """由需求来源推导 item_id / qty 后自动展开组件；无结构不阻断建单。"""
        if _blank(item_id) or _blank(qty):
            return {'code': 'no_structure', 'count': 0, 'structure_id': None,
                    'reason': 'missing_item_or_qty'}
        result = self.expand_components(work_order_id, item_id, qty)
        return {'code': result.get('code'),
                'count': len(result.get('components') or []),
                'structure_id': result.get('structure_id')}

    def expand_components(self, work_order_id: Any, item_id: Any, qty: Any,
                          as_of: Any = None) -> Dict[str, Any]:
        """按 active `item_structures(usage='production')` 展开组件（幂等重建）。

        口径:
          · 结构选择：alternative_no ASC, revision DESC, id DESC 取第一条；
            valid_from / valid_to 以业务日为界（NULL = 不限）。
          · qty_required = (qty_per × qty + fixed_qty) × (1 + scrap_rate)，ROUND_HALF_UP 4 位。
          · optional 行取 default_qty（缺省 min_qty），并按 min_qty / max_qty 夹紧。
          · 先 DELETE 再 INSERT（重复调用结果一致）；无结构返回 no_structure 且不动既有行。
        """
        if _blank(work_order_id) or _blank(item_id):
            raise WorkOrderError('组件展开需工单与物料', field_name='item_id',
                                 rule='ST_COMPONENT_INPUT_INVALID')
        quantity = _num(qty)
        if quantity is None:
            raise WorkOrderError('工单数量必须是数字：%s' % qty,
                                 rule='ST_COMPONENT_INPUT_INVALID')
        day = str(as_of or _now())[:10]

        try:
            structures = self.ds.query(
                "SELECT id, item_id, usage, alternative_no, revision, base_qty, "
                "status, valid_from, valid_to FROM %s "
                "WHERE item_id = ? AND usage = ? AND status = ? "
                "AND (valid_from IS NULL OR substr(valid_from, 1, 10) <= ?) "
                "AND (valid_to IS NULL OR substr(valid_to, 1, 10) >= ?) "
                "ORDER BY alternative_no ASC, revision DESC, id DESC LIMIT 1"
                % STRUCTURE_TABLE,
                [item_id, STRUCTURE_USAGE_PRODUCTION, STRUCTURE_STATUS_ACTIVE,
                 day, day])
        except Exception as e:  # 结构表未就绪 → 视为无结构（不阻断建单）
            logger.warning('[work_order] 读取 production 结构失败: %s', e)
            structures = []

        if not structures:
            return {'code': 'no_structure', 'structure_id': None, 'components': []}

        structure_id = structures[0].get('id')
        try:
            lines = self.ds.query(
                "SELECT id, structure_id, line_no, component_item_id, qty_per, "
                "fixed_qty, scrap_rate, optional_flag, default_qty, min_qty, max_qty "
                "FROM %s WHERE structure_id = ? "
                "AND (valid_from IS NULL OR substr(valid_from, 1, 10) <= ?) "
                "AND (valid_to IS NULL OR substr(valid_to, 1, 10) >= ?) "
                "ORDER BY line_no, id" % STRUCTURE_LINE_TABLE,
                [structure_id, day, day])
        except Exception as e:  # 结构行表未就绪 → 视为无组件
            logger.warning('[work_order] 读取 production 结构行失败: %s', e)
            lines = []

        self.ds.execute('DELETE FROM %s WHERE work_order_id = ?'
                        % COMPONENT_TABLE, [work_order_id])

        now = _now()
        created: List[Dict[str, Any]] = []
        for line in lines:
            qty_required = self._component_qty_required(line, quantity)
            self._insert(COMPONENT_TABLE, {
                'work_order_id': work_order_id,
                'structure_id': structure_id,
                'structure_line_id': line.get('id'),
                'component_item_id': line.get('component_item_id'),
                'line_no': line.get('line_no'),
                'qty_per': line.get('qty_per'),
                'fixed_qty': line.get('fixed_qty'),
                'scrap_rate': line.get('scrap_rate'),
                'qty_required': qty_required,
                'optional_flag': 1 if bool(line.get('optional_flag')) else 0,
                'created_at': now,
                'updated_at': now,
            })
            created.append({
                'structure_line_id': line.get('id'),
                'component_item_id': line.get('component_item_id'),
                'line_no': line.get('line_no'),
                'qty_required': qty_required,
            })

        return {'code': 'expanded', 'structure_id': structure_id,
                'components': created}

    @staticmethod
    def _component_qty_required(line: Dict[str, Any],
                                quantity: float) -> float:
        scrap = _num(line.get('scrap_rate')) or 0.0
        if bool(line.get('optional_flag')):
            base = _num(line.get('default_qty'))
            if base is None:
                base = _num(line.get('min_qty')) or 0.0
            minimum = _num(line.get('min_qty'))
            maximum = _num(line.get('max_qty'))
            value = base
            if minimum is not None:
                value = max(value, minimum)
            if maximum is not None:
                value = min(value, maximum)
            value = value * (1 + scrap)
        else:
            value = ((_num(line.get('qty_per')) or 0.0) * quantity
                     + (_num(line.get('fixed_qty')) or 0.0)) * (1 + scrap)
        return _round4(value)

    def _resolve_demand(self, demand_type: str,
                        demand_id: Any) -> Dict[str, Any]:
        """回查需求来源，冗余 order_id / order_line_id / customer_account_id / item_id / qty。"""
        if demand_type == SOURCE_DEMAND_SCHEDULE:
            rows = self.ds.query(
                'SELECT id, order_id, line_id, schedule_kind, promised_qty '
                'FROM %s WHERE id = ?' % SCHEDULE_TABLE, [demand_id])
            if not rows:
                raise WorkOrderError('需求来源计划行不存在',
                                     field_name='source_demand_id',
                                     rule='ST_SOURCE_DEMAND_INVALID')
            schedule = rows[0]
            # P-2：生产工单禁止追溯服务计划行
            if str(schedule.get('schedule_kind')) == SCHEDULE_KIND_SERVICE:
                raise WorkOrderError('生产工单不能追溯到服务计划行',
                                     field_name='source_demand_id',
                                     rule='ST_SCHEDULE_INVALID')
            line_info = self._line_item_qty(schedule.get('line_id'))
            qty = schedule.get('promised_qty')
            if _blank(qty):
                qty = line_info.get('qty')  # 未承诺数量时回退订单行数量
            return {
                'order_id': schedule.get('order_id'),
                'order_line_id': schedule.get('line_id'),
                'customer_account_id': self._order_customer(
                    schedule.get('order_id')),
                'item_id': line_info.get('item_id'),
                'qty': qty,
            }

        rows = self.ds.query(
            'SELECT id, order_id, item_id, qty FROM %s WHERE id = ?'
            % ORDER_LINE_TABLE, [demand_id])
        if not rows:
            raise WorkOrderError('需求来源订单行不存在',
                                 field_name='source_demand_id',
                                 rule='ST_SOURCE_DEMAND_INVALID')
        line = rows[0]
        return {
            'order_id': line.get('order_id'),
            'order_line_id': line.get('id'),
            'customer_account_id': self._order_customer(line.get('order_id')),
            'item_id': line.get('item_id'),
            'qty': line.get('qty'),
        }

    def _line_item_qty(self, line_id: Any) -> Dict[str, Any]:
        """从订单行取 item_id / qty（列缺失或行不存在时 fail-open 返回空）。"""
        if _blank(line_id):
            return {'item_id': None, 'qty': None}
        try:
            rows = self.ds.query(
                'SELECT id, item_id, qty FROM %s WHERE id = ?' % ORDER_LINE_TABLE,
                [line_id])
        except Exception as e:
            logger.warning('[work_order] 读取订单行物料失败: %s', e)
            return {'item_id': None, 'qty': None}
        if not rows:
            return {'item_id': None, 'qty': None}
        return {'item_id': rows[0].get('item_id'), 'qty': rows[0].get('qty')}

    def _order_customer(self, order_id: Any) -> Any:
        """从销售订单头取客户；主表 / 列缺失时 fail-open 返回 None。"""
        if _blank(order_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT customer_account_id FROM %s WHERE id = ?'
                % SALES_ORDER_TABLE, [order_id])
        except Exception as e:
            logger.warning('[work_order] 读取订单客户失败: %s', e)
            return None
        return rows[0].get('customer_account_id') if rows else None

    def _reject_service_schedule(self, schedule_id: Any) -> None:
        rows = self.ds.query(
            'SELECT id, schedule_kind FROM %s WHERE id = ?' % SCHEDULE_TABLE,
            [schedule_id])
        if not rows:
            raise WorkOrderError('计划行不存在', field_name='schedule_id',
                                 rule='ST_SCHEDULE_INVALID')
        if str(rows[0].get('schedule_kind')) == SCHEDULE_KIND_SERVICE:
            raise WorkOrderError('生产工单不能挂载服务计划行',
                                 field_name='schedule_id',
                                 rule='ST_SCHEDULE_INVALID')

    # -------------------------------------------------------------- 覆盖命中

    def match_coverage(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """R-ST-1 / R-ST-2：命中恰好 1 条规则才可用，否则返回 `SLA_RULE_AMBIGUOUS`。"""
        payload = dict(payload or {})
        severity = payload.get('severity')
        channel = payload.get('channel')
        day = str(payload.get('opened_at') or _now())[:10]

        try:
            coverages = self.ds.query(
                'SELECT id, name, org_id, calendar_id, start_date, end_date, active '
                'FROM %s' % COVERAGE_TABLE)
        except Exception as e:  # 表未就绪 → 视为未命中（fail-open）
            logger.warning('[work_order] 读取 SLA 覆盖失败: %s', e)
            coverages = []

        candidates: List[Dict[str, Any]] = []
        for coverage in coverages:
            if not self._coverage_applies(coverage, payload.get('org_id'), day):
                continue
            rules = self._load_rules(coverage.get('id'))
            for rule in rules:
                if self._rule_matches(rule, severity, channel):
                    candidates.append({'coverage': coverage, 'rule': rule})

        if len(candidates) == 1:
            return {
                'code': None,
                'reason': None,
                'trace': '命中 1 条 SLA 规则（覆盖 %s）' % candidates[0]['coverage'].get('id'),
                'candidates': [{'coverage_id': candidates[0]['coverage'].get('id'),
                                'rule_id': candidates[0]['rule'].get('id')}],
                'coverage': candidates[0]['coverage'],
                'rule': candidates[0]['rule'],
            }

        if not candidates:
            return {
                'code': SLA_RULE_AMBIGUOUS,
                'reason': 'no_rule',
                'trace': '未命中 SLA 规则（严重度 %s / 渠道 %s）' % (severity, channel),
                'candidates': [],
                'coverage': None,
                'rule': None,
            }

        return {
            'code': SLA_RULE_AMBIGUOUS,
            'reason': 'multiple_rules',
            'trace': '命中 %d 条 SLA 规则（需恰好 1 条）' % len(candidates),
            'candidates': [{'coverage_id': c['coverage'].get('id'),
                            'rule_id': c['rule'].get('id')}
                           for c in candidates],
            'coverage': None,
            'rule': None,
        }

    # -------------------------------------------------------------- 业务日历

    def compute_due_at(self, start_at: Any, minutes: Any,
                       calendar_id: Any = None) -> str:
        """R-ST-3：从 start_at 起按业务日历推进 minutes 个业务分钟，返回 'YYYY-MM-DD HH:MM:SS'。"""
        remaining = float(_int_minutes(minutes))
        cursor = _parse_dt(start_at)
        if remaining <= 0:
            return _fmt(cursor)

        mask = self._calendar_mask(calendar_id)
        guard = 0
        while remaining > 0:
            guard += 1
            if guard > 10000:
                raise WorkOrderError('业务日历推进超出上限', rule='ST_CALENDAR_LOOP')
            day = cursor.date()
            if not self._is_workday(day, calendar_id, mask):
                cursor = datetime.combine(
                    day + timedelta(days=1), time(BUSINESS_START_HOUR, 0))
                continue
            day_start = datetime.combine(day, time(BUSINESS_START_HOUR, 0))
            day_end = datetime.combine(day, time(BUSINESS_END_HOUR, 0))
            if cursor < day_start:
                cursor = day_start
            if cursor >= day_end:
                cursor = datetime.combine(
                    day + timedelta(days=1), time(BUSINESS_START_HOUR, 0))
                continue
            available = (day_end - cursor).total_seconds() / 60.0
            if remaining <= available:
                cursor = cursor + timedelta(minutes=remaining)
                remaining = 0
            else:
                remaining -= available
                cursor = datetime.combine(
                    day + timedelta(days=1), time(BUSINESS_START_HOUR, 0))
        return _fmt(cursor)

    # -------------------------------------------------------------- 暂停/恢复

    def pause(self, work_order_id: Any, now: Any = None,
              actor: Any = None, note: Any = None) -> Dict[str, Any]:
        """R-ST-4：处理中 → Waiting，里程碑 Paused（记录 hold 事件作为暂停起点）。"""
        occurred = now or _now()
        work_order = self._require_work_order(work_order_id)
        if str(work_order.get('status')) != STATUS_IN_PROGRESS:
            raise WorkOrderError(
                '仅处理中的工单可挂起（当前 %s）' % work_order.get('status'),
                field_name='status', rule='ST_STATE_INVALID')

        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % WORK_ORDER_TABLE,
            [STATUS_WAITING, occurred, work_order.get('id')])
        self._append_event(work_order.get('id'), 'hold', occurred, actor,
                           {'note': note})

        paused = []
        for milestone in self._load_milestones(work_order.get('id')):
            if str(milestone.get('state')) not in MILESTONE_PAUSABLE:
                continue
            self.ds.execute(
                'UPDATE %s SET state = ?, updated_at = ? WHERE id = ?'
                % MILESTONE_TABLE, [MILESTONE_PAUSED, occurred, milestone.get('id')])
            paused.append(milestone.get('id'))

        self._append_change_event(work_order.get('id'), 'state_change',
                                  {'status': (STATUS_IN_PROGRESS, STATUS_WAITING)})
        return {'id': work_order.get('id'), 'status': STATUS_WAITING,
                'paused_milestones': paused}

    def resume(self, work_order_id: Any, now: Any = None,
               actor: Any = None, note: Any = None) -> Dict[str, Any]:
        """R-ST-4：Waiting → 处理中，累加 paused_total_minutes 并顺延 due_at / warn_at。"""
        occurred = now or _now()
        work_order = self._require_work_order(work_order_id)
        if str(work_order.get('status')) != STATUS_WAITING:
            raise WorkOrderError(
                '仅等待中的工单可恢复（当前 %s）' % work_order.get('status'),
                field_name='status', rule='ST_STATE_INVALID')

        paused_minutes = self._hold_elapsed_minutes(work_order.get('id'), occurred)
        calendar_id = self._work_order_calendar_id(work_order)
        shifted = []
        for milestone in self._load_milestones(work_order.get('id')):
            if str(milestone.get('state')) != MILESTONE_PAUSED:
                continue
            total = int(milestone.get('paused_total_minutes') or 0) + paused_minutes
            due_at = milestone.get('due_at')
            warn_at = milestone.get('warn_at')
            if paused_minutes > 0 and not _blank(due_at):
                due_at = self.compute_due_at(due_at, paused_minutes, calendar_id)
            if paused_minutes > 0 and not _blank(warn_at):
                warn_at = self.compute_due_at(warn_at, paused_minutes, calendar_id)
            self.ds.execute(
                'UPDATE %s SET state = ?, paused_total_minutes = ?, due_at = ?, '
                'warn_at = ?, updated_at = ? WHERE id = ?' % MILESTONE_TABLE,
                [MILESTONE_RUNNING, total, due_at, warn_at, occurred,
                 milestone.get('id')])
            shifted.append({'id': milestone.get('id'),
                            'milestone_type': milestone.get('milestone_type'),
                            'due_at': due_at, 'warn_at': warn_at,
                            'paused_total_minutes': total})

        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?' % WORK_ORDER_TABLE,
            [STATUS_IN_PROGRESS, occurred, work_order.get('id')])
        self._append_event(work_order.get('id'), 'resume', occurred, actor,
                           {'note': note, 'paused_minutes': paused_minutes})
        self._append_change_event(work_order.get('id'), 'state_change',
                                  {'status': (STATUS_WAITING, STATUS_IN_PROGRESS)})
        return {'id': work_order.get('id'), 'status': STATUS_IN_PROGRESS,
                'paused_minutes': paused_minutes, 'milestones': shifted}

    # -------------------------------------------------------------- 结算

    def resolve_event(self, work_order_id: Any, occurred_at: Any = None,
                      actor: Any = None, payload: Any = None,
                      note: Any = None) -> Dict[str, Any]:
        """R-ST-6 / R-ST-7：resolve 事件结算 SLA 并回写计划行，**不写 fulfillment_status**。"""
        occurred = occurred_at or _now()
        work_order = self._require_work_order(work_order_id)
        status = str(work_order.get('status'))

        if status in STATUS_SETTLED:
            return {'id': work_order.get('id'), 'status': status,
                    'resolved_at': work_order.get('resolved_at'),
                    'schedule_id': work_order.get('schedule_id'),
                    'schedule_status': 'completed',
                    'milestone_state': None,
                    'already_resolved': True}
        if status == STATUS_CANCELLED:
            raise WorkOrderError('已取消的工单不能解决',
                                 field_name='status', rule='ST_STATE_INVALID')

        self._append_event(work_order.get('id'), 'resolve', occurred, actor,
                           payload, note)
        self.ds.execute(
            'UPDATE %s SET status = ?, resolved_at = ?, updated_at = ? WHERE id = ?'
            % WORK_ORDER_TABLE, [STATUS_RESOLVED, occurred, occurred,
                                 work_order.get('id')])

        milestone_state = None
        for milestone in self._load_milestones(work_order.get('id')):
            if str(milestone.get('milestone_type')) != MILESTONE_RESOLUTION:
                continue
            milestone_state = self._settle_milestone(milestone, occurred)

        schedule_id = work_order.get('schedule_id')
        schedule_status = None
        if not _blank(schedule_id):
            self.ds.execute(
                "UPDATE %s SET status = 'completed', updated_at = ? WHERE id = ?"
                % SCHEDULE_TABLE, [occurred, schedule_id])
            schedule_status = 'completed'

        self._append_change_event(work_order.get('id'), 'state_change',
                                  {'status': (status, STATUS_RESOLVED)})
        return {'id': work_order.get('id'), 'status': STATUS_RESOLVED,
                'resolved_at': occurred, 'schedule_id': schedule_id,
                'schedule_status': schedule_status,
                'milestone_state': milestone_state,
                'already_resolved': False}

    def recompute_milestones(self, work_order_id: Any,
                             now: Any = None) -> List[Dict[str, Any]]:
        """R-ST-6：按当前时间推进未结里程碑 → Warned / Breached（巡检任务入口）。"""
        now_dt = _parse_dt(now or _now())
        changed: List[Dict[str, Any]] = []
        for milestone in self._load_milestones(work_order_id):
            if str(milestone.get('state')) not in MILESTONE_OPEN:
                continue
            due_at = milestone.get('due_at')
            warn_at = milestone.get('warn_at')
            if not _blank(due_at) and now_dt >= _parse_dt(due_at):
                self.ds.execute(
                    'UPDATE %s SET state = ?, breached_at = ?, completed_at = ?, '
                    'updated_at = ? WHERE id = ?' % MILESTONE_TABLE,
                    [MILESTONE_BREACHED, _fmt(now_dt), _fmt(now_dt),
                     _fmt(now_dt), milestone.get('id')])
                changed.append({'id': milestone.get('id'),
                                'milestone_type': milestone.get('milestone_type'),
                                'state': MILESTONE_BREACHED, 'at': _fmt(now_dt)})
            elif not _blank(warn_at) and now_dt >= _parse_dt(warn_at) \
                    and str(milestone.get('state')) != MILESTONE_WARNED:
                self.ds.execute(
                    'UPDATE %s SET state = ?, warned_at = ?, updated_at = ? WHERE id = ?'
                    % MILESTONE_TABLE,
                    [MILESTONE_WARNED, _fmt(now_dt), _fmt(now_dt),
                     milestone.get('id')])
                changed.append({'id': milestone.get('id'),
                                'milestone_type': milestone.get('milestone_type'),
                                'state': MILESTONE_WARNED, 'at': _fmt(now_dt)})
        return changed

    def derive_service_status(self, order_id: Any) -> str:
        """§10.7：订单行级 service_status 派生（与 fulfillment_status 完全正交）。"""
        if _blank(order_id):
            return SERVICE_STATUS_NONE
        try:
            rows = self.ds.query(
                "SELECT status FROM %s WHERE order_id = ? AND schedule_kind = 'service'"
                % SCHEDULE_TABLE, [order_id])
        except Exception as e:
            logger.warning('[work_order] 派生 service_status 失败: %s', e)
            return SERVICE_STATUS_NONE
        statuses = [str(row.get('status')) for row in rows]
        if not statuses:
            return SERVICE_STATUS_NONE
        if all(s == 'cancelled' for s in statuses):
            return SERVICE_STATUS_CANCELLED
        if all(s == 'completed' for s in statuses):
            return SERVICE_STATUS_COMPLETED
        if any(s == 'completed' for s in statuses):
            return SERVICE_STATUS_PARTIAL
        return SERVICE_STATUS_PLANNED

    # -------------------------------------------------------------- 内部

    def _create_milestones(self, work_order_id: int, rule: Dict[str, Any],
                           calendar_id: Any,
                           started_at: Any) -> List[Dict[str, Any]]:
        now = _now()
        pairs = (
            (MILESTONE_FIRST_RESPONSE,
             rule.get('first_response_minutes'),
             rule.get('first_response_warn_minutes')),
            (MILESTONE_RESOLUTION,
             rule.get('resolution_minutes'),
             rule.get('resolution_warn_minutes')),
        )
        created = []
        for milestone_type, minutes, warn_minutes in pairs:
            total = _int_minutes(minutes)
            due_at = self.compute_due_at(started_at, total, calendar_id)
            warn_at = None
            if not _blank(warn_minutes):
                warn_at = self.compute_due_at(
                    started_at, max(0, total - _int_minutes(warn_minutes)),
                    calendar_id)
            self._insert(MILESTONE_TABLE, {
                'work_order_id': work_order_id,
                'milestone_type': milestone_type,
                'state': MILESTONE_RUNNING,
                'due_at': due_at,
                'warn_at': warn_at,
                'started_at': _fmt(_parse_dt(started_at)),
                'paused_total_minutes': 0,
                'completed_at': None,
                'warned_at': None,
                'breached_at': None,
                'created_at': now,
                'updated_at': now,
            })
            created.append({'milestone_type': milestone_type,
                            'state': MILESTONE_RUNNING,
                            'due_at': due_at, 'warn_at': warn_at})
        return created

    def _settle_milestone(self, milestone: Dict[str, Any],
                          occurred: Any) -> str:
        """R-ST-6：到期前解决 → Met；超过 due_at → Breached。"""
        occurred_at = _fmt(_parse_dt(occurred))
        due_at = milestone.get('due_at')
        if _blank(due_at) or _parse_dt(occurred) <= _parse_dt(due_at):
            self.ds.execute(
                'UPDATE %s SET state = ?, completed_at = ?, updated_at = ? WHERE id = ?'
                % MILESTONE_TABLE,
                [MILESTONE_MET, occurred_at, occurred_at, milestone.get('id')])
            return MILESTONE_MET
        self.ds.execute(
            'UPDATE %s SET state = ?, completed_at = ?, breached_at = ?, '
            'updated_at = ? WHERE id = ?' % MILESTONE_TABLE,
            [MILESTONE_BREACHED, occurred_at, occurred_at, occurred_at,
             milestone.get('id')])
        return MILESTONE_BREACHED

    def _hold_elapsed_minutes(self, work_order_id: Any, now: Any) -> int:
        try:
            rows = self.ds.query(
                "SELECT occurred_at FROM %s WHERE work_order_id = ? "
                "AND event_type = 'hold' ORDER BY occurred_at DESC, id DESC LIMIT 1"
                % EVENT_TABLE, [work_order_id])
        except Exception:  # 表未就绪 → 不计暂停时长
            rows = []
        if not rows:
            return 0
        delta = (_parse_dt(now) - _parse_dt(rows[0].get('occurred_at')))
        return max(0, int(delta.total_seconds() // 60))

    def _calendar_mask(self, calendar_id: Any) -> tuple:
        if _blank(calendar_id):
            return DEFAULT_DAY_MASK
        try:
            rows = self.ds.query(
                'SELECT day_mask_mon, day_mask_tue, day_mask_wed, '
                'day_mask_thu, day_mask_fri, day_mask_sat, day_mask_sun '
                'FROM %s WHERE id = ?' % CALENDAR_TABLE, [calendar_id])
        except Exception as e:
            logger.warning('[work_order] 读取日历 %s 失败: %s', calendar_id, e)
            return DEFAULT_DAY_MASK
        if not rows:
            return DEFAULT_DAY_MASK
        row = rows[0]
        return tuple(bool(row.get(key)) for key in (
            'day_mask_mon', 'day_mask_tue', 'day_mask_wed', 'day_mask_thu',
            'day_mask_fri', 'day_mask_sat', 'day_mask_sun'))

    def _is_workday(self, day, calendar_id: Any, mask: tuple) -> bool:
        if not _blank(calendar_id):
            try:
                rows = self.ds.query(
                    "SELECT day_type FROM %s WHERE calendar_id = ? "
                    "AND substr(date, 1, 10) = ?" % CALENDAR_DAY_TABLE,
                    [calendar_id, day.strftime('%Y-%m-%d')])
            except Exception:  # 例外日表未就绪 → 回落标准周
                rows = []
            if rows:
                day_type = str(rows[0].get('day_type'))
                if day_type == 'holiday':
                    return False
                if day_type == 'workday':
                    return True
        return bool(mask[day.weekday()])

    def _coverage_applies(self, coverage: Dict[str, Any], org_id: Any,
                          day: str) -> bool:
        active = coverage.get('active')
        if active in (0, '0', False, 'false', 'False'):
            return False
        start = coverage.get('start_date')
        if not _blank(start) and day < str(start)[:10]:
            return False
        end = coverage.get('end_date')
        if not _blank(end) and day > str(end)[:10]:
            return False
        cov_org = coverage.get('org_id')
        if not _blank(cov_org):
            if _blank(org_id) or str(cov_org) != str(org_id):
                return False
        return True

    def _load_rules(self, coverage_id: Any) -> List[Dict[str, Any]]:
        try:
            return self.ds.query(
                'SELECT id, coverage_id, severity, channel, '
                'first_response_minutes, first_response_warn_minutes, '
                'resolution_minutes, resolution_warn_minutes, seq '
                'FROM %s WHERE coverage_id = ? ORDER BY seq, id'
                % COVERAGE_RULE_TABLE, [coverage_id])
        except Exception as e:
            logger.warning('[work_order] 读取覆盖 %s 的规则失败: %s', coverage_id, e)
            return []

    @staticmethod
    def _rule_matches(rule: Dict[str, Any], severity: Any, channel: Any) -> bool:
        if str(rule.get('severity')) != str(severity):
            return False
        rule_channel = rule.get('channel')
        if _blank(rule_channel):
            return True
        if _blank(channel):
            return False
        return str(rule_channel) == str(channel)

    def _work_order_calendar_id(self, work_order: Dict[str, Any]) -> Any:
        coverage_id = work_order.get('coverage_id')
        if _blank(coverage_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT calendar_id FROM %s WHERE id = ?' % COVERAGE_TABLE,
                [coverage_id])
        except Exception:
            return None
        return rows[0].get('calendar_id') if rows else None

    def _require_work_order(self, work_order_id: Any) -> Dict[str, Any]:
        if _blank(work_order_id):
            raise WorkOrderError('工单 ID 不能为空', field_name='id',
                                 rule='ST_NOT_FOUND')
        rows = self.ds.query(
            'SELECT id, work_order_no, status, schedule_id, coverage_id, '
            'resolved_at FROM %s WHERE id = ?' % WORK_ORDER_TABLE,
            [work_order_id])
        if not rows:
            raise WorkOrderError('工单不存在', field_name='id',
                                 rule='ST_NOT_FOUND')
        return rows[0]

    def _require_service_schedule(self, schedule_id: Any) -> Dict[str, Any]:
        if _blank(schedule_id):
            raise WorkOrderError('工单必须挂载服务计划行（R-ST-0）',
                                 field_name='schedule_id',
                                 rule='ST_SCHEDULE_INVALID')
        rows = self.ds.query(
            'SELECT id, order_id, line_id, schedule_kind, promised_date, status '
            'FROM %s WHERE id = ?' % SCHEDULE_TABLE, [schedule_id])
        if not rows:
            raise WorkOrderError('服务计划行不存在', field_name='schedule_id',
                                 rule='ST_SCHEDULE_INVALID')
        schedule = rows[0]
        if str(schedule.get('schedule_kind')) != SCHEDULE_KIND_SERVICE:
            raise WorkOrderError(
                '工单只能挂载 schedule_kind=service 的计划行（R-ST-0）',
                field_name='schedule_id', rule='ST_SCHEDULE_INVALID')
        return schedule

    def _load_milestones(self, work_order_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT id, work_order_id, milestone_type, state, due_at, warn_at, '
            'started_at, paused_total_minutes, completed_at, warned_at, '
            'breached_at FROM %s WHERE work_order_id = ? ORDER BY id'
            % MILESTONE_TABLE, [work_order_id])

    def _next_work_order_no(self) -> str:
        prefix = 'WO-%s-' % datetime.now().strftime('%Y%m')
        rows = self.ds.query(
            'SELECT work_order_no FROM %s WHERE work_order_no LIKE ? '
            'ORDER BY id DESC LIMIT 1' % WORK_ORDER_TABLE, [prefix + '%'])
        seq = 1
        if rows:
            tail = str(rows[0].get('work_order_no')).rsplit('-', 1)[-1]
            try:
                seq = int(tail) + 1
            except ValueError:
                seq = 1
        return '%s%04d' % (prefix, seq)

    def _insert(self, table: str, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            table, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [row[c] for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _append_event(self, work_order_id: Any, event_type: str,
                      occurred_at: Any, actor: Any = None,
                      payload: Any = None, note: Any = None) -> int:
        stored = payload
        if isinstance(payload, (dict, list)):
            stored = json.dumps(payload, ensure_ascii=False)
        return self._insert(EVENT_TABLE, {
            'work_order_id': work_order_id,
            'event_type': event_type,
            'occurred_at': _fmt(_parse_dt(occurred_at)),
            'actor': actor,
            'payload': stored,
            'note': note,
            'created_at': _now(),
        })

    def _append_change_event(self, work_order_id: Any, event_type: str,
                             changes: Dict[str, Any]) -> None:
        """§10.7：复用 change_events（object_type='work_order'），失败 fail-open。"""
        try:
            changed_fields = list(changes.keys())
            old_values = {k: v[0] for k, v in changes.items()}
            new_values = {k: v[1] for k, v in changes.items()}
            self._insert(CHANGE_EVENT_TABLE, {
                'object_type': 'work_order',
                'object_id': int(work_order_id),
                'event_type': event_type,
                'changed_fields': json.dumps(changed_fields, ensure_ascii=False),
                'old_values': json.dumps(old_values, ensure_ascii=False),
                'new_values': json.dumps(new_values, ensure_ascii=False),
                'payload': None,
                'status': 'pending',
                'created_at': _now(),
            })
        except Exception as e:  # 事件底座不可用时不阻断业务写入
            logger.warning('[work_order] 写入 change_event 失败: %s', e)
