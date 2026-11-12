# -*- coding: utf-8 -*-
"""开票计划期次生成 —— S8 Wave C。

依据:
  docs/specs/s8-customer-invoice-wave-c/spec.md §6.2
  docs/specs/s8-customer-invoice-wave-c/tasks.md T37

口径（spec §6.2 / tasks.md T37）:
  · 只处理 `billing_relevance = 'plan'` 的订单行；其余行直接跳过。
  · 口径决定期次数：
      fixed_price          → 1 期，100%
      time_and_material    → N = billing_period_count（为空按 1），
                             前 N-1 期 = ROUND(100/N, 4)，末期吸尾差
      milestone            → 不自动生成（里程碑需人工维护）
      其他未知取值           → ORDER_BILLING_PLAN_INVALID（fail-closed）
  · 开票日 = 锚点 + (i-1) × billing_interval_months，再 + billing_lead_days。
    锚点取值优先级：billing_anchor_date > 订单 confirmed_date > 今天。
  · billing_proration = 'daily' 且服务起止日均存在时，按「期次窗口 ∩ 服务期」
    的天数占比分摊；零交集拒绝；任一端缺失退化为均分。
  · 幂等：该行已有非取消的 billing 期次或任一期次 billed_amount > 0 →
    不重算、不新增，返回既有期次（created=False）。
  · 每行写入前过 SalesOrderGuardService.validate_schedule_write，
    system_generated=True 以放行 R-SCH-5（订单确认后自动生成）。
  · 事务边界：本服务自带 _atomic 包裹；调用方事务内嵌套时透传。
"""

import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from meta.services.payment_term_schedule_service import add_months
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)

logger = logging.getLogger(__name__)

ORDER_TABLE = 'sales_orders'
LINE_TABLE = 'sales_order_lines'
SCHEDULE_TABLE = 'sales_order_schedules'

RELEVANCE_PLAN = 'plan'
METHOD_FIXED_PRICE = 'fixed_price'
METHOD_TM = 'time_and_material'
METHOD_MILESTONE = 'milestone'
KNOWN_METHODS = (METHOD_FIXED_PRICE, METHOD_TM, METHOD_MILESTONE)

KIND_BILLING = 'billing'
STATUS_PLANNED = 'planned'
BILLING_STATUS_NONE = 'none'

#: 订单允许生成计划的状态（确认触发 / 手工补跑）
GENERATABLE_ORDER_STATUSES = ('confirmed', 'closed')

#: 期数上限（与 v242 verify 的 1..60 对齐）
MAX_PERIODS = 60
MAX_INTERVAL_MONTHS = 12

#: 比例精度 / 金额容差
PERCENT_PLACES = 4
HUNDRED = Decimal('100')
EPSILON = Decimal('0.0001')

#: 计划行读取字段
LINE_FIELDS = (
    'id', 'order_id', 'line_no', 'qty', 'net_amount', 'billed_amount',
    'project_id', 'plant_location_id',
    'billing_relevance', 'billing_method',
    'service_start_date', 'service_end_date',
    'billing_period_count', 'billing_interval_months',
    'billing_anchor_date', 'billing_lead_days', 'billing_proration',
)

SCHEDULE_FIELDS = (
    'id', 'line_id', 'schedule_no', 'promised_date', 'promised_qty',
    'billing_percent', 'billed_amount', 'billing_status', 'status',
)


class BillingPlanError(ValueError):
    """开票计划生成失败。`field_name` / `rule` 供动作层映射错误码。"""

    def __init__(self, message: str, field_name: str = '',
                 rule: str = 'ORDER_BILLING_PLAN_INVALID'):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_decimal(value: Any) -> Optional[Decimal]:
    if _blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _round(value: Decimal, places: int = PERCENT_PLACES) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _to_int(value: Any) -> Optional[int]:
    if _blank(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any, field_name: str) -> Optional[date]:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        raise BillingPlanError('日期格式必须为 YYYY-MM-DD',
                               field_name=field_name)


def _today() -> date:
    return date.today()


@contextmanager
def _atomic(ds):
    txn = getattr(ds, 'transaction', None)
    if txn is None:
        yield
        return
    with txn():
        yield


def _split_equally(count: int) -> List[Decimal]:
    """均分 100，前 count-1 期四舍五入，末期吸尾差。"""
    if count == 1:
        return [HUNDRED]
    part = _round(HUNDRED / Decimal(count))
    parts = [part] * (count - 1)
    parts.append(_round(HUNDRED - sum(parts)))
    return parts


def _intersection_days(start: date, end: date,
                       range_start: date, range_end: date) -> int:
    """[start, end) 与 [range_start, range_end] 的交集天数（end 含当天）。"""
    left = max(start, range_start)
    right = min(end, range_end + timedelta(days=1))
    if right <= left:
        return 0
    return (right - left).days


