# -*- coding: utf-8 -*-
"""付款条件到期日推算 —— 头 + 分期行 → 分期计划（单一真源）。

依据: meta/schemas/payment_term_line.yaml 头注释「到期日计算口径」

口径（与 YAML 头注释逐条对应，改动必须两处同步）:
  1. 基准日 = 头的 basis_date_rule 指向的日期
     - invoice_date / delivery_date / order_date：由调用方传入对应单据日期（trigger_date）
     - month_end：取 trigger_date 所在月的最后一天
     若头的 cutoff_day 非空且 trigger_date 的日 > cutoff_day ⇒ 基准日顺延一个月（按月末夹取）
  2. 到期日 = add_months(基准日, offset_months)
     若 fixed_day_of_month 非空 ⇒ 落到该月第 N 天，超过当月天数取月末
  3. 到期日再加 offset_days
  4. 折扣到期日 = 基准日 + discount_days（**不经过** 第 2、3 步）

边界:
  - 本服务只做日期推算，不涉及金额、汇率、催收、会计凭证；
  - 分期占比合计必须为 100（G1 完整性），不足或超额直接拒绝，避免「半套账期」被下游误用。
"""

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from meta.services.payment_term_guard_service import PaymentTermGuardError

_HUNDRED = Decimal('100')
_PCT_TOLERANCE = Decimal('0.0001')

BASIS_RULES = ('invoice_date', 'delivery_date', 'order_date', 'month_end')


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise PaymentTermGuardError('缺少基准日期，无法推算到期日',
                                    field_name='basis_date_rule', rule='basis_date_missing')
    return datetime.strptime(text[:10], '%Y-%m-%d').date()


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_end(value: date) -> date:
    return value.replace(day=_last_day(value.year, value.month))


def add_months(value: date, months: int) -> date:
    """加月并夹取到月末（1/31 + 1 月 = 2/28 或 2/29）。"""
    if not months:
        return value
    index = value.year * 12 + (value.month - 1) + int(months)
    year, month = divmod(index, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, _last_day(year, month)))


def resolve_base_date(term: Dict[str, Any], trigger_date: Any) -> date:
    """按头口径把单据日期换算成账期基准日。"""
    rule = str(term.get('basis_date_rule') or 'invoice_date').strip()
    if rule not in BASIS_RULES:
        raise PaymentTermGuardError(
            f'未知的基准日口径 {rule}', field_name='basis_date_rule', rule='basis_rule_unknown')

    trigger = _as_date(trigger_date)
    base = _month_end(trigger) if rule == 'month_end' else trigger

    cutoff_day = term.get('cutoff_day')
    if not _is_blank(cutoff_day) and trigger.day > int(cutoff_day):
        base = add_months(base, 1)
    return base


def compute_due_date(base_date: date, line: Dict[str, Any]) -> date:
    """单行到期日：月偏移 → 固定日 → 天偏移。"""
    due = add_months(base_date, int(line.get('offset_months') or 0))
    fixed_day = line.get('fixed_day_of_month')
    if not _is_blank(fixed_day):
        day = int(fixed_day)
        due = due.replace(day=min(day, _last_day(due.year, due.month)))
    return due + timedelta(days=int(line.get('offset_days') or 0))


def compute_discount_date(base_date: date, line: Dict[str, Any]) -> Optional[date]:
    """折扣到期日 = 基准日 + 折扣天数（不经过月偏移与固定日）。"""
    days = line.get('discount_days')
    if _is_blank(days):
        return None
    return base_date + timedelta(days=int(days))


def _percentage_total(lines: Iterable[Dict[str, Any]]) -> Decimal:
    total = Decimal('0')
    for line in lines:
        value = line.get('percentage')
        if _is_blank(value):
            continue
        total += Decimal(str(value))
    return total


def compute_schedule(term: Dict[str, Any], lines: List[Dict[str, Any]],
                     trigger_date: Any) -> List[Dict[str, Any]]:
    """返回按 seq 升序的分期计划。

    每项: {seq, percentage, due_date, discount_percent, discount_due_date}
    分期占比合计不为 100 时抛 `PaymentTermGuardError(rule='percentage_not_100')`。
    """
    if not lines:
        raise PaymentTermGuardError('付款条件没有分期行，无法推算到期日',
                                    field_name='percentage', rule='no_lines')

    total = _percentage_total(lines)
    if abs(total - _HUNDRED) > _PCT_TOLERANCE:
        raise PaymentTermGuardError(
            f'付款条件分期占比合计为 {total}，应等于 100',
            field_name='percentage', rule='percentage_not_100')

    base = resolve_base_date(term, trigger_date)

    schedule: List[Dict[str, Any]] = []
    for line in sorted(lines, key=lambda r: int(r.get('seq') or 0)):
        schedule.append({
            'seq': int(line.get('seq') or 0),
            'percentage': float(line.get('percentage')),
            'due_date': compute_due_date(base, line),
            'discount_percent': line.get('discount_percent'),
            'discount_due_date': compute_discount_date(base, line),
        })
    return schedule


#: 供调用方按头的口径挑选单据日期
BASE_DATE_FIELD = {
    'invoice_date': 'invoice_date',
    'delivery_date': 'delivery_date',
    'order_date': 'order_date',
    'month_end': 'invoice_date',  # 月末口径以触发日期所在月为准，字段取触发日
}