class BillingPlanService:
    """按订单行口径生成 billing 期次。"""

    def __init__(self, data_source):
        self.ds = data_source
        self.guard = SalesOrderGuardService(data_source)

    # ------------------------------------------------------------ 对外入口

    def generate_for_order(self, order_id: Any,
                           *, triggered_by: str = 'confirm') -> List[int]:
        """为订单所有 plan 行生成期次，返回**新增**期次 id 列表。

        已是 confirmed / closed 且已有期次时幂等返回空列表。
        任一行失败 → 整单回滚（_atomic）并抛 `ORDER_BILLING_PLAN_INVALID`。
        """
        order = self._require_order(order_id)
        status = str(order.get('status') or '')
        if status not in GENERATABLE_ORDER_STATUSES:
            raise BillingPlanError(
                f'订单处于 {status or "未知"} 状态，仅已确认 / 已关闭订单可生成开票计划',
                field_name='status')

        lines = self._load_plan_lines(order['id'])
        created: List[int] = []
        with _atomic(self.ds):
            for line in lines:
                try:
                    rows = self.generate_for_line(order, line)
                except SalesOrderGuardError as exc:
                    raise BillingPlanError(
                        f'订单行 {line.get("line_no")} 开票计划生成被拒绝：{exc}',
                        field_name=exc.field_name) from exc
                created.extend(int(row['id']) for row in rows
                               if row.get('created'))
        logger.info('[billing_plan] order=%s triggered_by=%s lines=%s created=%s',
                    order['id'], triggered_by, len(lines), len(created))
        return created

    def generate_for_line(self, order: Dict[str, Any],
                          line: Dict[str, Any]) -> List[Dict[str, Any]]:
        """为单行生成期次。

        返回该行的 billing 期次列表（含既有行，带 created 标记）；
        不适用（非 plan 行 / 里程碑 / 已开票）时返回既有行或空列表。
        """
        if str(line.get('billing_relevance') or '') != RELEVANCE_PLAN:
            return []

        existing = self._load_billing_schedules(line.get('id'))
        if self._should_skip(line, existing):
            return [self._row_dict(row, created=False) for row in existing]

        method = str(line.get('billing_method') or METHOD_FIXED_PRICE).strip()
        if method == METHOD_MILESTONE:
            return []
        if method not in KNOWN_METHODS:
            raise BillingPlanError(
                f'未知的开票口径 {method}，无法生成计划',
                field_name='billing_method')

        count = self._period_count(line, method)
        interval = self._interval(line)
        lead_days = _to_int(line.get('billing_lead_days')) or 0
        anchor = self._anchor(order, line)

        percentages = self._percentages(line, anchor, count, interval)
        first_no = self._next_schedule_no(existing)

        rows: List[Dict[str, Any]] = []
        for index, percent in enumerate(percentages):
            row = self._build_row(order, line, first_no + index, index,
                                  anchor, interval, lead_days, percent)
            self.guard.validate_schedule_write(row, None, True,
                                               system_generated=True)
            row['id'] = self._insert(row)
            row['created'] = True
            rows.append(row)
        return rows

    # ------------------------------------------------------------ 读取

    def _require_order(self, order_id: Any) -> Dict[str, Any]:
        if _blank(order_id):
            raise BillingPlanError('缺少订单 id', field_name='order_id')
        rows = self.ds.query(
            f'SELECT id, order_no, status, confirmed_date, project_id '
            f'FROM {ORDER_TABLE} WHERE id = ?', [order_id])
        if not rows:
            raise BillingPlanError(f'订单 {order_id} 不存在',
                                   field_name='order_id')
        return rows[0]

    def _load_plan_lines(self, order_id: Any) -> List[Dict[str, Any]]:
        columns = ', '.join(LINE_FIELDS)
        rows = self.ds.query(
            f'SELECT {columns} FROM {LINE_TABLE} '
            f'WHERE order_id = ? AND billing_relevance = ? '
            f'ORDER BY COALESCE(line_no, 0), id',
            [order_id, RELEVANCE_PLAN])
        return rows

    def _load_billing_schedules(self, line_id: Any) -> List[Dict[str, Any]]:
        columns = ', '.join(SCHEDULE_FIELDS)
        return self.ds.query(
            f'SELECT {columns} FROM {SCHEDULE_TABLE} '
            f'WHERE line_id = ? AND schedule_kind = ? '
            f'ORDER BY schedule_no, id', [line_id, KIND_BILLING])

    # ------------------------------------------------------------ 判定

    @staticmethod
    def _should_skip(line: Dict[str, Any],
                     existing: List[Dict[str, Any]]) -> bool:
        if not existing:
            return (_to_decimal(line.get('billed_amount')) or Decimal('0')) \
                > EPSILON
        if (_to_decimal(line.get('billed_amount')) or Decimal('0')) > EPSILON:
            return True
        for row in existing:
            if (_to_decimal(row.get('billed_amount')) or Decimal('0')) \
                    > EPSILON:
                return True
            if str(row.get('status') or '') != 'cancelled':
                return True
        return False

    @staticmethod
    def _period_count(line: Dict[str, Any], method: str) -> int:
        if method == METHOD_FIXED_PRICE:
            return 1
        count = _to_int(line.get('billing_period_count')) or 1
        if count < 1 or count > MAX_PERIODS:
            raise BillingPlanError(
                f'开票期数必须在 1..{MAX_PERIODS} 之间（当前 {count}）',
                field_name='billing_period_count')
        return count

    @staticmethod
    def _interval(line: Dict[str, Any]) -> int:
        interval = _to_int(line.get('billing_interval_months')) or 1
        if interval < 1 or interval > MAX_INTERVAL_MONTHS:
            raise BillingPlanError(
                f'开票间隔月数必须在 1..{MAX_INTERVAL_MONTHS} 之间（当前 {interval}）',
                field_name='billing_interval_months')
        return interval

    @staticmethod
    def _anchor(order: Dict[str, Any], line: Dict[str, Any]) -> date:
        anchor = _as_date(line.get('billing_anchor_date'),
                          'billing_anchor_date')
        if anchor:
            return anchor
        confirmed = _as_date(order.get('confirmed_date'), 'confirmed_date')
        return confirmed or _today()

    @staticmethod
    def _next_schedule_no(existing: List[Dict[str, Any]]) -> int:
        numbers = [_to_int(row.get('schedule_no')) or 0 for row in existing]
        return max(numbers, default=0) + 1

    # ------------------------------------------------------------ 比例 / 日期

    def _percentages(self, line: Dict[str, Any], anchor: date,
                     count: int, interval: int) -> List[Decimal]:
        proration = str(line.get('billing_proration') or 'none').strip()
        if proration != 'daily':
            return _split_equally(count)

        start = _as_date(line.get('service_start_date'), 'service_start_date')
        end = _as_date(line.get('service_end_date'), 'service_end_date')
        if not start or not end:
            # 任一端缺失 → 退化为均分（spec §6.2）
            return _split_equally(count)

        windows = []
        for index in range(count):
            window_start = add_months(anchor, index * interval)
            window_end = add_months(anchor, (index + 1) * interval)
            windows.append((window_start, window_end))

        days = [_intersection_days(window_start, window_end, start, end)
                for window_start, window_end in windows]
        total = sum(days)
        if total <= 0:
            raise BillingPlanError(
                '服务期与开票期次窗口没有交集，无法按日分摊',
                field_name='service_start_date')

        parts = [_round(Decimal(value) / Decimal(total) * HUNDRED)
                 for value in days[:-1]]
        parts.append(_round(HUNDRED - sum(parts)))
        return parts

    def _build_row(self, order: Dict[str, Any], line: Dict[str, Any],
                   schedule_no: int, index: int, anchor: date, interval: int,
                   lead_days: int, percent: Decimal) -> Dict[str, Any]:
        promised = add_months(anchor, index * interval) \
            + timedelta(days=lead_days)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return {
            'order_id': order['id'],
            'line_id': line['id'],
            'project_id': line.get('project_id') or order.get('project_id'),
            # billing 期次不得挂发货点（守卫 R-SCH-12）
            'plant_location_id': None,
            'schedule_no': schedule_no,
            'schedule_kind': KIND_BILLING,
            'promised_date': promised.strftime('%Y-%m-%d'),
            'promised_qty': None,
            'billing_percent': float(percent),
            'billed_amount': 0,
            'billing_status': BILLING_STATUS_NONE,
            'milestone_code': None,
            'service_visit_no': None,
            'status': STATUS_PLANNED,
            'created_at': now,
            'updated_at': now,
        }

    def _insert(self, row: Dict[str, Any]) -> int:
        columns = ', '.join(row)
        placeholders = ', '.join(['?'] * len(row))
        cur = self.ds.execute(
            f'INSERT INTO {SCHEDULE_TABLE} ({columns}) '
            f'VALUES ({placeholders})', list(row.values()))
        return int(cur.lastrowid)

    @staticmethod
    def _row_dict(row: Dict[str, Any], *, created: bool) -> Dict[str, Any]:
        item = dict(row)
        item['created'] = created
        return item